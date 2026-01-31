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

def debug_log(message, level="INFO"):
    """Enhanced debug logging with timestamps"""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    prefix = {
        "INFO": "ℹ️",
        "SUCCESS": "✅",
        "ERROR": "❌",
        "WARNING": "⚠️",
        "DEBUG": "🔍"
    }.get(level, "📝")
    print(f"[{timestamp}] {prefix} {message}", flush=True)

def get_discord_timestamp(dt, style='f'):
    """Convert datetime to Discord timestamp format"""
    if not dt:
        return "Unknown"
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    timestamp = int(dt.timestamp())
    return f"<t:{timestamp}:{style}>"

def init_vote_db():
    """Initialize vote reminder database with migration support"""
    try:
        debug_log("Initializing vote database...", "INFO")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Create tables if they don't exist
        c.execute('''CREATE TABLE IF NOT EXISTS vote_reminders (
            user_id TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            last_vote DATETIME,
            next_reminder DATETIME,
            total_votes INTEGER DEFAULT 0,
            role_expires_at DATETIME
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS vote_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            voted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_weekend INTEGER DEFAULT 0,
            vote_type TEXT DEFAULT 'upvote'
        )''')
        
        # Migration: Add role_expires_at if missing
        try:
            c.execute('ALTER TABLE vote_reminders ADD COLUMN role_expires_at DATETIME')
            debug_log("Migrated database: added role_expires_at column", "SUCCESS")
        except sqlite3.OperationalError:
            debug_log("Column role_expires_at already exists, skipping migration", "DEBUG")
        
        conn.commit()
        conn.close()
        debug_log("Vote database initialized successfully", "SUCCESS")
    except Exception as e:
        debug_log(f"Database initialization error: {e}", "ERROR")
        tb.print_exc()


def db_query(query, params=(), fetch=False):
    """Execute database query with error handling"""
    try:
        debug_log(f"DB Query: {query} | Params: {params}", "DEBUG")
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute(query, params)
            conn.commit()
            result = c.fetchall() if fetch else None
            debug_log(f"DB Query result: {result}", "DEBUG")
            return result
    except Exception as e:
        debug_log(f"Database query error: {e}", "ERROR")
        debug_log(f"Query was: {query}", "ERROR")
        debug_log(f"Params were: {params}", "ERROR")
        tb.print_exc()
        return None

