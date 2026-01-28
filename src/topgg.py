from aiohttp import web
import discord
import sqlite3
import asyncio
import os
from datetime import datetime, timedelta
import json

DB_FILE = "bot_data.db"
TOPGG_WEBHOOK_SECRET = os.getenv('TOPGG_WEBHOOK_SECRET')  # Add this to your .env
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

def db_query(query, params=(), fetch=False):
    """Execute database query"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
        return c.fetchall() if fetch else None

async def handle_vote(request):
    """
    Handle Top.gg vote webhook
    
    Expected payload from Top.gg:
    {
        "bot": "bot_id",
        "user": "user_id", 
        "type": "upvote" or "test",
        "isWeekend": true/false,
        "query": "?query_params"
    }
    """
    try:
        # Verify webhook authorization header
        auth = request.headers.get('Authorization', '')
        
        if not TOPGG_WEBHOOK_SECRET:
            print("⚠️ TOPGG_WEBHOOK_SECRET not set in environment variables!")
            return web.Response(status=500, text="Webhook secret not configured")
        
        if auth != TOPGG_WEBHOOK_SECRET:
            print(f"❌ Invalid Top.gg webhook authorization. Expected: {TOPGG_WEBHOOK_SECRET[:10]}..., Got: {auth[:10] if auth else 'None'}...")
            return web.Response(status=401, text="Unauthorized")
        
        # Parse JSON payload
        try:
            data = await request.json()
        except json.JSONDecodeError:
            print("❌ Invalid JSON payload from Top.gg")
            return web.Response(status=400, text="Invalid JSON")
        
        # Extract data from payload
        bot_id = data.get('bot')
        user_id = data.get('user')
        vote_type = data.get('type', 'upvote')
        is_weekend = data.get('isWeekend', False)
        query_params = data.get('query', '')
        
        # Validate required fields
        if not user_id:
            print("❌ Missing 'user' field in Top.gg webhook payload")
            return web.Response(status=400, text="Missing user ID")
        
        if not bot_id:
            print("❌ Missing 'bot' field in Top.gg webhook payload")
            return web.Response(status=400, text="Missing bot ID")
        
        print(f"✅ Vote webhook received:")
        print(f"   Bot ID: {bot_id}")
        print(f"   User ID: {user_id}")
        print(f"   Type: {vote_type}")
        print(f"   Weekend: {is_weekend}")
        print(f"   Query: {query_params}")
        
        # Get bot instance from app
        bot = request.app['bot']
        
        # Verify bot ID matches
        if str(bot_id) != str(bot.user.id):
            print(f"⚠️ Bot ID mismatch: Expected {bot.user.id}, got {bot_id}")
            # Still process it, might be testing
        
        # Handle test votes differently
        if vote_type == 'test':
            print("🧪 Test vote received - processing normally")
        
        # Process the vote
        await process_vote(bot, user_id, is_weekend, vote_type)
        
        return web.Response(status=200, text="OK")
        
    except Exception as e:
        print(f"❌ Error handling vote webhook: {e}")
        import traceback
        traceback.print_exc()
        return web.Response(status=500, text="Internal server error")

async def process_vote(bot, user_id, is_weekend=False, vote_type='upvote'):
    """Process a vote and send notifications"""
    try:
        # Log the vote
        db_query(
            "INSERT INTO vote_logs (user_id, is_weekend, vote_type) VALUES (?, ?, ?)",
            (str(user_id), 1 if is_weekend else 0, vote_type)
        )
        
        # Update or create vote reminder entry
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
        else:
            total_votes = 1
            db_query(
                "INSERT INTO vote_reminders (user_id, last_vote, total_votes) VALUES (?, ?, ?)",
                (str(user_id), datetime.utcnow().isoformat(), total_votes)
            )
        
        # Get user
        try:
            user = await bot.fetch_user(int(user_id))
        except Exception as e:
            print(f"⚠️ Could not fetch user {user_id}: {e}")
            user = None
        
        # Send vote log to channel
        vote_channel = bot.get_channel(VOTE_LOG_CHANNEL_ID)
        if vote_channel:
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
                await vote_channel.send(embed=embed)
            except Exception as e:
                print(f"❌ Could not send vote log to channel: {e}")
        
        # Don't send DMs for test votes
        if vote_type == 'test':
            print("🧪 Skipping DM for test vote")
            return
        
        # Send DM to voter with reminder button
        if user:
            view = VoteReminderView(user_id)
            
            dm_embed = discord.Embed(
                title="🎉 Thank you for voting!",
                description=f"Your vote has been recorded! You now have **{total_votes}** total vote(s).",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            dm_embed.add_field(
                name="🎁 Rewards",
                value="• Voter role assigned in support server\n• Helping the bot grow!\n• Your vote matters! ❤️" + ("\n• **Weekend Bonus Active!** 🎊" if is_weekend else ""),
                inline=False
            )
            
            dm_embed.add_field(
                name="⏰ Vote Again",
                value="You can vote again in 12 hours!\nClick the button below to enable vote reminders.",
                inline=False
            )
            
            dm_embed.set_footer(text="You can vote every 12 hours")
            
            try:
                await user.send(embed=dm_embed, view=view)
                print(f"✅ Sent DM to {user.name}")
            except discord.Forbidden:
                print(f"⚠️ Could not DM user {user.name} (DMs disabled)")
            except Exception as e:
                print(f"❌ Error sending DM to user: {e}")
        
        # Assign voter role in support server
        try:
            support_server_id = int(os.getenv('SUPPORT_SERVER_ID', '0'))
            if support_server_id:
                guild = bot.get_guild(support_server_id)
                if guild:
                    member = guild.get_member(int(user_id))
                    if member:
                        role = guild.get_role(VOTER_ROLE_ID)
                        if role and role not in member.roles:
                            await member.add_roles(role, reason="Voted on Top.gg")
                            print(f"✅ Added voter role to {member.name}")
                    else:
                        print(f"⚠️ User {user_id} is not in support server")
                else:
                    print(f"⚠️ Support server {support_server_id} not found")
            else:
                print("⚠️ SUPPORT_SERVER_ID not set in environment")
        except Exception as e:
            print(f"⚠️ Could not assign voter role: {e}")
        
    except Exception as e:
        print(f"❌ Error processing vote: {e}")
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
        
        # Enable reminders
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
            
            # Find users who need reminders
            reminders = db_query(
                "SELECT user_id, total_votes FROM vote_reminders WHERE enabled = 1 AND next_reminder <= ?",
                (now.isoformat(),),
                fetch=True
            )
            
            if reminders:
                print(f"🔔 Processing {len(reminders)} vote reminder(s)")
            
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
                        value=f"**Total Votes:** {total_votes}\n**Next Vote Available:** Now!",
                        inline=False
                    )
                    
                    embed.add_field(
                        name="🗳️ Vote Now",
                        value="Click the button below to vote on Top.gg!",
                        inline=False
                    )
                    
                    embed.set_footer(text="You can disable reminders anytime with /votereminder disable")
                    
                    # Create view with vote button
                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(
                        label="Vote on Top.gg",
                        url=f"https://top.gg/bot/{bot.user.id}/vote",
                        style=discord.ButtonStyle.link,
                        emoji="🗳️"
                    ))
                    
                    await user.send(embed=embed, view=view)
                    
                    # Update next reminder time (12 hours from now)
                    next_reminder = now + timedelta(hours=12)
                    db_query(
                        "UPDATE vote_reminders SET next_reminder = ? WHERE user_id = ?",
                        (next_reminder.isoformat(), str(user_id))
                    )
                    
                    print(f"✅ Sent vote reminder to {user.name}")
                    
                except discord.Forbidden:
                    print(f"⚠️ Could not send reminder to user {user_id} (DMs disabled)")
                    # Disable reminders for this user
                    db_query("UPDATE vote_reminders SET enabled = 0 WHERE user_id = ?", (str(user_id),))
                except Exception as e:
                    print(f"❌ Error sending reminder to user {user_id}: {e}")
                
                # Small delay between reminders
                await asyncio.sleep(1)
            
            # Check every 5 minutes
            await asyncio.sleep(300)
            
        except Exception as e:
            print(f"❌ Error in vote reminder loop: {e}")
            import traceback
            traceback.print_exc()
            await asyncio.sleep(300)

async def start_webhook_server(bot, port=8080):
    """Start the webhook server for Top.gg"""
    try:
        app = web.Application()
        app['bot'] = bot
        
        # Add webhook route
        app.router.add_post('/topgg/webhook', handle_vote)
        
        # Add health check route
        async def health_check(request):
            return web.Response(text="Top.gg webhook server is running!", status=200)
        
        app.router.add_get('/health', health_check)
        app.router.add_get('/', health_check)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        print(f"✅ Top.gg webhook server started on port {port}")
        print(f"📍 Webhook URL: https://tamisha-dilatometric-lengthwise.ngrok-free.dev/topgg/webhook")
        print(f"🏥 Health check: https://tamisha-dilatometric-lengthwise.ngrok-free.dev/health")
        print(f"🔑 Remember to set this URL in Top.gg bot settings!")
        
    except Exception as e:
        print(f"❌ Failed to start webhook server: {e}")
        import traceback
        traceback.print_exc()
