from aiohttp import web
import discord
import sqlite3
import asyncio
import os
from datetime import datetime, timedelta
import json
import traceback as tb

DB_FILE = "bot_data.db"
TOPGG_WEBHOOK_SECRET = os.getenv('TOPGG_WEBHOOK_SECRET')
VOTE_LOG_CHANNEL_ID = 1466059183052034193
VOTER_ROLE_ID = 1466059698666213427

def debug_log(message, level="INFO"):
    """Enhanced debug logging with timestamps"""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    prefix = {
        "INFO": "ℹ️",
        "SUCCESS": "✅",
        "ERROR": "❌",
        "WARNING": "⚠️",
        "DEBUG": "🔍"
    }.get(level, "📝")
    print(f"[{timestamp}] {prefix} {message}")

def init_vote_db():
    """Initialize vote reminder database"""
    try:
        debug_log("Initializing vote database...", "INFO")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS vote_reminders (
            user_id TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 1,
            last_vote DATETIME,
            next_reminder DATETIME,
            total_votes INTEGER DEFAULT 0
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS vote_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            voted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_weekend INTEGER DEFAULT 0,
            vote_type TEXT DEFAULT 'upvote'
        )''')
        
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

async def handle_vote(request):
    """Handle Top.gg vote webhook with extensive debugging"""
    debug_log("="*80, "INFO")
    debug_log("WEBHOOK REQUEST RECEIVED", "INFO")
    debug_log(f"Path: {request.path}", "INFO")
    debug_log(f"Method: {request.method}", "INFO")
    debug_log(f"Remote: {request.remote}", "INFO")
    debug_log("="*80, "INFO")
    
    try:
        # Log ALL headers in detail
        debug_log("REQUEST HEADERS:", "DEBUG")
        for key, value in request.headers.items():
            if key.lower() == 'authorization':
                masked_value = f"{value[:10]}...{value[-10:]}" if len(value) > 20 else value
                debug_log(f"  {key}: {masked_value}", "DEBUG")
            else:
                debug_log(f"  {key}: {value}", "DEBUG")
        
        # Get and log raw body
        raw_body = await request.text()
        debug_log(f"RAW BODY LENGTH: {len(raw_body)} bytes", "DEBUG")
        debug_log(f"RAW BODY CONTENT: {raw_body}", "DEBUG")
        
        # Check authorization
        auth_header = request.headers.get('Authorization', '')
        debug_log(f"Authorization header present: {bool(auth_header)}", "DEBUG")
        debug_log(f"TOPGG_WEBHOOK_SECRET configured: {bool(TOPGG_WEBHOOK_SECRET)}", "DEBUG")
        
        if TOPGG_WEBHOOK_SECRET:
            if not auth_header:
                debug_log("No Authorization header provided but secret is configured", "WARNING")
                return web.Response(status=401, text="Missing Authorization header")
            
            if auth_header != TOPGG_WEBHOOK_SECRET:
                debug_log("Authorization mismatch!", "ERROR")
                debug_log(f"Expected: {TOPGG_WEBHOOK_SECRET[:10]}...", "ERROR")
                debug_log(f"Received: {auth_header[:10]}...", "ERROR")
                return web.Response(status=401, text="Invalid Authorization")
            
            debug_log("Authorization validated successfully", "SUCCESS")
        else:
            debug_log("No TOPGG_WEBHOOK_SECRET configured - accepting request", "WARNING")
        
        # Parse JSON with detailed error handling
        data = {}
        if not raw_body:
            debug_log("Empty request body!", "ERROR")
            return web.Response(status=400, text="Empty request body")
        
        try:
            data = json.loads(raw_body)
            debug_log("JSON parsed successfully", "SUCCESS")
            debug_log(f"Parsed data keys: {list(data.keys())}", "DEBUG")
            debug_log(f"Full parsed data: {json.dumps(data, indent=2)}", "DEBUG")
        except json.JSONDecodeError as e:
            debug_log(f"JSON decode error: {e}", "ERROR")
            debug_log(f"Error at position: {e.pos}", "ERROR")
            debug_log(f"Error line: {e.lineno}, column: {e.colno}", "ERROR")
            return web.Response(status=400, text=f"Invalid JSON: {str(e)}")
        
        # Extract and validate fields with multiple fallbacks
        user_id = data.get('user') or data.get('userId') or data.get('userid') or data.get('userID')
        bot_id = data.get('bot') or data.get('botId') or data.get('botid') or data.get('botID')
        vote_type = data.get('type', 'upvote')
        is_weekend = data.get('isWeekend', False) or data.get('weekend', False)
        query_params = data.get('query', '')
        
        debug_log("EXTRACTED FIELDS:", "INFO")
        debug_log(f"  user_id: {user_id} (type: {type(user_id).__name__})", "DEBUG")
        debug_log(f"  bot_id: {bot_id} (type: {type(bot_id).__name__})", "DEBUG")
        debug_log(f"  vote_type: {vote_type} (type: {type(vote_type).__name__})", "DEBUG")
        debug_log(f"  is_weekend: {is_weekend} (type: {type(is_weekend).__name__})", "DEBUG")
        debug_log(f"  query_params: {query_params}", "DEBUG")
        
        # Validate user_id
        if not user_id:
            debug_log("CRITICAL: Missing user_id in request!", "ERROR")
            debug_log(f"Available data keys: {list(data.keys())}", "ERROR")
            debug_log(f"Full data dump: {data}", "ERROR")
            return web.Response(status=400, text="Missing user ID")
        
        # Convert user_id to string if it's not already
        user_id = str(user_id)
        debug_log(f"User ID normalized to string: {user_id}", "DEBUG")
        
        # Get bot instance with validation
        bot = request.app.get('bot')
        debug_log(f"Bot instance retrieved: {bot is not None}", "DEBUG")
        
        if not bot:
            debug_log("CRITICAL: Bot instance not found in app!", "ERROR")
            return web.Response(status=500, text="Bot not initialized")
        
        debug_log(f"Bot user: {bot.user}", "DEBUG")
        debug_log(f"Bot ready: {bot.is_ready()}", "DEBUG")
        debug_log(f"Bot latency: {bot.latency * 1000:.2f}ms", "DEBUG")
        
        if bot.user:
            debug_log(f"Bot name: {bot.user.name}", "SUCCESS")
            debug_log(f"Bot ID: {bot.user.id}", "DEBUG")
        else:
            debug_log("Bot user is None - bot may not be ready!", "WARNING")
        
        # Process the vote
        debug_log("Starting vote processing...", "INFO")
        try:
            await process_vote(bot, user_id, is_weekend, vote_type)
            debug_log("Vote processing completed successfully", "SUCCESS")
        except Exception as vote_error:
            debug_log(f"Vote processing failed: {vote_error}", "ERROR")
            tb.print_exc()
            return web.Response(status=500, text=f"Vote processing error: {str(vote_error)}")
        
        debug_log("="*80, "INFO")
        debug_log("WEBHOOK REQUEST COMPLETED SUCCESSFULLY", "SUCCESS")
        debug_log("="*80, "INFO")
        
        return web.Response(status=200, text="OK")
        
    except Exception as e:
        debug_log(f"CRITICAL EXCEPTION in handle_vote: {e}", "ERROR")
        debug_log(f"Exception type: {type(e).__name__}", "ERROR")
        tb.print_exc()
        debug_log("="*80, "ERROR")
        return web.Response(status=500, text=f"Internal error: {str(e)}")

async def process_vote(bot, user_id, is_weekend=False, vote_type='upvote'):
    """Process a vote and send notifications with extensive debugging"""
    debug_log(f"PROCESS_VOTE CALLED", "INFO")
    debug_log(f"  user_id: {user_id}", "DEBUG")
    debug_log(f"  is_weekend: {is_weekend}", "DEBUG")
    debug_log(f"  vote_type: {vote_type}", "DEBUG")
    
    try:
        # Determine if this is a test vote
        is_test = (vote_type.lower() == 'test')
        debug_log(f"Vote is test vote: {is_test}", "INFO")
        
        # Log the vote to database
        debug_log("Inserting vote into vote_logs table...", "DEBUG")
        try:
            db_query(
                "INSERT INTO vote_logs (user_id, is_weekend, vote_type) VALUES (?, ?, ?)",
                (str(user_id), 1 if is_weekend else 0, vote_type)
            )
            debug_log("Vote logged to database successfully", "SUCCESS")
        except Exception as db_error:
            debug_log(f"Database insert failed: {db_error}", "ERROR")
            tb.print_exc()
        
        # Update vote count (only for non-test votes)
        total_votes = 0
        if not is_test:
            debug_log("Processing non-test vote - updating vote count", "INFO")
            try:
                existing = db_query(
                    "SELECT total_votes FROM vote_reminders WHERE user_id = ?",
                    (str(user_id),),
                    fetch=True
                )
                debug_log(f"Existing vote record: {existing}", "DEBUG")
                
                if existing and len(existing) > 0:
                    total_votes = existing[0][0] + 1
                    debug_log(f"Updating existing record. New total: {total_votes}", "DEBUG")
                    db_query(
                        "UPDATE vote_reminders SET last_vote = ?, total_votes = ? WHERE user_id = ?",
                        (datetime.utcnow().isoformat(), total_votes, str(user_id))
                    )
                    debug_log(f"Vote count updated to {total_votes}", "SUCCESS")
                else:
                    total_votes = 1
                    debug_log("Creating new vote record with count 1", "DEBUG")
                    db_query(
                        "INSERT INTO vote_reminders (user_id, last_vote, total_votes) VALUES (?, ?, ?)",
                        (str(user_id), datetime.utcnow().isoformat(), total_votes)
                    )
                    debug_log("New vote record created", "SUCCESS")
            except Exception as update_error:
                debug_log(f"Vote count update failed: {update_error}", "ERROR")
                tb.print_exc()
        else:
            debug_log("Test vote - skipping vote count update", "INFO")
            try:
                existing = db_query(
                    "SELECT total_votes FROM vote_reminders WHERE user_id = ?",
                    (str(user_id),),
                    fetch=True
                )
                total_votes = existing[0][0] if existing and len(existing) > 0 else 0
                debug_log(f"User's current vote count: {total_votes}", "INFO")
            except Exception as fetch_error:
                debug_log(f"Failed to fetch existing vote count: {fetch_error}", "WARNING")
        
        # Fetch user object
        debug_log(f"Fetching Discord user object for ID: {user_id}", "DEBUG")
        user = None
        try:
            user_id_int = int(user_id)
            debug_log(f"User ID converted to int: {user_id_int}", "DEBUG")
            user = await bot.fetch_user(user_id_int)
            debug_log(f"User fetched successfully: {user.name}#{user.discriminator}", "SUCCESS")
            debug_log(f"User avatar URL: {user.display_avatar.url}", "DEBUG")
        except ValueError as ve:
            debug_log(f"Invalid user ID format: {ve}", "ERROR")
        except discord.NotFound:
            debug_log(f"User {user_id} not found on Discord", "ERROR")
        except discord.HTTPException as http_err:
            debug_log(f"HTTP error fetching user: {http_err}", "ERROR")
        except Exception as user_error:
            debug_log(f"Failed to fetch user: {user_error}", "ERROR")
            tb.print_exc()
        
        # Send to vote log channel
        debug_log(f"Attempting to send message to vote log channel {VOTE_LOG_CHANNEL_ID}", "INFO")
        vote_channel = None
        try:
            vote_channel = bot.get_channel(VOTE_LOG_CHANNEL_ID)
            debug_log(f"Channel object retrieved: {vote_channel is not None}", "DEBUG")
            
            if not vote_channel:
                debug_log(f"Channel {VOTE_LOG_CHANNEL_ID} not found in cache, attempting fetch...", "WARNING")
                try:
                    vote_channel = await bot.fetch_channel(VOTE_LOG_CHANNEL_ID)
                    debug_log(f"Channel fetched successfully: #{vote_channel.name}", "SUCCESS")
                except Exception as fetch_err:
                    debug_log(f"Failed to fetch channel: {fetch_err}", "ERROR")
            else:
                debug_log(f"Channel found in cache: #{vote_channel.name}", "SUCCESS")
                debug_log(f"Channel type: {vote_channel.type}", "DEBUG")
                debug_log(f"Channel guild: {vote_channel.guild.name if hasattr(vote_channel, 'guild') else 'N/A'}", "DEBUG")
        except Exception as channel_error:
            debug_log(f"Error getting vote channel: {channel_error}", "ERROR")
            tb.print_exc()
        
        if vote_channel:
            debug_log("Creating embed for vote log channel", "DEBUG")
            try:
                embed = discord.Embed(
                    title="🗳️ New Vote Received!" if not is_test else "🧪 Test Vote Received!",
                    description="Thank you for voting!" if not is_test else "Test vote from Top.gg webhook (not counted)",
                    color=discord.Color.gold() if not is_test else discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                
                if user:
                    embed.add_field(
                        name="👤 Voter", 
                        value=f"{user.mention}\n`{user.name}` (`{user_id}`)", 
                        inline=True
                    )
                    embed.set_thumbnail(url=user.display_avatar.url)
                    debug_log("Added user info to embed", "DEBUG")
                else:
                    embed.add_field(name="👤 Voter", value=f"User ID: `{user_id}`", inline=True)
                    debug_log("Added user ID to embed (user object not available)", "DEBUG")
                
                embed.add_field(
                    name="📊 Total Votes", 
                    value=f"{total_votes}" + (" (test - not counted)" if is_test else ""), 
                    inline=True
                )
                embed.add_field(name="🎁 Weekend Bonus", value="Yes ✨" if is_weekend else "No", inline=True)
                embed.add_field(name="🔖 Vote Type", value=vote_type.capitalize(), inline=True)
                embed.set_footer(text="Vote on Top.gg" if not is_test else "Test vote - count not incremented")
                
                debug_log("Embed created, attempting to send...", "DEBUG")
                msg = await vote_channel.send(embed=embed)
                debug_log(f"Message sent successfully! Message ID: {msg.id}", "SUCCESS")
                debug_log(f"Message URL: {msg.jump_url}", "DEBUG")
                
            except discord.Forbidden as forbidden:
                debug_log(f"Missing permissions to send message: {forbidden}", "ERROR")
            except discord.HTTPException as http_err:
                debug_log(f"HTTP error sending message: {http_err}", "ERROR")
                debug_log(f"Status: {http_err.status}, Code: {http_err.code}", "ERROR")
            except Exception as send_error:
                debug_log(f"Failed to send message to channel: {send_error}", "ERROR")
                tb.print_exc()
        else:
            debug_log("Vote channel is None, cannot send message", "ERROR")
        
        # Send DM to user
        if user:
            debug_log(f"Preparing DM for user {user.name}", "INFO")
            try:
                dm_embed = discord.Embed(
                    title="🎉 Thank you for voting!" if not is_test else "🧪 Test Vote Received!",
                    description=f"Your vote has been recorded! You now have **{total_votes}** total vote(s)." if not is_test else f"This is a test vote and was **not counted**.\n\nYour current vote count: **{total_votes}**",
                    color=discord.Color.green() if not is_test else discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                
                if not is_test:
                    dm_embed.add_field(
                        name="🎁 Rewards",
                        value="• Voter role assigned\n• Helping the bot grow!\n• Your vote matters! ❤️" + ("\n• **Weekend Bonus!** 🎊" if is_weekend else ""),
                        inline=False
                    )
                    dm_embed.add_field(
                        name="⏰ Vote Again",
                        value="You can vote again in 12 hours!\nClick below to enable reminders.",
                        inline=False
                    )
                    view = VoteReminderView(user_id)
                    debug_log("Created reminder view for DM", "DEBUG")
                else:
                    dm_embed.add_field(
                        name="ℹ️ About Test Votes",
                        value="Test votes are used to verify the webhook is working correctly. They don't count toward your total or give rewards.",
                        inline=False
                    )
                    view = None
                    debug_log("No view for test vote DM", "DEBUG")
                
                dm_embed.set_footer(text="Vote every 12 hours" if not is_test else "Test vote from Top.gg")
                
                debug_log("Attempting to send DM...", "DEBUG")
                if view:
                    dm_msg = await user.send(embed=dm_embed, view=view)
                else:
                    dm_msg = await user.send(embed=dm_embed)
                debug_log(f"DM sent successfully! Message ID: {dm_msg.id}", "SUCCESS")
                
            except discord.Forbidden:
                debug_log(f"Cannot send DM to {user.name} - DMs are disabled", "WARNING")
            except discord.HTTPException as http_err:
                debug_log(f"HTTP error sending DM: {http_err}", "ERROR")
            except Exception as dm_error:
                debug_log(f"Failed to send DM: {dm_error}", "ERROR")
                tb.print_exc()
        else:
            debug_log("User object is None, cannot send DM", "WARNING")
        
        # Assign voter role (only for non-test votes)
        if not is_test:
            debug_log("Attempting to assign voter role...", "INFO")
            try:
                support_server_id = os.getenv('SUPPORT_SERVER_ID')
                debug_log(f"SUPPORT_SERVER_ID from env: {support_server_id}", "DEBUG")
                
                if not support_server_id:
                    debug_log("SUPPORT_SERVER_ID not set in environment variables", "WARNING")
                else:
                    support_server_id = int(support_server_id)
                    debug_log(f"Support server ID (int): {support_server_id}", "DEBUG")
                    
                    guild = bot.get_guild(support_server_id)
                    if not guild:
                        debug_log(f"Guild {support_server_id} not found in cache, fetching...", "WARNING")
                        try:
                            guild = await bot.fetch_guild(support_server_id)
                            debug_log(f"Guild fetched: {guild.name}", "SUCCESS")
                        except Exception as guild_err:
                            debug_log(f"Failed to fetch guild: {guild_err}", "ERROR")
                    else:
                        debug_log(f"Guild found: {guild.name}", "SUCCESS")
                    
                    if guild:
                        member = guild.get_member(int(user_id))
                        if not member:
                            debug_log(f"Member {user_id} not in cache, fetching...", "DEBUG")
                            try:
                                member = await guild.fetch_member(int(user_id))
                                debug_log(f"Member fetched: {member.name}", "SUCCESS")
                            except discord.NotFound:
                                debug_log(f"User {user_id} is not a member of {guild.name}", "WARNING")
                            except Exception as member_err:
                                debug_log(f"Failed to fetch member: {member_err}", "ERROR")
                        else:
                            debug_log(f"Member found: {member.name}", "SUCCESS")
                        
                        if member:
                            role = guild.get_role(VOTER_ROLE_ID)
                            if role:
                                debug_log(f"Voter role found: {role.name}", "SUCCESS")
                                if role in member.roles:
                                    debug_log(f"Member already has voter role", "INFO")
                                else:
                                    debug_log(f"Adding voter role to member...", "DEBUG")
                                    await member.add_roles(role, reason="Voted on Top.gg")
                                    debug_log(f"Voter role assigned successfully!", "SUCCESS")
                            else:
                                debug_log(f"Voter role {VOTER_ROLE_ID} not found in guild", "ERROR")
                        else:
                            debug_log("Member object is None after fetch attempts", "WARNING")
                    else:
                        debug_log("Guild object is None", "ERROR")
                        
            except ValueError as ve:
                debug_log(f"Invalid SUPPORT_SERVER_ID format: {ve}", "ERROR")
            except Exception as role_error:
                debug_log(f"Role assignment error: {role_error}", "ERROR")
                tb.print_exc()
        else:
            debug_log("Test vote - skipping role assignment", "INFO")
        
        debug_log("Vote processing completed successfully", "SUCCESS")
        
    except Exception as e:
        debug_log(f"CRITICAL ERROR in process_vote: {e}", "ERROR")
        debug_log(f"Exception type: {type(e).__name__}", "ERROR")
        tb.print_exc()
        raise

class VoteReminderView(discord.ui.View):
    """View with reminder button"""
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        debug_log(f"VoteReminderView created for user {user_id}", "DEBUG")
    
    @discord.ui.button(label="Remind me every 12 hours", style=discord.ButtonStyle.primary, emoji="🔔", custom_id="enable_vote_reminder")
    async def enable_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        debug_log(f"Reminder button clicked by {interaction.user.id}", "DEBUG")
        
        if str(interaction.user.id) != str(self.user_id):
            debug_log(f"Wrong user clicked button. Expected {self.user_id}, got {interaction.user.id}", "WARNING")
            await interaction.response.send_message("❌ This button is not for you!", ephemeral=True)
            return
        
        try:
            next_reminder = datetime.utcnow() + timedelta(hours=12)
            debug_log(f"Setting next reminder for {next_reminder.isoformat()}", "DEBUG")
            
            db_query(
                "UPDATE vote_reminders SET enabled = 1, next_reminder = ? WHERE user_id = ?",
                (next_reminder.isoformat(), str(self.user_id))
            )
            
            button.disabled = True
            button.label = "Reminders Enabled ✅"
            button.style = discord.ButtonStyle.success
            
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                "🔔 **Vote reminders enabled!**\n\nI'll remind you to vote again in 12 hours.",
                ephemeral=True
            )
            debug_log(f"Vote reminders enabled for user {self.user_id}", "SUCCESS")
            
        except Exception as e:
            debug_log(f"Error enabling reminders: {e}", "ERROR")
            tb.print_exc()
            await interaction.response.send_message(
                "❌ An error occurred while enabling reminders. Please try again.",
                ephemeral=True
            )

async def vote_reminder_loop(bot):
    """Background task to send vote reminders"""
    await bot.wait_until_ready()
    debug_log("Vote reminder loop started", "SUCCESS")
    
    while not bot.is_closed():
        try:
            now = datetime.utcnow()
            debug_log(f"Checking for reminders at {now.isoformat()}", "DEBUG")
            
            reminders = db_query(
                "SELECT user_id, total_votes FROM vote_reminders WHERE enabled = 1 AND next_reminder <= ?",
                (now.isoformat(),),
                fetch=True
            )
            
            if reminders:
                debug_log(f"Found {len(reminders)} reminder(s) to send", "INFO")
            
            for user_id, total_votes in reminders:
                try:
                    debug_log(f"Sending reminder to user {user_id}", "DEBUG")
                    user = await bot.fetch_user(int(user_id))
                    
                    embed = discord.Embed(
                        title="🔔 Vote Reminder",
                        description="It's time to vote again!",
                        color=discord.Color.blue(),
                        timestamp=datetime.utcnow()
                    )
                    
                    embed.add_field(
                        name="📊 Your Stats",
                        value=f"**Total Votes:** {total_votes}\n**Next Vote:** Now!",
                        inline=False
                    )
                    
                    embed.add_field(
                        name="🗳️ Vote Now",
                        value="Click below to vote!",
                        inline=False
                    )
                    
                    embed.set_footer(text="Disable with /votereminder disable")
                    
                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(
                        label="Vote on Top.gg",
                        url=f"https://top.gg/bot/{bot.user.id}/vote",
                        style=discord.ButtonStyle.link,
                        emoji="🗳️"
                    ))
                    
                    await user.send(embed=embed, view=view)
                    
                    next_reminder = now + timedelta(hours=12)
                    db_query(
                        "UPDATE vote_reminders SET next_reminder = ? WHERE user_id = ?",
                        (next_reminder.isoformat(), str(user_id))
                    )
                    
                    debug_log(f"Reminder sent successfully to {user.name}", "SUCCESS")
                    
                except discord.Forbidden:
                    db_query("UPDATE vote_reminders SET enabled = 0 WHERE user_id = ?", (str(user_id),))
                    debug_log(f"DMs closed for user {user_id}, disabled reminders", "WARNING")
                except Exception as e:
                    debug_log(f"Reminder error for user {user_id}: {e}", "ERROR")
                    tb.print_exc()
                
                await asyncio.sleep(1)
            
            await asyncio.sleep(300)  # Check every 5 minutes
            
        except Exception as e:
            debug_log(f"Reminder loop error: {e}", "ERROR")
            tb.print_exc()
            await asyncio.sleep(300)

async def start_webhook_server(bot, port=8080):
    """Start the webhook server"""
    debug_log("="*80, "INFO")
    debug_log("INITIALIZING WEBHOOK SERVER", "INFO")
    debug_log("="*80, "INFO")
    
    try:
        app = web.Application()
        app['bot'] = bot
        
        debug_log(f"Bot instance stored in app", "SUCCESS")
        if bot.user:
            debug_log(f"Bot: {bot.user.name} (ID: {bot.user.id})", "INFO")
        else:
            debug_log("Bot user not ready yet", "WARNING")
        
        # Add webhook routes
        app.router.add_post('/topgg/webhook', handle_vote)
        app.router.add_post('/webhook', handle_vote)
        app.router.add_post('/topgg', handle_vote)
        app.router.add_post('/', handle_vote)
        debug_log("POST routes added: /topgg/webhook, /webhook, /topgg, /", "SUCCESS")
        
        # Health check endpoint
        async def health_check(request):
            debug_log(f"Health check request from {request.remote}", "DEBUG")
            bot_status = "ready" if bot.is_ready() else "not ready"
            return web.Response(
                text=f"Webhook server running! Bot status: {bot_status}", 
                status=200
            )
        
        app.router.add_get('/health', health_check)
        app.router.add_get('/topgg/webhook', health_check)
        app.router.add_get('/', health_check)
        debug_log("GET routes added: /health, /topgg/webhook, /", "SUCCESS")
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        debug_log("="*80, "SUCCESS")
        debug_log(f"WEBHOOK SERVER RUNNING ON PORT {port}", "SUCCESS")
        debug_log("="*80, "SUCCESS")
        debug_log(f"Webhook URL: https://tamisha-dilatometric-lengthwise.ngrok-free.dev/topgg/webhook", "INFO")
        debug_log(f"Alternative: https://tamisha-dilatometric-lengthwise.ngrok-free.dev/webhook", "INFO")
        debug_log(f"Health check: https://tamisha-dilatometric-lengthwise.ngrok-free.dev/health", "INFO")
        
        if TOPGG_WEBHOOK_SECRET:
            debug_log(f"Auth secret configured: {TOPGG_WEBHOOK_SECRET[:10]}...", "INFO")
        else:
            debug_log("WARNING: No TOPGG_WEBHOOK_SECRET configured!", "WARNING")
        
        debug_log("="*80, "INFO")
        
    except Exception as e:
        debug_log(f"FAILED TO START SERVER: {e}", "ERROR")
        tb.print_exc()
        raise