async def assign_voter_role(bot, user_id, hours=12):
    """Assign voter role to a user with expiration time"""
    debug_log(f"🎭 Attempting to assign voter role to {user_id} for {hours} hours...", "INFO")
    
    if not SUPPORT_SERVER_ID:
        debug_log("⚠️ SUPPORT_SERVER_ID not configured", "WARNING")
        return False
    
    if not VOTER_ROLE_ID:
        debug_log("⚠️ VOTER_ROLE_ID not configured", "WARNING")
        return False
    
    try:
        # Wait for bot to be ready
        if not bot.is_ready():
            debug_log("⏳ Waiting for bot to be ready...", "INFO")
            await bot.wait_until_ready()
        
        guild = bot.get_guild(SUPPORT_SERVER_ID)
        if not guild:
            try:
                debug_log(f"🔍 Attempting to fetch guild {SUPPORT_SERVER_ID}...", "INFO")
                guild = await bot.fetch_guild(SUPPORT_SERVER_ID)
            except discord.NotFound:
                debug_log(f"❌ Guild {SUPPORT_SERVER_ID} not found - bot not in server?", "ERROR")
                return False
            except discord.Forbidden:
                debug_log(f"❌ No permission to access guild {SUPPORT_SERVER_ID}", "ERROR")
                return False
            except Exception as e:
                debug_log(f"❌ Failed to fetch guild {SUPPORT_SERVER_ID}: {e}", "ERROR")
                tb.print_exc()
                return False
        
        if not guild:
            debug_log(f"❌ Guild {SUPPORT_SERVER_ID} still not accessible", "ERROR")
            return False
        
        debug_log(f"✅ Guild found: {guild.name} (ID: {guild.id})", "SUCCESS")
        debug_log(f"📊 Guild members: {guild.member_count}", "INFO")
        
        # Try to get member
        member = None
        try:
            member = guild.get_member(int(user_id))
            if member:
                debug_log(f"✅ Member found in cache: {member.name}", "SUCCESS")
        except Exception as e:
            debug_log(f"⚠️ Error getting member from cache: {e}", "WARNING")
        
        # If not in cache, fetch
        if not member:
            try:
                debug_log(f"🔍 Member not in cache, fetching {user_id}...", "INFO")
                member = await guild.fetch_member(int(user_id))
                debug_log(f"✅ Member fetched: {member.name}", "SUCCESS")
            except discord.NotFound:
                debug_log(f"⚠️ User {user_id} is not a member of {guild.name}", "WARNING")
                debug_log(f"💡 They will get the role when they join the server", "INFO")
                return False
            except discord.Forbidden:
                debug_log(f"❌ No permission to fetch member {user_id}", "ERROR")
                return False
            except discord.HTTPException as e:
                debug_log(f"❌ HTTP error fetching member: {e}", "ERROR")
                tb.print_exc()
                return False
            except Exception as e:
                debug_log(f"❌ Unexpected error fetching member: {e}", "ERROR")
                tb.print_exc()
                return False
        
        if not member:
            debug_log(f"❌ Member {user_id} could not be retrieved", "ERROR")
            return False
        
        debug_log(f"✅ Member confirmed: {member.name}#{member.discriminator} ({member.id})", "SUCCESS")
        
        # Get the role
        role = guild.get_role(VOTER_ROLE_ID)
        if not role:
            debug_log(f"❌ Voter role {VOTER_ROLE_ID} not found in guild", "ERROR")
            debug_log(f"📋 Available roles: {[f'{r.name} ({r.id})' for r in guild.roles]}", "DEBUG")
            return False
        
        debug_log(f"✅ Voter role found: {role.name} (ID: {role.id})", "SUCCESS")
        debug_log(f"🔐 Role position: {role.position}, Bot's top role position: {guild.me.top_role.position}", "INFO")
        
        # Check bot permissions
        if not guild.me.guild_permissions.manage_roles:
            debug_log(f"❌ Bot does not have MANAGE_ROLES permission!", "ERROR")
            return False
        
        debug_log(f"✅ Bot has MANAGE_ROLES permission", "SUCCESS")
        
        # Check role hierarchy
        if role.position >= guild.me.top_role.position:
            debug_log(f"❌ Role {role.name} (pos {role.position}) is higher than or equal to bot's top role (pos {guild.me.top_role.position})", "ERROR")
            debug_log(f"💡 Move the bot's role above the voter role in server settings", "INFO")
            return False
        
        # Calculate expiration time (UTC timezone-aware)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
        
        # Check if member already has role
        if role in member.roles:
            debug_log(f"ℹ️ Member {member.name} already has voter role, updating expiration to {expires_at.isoformat()}", "INFO")
        else:
            # Add role
            try:
                debug_log(f"🎭 Adding role {role.name} to {member.name}...", "INFO")
                await member.add_roles(role, reason=f"Voted on Top.gg - expires in {hours}h", atomic=True)
                debug_log(f"✅ Voter role assigned to {member.name} until {expires_at.isoformat()}", "SUCCESS")
            except discord.Forbidden:
                debug_log(f"❌ Missing permissions to assign role (Forbidden)", "ERROR")
                debug_log(f"💡 Check: 1) Bot has Manage Roles, 2) Bot's role is above voter role, 3) Role is not managed by integration", "INFO")
                return False
            except discord.HTTPException as e:
                debug_log(f"❌ HTTP error assigning role: {e}", "ERROR")
                tb.print_exc()
                return False
            except Exception as e:
                debug_log(f"❌ Unexpected error assigning role: {e}", "ERROR")
                tb.print_exc()
                return False
        
        # Update expiration in database
        try:
            db_query(
                "UPDATE vote_reminders SET role_expires_at = ? WHERE user_id = ?",
                (expires_at.isoformat(), str(user_id))
            )
            debug_log(f"✅ Database updated with expiration time", "SUCCESS")
        except Exception as e:
            debug_log(f"⚠️ Failed to update database with expiration: {e}", "WARNING")
        
        return True
        
    except Exception as e:
        debug_log(f"❌ Critical error in assign_voter_role: {e}", "ERROR")
        tb.print_exc()
        return False

