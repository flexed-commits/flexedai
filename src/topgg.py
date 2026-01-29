from aiohttp import web
import discord
import sqlite3
import asyncio
import os
from datetime import datetime, timedelta
import json

DB_FILE = "bot_data.db"
TOPGG_WEBHOOK_SECRET = os.getenv('TOPGG_WEBHOOK_SECRET')
VOTE_LOG_CHANNEL_ID = 1466059183052034193
VOTER_ROLE_ID = 1466059698666213427

def init_vote_db():
    """Initialize vote reminder database"""
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
    print("✅ Vote database initialized")

def db_query(query, params=(), fetch=False):
    """Execute database query"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
        return c.fetchall() if fetch else None

async def handle_vote(request):
    """Handle Top.gg vote webhook - accepts ANY request (test or real)"""
    print("\n" + "="*60)
    print("🎯 WEBHOOK REQUEST RECEIVED!")
    print(f"   Path: {request.path}")
    print(f"   Method: {request.method}")
    print("="*60)
    
    try:
        # Log all headers
        print("📋 Headers:")
        for key, value in request.headers.items():
            if key.lower() == 'authorization':
                print(f"   {key}: {value[:20]}..." if len(value) > 20 else f"   {key}: {value}")
            else:
                print(f"   {key}: {value}")
        
        # Get raw body
        raw_body = await request.text()
        print(f"\n📦 Raw Body: {raw_body}")
        
        # Check if we have authorization (some webhooks don't send it for test)
        auth = request.headers.get('Authorization', '')
        
        # If we have a secret configured, verify it
        if TOPGG_WEBHOOK_SECRET:
            if auth and auth != TOPGG_WEBHOOK_SECRET:
                print(f"❌ Authorization mismatch!")
                print(f"   Expected: {TOPGG_WEBHOOK_SECRET}")
                print(f"   Got: {auth}")
                # Still process it anyway for debugging
                print("⚠️ Processing anyway for debugging...")
        else:
            print("⚠️ No TOPGG_WEBHOOK_SECRET set - accepting all requests")
        
        # Parse JSON
        try:
            data = json.loads(raw_body) if raw_body else {}
            print(f"\n📊 Parsed Data: {json.dumps(data, indent=2)}")
        except Exception as e:
            print(f"❌ JSON Parse Error: {e}")
            # Try to get data from query params
            print("Trying query params...")
            data = dict(request.query)
            print(f"Query params: {data}")
        
        # Extract fields - be flexible with field names
        user_id = data.get('user') or data.get('userid') or data.get('userID')
        bot_id = data.get('bot') or data.get('botid') or data.get('botID')
        vote_type = data.get('type', 'upvote')
        is_weekend = data.get('isWeekend', False) or data.get('weekend', False)
        
        print(f"\n📝 Extracted Data:")
        print(f"   Bot ID: {bot_id}")
        print(f"   User ID: {user_id}")
        print(f"   Type: {vote_type}")
        print(f"   Weekend: {is_weekend}")
        
        if not user_id:
            print("❌ Missing user ID!")
            # Still return 200 to not break the webhook
            return web.Response(status=200, text="OK - No user ID")
        
        # Get bot instance
        bot = request.app.get('bot')
        if not bot:
            print("❌ Bot instance not found in app!")
            return web.Response(status=500, text="Bot not initialized")
        
        print(f"✅ Bot instance found: {bot.user.name if bot.user else 'Not ready'}")
        
        # Process vote
        print("\n🔄 Processing vote...")
        await process_vote(bot, user_id, is_weekend, vote_type)
        
        print("✅ Vote processed successfully!")
        print("="*60 + "\n")
        
        return web.Response(status=200, text="OK")
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        print("="*60 + "\n")
        # Still return 200 to not break webhook
        return web.Response(status=200, text="Error but OK")

async def process_vote(bot, user_id, is_weekend=False, vote_type='upvote'):
    """Process a vote and send notifications"""
    print(f"\n▶️ PROCESSING VOTE for user {user_id}")
    
    try:
        # Log the vote
        print("   📝 Logging vote to database...")
        db_query(
            "INSERT INTO vote_logs (user_id, is_weekend, vote_type) VALUES (?, ?, ?)",
            (str(user_id), 1 if is_weekend else 0, vote_type)
        )
        print("   ✅ Vote logged")
        
        # Update vote count
        print("   🔢 Updating vote count...")
        existing = db_query(
            "SELECT total_votes FROM vote_reminders WHERE user_id = ?",
            (str(user_id),),
            fetch=True
        )
        
        if existing:
            total_votes = existing[0][0] + 1
            db_query(
                "UPDATE vote_reminders SET last_vote = ?, total_votes = ? WHERE user_id = ?",
                (datetime.utcnow().isoformat(), total_votes, str(user_id))
            )
            print(f"   ✅ Updated count to {total_votes}")
        else:
            total_votes = 1
            db_query(
                "INSERT INTO vote_reminders (user_id, last_vote, total_votes) VALUES (?, ?, ?)",
                (str(user_id), datetime.utcnow().isoformat(), total_votes)
            )
            print(f"   ✅ Created new entry with count {total_votes}")
        
        # Get user
        print(f"   👤 Fetching user {user_id}...")
        user = None
        try:
            user = await bot.fetch_user(int(user_id))
            print(f"   ✅ User found: {user.name}")
        except Exception as e:
            print(f"   ⚠️ Could not fetch user: {e}")
        
        # Send to vote log channel
        print(f"   📢 Sending to vote log channel {VOTE_LOG_CHANNEL_ID}...")
        vote_channel = bot.get_channel(VOTE_LOG_CHANNEL_ID)
        
        if not vote_channel:
            print(f"   ❌ Vote channel not found!")
        else:
            print(f"   ✅ Vote channel found: #{vote_channel.name}")
            
            embed = discord.Embed(
                title="🗳️ New Vote Received!" if vote_type != 'test' else "🧪 Test Vote Received!",
                description=f"Thank you for voting!" if vote_type != 'test' else "Test vote from Top.gg webhook",
                color=discord.Color.gold() if vote_type != 'test' else discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            if user:
                embed.add_field(name="👤 Voter", value=f"{user.mention}\n`{user.name}` (`{user_id}`)", inline=True)
                embed.set_thumbnail(url=user.display_avatar.url)
            else:
                embed.add_field(name="👤 Voter", value=f"User ID: `{user_id}`", inline=True)
            
            embed.add_field(name="📊 Total Votes", value=str(total_votes), inline=True)
            embed.add_field(name="🎁 Weekend Bonus", value="Yes ✨" if is_weekend else "No", inline=True)
            embed.add_field(name="🔖 Vote Type", value=vote_type.capitalize(), inline=True)
            embed.set_footer(text="Vote on Top.gg")
            
            try:
                msg = await vote_channel.send(embed=embed)
                print(f"   ✅ Message sent to channel! Message ID: {msg.id}")
            except Exception as e:
                print(f"   ❌ Failed to send message: {e}")
                import traceback
                traceback.print_exc()
        
        # Send DM for ALL votes (including test)
        if user:
            print(f"   💌 Sending DM to {user.name}...")
            view = VoteReminderView(user_id)
            
            dm_embed = discord.Embed(
                title="🎉 Thank you for voting!" if vote_type != 'test' else "🧪 Test Vote Received!",
                description=f"Your vote has been recorded! You now have **{total_votes}** total vote(s).",
                color=discord.Color.green() if vote_type != 'test' else discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
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
            
            dm_embed.set_footer(text="Vote every 12 hours")
            
            try:
                await user.send(embed=dm_embed, view=view)
                print(f"   ✅ DM sent successfully")
            except discord.Forbidden:
                print(f"   ⚠️ DMs disabled for user")
            except Exception as e:
                print(f"   ❌ DM error: {e}")
        
        # Assign voter role
        print("   🎭 Attempting to assign voter role...")
        try:
            support_server_id = int(os.getenv('SUPPORT_SERVER_ID', '0'))
            print(f"   Support server ID: {support_server_id}")
            
            if support_server_id:
                guild = bot.get_guild(support_server_id)
                if guild:
                    print(f"   ✅ Guild found: {guild.name}")
                    member = guild.get_member(int(user_id))
                    if member:
                        print(f"   ✅ Member found: {member.name}")
                        role = guild.get_role(VOTER_ROLE_ID)
                        if role:
                            print(f"   ✅ Role found: {role.name}")
                            if role not in member.roles:
                                await member.add_roles(role, reason="Voted on Top.gg")
                                print(f"   ✅ Role assigned!")
                            else:
                                print(f"   ℹ️ User already has role")
                        else:
                            print(f"   ❌ Role {VOTER_ROLE_ID} not found")
                    else:
                        print(f"   ⚠️ User not in support server")
                else:
                    print(f"   ❌ Support server not found")
            else:
                print(f"   ⚠️ SUPPORT_SERVER_ID not set in .env")
        except Exception as e:
            print(f"   ⚠️ Role assignment error: {e}")
        
        print("✅ Vote processing complete!\n")
        
    except Exception as e:
        print(f"❌ Error in process_vote: {e}")
        import traceback
        traceback.print_exc()

class VoteReminderView(discord.ui.View):
    """View with reminder button"""
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
    
    @discord.ui.button(label="Remind me every 12 hours", style=discord.ButtonStyle.primary, emoji="🔔", custom_id="enable_vote_reminder")
    async def enable_reminder(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != str(self.user_id):
            await interaction.response.send_message("❌ This button is not for you!", ephemeral=True)
            return
        
        next_reminder = datetime.utcnow() + timedelta(hours=12)
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
        print(f"✅ Enabled vote reminders for user {self.user_id}")

async def vote_reminder_loop(bot):
    """Background task to send vote reminders"""
    await bot.wait_until_ready()
    print("🔔 Vote reminder loop started")
    
    while not bot.is_closed():
        try:
            now = datetime.utcnow()
            reminders = db_query(
                "SELECT user_id, total_votes FROM vote_reminders WHERE enabled = 1 AND next_reminder <= ?",
                (now.isoformat(),),
                fetch=True
            )
            
            if reminders:
                print(f"🔔 Processing {len(reminders)} reminder(s)")
            
            for user_id, total_votes in reminders:
                try:
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
                    
                    print(f"✅ Sent reminder to {user.name}")
                    
                except discord.Forbidden:
                    db_query("UPDATE vote_reminders SET enabled = 0 WHERE user_id = ?", (str(user_id),))
                    print(f"⚠️ Disabled reminders for {user_id} (DMs closed)")
                except Exception as e:
                    print(f"❌ Reminder error for {user_id}: {e}")
                
                await asyncio.sleep(1)
            
            await asyncio.sleep(300)
            
        except Exception as e:
            print(f"❌ Reminder loop error: {e}")
            await asyncio.sleep(300)

async def start_webhook_server(bot, port=8080):
    """Start the webhook server"""
    print("\n" + "="*60)
    print("🚀 STARTING WEBHOOK SERVER")
    print("="*60)
    
    try:
        app = web.Application()
        app['bot'] = bot
        
        print(f"✅ Bot instance stored in app")
        print(f"   Bot: {bot.user.name if bot.user else 'Not ready yet'}")
        
        # Add webhook handler for BOTH paths (test and production)
        app.router.add_post('/topgg/webhook', handle_vote)
        app.router.add_post('/webhook', handle_vote)  # Alternative path
        app.router.add_post('/topgg', handle_vote)    # Alternative path
        app.router.add_post('/', handle_vote)         # Root path
        print("✅ Routes added: POST /topgg/webhook, /webhook, /topgg, /")
        
        # Health check
        async def health_check(request):
            print(f"🏥 Health check from {request.remote}")
            return web.Response(text="Webhook server running!", status=200)
        
        app.router.add_get('/health', health_check)
        app.router.add_get('/topgg/webhook', health_check)
        app.router.add_get('/', health_check)
        print("✅ Routes added: GET /health, /topgg/webhook, /")
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        print(f"\n✅ SERVER RUNNING ON PORT {port}")
        print(f"📍 Webhook URL: https://tamisha-dilatometric-lengthwise.ngrok-free.dev/topgg/webhook")
        print(f"📍 Alternative: https://tamisha-dilatometric-lengthwise.ngrok-free.dev/webhook")
        print(f"🏥 Health check: https://tamisha-dilatometric-lengthwise.ngrok-free.dev/health")
        print(f"🔑 Auth secret: {TOPGG_WEBHOOK_SECRET if TOPGG_WEBHOOK_SECRET else '⚠️ NOT SET - ACCEPTING ALL'}")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"❌ FAILED TO START SERVER: {e}")
        import traceback
        traceback.print_exc()
