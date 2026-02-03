from aiohttp import web
import discord
import sqlite3
import asyncio
import os
from datetime import datetime, timedelta, timezone
import json
import traceback as tb

DB_FILE = "bot_data.db"
TOPGG_WEBHOOK_SECRET = os.getenv('TOPGG_WEBHOOK_SECRET')
VOTE_LOG_CHANNEL_ID = 1466059183052034193
VOTER_ROLE_ID = 1466059698666213427
SUPPORT_SERVER_ID = int(os.getenv('SUPPORT_SERVER_ID')) if os.getenv('SUPPORT_SERVER_ID') else None

# ---------------------------------------------------------------------------
# Reminder-timing constants
# ---------------------------------------------------------------------------
BASE_REMINDER_HOURS = 12          # default cycle length
SKIP_PENALTY_HOURS  = 12          # added once if the user missed a full cycle
# ---------------------------------------------------------------------------

def debug_log(message, level="INFO"):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    prefix = {"INFO":"ℹ️","SUCCESS":"✅","ERROR":"❌","WARNING":"⚠️","DEBUG":"🔍"}.get(level,"📝")
    print(f"[{timestamp}] {prefix} {message}", flush=True)

def get_discord_timestamp(dt, style='f'):
    if not dt:
        return "Unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return f"<t:{int(dt.timestamp())}:{style}>"

# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
def init_vote_db():
    try:
        debug_log("Initializing vote database...", "INFO")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS vote_reminders (
            user_id        TEXT PRIMARY KEY,
            enabled        INTEGER  DEFAULT 0,
            last_vote      DATETIME,
            next_reminder  DATETIME,
            total_votes    INTEGER  DEFAULT 0,
            role_expires_at DATETIME,
            reminder_interval_hours REAL DEFAULT 12.0
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS vote_logs (
            id          INTEGER  PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT,
            voted_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_weekend  INTEGER  DEFAULT 0,
            vote_type   TEXT     DEFAULT 'upvote'
        )''')

        # migrations – safe to run every time
        for col, default in [("role_expires_at","DATETIME"),
                             ("reminder_interval_hours","REAL DEFAULT 12.0")]:
            try:
                c.execute(f'ALTER TABLE vote_reminders ADD COLUMN {col} {default}')
                debug_log(f"Migrated: added {col}", "SUCCESS")
            except sqlite3.OperationalError:
                pass                          # column already exists

        conn.commit()
        conn.close()
        debug_log("Vote database ready", "SUCCESS")
    except Exception as e:
        debug_log(f"DB init error: {e}", "ERROR")
        tb.print_exc()


def db_query(query, params=(), fetch=False):
    try:
        debug_log(f"DB: {query} | {params}", "DEBUG")
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute(query, params)
            conn.commit()
            result = c.fetchall() if fetch else None
            debug_log(f"DB result: {result}", "DEBUG")
            return result
    except Exception as e:
        debug_log(f"DB error: {e} | query={query} | params={params}", "ERROR")
        tb.print_exc()
        return None

# ---------------------------------------------------------------------------
# Reminder-interval helper  ── the core of the new adaptive logic
# ---------------------------------------------------------------------------
def compute_new_reminder_interval(last_vote_dt, prev_reminder_dt, prev_interval_hours):
    """
    Rules (all times in UTC):

    1. Normal vote (user voted right around when the reminder fired or
       before it was due)  →  keep the current interval unchanged.

    2. User skipped one full cycle then voted EARLY the next day
       (i.e. they voted *before* the next reminder would have fired).
       Let x = how many hours early they voted compared to that reminder.
       OLD behaviour  → next reminder = vote_time + (x + 12)   ← drifts badly
       NEW behaviour  → we snap the interval down to
                        (time_since_last_vote)  so future reminders match
                        the user's *actual* cadence.

    3. User voted LATE after the reminder was already sent.
       Let y = hours after the reminder the user actually voted.
       OLD behaviour  → next reminder = vote_time + (12 - y)   ← can frustrate
       NEW behaviour  → next reminder = vote_time + 12          ← always a full
                        cycle from when they actually voted, so no short waits.

    We return (new_interval_hours, next_reminder_dt).
    """
    now = datetime.now(timezone.utc)

    # ── guard: if we have no previous reminder we just use the base interval
    if prev_reminder_dt is None:
        return BASE_REMINDER_HOURS, now + timedelta(hours=BASE_REMINDER_HOURS)

    hours_since_vote = (now - last_vote_dt).total_seconds() / 3600   # should be ~0

    # time between the PREVIOUS reminder and when the user actually voted
    vote_vs_reminder = (last_vote_dt - prev_reminder_dt).total_seconds() / 3600

    # ── Case 3: voted LATE (after reminder fired)  →  y = vote_vs_reminder
    if vote_vs_reminder > 0:
        # Always give a full base cycle from the actual vote moment.
        new_interval = BASE_REMINDER_HOURS
        next_rem     = last_vote_dt + timedelta(hours=new_interval)
        debug_log(f"Reminder: late vote detected (y={vote_vs_reminder:.2f}h). "
                  f"Next reminder in {new_interval}h from vote time.", "DEBUG")
        return new_interval, next_rem

    # ── Case 2: voted EARLY (before reminder fired)  →  x = -vote_vs_reminder
    if vote_vs_reminder < 0:
        x = -vote_vs_reminder                          # positive hours-early
        # Snap the interval to the gap the user *actually* used.
        # gap = time from their *previous* vote to this vote.
        # We approximate that with prev_interval + (vote_vs_reminder)
        #      = prev_interval - x
        actual_gap = prev_interval_hours - x
        # Floor it so we never set something absurdly short (min 6 h)
        new_interval = max(actual_gap, 6.0)
        next_rem     = last_vote_dt + timedelta(hours=new_interval)
        debug_log(f"Reminder: early vote detected (x={x:.2f}h). "
                  f"Interval adjusted to {new_interval:.2f}h.", "DEBUG")
        return new_interval, next_rem

    # ── Case 1: voted right on time  →  no change
    new_interval = prev_interval_hours
    next_rem     = last_vote_dt + timedelta(hours=new_interval)
    debug_log(f"Reminder: on-time vote. Keeping interval at {new_interval:.2f}h.", "DEBUG")
    return new_interval, next_rem

# ---------------------------------------------------------------------------
# Role helpers  (unchanged logic, untouched)
# ---------------------------------------------------------------------------
async def assign_voter_role(bot, user_id, hours=12):
    debug_log(f"Attempting to assign voter role to {user_id} for {hours}h", "INFO")

    if not SUPPORT_SERVER_ID:
        debug_log("SUPPORT_SERVER_ID not configured", "WARNING"); return False
    if not VOTER_ROLE_ID:
        debug_log("VOTER_ROLE_ID not configured", "WARNING"); return False

    try:
        if not bot.is_ready():
            await bot.wait_until_ready()

        guild = bot.get_guild(SUPPORT_SERVER_ID)
        if not guild:
            try:
                guild = await bot.fetch_guild(SUPPORT_SERVER_ID)
            except (discord.NotFound, discord.Forbidden, Exception) as e:
                debug_log(f"Failed to fetch guild: {e}", "ERROR"); return False

        if not guild:
            debug_log("Guild still not accessible", "ERROR"); return False

        member = guild.get_member(int(user_id))
        if not member:
            try:
                member = await guild.fetch_member(int(user_id))
            except discord.NotFound:
                debug_log(f"User {user_id} not in guild – role will be assigned on join", "WARNING")
                return False
            except Exception as e:
                debug_log(f"Fetch member error: {e}", "ERROR"); return False

        if not member:
            debug_log(f"Member {user_id} could not be retrieved", "ERROR"); return False

        role = guild.get_role(VOTER_ROLE_ID)
        if not role:
            debug_log("Voter role not found in guild", "ERROR"); return False

        if not guild.me.guild_permissions.manage_roles:
            debug_log("Bot lacks MANAGE_ROLES", "ERROR"); return False
        if role.position >= guild.me.top_role.position:
            debug_log("Voter role is above bot role in hierarchy", "ERROR"); return False

        expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)

        if role not in member.roles:
            await member.add_roles(role, reason=f"Voted on Top.gg – expires in {hours}h", atomic=True)
            debug_log(f"Voter role assigned to {member.name}", "SUCCESS")

        db_query("UPDATE vote_reminders SET role_expires_at = ? WHERE user_id = ?",
                 (expires_at.isoformat(), str(user_id)))
        return True

    except Exception as e:
        debug_log(f"assign_voter_role error: {e}", "ERROR"); tb.print_exc()
        return False


async def check_and_assign_voter_role_on_join(bot, member):
    debug_log(f"Checking recent vote for {member.name} ({member.id})", "INFO")
    try:
        vote_data = db_query(
            "SELECT last_vote, role_expires_at FROM vote_reminders WHERE user_id = ?",
            (str(member.id),), fetch=True)
        if not vote_data:
            return

        last_vote_str, _ = vote_data[0]
        if not last_vote_str:
            return

        last_vote = datetime.fromisoformat(last_vote_str)
        if last_vote.tzinfo is None:
            last_vote = last_vote.replace(tzinfo=timezone.utc)

        hours_since = (datetime.now(timezone.utc) - last_vote).total_seconds() / 3600
        if hours_since >= 12:
            return

        remaining = 12 - hours_since
        await asyncio.sleep(2)
        success = await assign_voter_role(bot, member.id, remaining)

        if success:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=remaining)
            try:
                embed = discord.Embed(
                    title="Hey, welcome back!",
                    description=(f"Noticed you voted for the bot recently, so I went "
                                 f"ahead and added the Voter role to your account. "
                                 f"Nice of you to stop by again!"),
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(
                    name="How long does it last?",
                    value=f"It'll stick around until {get_discord_timestamp(expires_at, 'R')} "
                          f"({get_discord_timestamp(expires_at, 'F')}). "
                          f"Just vote again before then if you want to keep it.",
                    inline=False
                )
                embed.set_footer(text="Thanks for supporting us!")

                view = discord.ui.View(timeout=None)
                view.add_item(discord.ui.Button(
                    label="Vote on Top.gg", url=f"https://top.gg/bot/{bot.user.id}/vote",
                    style=discord.ButtonStyle.link, emoji="🗳️"))

                await member.send(embed=embed, view=view)
            except (discord.Forbidden, Exception) as e:
                debug_log(f"DM error on join: {e}", "WARNING")

    except Exception as e:
        debug_log(f"check_and_assign_voter_role_on_join error: {e}", "ERROR"); tb.print_exc()

# ---------------------------------------------------------------------------
# Webhook handler  (unchanged logic, untouched)
# ---------------------------------------------------------------------------
async def handle_vote(request):
    debug_log("=" * 60, "INFO")
    debug_log("WEBHOOK REQUEST RECEIVED", "SUCCESS")
    debug_log(f"Path: {request.path} | Method: {request.method}", "INFO")

    try:
        raw_body = await request.text()
        debug_log(f"Raw body ({len(raw_body)} bytes): {raw_body}", "INFO")

        auth_header = request.headers.get('Authorization', '')
        if TOPGG_WEBHOOK_SECRET:
            if not auth_header:
                return web.Response(status=401, text="Missing Authorization header")
            if auth_header != TOPGG_WEBHOOK_SECRET:
                return web.Response(status=403, text="Invalid Authorization")

        if not raw_body:
            return web.Response(status=400, text="Empty request body")

        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as e:
            return web.Response(status=400, text=f"Invalid JSON: {e}")

        user_id   = str(data.get('user') or data.get('userId') or data.get('userid') or data.get('userID') or '')
        vote_type = data.get('type', 'upvote')
        is_weekend= data.get('isWeekend', False) or data.get('weekend', False)

        if not user_id:
            return web.Response(status=400, text="Missing user ID")

        bot = request.app.get('bot')
        if not bot:
            return web.Response(status=500, text="Bot not initialized")

        await process_vote(bot, user_id, is_weekend, vote_type)
        debug_log("WEBHOOK COMPLETED SUCCESSFULLY", "SUCCESS")
        return web.Response(status=200, text="OK")

    except Exception as e:
        debug_log(f"Webhook exception: {e}", "ERROR"); tb.print_exc()
        return web.Response(status=500, text=f"Internal error: {e}")

# ---------------------------------------------------------------------------
# process_vote  ── updated reminder-interval logic + human-style embeds
# ---------------------------------------------------------------------------
async def process_vote(bot, user_id, is_weekend=False, vote_type='upvote'):
    debug_log(f"process_vote called for {user_id}", "INFO")

    try:
        is_test = vote_type.lower() == 'test'
        now     = datetime.now(timezone.utc)

        db_query("INSERT INTO vote_logs (user_id, is_weekend, vote_type) VALUES (?, ?, ?)",
                 (str(user_id), 1 if is_weekend else 0, vote_type))

        # ── pull existing row ──────────────────────────────────────────────
        total_votes       = 0
        reminder_enabled  = False
        prev_reminder_dt  = None
        prev_interval     = BASE_REMINDER_HOURS

        existing = db_query(
            "SELECT total_votes, enabled, next_reminder, reminder_interval_hours "
            "FROM vote_reminders WHERE user_id = ?",
            (str(user_id),), fetch=True)

        if existing and len(existing) > 0:
            row = existing[0]
            total_votes      = (row[0] or 0) + 1
            reminder_enabled = bool(row[1]) if row[1] is not None else False

            if row[2]:                                  # next_reminder string
                prev_reminder_dt = datetime.fromisoformat(row[2])
                if prev_reminder_dt.tzinfo is None:
                    prev_reminder_dt = prev_reminder_dt.replace(tzinfo=timezone.utc)

            prev_interval = float(row[3]) if row[3] else BASE_REMINDER_HOURS
        # ── end existing-row pull ──────────────────────────────────────────

        expires_at = now + timedelta(hours=12)

        if not is_test:
            # ── adaptive reminder calculation ──────────────────────────────
            new_interval, next_rem = compute_new_reminder_interval(
                now,                  # last_vote_dt  (just happened)
                prev_reminder_dt,     # when the reminder was *scheduled*
                prev_interval         # previous interval
            )

            if existing and len(existing) > 0:
                db_query(
                    "UPDATE vote_reminders SET last_vote = ?, total_votes = ?, "
                    "role_expires_at = ?, next_reminder = ?, reminder_interval_hours = ? "
                    "WHERE user_id = ?",
                    (now.isoformat(), total_votes, expires_at.isoformat(),
                     next_rem.isoformat(), new_interval, str(user_id)))
            else:
                total_votes = 1
                db_query(
                    "INSERT INTO vote_reminders "
                    "(user_id, last_vote, total_votes, enabled, role_expires_at, "
                    " next_reminder, reminder_interval_hours) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(user_id), now.isoformat(), total_votes, 0,
                     expires_at.isoformat(),
                     (now + timedelta(hours=BASE_REMINDER_HOURS)).isoformat(),
                     BASE_REMINDER_HOURS))
                reminder_enabled = False

        # ── fetch user ─────────────────────────────────────────────────────
        user = None
        try:
            user = await bot.fetch_user(int(user_id))
        except Exception as e:
            debug_log(f"Fetch user failed: {e}", "ERROR")

        # ── log-channel embed ──────────────────────────────────────────────
        vote_channel = bot.get_channel(VOTE_LOG_CHANNEL_ID)
        if not vote_channel:
            try:
                vote_channel = await bot.fetch_channel(VOTE_LOG_CHANNEL_ID)
            except Exception as e:
                debug_log(f"Fetch channel failed: {e}", "ERROR")

        if vote_channel:
            if is_test:
                embed = discord.Embed(
                    title="Test vote came in",
                    description="This one doesn't count – just making sure the webhook is working.",
                    color=discord.Color.blue(), timestamp=now)
            else:
                embed = discord.Embed(
                    title="Someone just voted!",
                    description="Another vote landed – nice.",
                    color=discord.Color.gold(), timestamp=now)

            if user:
                embed.add_field(name="Who", value=f"{user.mention}  (`{user.name}` · `{user_id}`)", inline=True)
                embed.set_thumbnail(url=user.display_avatar.url)
            else:
                embed.add_field(name="Who", value=f"`{user_id}`", inline=True)

            embed.add_field(name="Total votes", value=str(total_votes), inline=True)
            embed.add_field(name="Weekend?",    value="Yep ✨" if is_weekend else "Nope", inline=True)

            if not is_test:
                embed.add_field(name="Role expires", value=get_discord_timestamp(expires_at, 'R'), inline=True)

            embed.set_footer(text="via Top.gg" if not is_test else "test webhook")

            try:
                await vote_channel.send(embed=embed)
            except Exception as e:
                debug_log(f"Channel send failed: {e}", "ERROR")

        # ── role assignment (retry x3) ─────────────────────────────────────
        role_assigned = False
        if not is_test:
            for attempt in range(3):
                if attempt > 0:
                    await asyncio.sleep(2 ** attempt)
                role_assigned = await assign_voter_role(bot, user_id, hours=12)
                if role_assigned:
                    break

        # ── DM to voter ────────────────────────────────────────────────────
        if user:
            try:
                if is_test:
                    dm_embed = discord.Embed(
                        title="Just a test!",
                        description="This was a test vote – nothing has changed on your account. "
                                    "Everything's working fine on our end though!",
                        color=discord.Color.blue(), timestamp=now)
                    dm_embed.set_footer(text="test vote")
                    await user.send(embed=dm_embed)

                else:
                    dm_embed = discord.Embed(
                        title="Thanks for voting!",
                        description="Seriously, it means a lot. Every vote helps the bot get seen "
                                    "by more people, so thank you.",
                        color=discord.Color.green(), timestamp=now)

                    # rewards block
                    if role_assigned:
                        reward_text = (
                            "• Voter role – active for the next 12 hours\n"
                            "• You're helping the bot grow, which is awesome"
                            + ("\n• Oh, and it's the weekend – double the impact! 🎊" if is_weekend else ""))
                    else:
                        reward_text = (
                            "• Voter role – it'll show up once you join the support server\n"
                            "• You're helping the bot grow, which is awesome"
                            + ("\n• Weekend bonus is active too! 🎊" if is_weekend else ""))

                    dm_embed.add_field(name="What you get", value=reward_text, inline=False)

                    # expiry
                    if role_assigned:
                        dm_embed.add_field(
                            name="Role duration",
                            value=f"It'll expire {get_discord_timestamp(expires_at, 'R')}. "
                                  f"Vote again before then to keep it going.",
                            inline=False)
                    else:
                        dm_embed.add_field(
                            name="Role duration",
                            value="Join the support server within 12 hours and the role will be waiting for you.",
                            inline=False)

                    # reminder prompt / status
                    view = None
                    if not reminder_enabled:
                        dm_embed.add_field(
                            name="Want a nudge next time?",
                            value="I can ping you when it's time to vote again – just hit the button below.",
                            inline=False)
                        view = VoteReminderView(user_id)
                    else:
                        dm_embed.add_field(
                            name="Reminders",
                            value="Already on – I'll let you know when the next one's due.",
                            inline=False)

                    dm_embed.set_footer(text="Vote every 12 hours to keep the role!")

                    if view:
                        await user.send(embed=dm_embed, view=view)
                    else:
                        await user.send(embed=dm_embed)

                debug_log("DM sent", "SUCCESS")
            except discord.Forbidden:
                debug_log(f"DM blocked by {user.name}", "WARNING")
            except Exception as e:
                debug_log(f"DM error: {e}", "WARNING")

        debug_log("process_vote done", "SUCCESS")

    except Exception as e:
        debug_log(f"process_vote error: {e}", "ERROR"); tb.print_exc(); raise

# ---------------------------------------------------------------------------
# Views  (button callbacks)
# ---------------------------------------------------------------------------
class VoteReminderView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Yeah, remind me", style=discord.ButtonStyle.primary,
                       emoji="🔔", custom_id="enable_vote_reminder")
    async def enable_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != str(self.user_id):
            await interaction.response.send_message("That button isn't for you, sorry!", ephemeral=True)
            return
        try:
            next_rem = datetime.now(timezone.utc) + timedelta(hours=BASE_REMINDER_HOURS)
            db_query("UPDATE vote_reminders SET enabled = 1, next_reminder = ?, "
                     "reminder_interval_hours = ? WHERE user_id = ?",
                     (next_rem.isoformat(), BASE_REMINDER_HOURS, str(self.user_id)))

            button.disabled = True
            button.label    = "Reminders on ✅"
            button.style    = discord.ButtonStyle.success

            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                "Done! I'll ping you when it's time to vote again.", ephemeral=True)
        except Exception as e:
            debug_log(f"Enable reminder error: {e}", "ERROR")
            await interaction.response.send_message("Something went wrong – try again in a sec.", ephemeral=True)


class VoteReminderDisableView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Turn off reminders", style=discord.ButtonStyle.danger,
                       emoji="🔕", custom_id="disable_vote_reminder")
    async def disable_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != str(self.user_id):
            await interaction.response.send_message("That button isn't for you, sorry!", ephemeral=True)
            return
        try:
            db_query("UPDATE vote_reminders SET enabled = 0, next_reminder = NULL WHERE user_id = ?",
                     (str(self.user_id),))

            button.disabled = True
            button.label    = "Reminders off"

            await interaction.response.edit_message(view=self)
            await interaction.followup.send("Turned off. You won't get any more vote pings.", ephemeral=True)
        except Exception as e:
            debug_log(f"Disable reminder error: {e}", "ERROR")
            await interaction.response.send_message("Something went wrong – try again in a sec.", ephemeral=True)

# ---------------------------------------------------------------------------
# Reminder loop  ── uses the stored interval; never drifts
# ---------------------------------------------------------------------------
async def vote_reminder_loop(bot):
    await bot.wait_until_ready()
    debug_log("Vote reminder loop started", "SUCCESS")

    while not bot.is_closed():
        try:
            now = datetime.now(timezone.utc)

            reminders = db_query(
                "SELECT user_id, total_votes FROM vote_reminders "
                "WHERE enabled = 1 AND next_reminder IS NOT NULL AND next_reminder <= ?",
                (now.isoformat(),), fetch=True)

            if reminders:
                debug_log(f"Sending {len(reminders)} reminder(s)", "INFO")

            for user_id, total_votes in reminders:
                try:
                    user = await bot.fetch_user(int(user_id))

                    # pull the current interval so we schedule the *next* one correctly
                    row = db_query(
                        "SELECT reminder_interval_hours FROM vote_reminders WHERE user_id = ?",
                        (str(user_id),), fetch=True)
                    current_interval = float(row[0][0]) if row and row[0][0] else BASE_REMINDER_HOURS

                    embed = discord.Embed(
                        title="Hey, time to vote again!",
                        description="Your cooldown's done – you can vote again now. "
                                    "Only takes a second!",
                        color=discord.Color.blue(), timestamp=now)

                    embed.add_field(
                        name="Your votes so far",
                        value=f"**{total_votes}** – keep it up!",
                        inline=False)

                    embed.set_footer(text="You can turn these off any time.")

                    # buttons: vote link + disable
                    view = discord.ui.View(timeout=None)
                    view.add_item(discord.ui.Button(
                        label="Vote now",
                        url=f"https://top.gg/bot/{bot.user.id}/vote",
                        style=discord.ButtonStyle.link, emoji="🗳️"))

                    disable_view = VoteReminderDisableView(user_id)
                    for item in disable_view.children:
                        view.add_item(item)

                    await user.send(embed=embed, view=view)

                    # ── schedule next reminder using the stored interval ────
                    next_reminder = now + timedelta(hours=current_interval)
                    db_query("UPDATE vote_reminders SET next_reminder = ? WHERE user_id = ?",
                             (next_reminder.isoformat(), str(user_id)))

                except discord.Forbidden:
                    db_query("UPDATE vote_reminders SET enabled = 0 WHERE user_id = ?", (str(user_id),))
                    debug_log(f"Can't DM {user_id}, reminders disabled", "WARNING")
                except Exception as e:
                    debug_log(f"Reminder error for {user_id}: {e}", "ERROR")

                await asyncio.sleep(1)

            await asyncio.sleep(300)   # poll every 5 min

        except Exception as e:
            debug_log(f"Reminder loop error: {e}", "ERROR"); tb.print_exc()
            await asyncio.sleep(300)

# ---------------------------------------------------------------------------
# Role-expiration loop  (logic unchanged, embed text humanised)
# ---------------------------------------------------------------------------
async def role_expiration_loop(bot):
    await bot.wait_until_ready()
    debug_log("Role expiration loop started", "SUCCESS")

    while not bot.is_closed():
        try:
            now = datetime.now(timezone.utc)

            expired = db_query(
                "SELECT user_id, role_expires_at FROM vote_reminders "
                "WHERE role_expires_at IS NOT NULL AND role_expires_at <= ?",
                (now.isoformat(),), fetch=True)

            if expired:
                debug_log(f"{len(expired)} expired role(s) found", "INFO")

            for user_id, _ in expired:
                try:
                    if not SUPPORT_SERVER_ID:
                        continue

                    guild = bot.get_guild(SUPPORT_SERVER_ID)
                    if not guild:
                        try:
                            guild = await bot.fetch_guild(SUPPORT_SERVER_ID)
                        except Exception as e:
                            debug_log(f"Fetch guild failed: {e}", "ERROR"); continue

                    member = guild.get_member(int(user_id))
                    if not member:
                        try:
                            member = await guild.fetch_member(int(user_id))
                        except discord.NotFound:
                            db_query("UPDATE vote_reminders SET role_expires_at = NULL WHERE user_id = ?",
                                     (str(user_id),))
                            continue
                        except Exception as e:
                            debug_log(f"Fetch member error: {e}", "ERROR"); continue

                    role = guild.get_role(VOTER_ROLE_ID)
                    if not role:
                        continue

                    if role in member.roles:
                        await member.remove_roles(role, reason="Voter role expired after 12 hours")
                        debug_log(f"Removed voter role from {member.name}", "SUCCESS")

                        db_query("UPDATE vote_reminders SET role_expires_at = NULL WHERE user_id = ?",
                                 (str(user_id),))

                        # DM notification
                        try:
                            user = await bot.fetch_user(int(user_id))
                            embed = discord.Embed(
                                title="Your Voter role just expired",
                                description="It's been 12 hours since your last vote, so the role has been removed. "
                                            "No worries though – you can get it right back.",
                                color=discord.Color.orange(), timestamp=now)
                            embed.add_field(
                                name="Want it back?",
                                value="Just vote again and it'll be re-added straight away.",
                                inline=False)
                            embed.set_footer(text="Thanks for supporting us!")

                            view = discord.ui.View(timeout=None)
                            view.add_item(discord.ui.Button(
                                label="Vote now",
                                url=f"https://top.gg/bot/{bot.user.id}/vote",
                                style=discord.ButtonStyle.link, emoji="🗳️"))

                            await user.send(embed=embed, view=view)
                        except (discord.Forbidden, Exception) as e:
                            debug_log(f"Expiration DM error: {e}", "WARNING")
                    else:
                        db_query("UPDATE vote_reminders SET role_expires_at = NULL WHERE user_id = ?",
                                 (str(user_id),))

                except Exception as e:
                    debug_log(f"Role expiration error for {user_id}: {e}", "ERROR"); tb.print_exc()

                await asyncio.sleep(0.5)

            await asyncio.sleep(60)

        except Exception as e:
            debug_log(f"Role expiration loop error: {e}", "ERROR"); tb.print_exc()
            await asyncio.sleep(60)

# ---------------------------------------------------------------------------
# Webhook server  (unchanged)
# ---------------------------------------------------------------------------
async def start_webhook_server(bot, port=8080):
    debug_log("Initializing webhook server", "INFO")
    try:
        app = web.Application()
        app['bot'] = bot

        app.router.add_post('/topgg/webhook', handle_vote)
        app.router.add_post('/webhook',       handle_vote)
        app.router.add_post('/topgg',         handle_vote)
        app.router.add_post('/',              handle_vote)

        async def health_check(request):
            status = "ready" if bot.is_ready() else "not ready"
            return web.Response(text=f"Webhook running! Bot: {status}", status=200)

        async def test_vote(request):
            b = request.app.get('bot')
            if b:
                try:
                    await process_vote(b, "1081876265683927080", False, "test")
                    return web.Response(text="Test vote processed!", status=200)
                except Exception as e:
                    return web.Response(text=f"Test failed: {e}", status=500)
            return web.Response(text="Bot not initialized", status=500)

        app.router.add_get('/health', health_check)
        app.router.add_get('/test',   test_vote)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()

        debug_log(f"Webhook server running on port {port}", "SUCCESS")

    except Exception as e:
        debug_log(f"Failed to start webhook server: {e}", "ERROR"); tb.print_exc(); raise