async def check_and_assign_voter_role_on_join(bot, member):
    """Check if user voted recently and assign role with remaining time"""
    debug_log(f"🔍 Checking recent vote for {member.name} ({member.id})", "INFO")
    
    try:
        # Get user's last vote
        vote_data = db_query(
            "SELECT last_vote, role_expires_at FROM vote_reminders WHERE user_id = ?",
            (str(member.id),),
            fetch=True
        )
        
        if not vote_data:
            debug_log(f"ℹ️ {member.name} has never voted", "INFO")
            return
        
        last_vote_str, expires_at_str = vote_data[0]
        
        if not last_vote_str:
            debug_log(f"ℹ️ {member.name} has no recent vote", "INFO")
            return
        
        # Parse timestamps (ensure UTC)
        last_vote = datetime.fromisoformat(last_vote_str)
        if last_vote.tzinfo is None:
            last_vote = last_vote.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        
        # Calculate time since vote
        time_since_vote = now - last_vote
        hours_since_vote = time_since_vote.total_seconds() / 3600
        
        debug_log(f"⏰ {member.name} voted {hours_since_vote:.2f} hours ago", "INFO")
        
        # If voted within last 12 hours, assign role with remaining time
        if hours_since_vote < 12:
            remaining_hours = 12 - hours_since_vote
            debug_log(f"✅ Vote is recent! Assigning role for remaining {remaining_hours:.2f} hours", "SUCCESS")
            
            # Small delay to ensure guild is fully loaded
            await asyncio.sleep(2)
            
            # Assign role with remaining time
            success = await assign_voter_role(bot, member.id, remaining_hours)
            
            if success:
                # Calculate new expiration
                new_expires_at = now + timedelta(hours=remaining_hours)
                
                # Send DM notification
                try:
                    embed = discord.Embed(
                        title="🎭 Voter Role Assigned!",
                        description=f"Welcome to **{member.guild.name}**!\n\nYou recently voted for the bot, so you've been granted the Voter role!",
                        color=discord.Color.green(),
                        timestamp=now
                    )
                    
                    embed.add_field(
                        name="⏰ Role Duration",
                        value=f"Your Voter role will expire {get_discord_timestamp(new_expires_at, 'R')}\n({get_discord_timestamp(new_expires_at, 'F')})",
                        inline=False
                    )
                    
                    embed.add_field(
                        name="🗳️ Vote Again",
                        value="Vote again after 12 hours to keep your Voter role!",
                        inline=False
                    )
                    
                    embed.set_footer(text="Thank you for supporting the bot!")
                    
                    view = discord.ui.View(timeout=None)
                    view.add_item(discord.ui.Button(
                        label="Vote on Top.gg",
                        url=f"https://top.gg/bot/{bot.user.id}/vote",
                        style=discord.ButtonStyle.link,
                        emoji="🗳️"
                    ))
                    
                    await member.send(embed=embed, view=view)
                    debug_log(f"✅ Sent role notification DM to {member.name}", "SUCCESS")
                    
                except discord.Forbidden:
                    debug_log(f"⚠️ Cannot DM {member.name}", "WARNING")
                except Exception as dm_error:
                    debug_log(f"❌ DM error: {dm_error}", "ERROR")
            else:
                debug_log(f"❌ Failed to assign role to {member.name}", "ERROR")
        else:
            debug_log(f"⏱️ Vote is too old ({hours_since_vote:.2f}h), not assigning role", "INFO")
            
    except Exception as e:
        debug_log(f"❌ Error checking voter role on join: {e}", "ERROR")
        tb.print_exc()

