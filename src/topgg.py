from aiohttp import web
import discord
import sqlite3
import asyncio
import os
from datetime import datetime, timedelta, timezone
import json
import traceback as tb
import aiohttp  # For contact form email sending
import re       # For contact form email validation

DB_FILE = "bot_data.db"
TOPGG_WEBHOOK_SECRET = os.getenv('TOPGG_WEBHOOK_SECRET')
VOTE_LOG_CHANNEL_ID = 1466059183052034193
VOTER_ROLE_ID = 1466059698666213427
SUPPORT_SERVER_ID = int(os.getenv('SUPPORT_SERVER_ID')) if os.getenv('SUPPORT_SERVER_ID') else None

# ---------------------------------------------------------------------------
# Reminder-timing constants
# ---------------------------------------------------------------------------
BASE_REMINDER_HOURS = 12          # default cycle length
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
# DB - VOTE SYSTEM
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
            preferred_reminder_hour REAL DEFAULT NULL
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
                             ("preferred_reminder_hour","REAL DEFAULT NULL")]:
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

# ---------------------------------------------------------------------------
# DB - CONTACT FORM SYSTEM
# ---------------------------------------------------------------------------
def init_contact_db():
    """Initialize contact form database"""
    try:
        debug_log("Initializing contact form database...", "INFO")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS contact_handlers (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            added_at TEXT
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS contact_config (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        
        conn.commit()
        conn.close()
        debug_log("Contact form database ready", "SUCCESS")
    except Exception as e:
        debug_log(f"Contact DB init error: {e}", "ERROR")
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
# CONTACT FORM - Helper Functions
# ---------------------------------------------------------------------------
def add_contact_handler(user_id, username):
    """Add a user as contact form handler"""
    db_query(
        "INSERT OR REPLACE INTO contact_handlers VALUES (?, ?, ?)",
        (user_id, username, datetime.now(timezone.utc).isoformat())
    )

def remove_contact_handler(user_id):
    """Remove a contact form handler"""
    db_query("DELETE FROM contact_handlers WHERE user_id = ?", (user_id,))

def is_contact_handler(user_id):
    """Check if user is a contact form handler"""
    result = db_query("SELECT * FROM contact_handlers WHERE user_id = ?", (user_id,), fetch=True)
    return result is not None and len(result) > 0

def get_all_contact_handlers():
    """Get all contact form handlers"""
    result = db_query("SELECT * FROM contact_handlers", fetch=True)
    return result if result else []

def set_contact_channel(channel_id):
    """Store the contact form channel ID"""
    db_query("INSERT OR REPLACE INTO contact_config VALUES ('contact_channel_id', ?)", (str(channel_id),))

def get_contact_channel():
    """Get the contact form channel ID"""
    result = db_query("SELECT value FROM contact_config WHERE key = 'contact_channel_id'", fetch=True)
    if result and len(result) > 0:
        return int(result[0][0])
    return None

def is_valid_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# ---------------------------------------------------------------------------
# CONTACT FORM - Discord UI Components (HANDLERS ONLY)
# ---------------------------------------------------------------------------
class ReplyModal(discord.ui.Modal, title="Reply to Contact Form"):
    reply_text = discord.ui.TextInput(
        label="Your Reply",
        style=discord.TextStyle.paragraph,
        placeholder="Type your reply here (max 4000 characters)...",
        required=True,
        max_length=4000
    )

    def __init__(self, bot, user_email, message_id, channel_id):
        super().__init__()
        self.bot = bot
        self.user_email = user_email
        self.message_id = message_id
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if not is_valid_email(self.user_email):
            await interaction.followup.send("❌ Email is invalid. Failed to send reply.", ephemeral=True)
            return

        success = await self.send_reply_email(self.user_email, self.reply_text.value)

        if success:
            await interaction.followup.send(f"✅ Reply sent successfully to {self.user_email}", ephemeral=True)
            await self.update_embed_replied(interaction)
        else:
            await interaction.followup.send("❌ Failed to send reply. Please check logs.", ephemeral=True)

    async def send_reply_email(self, to_email, reply_message):
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://flexedai.netlify.app/.netlify/functions/send-reply"
                data = {"to": to_email, "message": reply_message}
                async with session.post(url, json=data, timeout=30) as resp:
                    if resp.status == 200:
                        debug_log(f"Reply email sent to {to_email}", "SUCCESS")
                        return True
                    else:
                        error_text = await resp.text()
                        debug_log(f"Reply email failed: {resp.status} - {error_text}", "ERROR")
                        return False
        except Exception as e:
            debug_log(f"Error sending reply email: {e}", "ERROR")
            return False

    async def update_embed_replied(self, interaction):
        try:
            channel = self.bot.get_channel(self.channel_id)
            message = await channel.fetch_message(self.message_id)
            embed = message.embeds[0]
            embed.color = discord.Color.green()
            embed.set_footer(text=f"✅ Replied by {interaction.user.name}")
            await message.edit(embed=embed, view=None)
        except Exception as e:
            debug_log(f"Error updating embed: {e}", "ERROR")


class IgnoreModal(discord.ui.Modal, title="Ignore Contact Form"):
    reason = discord.ui.TextInput(
        label="Reason for Ignoring",
        style=discord.TextStyle.paragraph,
        placeholder="Why are you ignoring this message?",
        required=True,
        max_length=500
    )

    def __init__(self, bot, user_email, message_id, channel_id):
        super().__init__()
        self.bot = bot
        self.user_email = user_email
        self.message_id = message_id
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        success = await self.send_ignore_notification(self.user_email, self.reason.value)
        
        if success:
            await interaction.followup.send(f"✅ Message ignored and notification sent to {self.user_email}", ephemeral=True)
            await self.update_embed_ignored(interaction)
        else:
            await interaction.followup.send("❌ Failed to send ignore notification.", ephemeral=True)

    async def send_ignore_notification(self, to_email, reason):
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://flexedai.netlify.app/.netlify/functions/send-ignore"
                data = {"to": to_email, "reason": reason}
                async with session.post(url, json=data, timeout=30) as resp:
                    if resp.status == 200:
                        debug_log(f"Ignore notification sent to {to_email}", "SUCCESS")
                        return True
                    else:
                        error_text = await resp.text()
                        debug_log(f"Ignore notification failed: {resp.status} - {error_text}", "ERROR")
                        return False
        except Exception as e:
            debug_log(f"Error sending ignore notification: {e}", "ERROR")
            return False

    async def update_embed_ignored(self, interaction):
        try:
            channel = self.bot.get_channel(self.channel_id)
            message = await channel.fetch_message(self.message_id)
            embed = message.embeds[0]
            embed.color = discord.Color.orange()
            embed.set_footer(text=f"⚠️ Ignored by {interaction.user.name}")
            await message.edit(embed=embed, view=None)
        except Exception as e:
            debug_log(f"Error updating embed: {e}", "ERROR")


class MarkInvalidModal(discord.ui.Modal, title="Mark as Invalid"):
    reason = discord.ui.TextInput(
        label="Reason for Marking Invalid",
        style=discord.TextStyle.paragraph,
        placeholder="Why is this message invalid?",
        required=True,
        max_length=500
    )

    def __init__(self, bot, message_id, channel_id):
        super().__init__()
        self.bot = bot
        self.message_id = message_id
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.mark_as_invalid(interaction, self.reason.value)
        await interaction.followup.send("✅ Message marked as invalid", ephemeral=True)

    async def mark_as_invalid(self, interaction, reason):
        try:
            channel = self.bot.get_channel(self.channel_id)
            message = await channel.fetch_message(self.message_id)
            embed = message.embeds[0]
            embed.color = discord.Color.dark_gray()
            embed.set_footer(text=f"❌ Invalid: {reason} (by {interaction.user.name})")
            await message.edit(embed=embed, view=None)
        except Exception as e:
            debug_log(f"Error marking as invalid: {e}", "ERROR")


class ContactFormButtons(discord.ui.View):
    """Buttons for contact forms - ONLY handlers can click these"""
    def __init__(self, bot, user_email, message_id, channel_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_email = user_email
        self.message_id = message_id
        self.channel_id = channel_id

    @discord.ui.button(label="Reply", style=discord.ButtonStyle.green, emoji="✉️")
    async def reply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ONLY handlers can click
        if not is_contact_handler(interaction.user.id):
            await interaction.response.send_message(
                "❌ You don't have permission to handle contact forms. Ask the bot owner to add you with `/handler add`.",
                ephemeral=True
            )
            return
        modal = ReplyModal(self.bot, self.user_email, self.message_id, self.channel_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Ignore", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def ignore_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ONLY handlers can click
        if not is_contact_handler(interaction.user.id):
            await interaction.response.send_message(
                "❌ You don't have permission to handle contact forms. Ask the bot owner to add you with `/handler add`.",
                ephemeral=True
            )
            return
        modal = IgnoreModal(self.bot, self.user_email, self.message_id, self.channel_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Mark Invalid", style=discord.ButtonStyle.danger, emoji="❌")
    async def invalid_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ONLY handlers can click
        if not is_contact_handler(interaction.user.id):
            await interaction.response.send_message(
                "❌ You don't have permission to handle contact forms. Ask the bot owner to add you with `/handler add`.",
                ephemeral=True
            )
            return
        modal = MarkInvalidModal(self.bot, self.message_id, self.channel_id)
        await interaction.response.send_modal(modal)

# ---------------------------------------------------------------------------
# CONTACT FORM - Webhook Handler
# ---------------------------------------------------------------------------
async def handle_contact_form(request):
    """Handle incoming contact form submissions from Netlify"""
    try:
        bot = request.app.get('bot')
        if not bot:
            debug_log("Bot not available in contact handler", "ERROR")
            return web.json_response({'error': 'Bot not initialized'}, status=500)

        data = await request.json()
        
        email = data.get('email')
        subject = data.get('subject')
        message = data.get('message')
        
        if not email or not subject or not message:
            debug_log("Missing required fields in contact form", "ERROR")
            return web.json_response({'error': 'Missing required fields'}, status=400)
        
        channel_id = get_contact_channel()
        if not channel_id:
            debug_log("No contact channel configured!", "ERROR")
            return web.json_response({'error': 'Bot not configured. Run /setup-contact first.'}, status=500)
        
        channel = bot.get_channel(channel_id)
        if not channel:
            debug_log(f"Channel {channel_id} not found!", "ERROR")
            return web.json_response({'error': 'Channel not found'}, status=500)
        
        # Create embed
        embed = discord.Embed(
            title="📧 New Contact Form Submission",
            color=0x667eea,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="📨 From", value=email, inline=False)
        embed.add_field(name="📋 Subject", value=subject, inline=False)
        embed.add_field(
            name="💬 Message",
            value=message[:1024] if len(message) > 1024 else message,
            inline=False
        )
        embed.set_footer(text="Contact Form • flexedAI")
        
        # Send message with buttons
        view = ContactFormButtons(bot, email, 0, channel.id)
        sent_message = await channel.send(embed=embed, view=view)
        
        # Update view with correct message ID
        view.message_id = sent_message.id
        await sent_message.edit(view=view)
        
        debug_log(f"Contact form sent with buttons for {email}", "SUCCESS")
        
        return web.json_response({
            'success': True,
            'message': 'Contact form submitted to Discord'
        })
        
    except Exception as e:
        debug_log(f"Error handling contact form: {e}", "ERROR")
        tb.print_exc()
        return web.json_response({'error': str(e)}, status=500)

# ---------------------------------------------------------------------------
# Reminder-interval helper  ── adaptive logic based on user behavior
# ---------------------------------------------------------------------------
def compute_next_reminder(current_vote_time, last_vote_time, scheduled_reminder_time, preferred_hour):
    """
    Adaptive reminder scheduling based on actual user voting behavior.
    
    Args:
        current_vote_time: When the user just voted (datetime, UTC)
        last_vote_time: When they voted previously (datetime, UTC, can be None)
        scheduled_reminder_time: When the reminder was scheduled to fire (datetime, UTC, can be None)
        preferred_hour: The user's learned preferred voting hour (float, 0-24, can be None)
    
    Returns:
        (next_reminder_datetime, new_preferred_hour)
    
    Logic:
    1. If this is first vote or no reminder was scheduled: use base 12 hours
    2. If user voted BEFORE the scheduled reminder (early):
       - Learn their preferred timing
       - Schedule next reminder to match their natural cadence
    3. If user voted AFTER the scheduled reminder (late):
       - Still give them a full 12 hours from when they actually voted
       - Don't punish them with a shorter window
    """
    
    now = current_vote_time
    
    # Case 1: First vote or no previous data
    if not last_vote_time or not scheduled_reminder_time:
        debug_log("First vote or no history – using base 12h interval", "DEBUG")
        return now + timedelta(hours=BASE_REMINDER_HOURS), None
    
    # Calculate actual voting interval (how long since their last vote)
    actual_interval_hours = (now - last_vote_time).total_seconds() / 3600
    
    # Calculate how early/late they were relative to the scheduled reminder
    delta_vs_reminder = (now - scheduled_reminder_time).total_seconds() / 3600
    
    debug_log(f"Vote analysis: actual_interval={actual_interval_hours:.2f}h, "
              f"delta_vs_reminder={delta_vs_reminder:.2f}h", "DEBUG")
    
    # Case 2: User voted EARLY (before the reminder)
    if delta_vs_reminder < -0.5:  # More than 30min early
        hours_early = -delta_vs_reminder
        debug_log(f"User voted {hours_early:.2f}h EARLY", "INFO")
        
        # Learn their preferred hour of day
        vote_hour = now.hour + (now.minute / 60.0)
        
        # If they consistently vote early, adjust to their natural schedule
        # Use their actual voting interval as the new cadence
        if actual_interval_hours >= 10 and actual_interval_hours <= 14:
            # They're voting roughly every 12 hours but earlier than reminder
            # Schedule next reminder to match their actual pattern
            next_reminder = now + timedelta(hours=actual_interval_hours)
            debug_log(f"Adapting to user's natural {actual_interval_hours:.2f}h cadence", "INFO")
            return next_reminder, vote_hour
        else:
            # Unusual interval, just use standard 12h from now
            return now + timedelta(hours=BASE_REMINDER_HOURS), vote_hour
    
    # Case 3: User voted LATE (after the reminder)
    elif delta_vs_reminder > 0.5:  # More than 30min late
        hours_late = delta_vs_reminder
        debug_log(f"User voted {hours_late:.2f}h LATE", "INFO")
        
        # Always give them a full 12 hours from when they actually voted
        # Don't punish them with a shorter interval
        next_reminder = now + timedelta(hours=BASE_REMINDER_HOURS)
        vote_hour = now.hour + (now.minute / 60.0)
        
        debug_log(f"Giving full 12h from actual vote time", "INFO")
        return next_reminder, vote_hour
    
    # Case 4: User voted ON TIME (within 30min of reminder)
    else:
        debug_log(f"User voted ON TIME (within 30min of reminder)", "INFO")
        
        # Keep the established pattern
        next_reminder = now + timedelta(hours=BASE_REMINDER_HOURS)
        vote_hour = now.hour + (now.minute / 60.0)
        
        return next_reminder, vote_hour

# ---------------------------------------------------------------------------
# Role helpers  (unchanged logic)
# ---------------------------------------------------------------------------
async def assign_voter_role(bot, user_id, hours=12):
    debug_log(f"Attempting to assign voter role to {user_id} for {hours}h", "INFO")
    
    if not SUPPORT_SERVER_ID:
        debug_log("SUPPORT_SERVER_ID not configured", "WARNING")
        return

    try:
        guild = bot.get_guild(SUPPORT_SERVER_ID)
        if not guild:
            try:
                guild = await bot.fetch_guild(SUPPORT_SERVER_ID)
            except Exception as e:
                debug_log(f"Could not fetch guild {SUPPORT_SERVER_ID}: {e}", "ERROR")
                return

        member = guild.get_member(int(user_id))
        if not member:
            try:
                member = await guild.fetch_member(int(user_id))
            except discord.NotFound:
                debug_log(f"Member {user_id} not in support server", "WARNING")
                return
            except Exception as e:
                debug_log(f"Could not fetch member {user_id}: {e}", "ERROR")
                return

        role = guild.get_role(VOTER_ROLE_ID)
        if not role:
            debug_log(f"Role {VOTER_ROLE_ID} not found", "ERROR")
            return

        if role not in member.roles:
            await member.add_roles(role, reason=f"Voted for the bot ({hours}h temporary)")
            debug_log(f"Assigned voter role to {member.name}", "SUCCESS")
        else:
            debug_log(f"{member.name} already has voter role", "INFO")

        # schedule role removal
        expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
        db_query("UPDATE vote_reminders SET role_expires_at = ? WHERE user_id = ?",
                 (expires_at.isoformat(), str(user_id)))
        debug_log(f"Voter role expires at {get_discord_timestamp(expires_at)}", "INFO")

    except Exception as e:
        debug_log(f"Error assigning voter role: {e}", "ERROR")
        tb.print_exc()

# ---------------------------------------------------------------------------
# Process vote  (unchanged)
# ---------------------------------------------------------------------------
async def process_vote(bot, user_id, is_weekend, vote_type):
    debug_log(f"Processing vote: user={user_id}, weekend={is_weekend}, type={vote_type}", "INFO")
    try:
        now = datetime.now(timezone.utc)

        # Log vote
        db_query("INSERT INTO vote_logs (user_id, voted_at, is_weekend, vote_type) VALUES (?, ?, ?, ?)",
                 (str(user_id), now.isoformat(), int(is_weekend), vote_type))
        debug_log(f"Vote logged for {user_id}", "SUCCESS")

        # Get reminder row
        row = db_query(
            "SELECT enabled, total_votes, last_vote, next_reminder, preferred_reminder_hour "
            "FROM vote_reminders WHERE user_id = ?",
            (str(user_id),), fetch=True)

        # Parse existing data
        enabled, total, last_vote_str, next_reminder_str, preferred_hour = \
            row[0] if row else (0, 0, None, None, None)

        last_vote = datetime.fromisoformat(last_vote_str) if last_vote_str else None
        next_reminder = datetime.fromisoformat(next_reminder_str) if next_reminder_str else None

        # Compute next reminder adaptively
        next_reminder_new, preferred_hour_new = compute_next_reminder(
            current_vote_time=now,
            last_vote_time=last_vote,
            scheduled_reminder_time=next_reminder,
            preferred_hour=preferred_hour
        )

        # Update DB
        db_query(
            "INSERT OR REPLACE INTO vote_reminders "
            "(user_id, enabled, last_vote, next_reminder, total_votes, preferred_reminder_hour) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(user_id), enabled, now.isoformat(), next_reminder_new.isoformat(),
             total + 1, preferred_hour_new)
        )
        debug_log(f"Updated vote record for {user_id} | next reminder: {get_discord_timestamp(next_reminder_new)}", "SUCCESS")

        # Assign role
        await assign_voter_role(bot, user_id, hours=12)

        # If reminders are on, send confirmation
        if enabled:
            try:
                user = await bot.fetch_user(int(user_id))
                embed = discord.Embed(
                    title="Thanks for voting!",
                    description=f"Your vote's been counted. You can vote again in 12 hours.",
                    color=discord.Color.green(), timestamp=now)

                embed.add_field(
                    name="Your total votes",
                    value=f"**{total + 1}** – you're awesome!",
                    inline=False)

                embed.add_field(
                    name="When can I vote next?",
                    value=f"{get_discord_timestamp(next_reminder_new, 'R')} "
                          f"(that's {get_discord_timestamp(next_reminder_new, 'f')})",
                    inline=False)

                embed.set_footer(text="I'll remind you when it's time • /votereminder to turn off")

                view = discord.ui.View(timeout=None)
                view.add_item(discord.ui.Button(
                    label="Vote again later",
                    url=f"https://top.gg/bot/{bot.user.id}/vote",
                    style=discord.ButtonStyle.link, emoji="🗳️"))

                await user.send(embed=embed, view=view)
                debug_log(f"Vote confirmation sent to {user_id}", "SUCCESS")

            except discord.Forbidden:
                debug_log(f"Can't DM {user_id}, skipping confirmation", "WARNING")
            except Exception as e:
                debug_log(f"Vote DM error for {user_id}: {e}", "ERROR")

        # Log in vote-log channel
        try:
            channel = bot.get_channel(VOTE_LOG_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="New Vote Received",
                    color=discord.Color.blue(), timestamp=now)
                embed.add_field(name="User", value=f"<@{user_id}>", inline=False)
                embed.add_field(name="Total Votes", value=str(total + 1), inline=True)
                embed.add_field(name="Next Vote", value=get_discord_timestamp(next_reminder_new, 'R'), inline=True)
                await channel.send(embed=embed)
                debug_log(f"Vote logged in channel {VOTE_LOG_CHANNEL_ID}", "SUCCESS")
        except Exception as e:
            debug_log(f"Vote log channel error: {e}", "ERROR")

    except Exception as e:
        debug_log(f"Process vote error: {e}", "ERROR")
        tb.print_exc()

# ---------------------------------------------------------------------------
# Webhook handler  (unchanged)
# ---------------------------------------------------------------------------
async def handle_vote(request):
    debug_log("Received vote webhook", "INFO")
    try:
        # auth header check
        auth = request.headers.get('Authorization', '')
        if TOPGG_WEBHOOK_SECRET and auth != TOPGG_WEBHOOK_SECRET:
            debug_log(f"Unauthorized vote attempt | auth={auth}", "WARNING")
            return web.Response(status=401)

        data = await request.json()
        debug_log(f"Vote data: {data}", "DEBUG")

        user_id = data.get('user')
        vote_type = data.get('type', 'upvote')
        is_weekend = data.get('isWeekend', False)

        if not user_id:
            debug_log("Vote missing user_id", "ERROR")
            return web.json_response({'error': 'Missing user_id'}, status=400)

        bot = request.app.get('bot')
        if not bot:
            debug_log("Bot not available", "ERROR")
            return web.json_response({'error': 'Bot not ready'}, status=503)

        await process_vote(bot, user_id, is_weekend, vote_type)

        return web.json_response({'success': True})

    except Exception as e:
        debug_log(f"Vote webhook error: {e}", "ERROR")
        tb.print_exc()
        return web.json_response({'error': str(e)}, status=500)

# ---------------------------------------------------------------------------
# Vote reminders UI  (unchanged)
# ---------------------------------------------------------------------------
class VoteReminderEnableView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Turn on vote reminders", style=discord.ButtonStyle.green, emoji="🔔")
    async def enable_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != str(self.user_id):
            await interaction.response.send_message("This isn't for you.", ephemeral=True)
            return

        # check total votes first
        row = db_query("SELECT total_votes FROM vote_reminders WHERE user_id = ?",
                       (str(self.user_id),), fetch=True)

        if not row or row[0][0] == 0:
            await interaction.response.send_message(
                "You need to vote at least once before turning on reminders.\n"
                f"Vote here: https://top.gg/bot/{interaction.client.user.id}/vote",
                ephemeral=True)
            return

        db_query("UPDATE vote_reminders SET enabled = 1 WHERE user_id = ?", (str(self.user_id),))
        debug_log(f"Enabled reminders for {self.user_id}", "SUCCESS")

        await interaction.response.send_message(
            "✅ Reminders are now **on**. I'll DM you when your cooldown's up.",
            ephemeral=True)


class VoteReminderDisableView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Turn off reminders", style=discord.ButtonStyle.red, emoji="🔕")
    async def disable_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != str(self.user_id):
            await interaction.response.send_message("This isn't for you.", ephemeral=True)
            return

        db_query("UPDATE vote_reminders SET enabled = 0 WHERE user_id = ?", (str(self.user_id),))
        debug_log(f"Disabled reminders for {self.user_id}", "SUCCESS")

        await interaction.response.send_message(
            "🔕 Reminders turned off. You can turn them back on any time with `/votereminder`.",
            ephemeral=True)

# ---------------------------------------------------------------------------
# Reminder-sending loop  (unchanged)
# ---------------------------------------------------------------------------
async def reminder_loop(bot):
    await bot.wait_until_ready()
    debug_log("Reminder loop started", "SUCCESS")

    while not bot.is_closed():
        try:
            now = datetime.now(timezone.utc)

            reminders = db_query(
                "SELECT user_id, total_votes, next_reminder FROM vote_reminders "
                "WHERE enabled = 1 AND next_reminder IS NOT NULL AND next_reminder <= ?",
                (now.isoformat(),), fetch=True)

            if reminders:
                debug_log(f"{len(reminders)} reminder(s) to send", "INFO")

            for user_id, total_votes, next_reminder_str in reminders:
                try:
                    user = await bot.fetch_user(int(user_id))

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

                    # ── The next reminder will be set when they actually vote ──
                    # We don't pre-calculate it here because we want to adapt to
                    # their actual voting behavior
                    debug_log(f"Reminder sent to {user_id}, next will be set on vote", "SUCCESS")

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
# Webhook server  (with /contact route added)
# ---------------------------------------------------------------------------
async def start_webhook_server(bot, port=8080):
    debug_log("Initializing webhook server", "INFO")
    try:
        app = web.Application()
        app['bot'] = bot

        # Top.gg vote routes (existing)
        app.router.add_post('/topgg/webhook', handle_vote)
        app.router.add_post('/webhook',       handle_vote)
        app.router.add_post('/topgg',         handle_vote)
        app.router.add_post('/',              handle_vote)
        
        # Contact form route (NEW)
        app.router.add_post('/contact',       handle_contact_form)

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
        debug_log(f"Available routes: /topgg, /webhook, /contact", "INFO")

    except Exception as e:
        debug_log(f"Failed to start webhook server: {e}", "ERROR"); tb.print_exc(); raise
