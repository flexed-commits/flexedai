```python
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
    
    try:
        guild = bot.get_guild(SUPPORT_SERVER_ID)
        if not guild:
            guild = await bot.fetch_guild(SUPPORT_SERVER_ID)
        
        if not guild:
            debug_log(f"❌ Guild {SUPPORT_SERVER_ID} not found", "ERROR")
            return False
        
        debug_log(f"✅ Guild found: {guild.name}", "SUCCESS")
        
        member = guild.get_member(int(user_id))
        if not member:
            try:
                member = await guild.fetch_member(int(user_id))
            except discord.NotFound:
                debug_log(f"⚠️ User {user_id} is not a member of {guild.name}", "WARNING")
                return False
        
        if not member:
            debug_log(f"❌ Member {user_id} not found in guild", "ERROR")
            return False
        
        debug_log(f"✅ Member found: {member.name}", "SUCCESS")
        
        role = guild.get_role(VOTER_ROLE_ID)
        if not role:
            debug_log(f"❌ Voter role {VOTER_ROLE_ID} not found", "ERROR")
            return False
        
        debug_log(f"✅ Voter role found: {role.name}", "SUCCESS")
        
        # Calculate expiration time (UTC timezone-aware)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
        
        # Add role
        if role not in member.roles:
            await member.add_roles(role, reason=f"Voted on Top.gg - expires in {hours}h")
            debug_log(f"✅ Voter role assigned to {member.name} until {expires_at.isoformat()}", "SUCCESS")
        else:
            debug_log(f"ℹ️ Member {member.name} already has voter role, updating expiration", "INFO")
        
        # Update expiration in database
        db_query(
            "UPDATE vote_reminders SET role_expires_at = ? WHERE user_id = ?",
            (expires_at.isoformat(), str(user_id))
        )
        
        return True
        
    except Exception as e:
        debug_log(f"❌ Role assignment error: {e}", "ERROR")
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
                debug_log("⚠️⚠️⚠️ ALLOWING ANYWAY FOR DEBUGGING ⚠️⚠️⚠️", "WARNING")
            else:
                debug_log("✅ Authorization validated successfully", "SUCCESS")
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
                    dm_embed.add_field(
                        name="🎁 Rewards",
                        value="• Voter role (12 hours)\n• Helping the bot grow!" + ("\n• Weekend Bonus! 🎊" if is_weekend else ""),
                        inline=False
                    )
                    
                    dm_embed.add_field(
                        name="⏰ Role Expires",
                        value=f"{get_discord_timestamp(expires_at, 'R')}\n\n*Join the server within 12 hours to get the role!*",
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
           