async def handle_vote(request):
    """Handle Top.gg vote webhook with extensive debugging"""
    debug_log("="*80, "INFO")
    debug_log("🚨🚨🚨 WEBHOOK REQUEST RECEIVED! 🚨🚨🚨", "SUCCESS")
    debug_log(f"Path: {request.path}", "INFO")
    debug_log(f"Method: {request.method}", "INFO")
    debug_log(f"Remote: {request.remote}", "INFO")
    debug_log(f"Host: {request.host}", "INFO")
    debug_log("="*80, "INFO")
    
    try:
        # Log ALL headers
        debug_log("📋 REQUEST HEADERS:", "INFO")
        for key, value in request.headers.items():
            if key.lower() == 'authorization':
                masked_value = f"{value[:10]}...{value[-10:]}" if len(value) > 20 else value
                debug_log(f"  {key}: {masked_value}", "DEBUG")
            else:
                debug_log(f"  {key}: {value}", "DEBUG")
        
        # Get and log raw body
        raw_body = await request.text()
        debug_log(f"📦 RAW BODY LENGTH: {len(raw_body)} bytes", "INFO")
        debug_log(f"📦 RAW BODY CONTENT: {raw_body}", "INFO")
        
        # Check authorization
        auth_header = request.headers.get('Authorization', '')
        debug_log(f"🔑 Authorization header present: {bool(auth_header)}", "INFO")
        debug_log(f"🔑 TOPGG_WEBHOOK_SECRET configured: {bool(TOPGG_WEBHOOK_SECRET)}", "INFO")
        
        if TOPGG_WEBHOOK_SECRET:
            if not auth_header:
                debug_log("❌ NO AUTHORIZATION HEADER - Rejecting request", "ERROR")
                return web.Response(status=401, text="Missing Authorization header")
            
            if auth_header != TOPGG_WEBHOOK_SECRET:
                debug_log("❌ AUTHORIZATION MISMATCH!", "ERROR")
                debug_log(f"Expected: {TOPGG_WEBHOOK_SECRET[:10]}...", "ERROR")
                debug_log(f"Received: {auth_header[:10]}...", "ERROR")
                return web.Response(status=403, text="Invalid Authorization")
        else:
            debug_log("⚠️ No TOPGG_WEBHOOK_SECRET configured - accepting request", "WARNING")
        
        # Parse JSON
        data = {}
        if not raw_body:
            debug_log("❌ EMPTY REQUEST BODY!", "ERROR")
            return web.Response(status=400, text="Empty request body")
        
        try:
            data = json.loads(raw_body)
            debug_log("✅ JSON parsed successfully", "SUCCESS")
            debug_log(f"📊 Parsed data keys: {list(data.keys())}", "INFO")
            debug_log(f"📊 Full parsed data: {json.dumps(data, indent=2)}", "INFO")
        except json.JSONDecodeError as e:
            debug_log(f"❌ JSON decode error: {e}", "ERROR")
            return web.Response(status=400, text=f"Invalid JSON: {str(e)}")
        
        # Extract fields
        user_id = data.get('user') or data.get('userId') or data.get('userid') or data.get('userID')
        bot_id = data.get('bot') or data.get('botId') or data.get('botid') or data.get('botID')
        vote_type = data.get('type', 'upvote')
        is_weekend = data.get('isWeekend', False) or data.get('weekend', False)
        
        debug_log("📝 EXTRACTED FIELDS:", "INFO")
        debug_log(f"  user_id: {user_id}", "INFO")
        debug_log(f"  bot_id: {bot_id}", "INFO")
        debug_log(f"  vote_type: {vote_type}", "INFO")
        debug_log(f"  is_weekend: {is_weekend}", "INFO")
        
        if not user_id:
            debug_log("❌ CRITICAL: Missing user_id!", "ERROR")
            return web.Response(status=400, text="Missing user ID")
        
        user_id = str(user_id)
        debug_log(f"✅ User ID normalized: {user_id}", "SUCCESS")
        
        # Get bot instance
        bot = request.app.get('bot')
        if not bot:
            debug_log("❌ CRITICAL: Bot instance not found!", "ERROR")
            return web.Response(status=500, text="Bot not initialized")
        
        debug_log(f"🤖 Bot ready: {bot.is_ready()}", "INFO")
        debug_log(f"🤖 Bot user: {bot.user.name if bot.user else 'Not logged in'}", "INFO")
        
        # Process the vote
        await process_vote(bot, user_id, is_weekend, vote_type)
        debug_log("✅✅✅ WEBHOOK REQUEST COMPLETED SUCCESSFULLY ✅✅✅", "SUCCESS")
        
        return web.Response(status=200, text="OK")
        
    except Exception as e:
        debug_log(f"❌ CRITICAL EXCEPTION: {e}", "ERROR")
        tb.print_exc()
        return web.Response(status=500, text=f"Internal error: {str(e)}")

async def process_vote(bot, user_id, is_weekend=False, vote_type='upvote'):
    """Process a vote and send notifications"""
    debug_log(f"▶️▶️▶️ PROCESS_VOTE CALLED for user {user_id}", "INFO")
    
    try:
        is_test = (vote_type.lower() == 'test')
        now = datetime.now(timezone.utc)
        
        # Log to database
        db_query(
            "INSERT INTO vote_logs (user_id, is_weekend, vote_type) VALUES (?, ?, ?)",
            (str(user_id), 1 if is_weekend else 0, vote_type)
        )
        debug_log("✅ Vote logged to database", "SUCCESS")
        
        # Update vote count and expiration
        total_votes = 0
        reminder_enabled = False
        expires_at = now + timedelta(hours=12)
        
        if not is_test:
            existing = db_query(
                "SELECT total_votes, enabled FROM vote_reminders WHERE user_id = ?",
                (str(user_id),),
                fetch=True
            )
            
            if existing and len(existing) > 0:
                total_votes = existing[0][0] + 1
                reminder_enabled = bool(existing[0][1]) if len(existing[0]) > 1 else False
                db_query(
                    "UPDATE vote_reminders SET last_vote = ?, total_votes = ?, role_expires_at = ? WHERE user_id = ?",
                    (now.isoformat(), total_votes, expires_at.isoformat(), str(user_id))
                )
                debug_log(f"✅ Updated vote count to {total_votes}", "SUCCESS")
            else:
                total_votes = 1
                db_query(
                    "INSERT INTO vote_reminders (user_id, last_vote, total_votes, enabled, role_expires_at) VALUES (?, ?, ?, ?, ?)",
                    (str(user_id), now.isoformat(), total_votes, 0, expires_at.isoformat())
                )
                debug_log("✅ Created new vote record", "SUCCESS")
        
        # Fetch user
        user = None
        try:
            user = await bot.fetch_user(int(user_id))
            debug_log(f"✅ User fetched: {user.name}", "SUCCESS")
        except Exception as e:
            debug_log(f"❌ Failed to fetch user: {e}", "ERROR")
        
        # Send to vote log channel
        vote_channel = bot.get_channel(VOTE_LOG_CHANNEL_ID)
        if not vote_channel:
            try:
                vote_channel = await bot.fetch_channel(VOTE_LOG_CHANNEL_ID)
            except Exception as e:
                debug_log(f"❌ Failed to fetch channel: {e}", "ERROR")
        
        if vote_channel:
            embed = discord.Embed(
                title="🗳️ New Vote Received!" if not is_test else "🧪 Test Vote",
                description="Thank you for voting!" if not is_test else "Test vote (not counted)",
                color=discord.Color.gold() if not is_test else discord.Color.blue(),
                timestamp=now
            )
            
            if user:
                embed.add_field(
                    name="👤 Voter",
                    value=f"{user.mention}\n`{user.name}` (`{user_id}`)",
                    inline=True
                )
                embed.set_thumbnail(url=user.display_avatar.url)
            else:
                embed.add_field(name="👤 Voter", value=f"User ID: `{user_id}`", inline=True)
            
            embed.add_field(name="📊 Total Votes", value=f"{total_votes}", inline=True)
            embed.add_field(name="🎁 Weekend", value="Yes ✨" if is_weekend else "No", inline=True)
            
            if not is_test:
                embed.add_field(
                    name="⏰ Role Expires",
                    value=get_discord_timestamp(expires_at, 'R'),
                    inline=True
                )
            
            embed.set_footer(text="Test vote" if is_test else "Vote on Top.gg")
            
            try:
                msg = await vote_channel.send(embed=embed)
                debug_log(f"✅ Message sent to channel! ID: {msg.id}", "SUCCESS")
            except Exception as e:
                debug_log(f"❌ Failed to send to channel: {e}", "ERROR")
        
        # Assign voter role (with retry logic)
        role_assigned = False
        if not is_test:
            debug_log("🎭 Starting role assignment process...", "INFO")
            
            # Try up to 3 times with delays
            for attempt in range(3):
                if attempt > 0:
                    debug_log(f"🔄 Role assignment attempt {attempt + 1}/3", "INFO")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                
                role_assigned = await assign_voter_role(bot, user_id, hours=12)
                
                if role_assigned:
                    debug_log(f"✅ Voter role assigned successfully on attempt {attempt + 1}", "SUCCESS")
                    break
                else:
                    debug_log(f"⚠️ Role assignment attempt {attempt + 1} failed", "WARNING")
            
            if not role_assigned:
                debug_log(f"⚠️ Role assignment failed after 3 attempts (user may not be in server)", "WARNING")
        
        # Send DM to user
        if user:
            try:
                dm_embed = discord.Embed(
                    title="🎉 Thank you for voting!" if not is_test else "🧪 Test Vote",
                    description=f"Your vote has been recorded! Total: **{total_votes}**" if not is_test else f"Test vote (not counted). Current total: **{total_votes}**",
                    color=discord.Color.green() if not is_test else discord.Color.blue(),
                    timestamp=now
                )
                
                view = None
                
                if not is_test:
                    # Show different message based on whether role was assigned
                    if role_assigned:
                        dm_embed.add_field(
                            name="🎁 Rewards",
                            value="• ✅ Voter role assigned (12 hours)\n• Helping the bot grow!" + ("\n• Weekend Bonus! 🎊" if is_weekend else ""),
                            inline=False
                        )
                    else:
                        dm_embed.add_field(
                            name="🎁 Rewards",
                            value="• 🔄 Voter role (will be assigned when you join the server)\n• Helping the bot grow!" + ("\n• Weekend Bonus! 🎊" if is_weekend else ""),
                            inline=False
                        )
                    
                    dm_embed.add_field(
                        name="⏰ Role Duration",
                        value=f"Expires {get_discord_timestamp(expires_at, 'R')}\n\n*{'Role active for 12 hours!' if role_assigned else 'Join the server within 12 hours to get the role!'}*",
                        inline=False
                    )
                    
                    if not reminder_enabled:
                        dm_embed.add_field(
                            name="🔔 Reminders",
                            value="Click below to enable vote reminders!",
                            inline=False
                        )
                        view = VoteReminderView(user_id)
                    else:
                        dm_embed.add_field(
                            name="🔔 Reminders",
                            value="✅ Already enabled",
                            inline=False
                        )
                
                dm_embed.set_footer(text="Vote every 12 hours!" if not is_test else "Test vote")
                
                if view:
                    await user.send(embed=dm_embed, view=view)
                else:
                    await user.send(embed=dm_embed)
                debug_log("✅ DM sent successfully", "SUCCESS")
                
            except discord.Forbidden:
                debug_log(f"⚠️ DM failed (user has DMs disabled): {user.name}", "WARNING")
            except Exception as e:
                debug_log(f"⚠️ DM failed: {e}", "WARNING")
        
        debug_log("✅✅✅ VOTE PROCESSING COMPLETED", "SUCCESS")
        
    except Exception as e:
        debug_log(f"❌ ERROR in process_vote: {e}", "ERROR")
        tb.print_exc()
        raise

class VoteReminderView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
    
    @discord.ui.button(label="Remind me every 12 hours", style=discord.ButtonStyle.primary, emoji="🔔", custom_id="enable_vote_reminder")
    async def enable_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != str(self.user_id):
            await interaction.response.send_message("❌ This button is not for you!", ephemeral=True)
            return
        
        try:
            next_reminder = datetime.now(timezone.utc) + timedelta(hours=12)
            db_query(
                "UPDATE vote_reminders SET enabled = 1, next_reminder = ? WHERE user_id = ?",
                (next_reminder.isoformat(), str(self.user_id))
            )
            
            button.disabled = True
            button.label = "Reminders Enabled ✅"
            button.style = discord.ButtonStyle.success
            
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("🔔 Vote reminders enabled! I'll remind you in 12 hours.", ephemeral=True)
        except Exception as e:
            debug_log(f"❌ Error enabling reminders: {e}", "ERROR")
            await interaction.response.send_message("❌ Failed to enable reminders. Please try again.", ephemeral=True)

class VoteReminderDisableView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
    
    @discord.ui.button(label="Disable Reminders", style=discord.ButtonStyle.danger, emoji="🔕", custom_id="disable_vote_reminder")
    async def disable_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != str(self.user_id):
            await interaction.response.send_message("❌ This button is not for you!", ephemeral=True)
            return
        
        try:
            db_query(
                "UPDATE vote_reminders SET enabled = 0, next_reminder = NULL WHERE user_id = ?",
                (str(self.user_id),)
            )
            
            button.disabled = True
            button.label = "Reminders Disabled ✅"
            
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("🔕 Reminders disabled.", ephemeral=True)
        except Exception as e:
            debug_log(f"❌ Error disabling reminders: {e}", "ERROR")
            await interaction.response.send_message("❌ Failed to disable reminders. Please try again.", ephemeral=True)

async def vote_reminder_loop(bot):
    """Background task to send vote reminders"""
    await bot.wait_until_ready()
    debug_log("✅ Vote reminder loop started", "SUCCESS")
    
    while not bot.is_closed():
        try:
            now = datetime.now(timezone.utc)
            
            reminders = db_query(
                "SELECT user_id, total_votes FROM vote_reminders WHERE enabled = 1 AND next_reminder <= ?",
                (now.isoformat(),),
                fetch=True
            )
            
            if reminders:
                debug_log(f"📬 Found {len(reminders)} reminder(s)", "INFO")
            
            for user_id, total_votes in reminders:
                try:
                    user = await bot.fetch_user(int(user_id))
                    
                    embed = discord.Embed(
                        title="🔔 Vote Reminder",
                        description="Time to vote again!",
                        color=discord.Color.blue(),
                        timestamp=now
                    )
                    
                    embed.add_field(
                        name="📊 Your Stats",
                        value=f"**Total Votes:** {total_votes}",
                        inline=False
                    )
                    
                    view = discord.ui.View(timeout=None)
                    view.add_item(discord.ui.Button(
                        label="Vote on Top.gg",
                        url=f"https://top.gg/bot/{bot.user.id}/vote",
                        style=discord.ButtonStyle.link,
                        emoji="🗳️"
                    ))
                    
                    disable_view = VoteReminderDisableView(user_id)
                    for item in disable_view.children:
                        view.add_item(item)
                    
                    await user.send(embed=embed, view=view)
                    
                    next_reminder = now + timedelta(hours=12)
                    db_query(
                        "UPDATE vote_reminders SET next_reminder = ? WHERE user_id = ?",
                        (next_reminder.isoformat(), str(user_id))
                    )
                    
                except discord.Forbidden:
                    db_query("UPDATE vote_reminders SET enabled = 0 WHERE user_id = ?", (str(user_id),))
                    debug_log(f"⚠️ Cannot send reminder to {user_id} (DMs disabled), disabling reminders", "WARNING")
                except Exception as e:
                    debug_log(f"❌ Reminder error for {user_id}: {e}", "ERROR")
                
                await asyncio.sleep(1)
            
            await asyncio.sleep(300)  # Check every 5 minutes
            
        except Exception as e:
            debug_log(f"❌ Reminder loop error: {e}", "ERROR")
            tb.print_exc()
            await asyncio.sleep(300)

async def role_expiration_loop(bot):
    """Background task to remove expired voter roles"""
    await bot.wait_until_ready()
    debug_log("✅ Role expiration loop started", "SUCCESS")
    
    while not bot.is_closed():
        try:
            now = datetime.now(timezone.utc)
            
            expired = db_query(
                "SELECT user_id, role_expires_at FROM vote_reminders WHERE role_expires_at IS NOT NULL AND role_expires_at <= ?",
                (now.isoformat(),),
                fetch=True
            )
            
            if expired:
                debug_log(f"⏰ Found {len(expired)} expired role(s)", "INFO")
            
            for user_id, expires_at in expired:
                try:
                    if not SUPPORT_SERVER_ID:
                        continue
                    
                    guild = bot.get_guild(SUPPORT_SERVER_ID)
                    if not guild:
                        try:
                            guild = await bot.fetch_guild(SUPPORT_SERVER_ID)
                        except Exception as e:
                            debug_log(f"❌ Failed to fetch guild: {e}", "ERROR")
                            continue
                    
                    if not guild:
                        continue
                    
                    member = guild.get_member(int(user_id))
                    if not member:
                        try:
                            member = await guild.fetch_member(int(user_id))
                        except discord.NotFound:
                            db_query("UPDATE vote_reminders SET role_expires_at = NULL WHERE user_id = ?", (str(user_id),))
                            debug_log(f"ℹ️ User {user_id} not in guild, clearing expiration", "INFO")
                            continue
                        except Exception as e:
                            debug_log(f"❌ Error fetching member {user_id}: {e}", "ERROR")
                            continue
                    
                    if not member:
                        continue
                    
                    role = guild.get_role(VOTER_ROLE_ID)
                    if not role:
                        debug_log(f"❌ Voter role {VOTER_ROLE_ID} not found", "ERROR")
                        continue
                    
                    if role in member.roles:
                        await member.remove_roles(role, reason="Voter role expired (12 hours)")
                        debug_log(f"✅ Removed voter role from {member.name}", "SUCCESS")
                        
                        db_query("UPDATE vote_reminders SET role_expires_at = NULL WHERE user_id = ?", (str(user_id),))
                        
                        # Send DM notification
                        try:
                            user = await bot.fetch_user(int(user_id))
                            embed = discord.Embed(
                                title="⏰ Voter Role Expired",
                                description="Your Voter role has expired after 12 hours.",
                                color=discord.Color.orange(),
                                timestamp=now
                            )
                            
                            embed.add_field(
                                name="🗳️ Vote Again",
                                value="Vote now to get your role back!",
                                inline=False
                            )
                            
                            view = discord.ui.View(timeout=None)
                            view.add_item(discord.ui.Button(
                                label="Vote on Top.gg",
                                url=f"https://top.gg/bot/{bot.user.id}/vote",
                                style=discord.ButtonStyle.link,
                                emoji="🗳️"
                            ))
                            
                            await user.send(embed=embed, view=view)
                            debug_log(f"✅ Sent expiration notice to {user.name}", "SUCCESS")
                        except discord.Forbidden:
                            debug_log(f"⚠️ Cannot DM {user_id} about expiration", "WARNING")
                        except Exception as dm_error:
                            debug_log(f"⚠️ Failed to send expiration DM: {dm_error}", "WARNING")
                    else:
                        # Role not found, just clear the expiration
                        db_query("UPDATE vote_reminders SET role_expires_at = NULL WHERE user_id = ?", (str(user_id),))
                        debug_log(f"ℹ️ User {member.name} doesn't have role, clearing expiration", "INFO")
                    
                except discord.Forbidden as e:
                    debug_log(f"❌ Missing permissions for {user_id}: {e}", "ERROR")
                except Exception as e:
                    debug_log(f"❌ Error removing role from {user_id}: {e}", "ERROR")
                    tb.print_exc()
                
                await asyncio.sleep(0.5)
            
            await asyncio.sleep(60)  # Check every minute
            
        except Exception as e:
            debug_log(f"❌ Role expiration loop error: {e}", "ERROR")
            tb.print_exc()
            await asyncio.sleep(60)

async def start_webhook_server(bot, port=8080):
    """Start the webhook server"""
    debug_log("🚀 INITIALIZING WEBHOOK SERVER", "INFO")
    
    try:
        app = web.Application()
        app['bot'] = bot
        
        app.router.add_post('/topgg/webhook', handle_vote)
        app.router.add_post('/webhook', handle_vote)
        app.router.add_post('/topgg', handle_vote)
        app.router.add_post('/', handle_vote)
        
        async def health_check(request):
            bot_status = "ready" if bot.is_ready() else "not ready"
            return web.Response(text=f"Webhook running! Bot: {bot_status}", status=200)
        
        async def test_vote(request):
            test_data = {
                "user": "1081876265683927080",
                "bot": "1379152032358858762",
                "type": "test",
                "isWeekend": False
            }
            
            bot = request.app.get('bot')
            if bot:
                try:
                    await process_vote(bot, test_data['user'], test_data['isWeekend'], test_data['type'])
                    return web.Response(text="Test vote processed!", status=200)
                except Exception as e:
                    return web.Response(text=f"Test failed: {str(e)}", status=500)
            return web.Response(text="Bot not initialized", status=500)
        
        app.router.add_get('/health', health_check)
        app.router.add_get('/test', test_vote)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        debug_log(f"✅ WEBHOOK SERVER RUNNING ON PORT {port}", "SUCCESS")
        debug_log(f"📡 Listening on: http://0.0.0.0:{port}", "INFO")
        debug_log(f"🔑 Webhook secret configured: {bool(TOPGG_WEBHOOK_SECRET)}", "INFO")
        debug_log(f"🏰 Support server ID: {SUPPORT_SERVER_ID}", "INFO")
        debug_log(f"🎭 Voter role ID: {VOTER_ROLE_ID}", "INFO")
        
    except Exception as e:
        debug_log(f"❌ FAILED TO START SERVER: {e}", "ERROR")
        tb.print_exc()
        raise
