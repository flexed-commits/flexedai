# Feel free to use my code; Just make sure to edit the hardcoded ids.

import discord
import hashlib, string
from discord.ext import commands, tasks
import os, time, datetime, json, sqlite3, asyncio
from groq import AsyncGroq 
from collections import deque
import random
from patreon import PatreonPromoter
from dotenv import load_dotenv
load_dotenv()

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MODEL_NAME = os.getenv('MODEL_NAME', "meta-llama/llama-4-maverick-17b-128e-instruct")
OWNER_ID = int(os.getenv('OWNER_ID'))
OWNER_NAME = os.getenv('OWNER_NAME')
DB_FILE = "bot_data.db"
JSON_FILE = "bot_data.json"
INTERACTION_JSON = "interaction_logs.json"
BOT_NAME= os.getenv('BOT_NAME')
ENCODING_FILE="encoding_map.json"
# Logging Channels
LOG_CHANNELS = {
    'server_join_leave': int(os.getenv('LOG_CHANNEL_SERVER_JOIN_LEAVE')),
    'strikes': int(os.getenv('LOG_CHANNEL_STRIKES')),
    'blacklist': int(os.getenv('LOG_CHANNEL_BLACKLIST')),
    'banned_words': int(os.getenv('LOG_CHANNEL_BANNED_WORDS')),
    'admin_logs': int(os.getenv('LOG_CHANNEL_ADMIN_LOGS')),
    'reports': int(os.getenv('LOG_CHANNEL_REPORTS'))
}
# Discord message limits
MAX_MESSAGE_LENGTH = 2000
MAX_INPUT_TOKENS = 8000

# Available languages constant
AVAILABLE_LANGUAGES = [
    "English", "Hindi", "Hinglish", "Spanish", "French", 
    "German", "Portuguese", "Italian", "Japanese", "Korean",
    "Chinese", "Russian", "Arabic", "Turkish", "Dutch", "Marathi"
]

# Owner information for bot knowledge
OWNER_INFO = {
    'name': os.getenv('OWNER_NAME'),
    'id': int(os.getenv('OWNER_ID')),
    'bio': os.getenv('OWNER_BIO', f'Creator and core maintainer of {BOT_NAME} Discord Bot')
}
# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, 
        strikes INTEGER DEFAULT 0, 
        blacklisted INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS banned_words (
        word TEXT PRIMARY KEY
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        id TEXT PRIMARY KEY, 
        prefix TEXT DEFAULT "/", 
        language TEXT DEFAULT "English", 
        mode TEXT DEFAULT "stop"
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        log TEXT, 
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS interaction_logs (
        timestamp REAL, 
        guild_id TEXT, 
        channel_id TEXT, 
        user_name TEXT, 
        user_id TEXT, 
        prompt TEXT, 
        response TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS bot_admins (
        user_id TEXT PRIMARY KEY,
        added_by TEXT,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS word_filter_bypass (
        user_id TEXT PRIMARY KEY,
        added_by TEXT,
        reason TEXT,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS reports (
        report_id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id TEXT,
        reporter_name TEXT,
        reported_user_id TEXT,
        reported_user_name TEXT,
        guild_id TEXT,
        guild_name TEXT,
        reason TEXT,
        proof TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending'
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS blacklisted_guilds (
        guild_id TEXT PRIMARY KEY,
        guild_name TEXT,
        blacklisted_by TEXT,
        reason TEXT,
        blacklisted_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # FIXED: This was likely the cause of your error
    c.execute('''CREATE TABLE IF NOT EXISTS updates_channels (
        guild_id TEXT PRIMARY KEY,
        channel_id TEXT NOT NULL,
        setup_by TEXT,
        setup_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
 
    conn.commit()
    conn.close()



def migrate_json_to_db():
    if not os.path.exists(JSON_FILE):
        print("⚠️ No bot_data.json found. Skipping migration.")
        return

    with open(JSON_FILE, 'r') as f:
        data = json.load(f)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    for user_id in data.get('blacklist', []):
        c.execute("INSERT OR IGNORE INTO users (user_id, blacklisted) VALUES (?, 1)", (str(user_id),))

    for word in data.get('banned_words', []):
        c.execute("INSERT OR IGNORE INTO banned_words (word) VALUES (?)", (word.lower(),))

    for user_id, strikes in data.get('violations', {}).items():
        clean_id = user_id.replace('<@', '').replace('>', '')
        blacklisted = 1 if strikes >= 3 else 0
        c.execute("INSERT OR REPLACE INTO users (user_id, strikes, blacklisted) VALUES (?, ?, ?)", (clean_id, strikes, blacklisted))

    for channel_id, lang in data.get('languages', {}).items():
        c.execute("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", (str(channel_id), lang))

    for guild_id, prefix in data.get('prefixes', {}).items():
        c.execute("INSERT OR REPLACE INTO settings (id, prefix) VALUES (?, ?)", (str(guild_id), prefix))

    for channel_id, mode in data.get('response_mode', {}).items():
        c.execute("INSERT OR REPLACE INTO settings (id, mode) VALUES (?, ?)", (str(channel_id), mode))

    for log in data.get('admin_logs', []):
        c.execute("INSERT INTO admin_logs (log) VALUES (?)", (log,))

    conn.commit()
    conn.close()

    os.rename(JSON_FILE, f"{JSON_FILE}.backup")
    print(f"✅ Migrated bot_data.json → {DB_FILE}")

def migrate_interaction_logs():
    if not os.path.exists(INTERACTION_JSON):
        print("⚠️ No interaction_logs.json found. Skipping migration.")
        return

    with open(INTERACTION_JSON, 'r') as f:
        logs = json.load(f)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    for log in logs:
        c.execute("""INSERT INTO interaction_logs (timestamp, guild_id, channel_id, user_name, user_id, prompt, response) VALUES (?, ?, ?, ?, ?, ?, ?)""", (log['timestamp'], str(log.get('guild_id', 'DM')), str(log['channel_id']), log['user_name'], str(log['user_id']), log['prompt'], log['response']))

    conn.commit()
    conn.close()

    os.rename(INTERACTION_JSON, f"{INTERACTION_JSON}.backup")
    print(f"✅ Migrated interaction_logs.json → {DB_FILE}")

def db_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
        return c.fetchall() if fetch else None

def is_bot_admin(user_id):
    """Check if user is owner or bot admin"""
    if user_id == OWNER_ID:
        return True
    res = db_query("SELECT user_id FROM bot_admins WHERE user_id = ?", (str(user_id),), fetch=True)
    return bool(res)

def get_channel_language(channel_id):
    """Get the configured language for a channel"""
    res = db_query("SELECT language FROM settings WHERE id = ?", (str(channel_id),), fetch=True)
    return res[0][0] if res and res[0][0] else "English"

def is_bypass_user(user_id):
    """Check if user has word filter bypass"""
    if user_id == OWNER_ID:
        return True
    res = db_query("SELECT user_id FROM word_filter_bypass WHERE user_id = ?", (str(user_id),), fetch=True)
    return bool(res)

def is_guild_blacklisted(guild_id):
    """Check if a guild is blacklisted"""
    res = db_query("SELECT guild_id FROM blacklisted_guilds WHERE guild_id = ?", (str(guild_id),), fetch=True)
    return bool(res)

def has_updates_channel(guild_id):
    """Check if a guild has setup an updates channel"""
    res = db_query("SELECT channel_id FROM updates_channels WHERE guild_id = ?", (str(guild_id),), fetch=True)
    return bool(res)

def get_updates_channel(guild_id):
    """Get the updates channel ID for a guild"""
    res = db_query("SELECT channel_id FROM updates_channels WHERE guild_id = ?", (str(guild_id),), fetch=True)
    return res[0][0] if res else None

def export_db_to_json():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    data = {}

    c.execute("SELECT * FROM users")
    users = c.fetchall()
    data['users'] = [{"user_id": u[0], "strikes": u[1], "blacklisted": bool(u[2])} for u in users]

    c.execute("SELECT word FROM banned_words")
    data['banned_words'] = [w[0] for w in c.fetchall()]

    c.execute("SELECT * FROM settings")
    settings = c.fetchall()
    data['settings'] = [{"id": s[0], "prefix": s[1], "language": s[2], "mode": s[3]} for s in settings]

    c.execute("SELECT * FROM admin_logs ORDER BY timestamp DESC LIMIT 100")
    logs = c.fetchall()
    data['admin_logs'] = [{"log": l[0], "timestamp": l[1]} for l in logs]

    c.execute("SELECT * FROM bot_admins")
    admins = c.fetchall()
    data['bot_admins'] = [{"user_id": a[0], "added_by": a[1], "added_at": a[2]} for a in admins]

    c.execute("SELECT * FROM word_filter_bypass")
    bypass_users = c.fetchall()
    data['word_filter_bypass'] = [{"user_id": b[0], "added_by": b[1], "reason": b[2], "added_at": b[3]} for b in bypass_users]

    cutoff = time.time() - 86400
    c.execute("SELECT * FROM interaction_logs WHERE timestamp > ? ORDER BY timestamp DESC", (cutoff,))
    interactions = c.fetchall()
    data['interaction_logs'] = [{"timestamp": i[0], "guild_id": i[1], "channel_id": i[2], "user_name": i[3], "user_id": i[4], "prompt": i[5], "response": i[6]} for i in interactions]

    conn.close()
    return data

# --- UTILITY FUNCTIONS ---
async def log_to_channel(bot, channel_key, embed):
    """Send log embed to specified channel"""
    try:
        channel_id = LOG_CHANNELS.get(channel_key)
        if not channel_id:
            print(f"⚠️ No log channel configured for: {channel_key}")
            return False
        
        channel = bot.get_channel(channel_id)
        if not channel:
            print(f"❌ Could not find log channel: {channel_id}")
            return False
        
        await channel.send(embed=embed)
        return True
    except Exception as e:
        print(f"❌ Failed to log to {channel_key}: {e}")
        return False

def truncate_message(content, max_length=MAX_INPUT_TOKENS):
    """Truncate message if it's too long, keeping the most recent content"""
    if len(content) <= max_length:
        return content, False
    
    truncated = content[-max_length:]
    return f"[Message truncated due to length]\n{truncated}", True

async def split_and_send(message, content):
    """Split long responses and send them in multiple messages"""
    if len(content) <= MAX_MESSAGE_LENGTH:
        try:
            await message.reply(content)
        except discord.errors.HTTPException:
            # Message was deleted, send to channel instead
            await message.channel.send(content)
        return
    
    paragraphs = content.split('\n\n')
    current_chunk = ""
    chunks = []
    
    for para in paragraphs:
        if len(para) > MAX_MESSAGE_LENGTH:
            sentences = para.split('. ')
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 2 > MAX_MESSAGE_LENGTH:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = sentence + ". "
                else:
                    current_chunk += sentence + ". "
        else:
            if len(current_chunk) + len(para) + 2 > MAX_MESSAGE_LENGTH:
                chunks.append(current_chunk)
                current_chunk = para + "\n\n"
            else:
                current_chunk += para + "\n\n"
    
    if current_chunk:
        chunks.append(current_chunk)
    
    try:
        await message.reply(chunks[0])
    except discord.errors.HTTPException:
        # Message was deleted, send to channel instead
        await message.channel.send(chunks[0])
    
    for chunk in chunks[1:]:
        await message.channel.send(chunk)
        await asyncio.sleep(0.5)
async def send_user_dm(user_id, message):
    """Send DM to user, handle errors silently"""
    try:
        user = await bot.fetch_user(int(user_id))
        await user.send(message)
        return True
    except:
        return False

init_db()
migrate_json_to_db()
migrate_interaction_logs()
async def get_prefix(bot, message):
    guild_or_user_id = str(message.guild.id if message.guild else message.author.id)
    res = db_query("SELECT prefix FROM settings WHERE id = ?", (guild_or_user_id,), fetch=True)
    return res[0][0] if res and res[0][0] else "/"

class AIBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=get_prefix, intents=discord.Intents.all(), help_command=None)
        self.groq_client = AsyncGroq(api_key=GROQ_API_KEY)
        self.memory = {}
        self.reaction_chance = 0.10  # 10% chance to add reactions; 10/100 = 10% i.e 0.10
        self.last_response_time = 0
        
    async def setup_hook(self):
        self.daily_backup.start()
        print(f"✅ {self.user} Online | All Commands Locked & Loaded")
        print(f"🔄 Daily backup task started")

# Initialize Patreon promoter (OUTSIDE the class, at module level)
patreon_promoter = PatreonPromoter(
    patreon_url="https://patreon.com/flexedAI/membership",
    min_messages=15,
    max_messages=20
)

bot = AIBot()

# --- EVENT HANDLERS FOR LOGGING ---
@bot.event
async def on_guild_join(guild):
    """Log when bot joins a server and auto-leave if blacklisted"""
    
    # Check if guild is blacklisted
    if is_guild_blacklisted(guild.id):
        blacklist_info = db_query(
            "SELECT reason, blacklisted_by FROM blacklisted_guilds WHERE guild_id = ?", 
            (str(guild.id),), 
            fetch=True
        )
        
        if blacklist_info:
            reason, blacklisted_by = blacklist_info[0]
            
            # Try to notify owner
            try:
                await guild.owner.send(
                    f"""🚫 **{BOT_NAME} Bot - Blacklisted Server**

Hello {guild.owner.name},

Your server **{guild.name}** is blacklisted from using {BOT_NAME} Bot.

**Reason:** {reason}

The bot has automatically left your server. You cannot re-add this bot while blacklisted.

**Appeal:** Contact <@{OWNER_ID}>
**Join the Support Server:** {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}

*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""
                )
            except:
                pass
            
            # Log the attempted join
            log_embed = discord.Embed(
                title="🚫 Blacklisted Guild Attempted Join",
                description=f"Bot was added to a blacklisted server and auto-left.",
                color=discord.Color.dark_red(),
                timestamp=datetime.datetime.utcnow()
            )
            log_embed.add_field(name="🏰 Server Name", value=guild.name, inline=True)
            log_embed.add_field(name="🆔 Server ID", value=f"`{guild.id}`", inline=True)
            log_embed.add_field(name="👑 Server Owner", value=f"{guild.owner.mention} (`{guild.owner.id}`)", inline=False)
            log_embed.add_field(name="📝 Blacklist Reason", value=reason, inline=False)
            log_embed.add_field(name="⚖️ Originally Blacklisted By", value=f"<@{blacklisted_by}>", inline=True)
            
            await log_to_channel(bot, 'blacklist', log_embed)
            
            # Leave the guild
            await guild.leave()
            return
    
    # Original join logic continues below...
    embed = discord.Embed(
        title="🟢 Bot Joined Server",
        description=f"{BOT_NAME} has been added to a new server!",
        color=discord.Color.green(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(name="📋 Server Name", value=guild.name, inline=True)
    embed.add_field(name="🆔 Server ID", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="👑 Server Owner", value=f"{guild.owner.mention} (`{guild.owner.id}`)", inline=False)
    embed.add_field(name="👥 Member Count", value=guild.member_count, inline=True)
    embed.add_field(name="📅 Server Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="📊 Total Servers", value=len(bot.guilds), inline=True)
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.set_footer(text=f"Server Owner ID: {guild.owner.id}")
    
    await log_to_channel(bot, 'server_join_leave', embed)
    
    # Log to database
    db_query("INSERT INTO admin_logs (log) VALUES (?)", 
             (f"Bot joined server: {guild.name} (ID: {guild.id}, Owner: {guild.owner.name} - {guild.owner.id})",))
    
    # Try to send welcome message to server owner
    try:
        welcome_msg = f"""👋 **Hello {guild.owner.name}!**

Thank you for adding **{BOT_NAME} Bot** to **{guild.name}**!

🚀 **Quick Start Guide:**
• Use `/help` to see all available commands
• Use `/start` in a channel to enable automatic responses
• Use `/stop` to make the bot respond only when mentioned
• Use `/lang` to set the bot's language for a channel
• Server administrators can configure bot settings

📚 **Key Features:**
• AI-powered conversations with context memory
• Multi-language support (15+ languages)
• Moderation tools (strikes, blacklist, word filter)
• Customizable command prefix
• Channel-specific response modes

⏱️ **Response Cooldown:**
To maintain optimal performance with our AI API, the bot has a 0.6-second cooldown between responses. This means:
• The bot responds immediately to any user's message
• If another user sends a message within 0.6 seconds of the last response, the bot remains silent
• This prevents API rate limiting and ensures stable service for everyone

💡 **Need Help?**
Contact the bot owner: <@{OWNER_ID}>
Join the Support Server: {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}

Enjoy using {BOT_NAME}! 🎉
"""
        await guild.owner.send(welcome_msg)
    except:
        pass  # Owner has DMs disabled
    
    # Try to find a general/system channel to send welcome message
    try:
        # Try to find the system channel or first text channel
        target_channel = guild.system_channel
        
        if not target_channel:
            # Find first text channel bot can send messages to
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    target_channel = channel
                    break
        
        if target_channel:
            welcome_embed = discord.Embed(
                title=f"👋 Thanks for adding {BOT_NAME}!",
                description="**⚠️ IMPORTANT: Setup Required**\n\nBefore you can use this bot, you need to set up an updates channel!",
                color=discord.Color.orange()
            )
            
            welcome_embed.add_field(
                name="🔧 Required Setup",
                value=f"Use `/setupupdates` to set a channel for important bot announcements and updates.\n\n**Without this setup, the bot will not function!**",
                inline=False
            )
            
            welcome_embed.add_field(
                name="🚀 Getting Started",
                value="• Use `/setupupdates #channel` to set updates channel\n• Use `/help` to see all commands\n• Use `/start` to enable auto-responses in channels\n• Use `/lang` to set your preferred language",
                inline=False
            )
            
            welcome_embed.add_field(
                name="⏱️ Response Cooldown (Important!)",
                value="**The bot has a 0.6-second cooldown between responses.**\n\n"
                      "**How it works:**\n"
                      "• Bot responds immediately to any message\n"
                      "• If another user messages within 0.6s of last response, bot stays silent\n"
                      "• After 0.6s, bot will respond to new messages normally\n\n"
                      "**Why?** We use a cost-effective API with rate limits. This cooldown ensures stable, reliable service for everyone! 🎯",
                inline=False
            )
            
            welcome_embed.add_field(
                name="💡 Need Help?",
                value=f"Contact: <@{OWNER_ID}>\n[Join Support Server]({os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')})",
                inline=False
            )
            
            welcome_embed.set_footer(text="⚠️ Setup updates channel first using /setupupdates")
            
            await target_channel.send(embed=welcome_embed)
    except Exception as e:
        print(f"⚠️ Could not send welcome message to server {guild.name}: {e}")


@bot.event
async def on_guild_remove(guild):
    """Log when bot leaves a server"""
    embed = discord.Embed(
        title="🔴 Bot Left Server",
        description=f"{BOT_NAME} has been removed from a server.",
        color=discord.Color.red(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(name="📋 Server Name", value=guild.name, inline=True)
    embed.add_field(name="🆔 Server ID", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="👑 Server Owner", value=f"{guild.owner.mention} (`{guild.owner.id}`)", inline=False)
    embed.add_field(name="👥 Member Count", value=guild.member_count, inline=True)
    embed.add_field(name="📊 Remaining Servers", value=len(bot.guilds), inline=True)
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.set_footer(text=f"Server Owner ID: {guild.owner.id}")
    
    await log_to_channel(bot, 'server_join_leave', embed)
    
    # Log to database
    db_query("INSERT INTO admin_logs (log) VALUES (?)", 
             (f"Bot left server: {guild.name} (ID: {guild.id}, Owner: {guild.owner.name} - {guild.owner.id})",))

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user.name}")
    print(f"📊 Connected to {len(bot.guilds)} servers")
    print(f"👤 Owner: {OWNER_INFO['name']} (ID: {OWNER_INFO['id']})")

@tasks.loop(hours=24)
async def daily_backup_task():
    try:
        owner = await bot.fetch_user(OWNER_ID)
        db_data = export_db_to_json()
        timestamp = int(time.time())
        filename = f"backup_{timestamp}.json"

        with open(filename, "w") as f:
            json.dump(db_data, f, indent=2)

        embed = discord.Embed(
            title="📦 24-Hour Database Backup", 
            description=f"**Timestamp:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
            color=discord.Color.green()
        )
        embed.add_field(name="Users", value=len(db_data['users']), inline=True)
        embed.add_field(name="Banned Words", value=len(db_data['banned_words']), inline=True)
        embed.add_field(name="Interactions (24h)", value=len(db_data['interaction_logs']), inline=True)

        await owner.send(embed=embed, file=discord.File(filename))
        os.remove(filename)
        print(f"✅ Backup sent to owner at {datetime.datetime.now()}")
    except Exception as e:
        print(f"❌ Backup failed: {e}")

@daily_backup_task.before_loop
async def before_backup():
    await bot.wait_until_ready()

bot.daily_backup = daily_backup_task

# Language Select View (Dropdown for slash command)
class LanguageSelectView(discord.ui.View):
    def __init__(self, channel_id, author_id):
        super().__init__(timeout=60)
        self.channel_id = channel_id
        self.author_id = author_id
        self.add_item(LanguageSelect(channel_id, author_id))

class LanguageSelect(discord.ui.Select):
    def __init__(self, channel_id, author_id):
        self.channel_id = channel_id
        self.author_id = author_id
        
        options = [
            discord.SelectOption(label=lang, value=lang, emoji="🌐")
            for lang in AVAILABLE_LANGUAGES
        ]
        
        super().__init__(
            placeholder="Choose a language...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Only the command user can select a language.", ephemeral=True)
            return
        
        selected_lang = self.values[0]
        db_query("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", (str(self.channel_id), selected_lang))
        
        await interaction.response.send_message(f"🌐 Language set to **{selected_lang}** for this channel.", ephemeral=True)
        self.view.stop()

# Language Button View (for prefix command)
class LanguageButtonView(discord.ui.View):
    def __init__(self, channel_id, author_id, owner_id):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.author_id = author_id
        self.owner_id = owner_id
        self.message = None
        
        for i, lang in enumerate(AVAILABLE_LANGUAGES):
            button = discord.ui.Button(
                label=lang,
                style=discord.ButtonStyle.primary,
                custom_id=f"lang_{lang}",
                row=i // 5
            )
            button.callback = self.create_callback(lang)
            self.add_item(button)
    
    def create_callback(self, lang):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                if not interaction.guild or not interaction.user.guild_permissions.administrator:
                    await interaction.response.send_message("❌ Only administrators and the bot owner can change language settings.", ephemeral=True)
                    return
            
            db_query("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", (str(self.channel_id), lang))
            
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(
                content=f"🌐 Language set to **{lang}** by {interaction.user.mention}. {BOT_NAME} will now respond in {lang}",
                view=self
            )
            
            await interaction.followup.send(f"✅ Language successfully changed to **{lang}** for this channel.", ephemeral=True)
            
            self.stop()
        
        return callback

# Permission checker decorator
def owner_or_bot_admin():
    async def predicate(ctx):
        if ctx.author.id == OWNER_ID:
            return True
        if is_bot_admin(ctx.author.id):
            return True
        await ctx.send("❌ **Permission Denied**\n**Required:** Bot Owner or Bot Admin privileges\n\nThis command is restricted to authorized personnel only.")
        return False
    return commands.check(predicate)
# Moderation Commands with Enhanced Logging

@bot.hybrid_command(name="sync", description="Owner/Admin: Sync slash commands.")
@owner_or_bot_admin()
async def sync(ctx):
    await bot.tree.sync()
    await ctx.send("🚀 **Slash commands synced globally!**\nAll commands are now up to date across Discord.")

@bot.hybrid_command(name="allinteractions", description="Owner/Admin: Export ALL interaction logs.")
@owner_or_bot_admin()
@commands.dm_only()
async def all_interactions(ctx):
    rows = db_query("SELECT * FROM interaction_logs ORDER BY timestamp DESC", fetch=True)

    if not rows:
        await ctx.send("❌ **No interaction logs found.**\nThe database is currently empty.")
        return

    data = [{"timestamp": r[0], "guild_id": r[1], "channel_id": r[2], "user_name": r[3], "user_id": r[4], "prompt": r[5], "response": r[6]} for r in rows]
    fname = f"all_logs_{int(time.time())}.json"

    with open(fname, "w") as f: 
        json.dump(data, f, indent=2)

    await ctx.send(f"📊 **Export Complete**\n**Total Interactions:** {len(data)}\n\nAll interaction logs have been exported successfully.", file=discord.File(fname))
    os.remove(fname)

@bot.hybrid_command(name="messages", description="Owner/Admin: Export interaction logs (last 24h).")
@owner_or_bot_admin()
@commands.dm_only()
async def messages(ctx):
    cutoff = time.time() - 86400
    rows = db_query("SELECT * FROM interaction_logs WHERE timestamp > ? ORDER BY timestamp DESC", (cutoff,), fetch=True)
    
    if not rows:
        await ctx.send("❌ **No interactions in the last 24 hours.**")
        return
    
    data = [{"timestamp": r[0], "guild_id": r[1], "channel_id": r[2], "user_name": r[3], "user_id": r[4], "prompt": r[5], "response": r[6]} for r in rows]
    fname = f"logs_{int(time.time())}.json"

    with open(fname, "w") as f: 
        json.dump(data, f, indent=2)

    await ctx.send(f"📊 **24-Hour Export Complete**\n**Interactions:** {len(data)}", file=discord.File(fname))
    os.remove(fname)

@bot.hybrid_command(name="clearlogs", description="Owner/Admin: Wipe interaction logs.")
@owner_or_bot_admin()
@commands.dm_only()
async def clear_logs(ctx):
    count = db_query("SELECT COUNT(*) FROM interaction_logs", fetch=True)[0][0]
    db_query("DELETE FROM interaction_logs")
    await ctx.send(f"🗑️ **Interaction logs cleared!**\n**Removed:** {count} interaction records")

@bot.command(name="server-list", description="Owner/Admin: Export server list.")
@owner_or_bot_admin()
@commands.dm_only()
async def server_list(ctx):
    guilds = [{"id": str(g.id), "name": g.name, "member_count": g.member_count, "owner_id": str(g.owner.id), "owner_name": g.owner.name} for g in bot.guilds]
    fname = f"servers_{int(time.time())}.json"

    with open(fname, "w") as f:
        json.dump(guilds, f, indent=2)

    await ctx.send(f"📊 **Server List Export**\n**Total Servers:** {len(guilds)}", file=discord.File(fname))
    os.remove(fname)

@bot.command(name="data", description="Owner/Admin: Complete bot configuration data.")
@owner_or_bot_admin()
@commands.dm_only()
async def bot_data(ctx):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    data = {
        "export_timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "bot_info": {
            "total_servers": len(bot.guilds),
            "total_users_tracked": 0,
            "total_interactions_logged": 0
        },
        "users": {
            "blacklisted": [],
            "strikes": [],
            "all_tracked": []
        },
        "banned_words": [],
        "bot_admins": [],
        "word_filter_bypass": [],
        "blacklisted_guilds": [],
        "server_configurations": {},
        "channel_configurations": {},
        "statistics": {
            "total_strikes_issued": 0,
            "total_blacklists": 0,
            "total_banned_words": 0,
            "total_blacklisted_guilds": 0,
            "channels_in_start_mode": 0,
            "channels_in_stop_mode": 0
        }
    }

    # Users data
    c.execute("SELECT user_id, strikes, blacklisted FROM users")
    users = c.fetchall()
    data['bot_info']['total_users_tracked'] = len(users)

    for user in users:
        user_data = {
            "user_id": user[0],
            "strikes": user[1],
            "blacklisted": bool(user[2])
        }
        data['users']['all_tracked'].append(user_data)

        if user[2] == 1:
            data['users']['blacklisted'].append(user[0])
            data['statistics']['total_blacklists'] += 1

        if user[1] > 0:
            data['users']['strikes'].append({
                "user_id": user[0],
                "strike_count": user[1]
            })
            data['statistics']['total_strikes_issued'] += user[1]

    # Banned words
    c.execute("SELECT word FROM banned_words")
    banned = c.fetchall()
    data['banned_words'] = [w[0] for w in banned]
    data['statistics']['total_banned_words'] = len(data['banned_words'])

    # Bot admins
    c.execute("SELECT user_id, added_by, added_at FROM bot_admins")
    admins = c.fetchall()
    data['bot_admins'] = [{"user_id": a[0], "added_by": a[1], "added_at": a[2]} for a in admins]

    # Word filter bypass users
    c.execute("SELECT user_id, added_by, reason, added_at FROM word_filter_bypass")
    bypass_users = c.fetchall()
    data['word_filter_bypass'] = [
        {
            "user_id": b[0],
            "added_by": b[1],
            "reason": b[2],
            "added_at": b[3]
        } for b in bypass_users
    ]

    # Blacklisted guilds
    c.execute("SELECT guild_id, guild_name, blacklisted_by, reason, blacklisted_at FROM blacklisted_guilds")
    guild_blacklist = c.fetchall()
    data['blacklisted_guilds'] = [
        {
            "guild_id": g[0],
            "guild_name": g[1],
            "blacklisted_by": g[2],
            "reason": g[3],
            "blacklisted_at": g[4]
        } for g in guild_blacklist
    ]
    data['statistics']['total_blacklisted_guilds'] = len(data['blacklisted_guilds'])
    # Updates channels configuration
    c.execute("SELECT guild_id, channel_id, setup_by, setup_at FROM updates_channels")
    updates_channels_data = c.fetchall()
    data['updates_channels'] = [
        {
            "guild_id": u[0],
            "guild_name": bot.get_guild(int(u[0])).name if bot.get_guild(int(u[0])) else "Unknown",
            "channel_id": u[1],
            "setup_by": u[2],
            "setup_at": u[3]
        } for u in updates_channels_data
    ]
    data['statistics']['total_configured_updates_channels'] = len(data['updates_channels'])

    # Server and channel configurations
    c.execute("SELECT id, prefix, language, mode FROM settings")
    settings = c.fetchall()

    for setting in settings:
        setting_id = setting[0]
        prefix = setting[1] if setting[1] else "!"
        language = setting[2] if setting[2] else "English"
        mode = setting[3] if setting[3] else "stop"

        try:
            guild = bot.get_guild(int(setting_id))
            if guild:
                data['server_configurations'][guild.name] = {
                    "guild_id": setting_id,
                    "prefix": prefix,
                    "member_count": guild.member_count
                }
            else:
                channel = bot.get_channel(int(setting_id))
                if channel:
                    guild_name = channel.guild.name if channel.guild else "DM"
                    data['channel_configurations'][f"{guild_name} > {channel.name}"] = {
                        "channel_id": setting_id,
                        "guild_id": str(channel.guild.id) if channel.guild else "DM",
                        "language": language,
                        "mode": mode
                    }

                    if mode == "start":
                        data['statistics']['channels_in_start_mode'] += 1
                    else:
                        data['statistics']['channels_in_stop_mode'] += 1
                else:
                    data['channel_configurations'][f"Unknown Channel {setting_id}"] = {
                        "channel_id": setting_id,
                        "language": language,
                        "mode": mode,
                        "note": "Channel/Guild not found - may have been deleted"
                    }
        except:
            pass

    # Interaction logs count
    c.execute("SELECT COUNT(*) FROM interaction_logs")
    interaction_count = c.fetchone()[0]
    data['bot_info']['total_interactions_logged'] = interaction_count

    # Recent admin logs
    c.execute("SELECT log, timestamp FROM admin_logs ORDER BY timestamp DESC LIMIT 100")
    logs = c.fetchall()
    data['admin_logs_recent'] = [{"log": l[0], "timestamp": l[1]} for l in logs]

    # Recent reports
    c.execute("SELECT report_id, reporter_id, reported_user_id, reason, status, timestamp FROM reports ORDER BY timestamp DESC LIMIT 50")
    reports = c.fetchall()
    data['recent_reports'] = [
        {
            "report_id": r[0],
            "reporter_id": r[1],
            "reported_user_id": r[2],
            "reason": r[3],
            "status": r[4],
            "timestamp": r[5]
        } for r in reports
    ]

    conn.close()

    timestamp = int(time.time())
    filename = f"bot_data_complete_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

    embed = discord.Embed(
        title="🗄️ Complete Bot Configuration Data",
        description=f"**Export Time:** {data['export_timestamp']}",
        color=discord.Color.purple()
    )

    # Bot statistics
    embed.add_field(name="📊 Servers", value=data['bot_info']['total_servers'], inline=True)
    embed.add_field(name="👥 Users Tracked", value=data['bot_info']['total_users_tracked'], inline=True)
    embed.add_field(name="💬 Total Interactions", value=data['bot_info']['total_interactions_logged'], inline=True)

    # Moderation statistics
    embed.add_field(name="🚫 Blacklisted Users", value=data['statistics']['total_blacklists'], inline=True)
    embed.add_field(name="⚡ Total Strikes", value=data['statistics']['total_strikes_issued'], inline=True)
    embed.add_field(name="🔇 Banned Words", value=data['statistics']['total_banned_words'], inline=True)

    # Guild blacklist statistic
    embed.add_field(name="🏰 Blacklisted Guilds", value=data['statistics']['total_blacklisted_guilds'], inline=True)
    embed.add_field(name="🔓 Filter Bypass Users", value=len(data['word_filter_bypass']), inline=True)
    embed.add_field(name="✨ Bot Admins", value=len(data['bot_admins']), inline=True)
    embed.add_field(name="📢 Updates Channels", value=len(data['updates_channels']), inline=True)

    # Channel statistics
    embed.add_field(name="🟢 Channels (Start Mode)", value=data['statistics']['channels_in_start_mode'], inline=True)
    embed.add_field(name="🔴 Channels (Stop Mode)", value=data['statistics']['channels_in_stop_mode'], inline=True)
    embed.add_field(name="⚙️ Server Configs", value=len(data['server_configurations']), inline=True)

    # Additional info
    embed.add_field(name="📋 Recent Reports", value=len(data['recent_reports']), inline=True)
    embed.add_field(name="📝 Recent Logs", value=len(data['admin_logs_recent']), inline=True)
    embed.add_field(name="📦 Export Size", value=f"{os.path.getsize(filename) / 1024:.2f} KB", inline=True)

    embed.set_footer(text=f"Complete data export • File: {filename}")

    await ctx.send(embed=embed, file=discord.File(filename))
    os.remove(filename)

    print(f"✅ Complete data export sent to owner at {datetime.datetime.now()}")
@bot.hybrid_command(name="backup", description="Owner/Admin: Trigger immediate backup.")
@owner_or_bot_admin()
@commands.dm_only()
async def manual_backup(ctx):
    db_data = export_db_to_json()
    timestamp = int(time.time())
    filename = f"manual_backup_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(db_data, f, indent=2)

    embed = discord.Embed(
        title="📦 Manual Database Backup", 
        description=f"**Timestamp:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
        color=discord.Color.blue()
    )
    embed.add_field(name="Users", value=len(db_data['users']), inline=True)
    embed.add_field(name="Banned Words", value=len(db_data['banned_words']), inline=True)
    embed.add_field(name="Interactions (24h)", value=len(db_data['interaction_logs']), inline=True)

    await ctx.send(embed=embed, file=discord.File(filename))
    os.remove(filename)

@bot.hybrid_group(name="blacklist", description="Owner/Admin: Manage user access.", invoke_without_command=True)
@owner_or_bot_admin()
async def blacklist_group(ctx):
    res = db_query("SELECT user_id FROM users WHERE blacklisted = 1", fetch=True)
    if res:
        user_list = "\n".join([f"• <@{r[0]}> (`{r[0]}`)" for r in res])
        embed = discord.Embed(
            title="🚫 Blacklisted Users",
            description=user_list,
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Total: {len(res)} user(s)")
        await ctx.send(embed=embed)
    else:
        await ctx.send("✅ **No blacklisted users**\nThe blacklist is currently empty.")

@blacklist_group.command(name="add")
@owner_or_bot_admin()
async def bl_add(ctx, user_id: str, *, reason: str = "No reason provided"):
    db_query("INSERT OR REPLACE INTO users (user_id, blacklisted) VALUES (?, 1)", (user_id,))
    log_msg = f"User {user_id} BLACKLISTED by {ctx.author.name} ({ctx.author.id}). Reason: {reason}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_sent = await send_user_dm(
        user_id, 
        f"🚫 **You have been blacklisted from {BOT_NAME} Bot**\n\n**Reason:** {reason}\n\n**What this means:**\n• You can no longer use any bot commands\n• The bot will not respond to your messages\n• This action has been logged by bot administrators\n\n**Believe this is a mistake?**\nContact the bot owner: <@{OWNER_ID}>\n**Join the Support Server:** {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}\n\n*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*"
    )
    
    # Log to dedicated blacklist channel
    log_embed = discord.Embed(
        title="🚫 User Blacklisted",
        description=f"A user has been added to the blacklist.",
        color=discord.Color.dark_red(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="⚖️ Actioned By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    log_embed.add_field(name="📬 DM Notification", value="✅ Delivered" if dm_sent else "❌ Failed (DMs closed)", inline=True)
    log_embed.add_field(name="🕐 Timestamp", value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
    
    await log_to_channel(bot, 'blacklist', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="🚫 User Blacklisted",
        description=f"User `{user_id}` has been successfully added to the blacklist.",
        color=discord.Color.red()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Actioned By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="DM Notification", value="✅ Sent" if dm_sent else "❌ Failed (DMs disabled)", inline=True)
    
    await ctx.send(embed=embed)

@blacklist_group.command(name="remove")
@owner_or_bot_admin()
async def bl_rem(ctx, user_id: str, *, reason: str = "No reason provided"):
    db_query("UPDATE users SET blacklisted = 0 WHERE user_id = ?", (user_id,))
    log_msg = f"User {user_id} removed from blacklist by {ctx.author.name} ({ctx.author.id}). Reason: {reason}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_sent = await send_user_dm(
        user_id, 
        f"✅ **Your blacklist has been removed**\n\n**Reason:** {reason}\n\n**What this means:**\n• You can now use the bot again\n• All bot features are now accessible to you\n• Your previous violations have been reviewed\n\n**Welcome back!** Please follow the community guidelines to maintain your access.\n\n*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*"
    )
    
    # Log to dedicated blacklist channel
    log_embed = discord.Embed(
        title="✅ User Unblacklisted",
        description=f"A user has been removed from the blacklist.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="⚖️ Actioned By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    log_embed.add_field(name="📬 DM Notification", value="✅ Delivered" if dm_sent else "❌ Failed (DMs closed)", inline=True)
    log_embed.add_field(name="🕐 Timestamp", value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
    
    await log_to_channel(bot, 'blacklist', log_embed)
    
    # ADD THIS MISSING CONFIRMATION EMBED
    embed = discord.Embed(
        title="✅ User Unblacklisted",
        description=f"User `{user_id}` has been successfully removed from the blacklist.",
        color=discord.Color.green()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Actioned By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="DM Notification", value="✅ Sent" if dm_sent else "❌ Failed (DMs disabled)", inline=True)
    
    await ctx.send(embed=embed)

@bot.hybrid_group(name="blacklist-guild", description="Owner/Admin: Manage guild blacklist.", invoke_without_command=True)
@owner_or_bot_admin()
async def blacklist_guild_group(ctx):
    """List all blacklisted guilds"""
    res = db_query("SELECT guild_id, guild_name, reason, blacklisted_by, blacklisted_at FROM blacklisted_guilds ORDER BY blacklisted_at DESC", fetch=True)
    
    if not res:
        await ctx.send("✅ **No blacklisted guilds**\nThe guild blacklist is currently empty.")
        return
    
    embed = discord.Embed(
        title="🚫 Blacklisted Guilds",
        description="Servers that are banned from using this bot:",
        color=discord.Color.dark_red()
    )
    
    for guild in res:
        guild_id, guild_name, reason, blacklisted_by, blacklisted_at = guild
        embed.add_field(
            name=f"🏰 {guild_name}",
            value=f"**ID:** `{guild_id}`\n**Reason:** {reason}\n**By:** <@{blacklisted_by}>\n**Date:** {blacklisted_at}",
            inline=False
        )
    
    embed.set_footer(text=f"Total: {len(res)} blacklisted guild(s)")
    await ctx.send(embed=embed)

@blacklist_guild_group.command(name="add")
@owner_or_bot_admin()
async def blacklist_guild_add(ctx, guild_id: str, *, reason: str = "No reason provided"):
    """Blacklist a guild and force bot to leave"""
    try:
        guild = bot.get_guild(int(guild_id))
        
        # Check if already blacklisted
        existing = db_query("SELECT guild_id FROM blacklisted_guilds WHERE guild_id = ?", (guild_id,), fetch=True)
        if existing:
            await ctx.send(f"⚠️ **Guild `{guild_id}` is already blacklisted.**")
            return
        
        guild_name = guild.name if guild else "Unknown Server"
        
        # Add to blacklist database
        db_query(
            "INSERT INTO blacklisted_guilds (guild_id, guild_name, blacklisted_by, reason) VALUES (?, ?, ?, ?)",
            (guild_id, guild_name, str(ctx.author.id), reason)
        )
        
        # Log the action
        log_msg = f"Guild {guild_name} ({guild_id}) BLACKLISTED by {ctx.author.name} ({ctx.author.id}). Reason: {reason}"
        db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
        
        # Try to notify guild owner before leaving
        owner_notified = False
        if guild and guild.owner:
            try:
                dm_message = f"""🚫 **{BOT_NAME} Bot - Server Blacklisted**

Hello {guild.owner.name},

Your server **{guild_name}** has been blacklisted from using {BOT_NAME} Bot.

**Reason:** {reason}

**What this means:**
• The bot will leave your server immediately
• Your server cannot re-add the bot
• This is a permanent restriction

**Appeal Process:**
If you believe this is a mistake, contact: <@{OWNER_ID}>
**Join the Support Server:** {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}

*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""
                await guild.owner.send(dm_message)
                owner_notified = True
            except:
                pass
        
        # Leave the guild if bot is in it
        left_guild = False
        if guild:
            try:
                await guild.leave()
                left_guild = True
            except Exception as e:
                left_guild = False
        
        # Log to blacklist channel
        log_embed = discord.Embed(
            title="🚫 Guild Blacklisted",
            description=f"A server has been blacklisted.",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.utcnow()
        )
        log_embed.add_field(name="🏰 Server Name", value=guild_name, inline=True)
        log_embed.add_field(name="🆔 Server ID", value=f"`{guild_id}`", inline=True)
        log_embed.add_field(name="⚖️ Blacklisted By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
        
        if guild:
            log_embed.add_field(name="👑 Server Owner", value=f"<@{guild.owner.id}> (`{guild.owner.id}`)", inline=True)
            log_embed.add_field(name="👥 Member Count", value=str(guild.member_count), inline=True)
        
        log_embed.add_field(name="📝 Reason", value=reason, inline=False)
        log_embed.add_field(name="📬 Owner Notified", value="✅ Yes" if owner_notified else "❌ No", inline=True)
        log_embed.add_field(name="🚪 Bot Left Server", value="✅ Yes" if left_guild else "❌ Not in server", inline=True)
        
        await log_to_channel(bot, 'blacklist', log_embed)
        
        # Confirm to command user
        embed = discord.Embed(
            title="🚫 Guild Blacklisted",
            description=f"Server has been blacklisted.",
            color=discord.Color.red()
        )
        embed.add_field(name="Server Name", value=guild_name, inline=True)
        embed.add_field(name="Server ID", value=guild_id, inline=True)
        embed.add_field(name="Blacklisted By", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Owner Notified", value="✅ Yes" if owner_notified else "❌ No", inline=True)
        embed.add_field(name="Bot Left", value="✅ Yes" if left_guild else "❌ Not in server", inline=True)
        
        await ctx.send(embed=embed)
        
    except ValueError:
        await ctx.send("❌ **Invalid guild ID**\nPlease provide a valid numeric guild ID.")
    except Exception as e:
        await ctx.send(f"❌ **Error:** {str(e)}")

@blacklist_guild_group.command(name="remove")
@owner_or_bot_admin()
async def blacklist_guild_remove(ctx, guild_id: str, *, reason: str = "No reason provided"):
    """Remove a guild from the blacklist"""
    # Check if blacklisted
    existing = db_query("SELECT guild_name, blacklisted_by, blacklisted_at FROM blacklisted_guilds WHERE guild_id = ?", (guild_id,), fetch=True)
    
    if not existing:
        await ctx.send(f"⚠️ **Guild `{guild_id}` is not blacklisted.**")
        return
    
    guild_name, blacklisted_by, blacklisted_at = existing[0]
    
    # Remove from blacklist
    db_query("DELETE FROM blacklisted_guilds WHERE guild_id = ?", (guild_id,))
    
    # Log the action
    log_msg = f"Guild {guild_name} ({guild_id}) removed from blacklist by {ctx.author.name} ({ctx.author.id}). Reason: {reason}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Log to blacklist channel
    log_embed = discord.Embed(
        title="✅ Guild Unblacklisted",
        description=f"A server has been removed from the blacklist.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="🏰 Server Name", value=guild_name, inline=True)
    log_embed.add_field(name="🆔 Server ID", value=f"`{guild_id}`", inline=True)
    log_embed.add_field(name="⚖️ Removed By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📜 Originally Blacklisted", value=f"**By:** <@{blacklisted_by}>\n**Date:** {blacklisted_at}", inline=False)
    log_embed.add_field(name="📝 Removal Reason", value=reason, inline=False)
    
    await log_to_channel(bot, 'blacklist', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="✅ Guild Unblacklisted",
        description=f"Server has been removed from the blacklist and can now re-add the bot.",
        color=discord.Color.green()
    )
    embed.add_field(name="Server Name", value=guild_name, inline=True)
    embed.add_field(name="Server ID", value=guild_id, inline=True)
    embed.add_field(name="Removed By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    
    await ctx.send(embed=embed)


@bot.hybrid_command(name="addstrike", description="Owner/Admin: Add strikes to a user.")
@owner_or_bot_admin()
async def add_strike(ctx, user_id: str, amount: int = 1, *, reason: str = "No reason provided"):
    res = db_query("SELECT strikes FROM users WHERE user_id = ?", (user_id,), fetch=True)
    current_strikes = res[0][0] if res else 0
    new_strikes = current_strikes + amount
    is_banned = 1 if new_strikes >= 3 else 0

    db_query("INSERT OR REPLACE INTO users (user_id, strikes, blacklisted) VALUES (?, ?, ?)", (user_id, new_strikes, is_banned))

    log_msg = f"Strike added to {user_id} by {ctx.author.name} ({ctx.author.id}). Amount: {amount}. Total: {new_strikes}/3. Reason: {reason}"
    if is_banned:
        log_msg += f" | User {user_id} AUTO-BLACKLISTED (3 strikes reached)."

    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_message = f"⚡ **Strike Issued**\n\n**You have received {amount} strike(s)**\n\n**Reason:** {reason}\n**Total Strikes:** {new_strikes}/3\n**Issued By:** Administrator\n\n"
    if is_banned:
        dm_message += f"🚫 **ACCOUNT SUSPENDED**\n\nYou have reached 3 strikes and have been automatically blacklisted from {BOT_NAME} Bot.\n\n**What this means:**\n• You can no longer use the bot\n• All access has been revoked\n• This is a permanent suspension unless appealed\n\n**Appeal Process:**\nContact the bot owner: <@!{OWNER_ID}>\n**Join the Support Server:** {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}"
    else:
        strikes_remaining = 3 - new_strikes
        dm_message += f"⚠️ **Warning:** You are {strikes_remaining} strike(s) away from being blacklisted.\n\n**How to avoid more strikes:**\n• Follow community guidelines\n• Avoid using banned words\n• Be respectful to others\n• Follow server and bot rules"
    
    dm_message += f"\n\n*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*"
    
    dm_sent = await send_user_dm(user_id, dm_message)
    
    # Log to dedicated strikes channel
    log_embed = discord.Embed(
        title="⚡ Strike Issued" if not is_banned else "🚫 User Auto-Blacklisted (3 Strikes)",
        description=f"Strike(s) have been added to a user.",
        color=discord.Color.orange() if not is_banned else discord.Color.dark_red(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="⚡ Strikes Added", value=str(amount), inline=True)
    log_embed.add_field(name="📊 Total Strikes", value=f"{new_strikes}/3", inline=True)
    log_embed.add_field(name="⚖️ Actioned By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📌 Status", value="🚫 **AUTO-BANNED**" if is_banned else f"⚠️ Active ({3-new_strikes} remaining)", inline=True)
    log_embed.add_field(name="📬 DM Sent", value="✅ Delivered" if dm_sent else "❌ Failed", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    
    await log_to_channel(bot, 'strikes', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="⚡ Strike Added" if not is_banned else "🚫 User Auto-Blacklisted",
        description=f"Strike(s) successfully added to user `{user_id}`",
        color=discord.Color.orange() if not is_banned else discord.Color.red()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Strikes Added", value=amount, inline=True)
    embed.add_field(name="Total Strikes", value=f"{new_strikes}/3", inline=True)
    embed.add_field(name="Actioned By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Status", value="🚫 AUTO-BANNED" if is_banned else "⚠️ Active", inline=True)
    embed.add_field(name="DM Sent", value="✅ Yes" if dm_sent else "❌ Failed", inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="removestrike", description="Owner/Admin: Remove strikes from a user.")
@owner_or_bot_admin()
async def remove_strike(ctx, user_id: str, amount: int = 1, *, reason: str = "No reason provided"):
    res = db_query("SELECT strikes FROM users WHERE user_id = ?", (user_id,), fetch=True)

    if not res or res[0][0] == 0:
        await ctx.send(f"⚠️ **User `{user_id}` has no strikes to remove.**")
        return

    current_strikes = res[0][0]
    new_strikes = max(0, current_strikes - amount)
    is_banned = 1 if new_strikes >= 3 else 0

    db_query("UPDATE users SET strikes = ?, blacklisted = ? WHERE user_id = ?", (new_strikes, is_banned, user_id))

    log_msg = f"Removed {amount} strike(s) from {user_id} by {ctx.author.name} ({ctx.author.id}). Total: {new_strikes}/3. Reason: {reason}"
    was_unbanned = current_strikes >= 3 and new_strikes < 3
    if was_unbanned:
        log_msg += f" | User {user_id} unbanned (below 3 strikes)."

    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_message = f"✅ **Strike(s) Removed**\n\n**{amount} strike(s) have been removed from your account**\n\n**Reason:** {reason}\n**Previous Strikes:** {current_strikes}/3\n**Current Strikes:** {new_strikes}/3\n**Reviewed By:** Administrator\n\n"
    if was_unbanned:
        dm_message += f"🎉 **ACCOUNT RESTORED**\n\nYour blacklist has been lifted! You can now use {BOT_NAME} Bot again.\n\n**Remember:**\n• Follow community guidelines\n• Avoid accumulating more strikes\n• Be respectful and follow the rules\n\nWelcome back!"
    else:
        dm_message += "**Status:** Your account is in good standing. Keep following the rules to avoid future strikes."
    
    dm_message += f"\n\n*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*"
    
    dm_sent = await send_user_dm(user_id, dm_message)
    
    # Log to dedicated strikes channel
    log_embed = discord.Embed(
        title="✅ Strike(s) Removed" if not was_unbanned else "🎉 User Unbanned (Strike Removal)",
        description=f"Strike(s) have been removed from a user.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="⚡ Strikes Removed", value=str(amount), inline=True)
    log_embed.add_field(name="📊 Remaining Strikes", value=f"{new_strikes}/3", inline=True)
    log_embed.add_field(name="⚖️ Actioned By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📌 Status", value="🎉 **UNBANNED**" if was_unbanned else "✅ Active", inline=True)
    log_embed.add_field(name="📬 DM Sent", value="✅ Delivered" if dm_sent else "❌ Failed", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    
    await log_to_channel(bot, 'strikes', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="✅ Strike Removed" if not was_unbanned else "🎉 User Unbanned",
        description=f"Strike(s) successfully removed from user `{user_id}`",
        color=discord.Color.green()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Strikes Removed", value=amount, inline=True)
    embed.add_field(name="Remaining Strikes", value=f"{new_strikes}/3", inline=True)
    embed.add_field(name="Actioned By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Status", value="🎉 Unbanned" if was_unbanned else "✅ Active", inline=True)
    embed.add_field(name="DM Sent", value="✅ Yes" if dm_sent else "❌ Failed", inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    
    await ctx.send(embed=embed)
@bot.hybrid_command(name="strikelist", description="Owner/Admin: View all users with strikes.")
@owner_or_bot_admin()
async def strike_list(ctx):
    res = db_query("SELECT user_id, strikes FROM users WHERE strikes > 0 ORDER BY strikes DESC", fetch=True)
    
    if not res:
        await ctx.send("✅ **No active strikes**\nAll users are in good standing.")
        return
    
    strike_text = "\n".join([f"{'🚫' if r[1] >= 3 else '⚡'} <@{r[0]}> - **{r[1]}/3** strikes" for r in res])
    
    embed = discord.Embed(
        title="⚡ Strike Ledger", 
        description=strike_text, 
        color=discord.Color.orange()
    )
    embed.set_footer(text=f"Total users with strikes: {len(res)}")
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="clearstrike", description="Owner/Admin: Clear all strikes for a user.")
@owner_or_bot_admin()
async def clear_strike(ctx, user_id: str, *, reason: str = "Strikes cleared by administrator"):
    res = db_query("SELECT strikes FROM users WHERE user_id = ?", (user_id,), fetch=True)
    
    if not res or res[0][0] == 0:
        await ctx.send(f"⚠️ **User `{user_id}` has no strikes to clear.**")
        return
    
    previous_strikes = res[0][0]
    db_query("UPDATE users SET strikes = 0, blacklisted = 0 WHERE user_id = ?", (user_id,))
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (f"All strikes cleared for {user_id} by {ctx.author.name} ({ctx.author.id}). Previous strikes: {previous_strikes}. Reason: {reason}",))
    
    # Send DM to user
    dm_message = f"✅ **All Strikes Cleared**\n\n**Your account has been fully restored**\n\n**Previous Strikes:** {previous_strikes}/3\n**Current Strikes:** 0/3\n**Reason:** {reason}\n\n🎉 You now have a clean slate! Your account is in good standing.\n\n**Remember to:**\n• Follow all community guidelines\n• Respect other users\n• Avoid banned words and inappropriate behavior\n\nThank you for being part of the community!\n\n*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*"
    
    dm_sent = await send_user_dm(user_id, dm_message)
    
    # Log to strikes channel
    log_embed = discord.Embed(
        title="🧹 All Strikes Cleared",
        description=f"All strikes have been cleared for a user.",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="📊 Previous Strikes", value=f"{previous_strikes}/3", inline=True)
    log_embed.add_field(name="📊 Current Strikes", value="0/3", inline=True)
    log_embed.add_field(name="⚖️ Actioned By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📬 DM Sent", value="✅ Delivered" if dm_sent else "❌ Failed", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    
    await log_to_channel(bot, 'strikes', log_embed)
    
    embed = discord.Embed(
        title="✅ Strikes Cleared",
        description=f"All strikes have been cleared for user `{user_id}`",
        color=discord.Color.green()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Previous Strikes", value=f"{previous_strikes}/3", inline=True)
    embed.add_field(name="Actioned By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    
    await ctx.send(embed=embed)

@bot.hybrid_group(name="bannedword", invoke_without_command=True)
@owner_or_bot_admin()
async def bw_group(ctx):
    res = db_query("SELECT word FROM banned_words ORDER BY word", fetch=True)
    
    if not res:
        await ctx.send("✅ **No banned words**\nThe word filter is currently empty.")
        return
    
    words = ', '.join([f"`{r[0]}`" for r in res])
    embed = discord.Embed(
        title="🔇 Banned Words List",
        description=words,
        color=discord.Color.red()
    )
    embed.set_footer(text=f"Total: {len(res)} banned word(s)")
    
    await ctx.send(embed=embed)

@bw_group.command(name="add")
@owner_or_bot_admin()
async def bw_add(ctx, word: str):
    word_lower = word.lower()
    existing = db_query("SELECT word FROM banned_words WHERE word = ?", (word_lower,), fetch=True)
    
    if existing:
        await ctx.send(f"⚠️ **`{word}` is already in the banned words list.**")
        return
    
    db_query("INSERT INTO banned_words VALUES (?)", (word_lower,))
    log_msg = f"Banned word added: '{word}' by {ctx.author.name} ({ctx.author.id})"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Log to banned words channel
    log_embed = discord.Embed(
        title="🔇 Banned Word Added",
        description=f"A new word has been added to the filter.",
        color=discord.Color.red(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="🔤 Word", value=f"`{word_lower}`", inline=True)
    log_embed.add_field(name="⚖️ Added By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📊 Total Banned Words", value=str(len(db_query("SELECT word FROM banned_words", fetch=True))), inline=True)
    
    await log_to_channel(bot, 'banned_words', log_embed)
    
    await ctx.send(f"🚫 **Word banned successfully**\n`{word}` has been added to the filter and will be automatically removed from messages.")

@bw_group.command(name="remove")
@owner_or_bot_admin()
async def bw_rem(ctx, word: str):
    word_lower = word.lower()
    existing = db_query("SELECT word FROM banned_words WHERE word = ?", (word_lower,), fetch=True)
    
    if not existing:
        await ctx.send(f"⚠️ **`{word}` is not in the banned words list.**")
        return
    
    db_query("DELETE FROM banned_words WHERE word = ?", (word_lower,))
    log_msg = f"Banned word removed: '{word}' by {ctx.author.name} ({ctx.author.id})"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Log to banned words channel
    log_embed = discord.Embed(
        title="✅ Banned Word Removed",
        description=f"A word has been removed from the filter.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="🔤 Word", value=f"`{word_lower}`", inline=True)
    log_embed.add_field(name="⚖️ Removed By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📊 Total Banned Words", value=str(len(db_query("SELECT word FROM banned_words", fetch=True))), inline=True)
    
    await log_to_channel(bot, 'banned_words', log_embed)
    
    await ctx.send(f"✅ **Word unbanned successfully**\n`{word}` has been removed from the filter.")

@bot.hybrid_group(name="bypass", description="Owner/Admin: Manage word filter bypass.", invoke_without_command=True)
@owner_or_bot_admin()
async def bypass_group(ctx):
    """List all users with word filter bypass"""
    res = db_query("SELECT user_id, reason, added_by, added_at FROM word_filter_bypass ORDER BY added_at DESC", fetch=True)
    
    if not res:
        await ctx.send("✅ **No bypass users**\nNo users currently have word filter bypass privileges.")
        return
    
    embed = discord.Embed(
        title="🔓 Word Filter Bypass List",
        description="Users who can use banned words:",
        color=discord.Color.blue()
    )
    
    for user in res:
        user_id, reason, added_by, added_at = user
        embed.add_field(
            name=f"👤 <@{user_id}>",
            value=f"**ID:** `{user_id}`\n**Reason:** {reason}\n**Added By:** <@{added_by}>\n**Date:** {added_at}",
            inline=False
        )
    
    embed.set_footer(text=f"Total: {len(res)} user(s) with bypass")
    await ctx.send(embed=embed)

@bypass_group.command(name="add")
@owner_or_bot_admin()
async def bypass_add(ctx, user_id: str, *, reason: str = "No reason provided"):
    """Add a user to word filter bypass"""
    # Check if already has bypass
    existing = db_query("SELECT user_id FROM word_filter_bypass WHERE user_id = ?", (user_id,), fetch=True)
    if existing:
        await ctx.send(f"⚠️ **User `{user_id}` already has word filter bypass.**")
        return
    
    # Add to database
    db_query("INSERT INTO word_filter_bypass (user_id, added_by, reason) VALUES (?, ?, ?)", 
             (user_id, str(ctx.author.id), reason))
    
    # Log the action
    log_msg = f"Word filter bypass granted to {user_id} by {ctx.author.name} ({ctx.author.id}). Reason: {reason}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_message = f"""🔓 **Word Filter Bypass Granted**

You have been granted permission to bypass the word filter in {BOT_NAME} Bot.

**Reason:** {reason}
**Granted By:** {ctx.author.name}

**What this means:**
• You can use banned words without being filtered
• Your messages will not be automatically deleted
• This privilege can be revoked at any time

**Important:**
• Use this privilege responsibly
• Don't abuse this permission
• Follow all other server and bot rules

*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""
    dm_sent = await send_user_dm(user_id, dm_message)
    
    # Log to banned words channel (since it's filter-related)
    log_embed = discord.Embed(
        title="🔓 Word Filter Bypass Granted",
        description="A user has been granted word filter bypass privileges.",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="⚖️ Granted By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    log_embed.add_field(name="📬 DM Sent", value="✅ Delivered" if dm_sent else "❌ Failed", inline=True)
    log_embed.add_field(name="🕐 Timestamp", value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
    
    await log_to_channel(bot, 'banned_words', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="🔓 Word Filter Bypass Granted",
        description=f"User `{user_id}` can now bypass the word filter.",
        color=discord.Color.green()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Granted By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="DM Notification", value="✅ Sent" if dm_sent else "❌ Failed", inline=True)
    
    await ctx.send(embed=embed)

@bypass_group.command(name="remove")
@owner_or_bot_admin()
async def bypass_remove(ctx, user_id: str, *, reason: str = "No reason provided"):
    """Remove a user from word filter bypass"""
    # Check if has bypass
    existing = db_query("SELECT user_id FROM word_filter_bypass WHERE user_id = ?", (user_id,), fetch=True)
    if not existing:
        await ctx.send(f"⚠️ **User `{user_id}` does not have word filter bypass.**")
        return
    
    # Remove from database
    db_query("DELETE FROM word_filter_bypass WHERE user_id = ?", (user_id,))
    
    # Log the action
    log_msg = f"Word filter bypass revoked from {user_id} by {ctx.author.name} ({ctx.author.id}). Reason: {reason}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_message = f"""🔒 **Word Filter Bypass Revoked**

Your word filter bypass privileges have been revoked.

**Reason:** {reason}
**Revoked By:** {ctx.author.name}

**What this means:**
• You can no longer use banned words
• Your messages will be filtered like normal users
• Using banned words will result in message deletion

**Remember:**
• Follow the word filter rules
• Avoid using banned words
• Repeated violations may result in strikes

*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""
    dm_sent = await send_user_dm(user_id, dm_message)
    
    # Log to banned words channel
    log_embed = discord.Embed(
        title="🔒 Word Filter Bypass Revoked",
        description="Word filter bypass has been removed from a user.",
        color=discord.Color.orange(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="⚖️ Revoked By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    log_embed.add_field(name="📬 DM Sent", value="✅ Delivered" if dm_sent else "❌ Failed", inline=True)
    log_embed.add_field(name="🕐 Timestamp", value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
    
    await log_to_channel(bot, 'banned_words', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="🔒 Word Filter Bypass Revoked",
        description=f"User `{user_id}` can no longer bypass the word filter.",
        color=discord.Color.orange()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Revoked By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="DM Notification", value="✅ Sent" if dm_sent else "❌ Failed", inline=True)
    
    await ctx.send(embed=embed)


@bot.hybrid_command(name="listwords", description="Owner/Admin: List all banned words.")
@owner_or_bot_admin()
async def list_words(ctx):
    await bw_group.invoke(ctx)

@bot.hybrid_command(name="logs", description="Owner/Admin: View recent moderation logs.")
@owner_or_bot_admin()
async def view_logs(ctx):
    res = db_query("SELECT log, timestamp FROM admin_logs ORDER BY timestamp DESC LIMIT 15", fetch=True)
    
    if not res:
        await ctx.send("📋 **No admin logs found**\nNo moderation actions have been logged yet.")
        return
    
    log_text = "\n".join([f"[{r[1]}] {r[0]}" for r in res])
    
    await ctx.send(f"```\n{log_text}\n```")

@bot.hybrid_command(name="clearadminlogs", description="Owner/Admin: Clear all admin logs.")
@owner_or_bot_admin()
async def clear_admin_logs(ctx):
    count = db_query("SELECT COUNT(*) FROM admin_logs", fetch=True)[0][0]
    db_query("DELETE FROM admin_logs")
    
    # Log this action to admin logs channel before clearing
    log_embed = discord.Embed(
        title="🗑️ Admin Logs Cleared",
        description=f"All admin logs have been cleared.",
        color=discord.Color.orange(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="📊 Logs Cleared", value=str(count), inline=True)
    log_embed.add_field(name="⚖️ Cleared By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    
    await log_to_channel(bot, 'admin_logs', log_embed)
    
    await ctx.send(f"🗑️ **Admin logs cleared**\n**Removed:** {count} log entries")

@bot.hybrid_command(name="searchlogs", description="Owner/Admin: Search interaction logs.")
@owner_or_bot_admin()
async def search_logs(ctx, keyword: str):
    rows = db_query("SELECT * FROM interaction_logs WHERE prompt LIKE ? OR response LIKE ? ORDER BY timestamp DESC LIMIT 20", (f"%{keyword}%", f"%{keyword}%"), fetch=True)

    if not rows:
        await ctx.send(f"❌ **No results found for:** `{keyword}`")
        return

    text = "\n".join([f"[{r[3]}]: {r[5][:50]}..." for r in rows])
    await ctx.send(f"🔍 **Search Results for `{keyword}`**\n```\n{text}\n```")

# Report Action View with Buttons
class ReportActionView(discord.ui.View):
    def __init__(self, report_id, reported_user_id, reported_user_name):
        super().__init__(timeout=None)  # No timeout for report actions
        self.report_id = report_id
        self.reported_user_id = reported_user_id
        self.reported_user_name = reported_user_name
    
    @discord.ui.button(label="Claim Report", style=discord.ButtonStyle.primary, emoji="✋", custom_id="claim_report")
    async def claim_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user is admin
        if not is_bot_admin(interaction.user.id):
            await interaction.response.send_message("❌ Only bot admins can claim reports.", ephemeral=True)
            return
        
        # Update database to mark as claimed
        db_query("UPDATE reports SET status = 'claimed' WHERE report_id = ?", (self.report_id,))
        db_query("INSERT INTO admin_logs (log) VALUES (?)", 
                (f"Report #{self.report_id} claimed by {interaction.user.name} ({interaction.user.id})",))
        
        # Update embed
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.blue()
        embed.set_footer(text=f"Report ID: {self.report_id} | Status: CLAIMED by {interaction.user.name} | {embed.footer.text.split('|')[-1]}")
        
        # Disable claim button
        button.disabled = True
        button.label = f"Claimed by {interaction.user.name}"
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Log to admin logs channel
        log_embed = discord.Embed(
            title=f"✋ Report #{self.report_id} Claimed",
            description=f"Report has been claimed by an administrator.",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        log_embed.add_field(name="👤 Reported User", value=f"<@{self.reported_user_id}> (`{self.reported_user_id}`)", inline=True)
        log_embed.add_field(name="⚖️ Claimed By", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
        log_embed.add_field(name="🆔 Report ID", value=f"`#{self.report_id}`", inline=True)
        
        await log_to_channel(bot, 'admin_logs', log_embed)
    
    @discord.ui.button(label="Add Strike", style=discord.ButtonStyle.danger, emoji="⚡", custom_id="add_strike")
    async def add_strike_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user is admin
        if not is_bot_admin(interaction.user.id):
            await interaction.response.send_message("❌ Only bot admins can add strikes.", ephemeral=True)
            return
        
        # Add strike
        res = db_query("SELECT strikes FROM users WHERE user_id = ?", (str(self.reported_user_id),), fetch=True)
        current_strikes = res[0][0] if res else 0
        new_strikes = current_strikes + 1
        is_banned = 1 if new_strikes >= 3 else 0
        
        db_query("INSERT OR REPLACE INTO users (user_id, strikes, blacklisted) VALUES (?, ?, ?)", 
                (str(self.reported_user_id), new_strikes, is_banned))
        
        # Update report status
        db_query("UPDATE reports SET status = 'actioned' WHERE report_id = ?", (self.report_id,))
        
        log_msg = f"Report #{self.report_id}: Strike added to {self.reported_user_id} by {interaction.user.name} ({interaction.user.id}). Total: {new_strikes}/3. Reason: Action from report"
        if is_banned:
            log_msg += f" | User {self.reported_user_id} AUTO-BLACKLISTED."
        db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
        
        # Send DM to reported user
        dm_message = f"⚡ **Strike Issued**\n\n**You have received 1 strike**\n\n**Reason:** Action taken from user report #{self.report_id}\n**Total Strikes:** {new_strikes}/3\n**Issued By:** Administrator\n\n"
        if is_banned:
            dm_message += f"🚫 **ACCOUNT SUSPENDED**\n\nYou have reached 3 strikes and have been automatically blacklisted from {BOT_NAME} Bot.\n\n**Appeal Process:**\nContact the bot owner: <@{OWNER_ID}>\n**Join the Support Server:** {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}"
        else:
            strikes_remaining = 3 - new_strikes
            dm_message += f"⚠️ **Warning:** You are {strikes_remaining} strike(s) away from being blacklisted.\n\n**How to avoid more strikes:**\n• Follow community guidelines\n• Be respectful to others\n• Follow server and bot rules"
        
        dm_message += f"\n\n*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*"
        dm_sent = await send_user_dm(str(self.reported_user_id), dm_message)
        
        # Log to strikes channel
        log_embed = discord.Embed(
            title="⚡ Strike Issued (From Report)" if not is_banned else "🚫 User Auto-Blacklisted (3 Strikes - From Report)",
            description=f"Strike added from report #{self.report_id}.",
            color=discord.Color.orange() if not is_banned else discord.Color.dark_red(),
            timestamp=datetime.datetime.utcnow()
        )
        log_embed.add_field(name="👤 User ID", value=f"`{self.reported_user_id}`", inline=True)
        log_embed.add_field(name="⚡ Strikes Added", value="1", inline=True)
        log_embed.add_field(name="📊 Total Strikes", value=f"{new_strikes}/3", inline=True)
        log_embed.add_field(name="⚖️ Actioned By", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
        log_embed.add_field(name="🆔 Report ID", value=f"`#{self.report_id}`", inline=True)
        log_embed.add_field(name="📬 DM Sent", value="✅ Delivered" if dm_sent else "❌ Failed", inline=True)
        log_embed.add_field(name="📝 Reason", value=f"Action from report #{self.report_id}", inline=False)
        
        await log_to_channel(bot, 'strikes', log_embed)
        
        # Update embed
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.orange()
        embed.set_footer(text=f"Report ID: {self.report_id} | Status: ACTIONED (Strike) by {interaction.user.name}")
        
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"✅ Added 1 strike to <@{self.reported_user_id}>. Total: {new_strikes}/3" + (" 🚫 **User auto-blacklisted!**" if is_banned else ""), ephemeral=True)
    
    @discord.ui.button(label="Blacklist", style=discord.ButtonStyle.danger, emoji="🚫", custom_id="blacklist")
    async def blacklist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user is admin
        if not is_bot_admin(interaction.user.id):
            await interaction.response.send_message("❌ Only bot admins can blacklist users.", ephemeral=True)
            return
        
        # Blacklist user
        db_query("INSERT OR REPLACE INTO users (user_id, blacklisted) VALUES (?, 1)", (str(self.reported_user_id),))
        
        # Update report status
        db_query("UPDATE reports SET status = 'actioned' WHERE report_id = ?", (self.report_id,))
        
        log_msg = f"Report #{self.report_id}: User {self.reported_user_id} BLACKLISTED by {interaction.user.name} ({interaction.user.id}). Reason: Action from report"
        db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
        
        # Send DM
        dm_message = f"🚫 **You have been blacklisted from {BOT_NAME} Bot**\n\n**Reason:** Action taken from user report #{self.report_id}\n\n**What this means:**\n• You can no longer use any bot commands\n• The bot will not respond to your messages\n• This action has been logged by bot administrators\n\n**Believe this is a mistake?**\nContact the bot owner: <@{OWNER_ID}>\n**Join the Support Server:** {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}\n\n*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*"
        dm_sent = await send_user_dm(str(self.reported_user_id), dm_message)
        
        # Log to blacklist channel
        log_embed = discord.Embed(
            title="🚫 User Blacklisted (From Report)",
            description=f"User blacklisted from report #{self.report_id}.",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.utcnow()
        )
        log_embed.add_field(name="👤 User ID", value=f"`{self.reported_user_id}`", inline=True)
        log_embed.add_field(name="⚖️ Actioned By", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
        log_embed.add_field(name="🆔 Report ID", value=f"`#{self.report_id}`", inline=True)
        log_embed.add_field(name="📝 Reason", value=f"Action from report #{self.report_id}", inline=False)
        log_embed.add_field(name="📬 DM Notification", value="✅ Delivered" if dm_sent else "❌ Failed", inline=True)
        
        await log_to_channel(bot, 'blacklist', log_embed)
        
        # Update embed
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.dark_red()
        embed.set_footer(text=f"Report ID: {self.report_id} | Status: ACTIONED (Blacklist) by {interaction.user.name}")
        
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"✅ Blacklisted <@{self.reported_user_id}>", ephemeral=True)

# --- REPORT COMMAND ---
@bot.hybrid_command(name="report", description="Report a user for misbehavior.")
async def report_user(ctx, member: discord.Member, proof: str, *, reason: str):
    """
    Report a user for misbehavior
    Usage: /report @user <proof_url_or_text> <reason>
    """
    if not ctx.guild:
        await ctx.send("❌ **This command can only be used in servers.**")
        return
    
    # Prevent self-reporting
    if member.id == ctx.author.id:
        await ctx.send("❌ **You cannot report yourself.**")
        return
    
    # Prevent reporting bots
    if member.bot:
        await ctx.send("❌ **You cannot report bots.**")
        return
    
    # Collect proof from attachments if available
    attachments_list = []
    if ctx.message and ctx.message.attachments:
        attachments_list = [att.url for att in ctx.message.attachments]
    
    # Combine proof text and attachments
    full_proof = proof
    if attachments_list:
        full_proof += "\n" + "\n".join(attachments_list)
    
    # Store in database
    db_query(
        "INSERT INTO reports (reporter_id, reporter_name, reported_user_id, reported_user_name, guild_id, guild_name, reason, proof) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(ctx.author.id), ctx.author.name, str(member.id), member.name, str(ctx.guild.id), ctx.guild.name, reason, full_proof)
    )
    
    # Get report ID
    report_id = db_query("SELECT last_insert_rowid()", fetch=True)[0][0]
    
    # Log to database
    db_query("INSERT INTO admin_logs (log) VALUES (?)", 
             (f"Report #{report_id}: {ctx.author.name} ({ctx.author.id}) reported {member.name} ({member.id}) in {ctx.guild.name}. Reason: {reason}",))
    
    # Create detailed embed for logging channel
    log_embed = discord.Embed(
        title=f"📢 New User Report - #{report_id}",
        description="A user has been reported for misbehavior.",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow()
    )
    
    log_embed.add_field(name="👤 Reported User", value=f"{member.mention} (`{member.id}`)\n**Username:** {member.name}\n**Display Name:** {member.display_name}", inline=True)
    log_embed.add_field(name="🚨 Reported By", value=f"{ctx.author.mention} (`{ctx.author.id}`)\n**Username:** {ctx.author.name}", inline=True)
    log_embed.add_field(name="🆔 Report ID", value=f"`#{report_id}`", inline=True)
    
    log_embed.add_field(name="🏠 Server", value=f"**Name:** {ctx.guild.name}\n**ID:** `{ctx.guild.id}`", inline=True)
    log_embed.add_field(name="📍 Channel", value=f"{ctx.channel.mention}\n**ID:** `{ctx.channel.id}`", inline=True)
    log_embed.add_field(name="📅 Report Date", value=discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
    
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    
    # Add proof section with better formatting
    proof_lines = full_proof.split('\n')
    proof_display = []
    
    for line in proof_lines:
        if line.startswith('http://') or line.startswith('https://'):
            file_ext = line.split('.')[-1].split('?')[0].lower()
            if file_ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                file_type = "🖼️ Image"
                if len(proof_display) == 0:
                    log_embed.set_image(url=line)
            elif file_ext in ['mp4', 'mov', 'avi', 'webm']:
                file_type = "🎥 Video"
            elif file_ext in ['pdf', 'txt', 'doc', 'docx']:
                file_type = "📄 Document"
            else:
                file_type = "📎 File"
            proof_display.append(f"{file_type}: [View]({line})")
        else:
            proof_display.append(f"📝 {line}")
    
    log_embed.add_field(name="📎 Proof", value="\n".join(proof_display) if proof_display else "No proof provided", inline=False)
    
    # --- FIX START: Timezone-aware datetime subtraction ---
    now = discord.utils.utcnow()
    account_age = (now - member.created_at).days
    join_age = (now - member.joined_at).days if member.joined_at else 0
    # --- FIX END ---
    
    log_embed.add_field(
        name="ℹ️ Account Information", 
        value=f"**Account Created:** {member.created_at.strftime('%Y-%m-%d')} ({account_age} days ago)\n**Joined Server:** {member.joined_at.strftime('%Y-%m-%d') if member.joined_at else 'Unknown'} ({join_age} days ago)\n**Roles:** {len(member.roles)-1} roles", 
        inline=True
    )
    
    # Check if reported user has existing strikes
    existing_strikes = db_query("SELECT strikes, blacklisted FROM users WHERE user_id = ?", (str(member.id),), fetch=True)
    if existing_strikes and existing_strikes[0]:
        strikes, blacklisted = existing_strikes[0]
        if blacklisted:
            status = "🚫 **BLACKLISTED**"
            status_color = "This user is currently banned from the bot"
        elif strikes >= 2:
            status = f"⚠️ **{strikes}/3 Strikes** (High Risk)"
            status_color = "User is close to automatic blacklist"
        elif strikes >= 1:
            status = f"⚡ **{strikes}/3 Strikes**"
            status_color = "User has previous violations"
        else:
            status = "✅ Clean Record"
            status_color = "No previous violations"
        
        log_embed.add_field(name="📊 User Status", value=f"{status}\n*{status_color}*", inline=True)
    else:
        log_embed.add_field(name="📊 User Status", value="✅ **Clean Record**\n*No previous violations*", inline=True)
    
    # Add reporter's credibility info
    reporter_reports = db_query("SELECT COUNT(*) FROM reports WHERE reporter_id = ?", (str(ctx.author.id),), fetch=True)
    report_count = reporter_reports[0][0] if reporter_reports else 0
    
    log_embed.add_field(
        name="📊 Reporter Info",
        value=f"**Total Reports Filed:** {report_count}\n**Account Age:** {(now - ctx.author.created_at).days} days",
        inline=False
    )
    
    log_embed.set_thumbnail(url=member.display_avatar.url)
    log_embed.set_footer(text=f"Report ID: {report_id} | Status: PENDING | Reported by: {ctx.author.name}")
    
    # Send to reports/admin logs channel with action buttons
    channel = bot.get_channel(LOG_CHANNELS['admin_logs'])
    if channel:
        view = ReportActionView(report_id, member.id, member.name)
        await channel.send(embed=log_embed, view=view)
    
    # Confirm to reporter
    confirm_embed = discord.Embed(
        title="✅ Report Submitted Successfully",
        description=f"Your report has been forwarded to the bot administrators for review.",
        color=discord.Color.green()
    )
    confirm_embed.add_field(name="🆔 Report ID", value=f"`#{report_id}`", inline=True)
    confirm_embed.add_field(name="👤 Reported User", value=member.mention, inline=True)
    confirm_embed.add_field(name="📌 Status", value="Pending Review", inline=True)
    confirm_embed.set_footer(text="Thank you for helping maintain a safe community!")
    
    if ctx.interaction:
        await ctx.send(embed=confirm_embed, ephemeral=True)
    else:
        await ctx.send(embed=confirm_embed)
        try:
            await ctx.message.delete(delay=10)
        except:
            pass

@bot.hybrid_command(name="reports", description="Owner/Admin: View recent reports.")
@owner_or_bot_admin()
async def view_reports(ctx, status: str = "pending"):
    """View reports by status (pending, reviewed, dismissed)"""
    valid_statuses = ["pending", "reviewed", "dismissed", "all"]
    
    if status not in valid_statuses:
        await ctx.send(f"❌ **Invalid status**\n\nValid options: `{', '.join(valid_statuses)}`")
        return
    
    if status == "all":
        reports = db_query("SELECT * FROM reports ORDER BY timestamp DESC LIMIT 20", fetch=True)
    else:
        reports = db_query("SELECT * FROM reports WHERE status = ? ORDER BY timestamp DESC LIMIT 20", (status,), fetch=True)
    
    if not reports:
        await ctx.send(f"📋 **No {status} reports found.**")
        return
    
    embed = discord.Embed(
        title=f"📊 Reports - {status.capitalize()}",
        description=f"Showing recent {status} reports",
        color=discord.Color.blue()
    )
    
    for report in reports[:10]:  # Show max 10 in embed
        report_id, reporter_id, reporter_name, reported_id, reported_name, guild_id, guild_name, reason, proof, timestamp, report_status = report
        
        embed.add_field(
            name=f"Report #{report_id} - {report_status.upper()}",
            value=f"**Reported:** <@{reported_id}> ({reported_name})\n**By:** <@{reporter_id}>\n**Server:** {guild_name}\n**Reason:** {reason[:100]}...\n**Date:** {timestamp}",
            inline=False
        )
    
    embed.set_footer(text=f"Total {status} reports: {len(reports)} | Use /reportview <id> for details")
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="reportview", description="Owner/Admin: View detailed report.")
@owner_or_bot_admin()
async def view_report_detail(ctx, report_id: int):
    """View detailed information about a specific report"""
    report = db_query("SELECT * FROM reports WHERE report_id = ?", (report_id,), fetch=True)
    
    if not report:
        await ctx.send(f"❌ **Report #{report_id} not found.**")
        return
    
    report = report[0]
    r_id, reporter_id, reporter_name, reported_id, reported_name, guild_id, guild_name, reason, proof, timestamp, status = report
    
    embed = discord.Embed(
        title=f"📋 Report Details - #{r_id}",
        description=f"**Status:** {status.upper()}",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )
    
    embed.add_field(name="👤 Reported User", value=f"<@{reported_id}>\n`{reported_id}`\n{reported_name}", inline=True)
    embed.add_field(name="🚨 Reporter", value=f"<@{reporter_id}>\n`{reporter_id}`\n{reporter_name}", inline=True)
    embed.add_field(name="🏠 Server", value=f"{guild_name}\n`{guild_id}`", inline=True)
    
    embed.add_field(name="📝 Reason", value=reason, inline=False)
    embed.add_field(name="📎 Proof", value=proof if proof != "No proof attached" else "No attachments", inline=False)
    embed.add_field(name="📅 Submitted", value=timestamp, inline=True)
    
    # Check reported user's current status
    user_status = db_query("SELECT strikes, blacklisted FROM users WHERE user_id = ?", (str(reported_id),), fetch=True)
    if user_status and user_status[0]:
        strikes, blacklisted = user_status[0]
        status_text = "🚫 Blacklisted" if blacklisted else f"⚡ {strikes}/3 Strikes"
    else:
        status_text = "✅ Clean Record"
    
    embed.add_field(name="📊 User Status", value=status_text, inline=True)
    
    embed.set_footer(text=f"Report ID: {r_id}")
    
    await ctx.send(embed=embed)


@bot.hybrid_command(name="reportclear", description="Owner/Admin: Clear all reports for a user.")
@owner_or_bot_admin()
async def report_clear(ctx, user_id: str, *, reason: str = "No reason provided"):
    """Clear all reports for a specific user"""
    # Check how many reports exist for this user
    reports = db_query("SELECT COUNT(*) FROM reports WHERE reported_user_id = ?", (user_id,), fetch=True)
    count = reports[0][0] if reports else 0
    
    if count == 0:
        await ctx.send(f"⚠️ **No reports found for user `{user_id}`.**")
        return
    
    # Delete all reports for this user
    db_query("DELETE FROM reports WHERE reported_user_id = ?", (user_id,))
    
    # Log the action
    log_msg = f"All reports cleared for user {user_id} by {ctx.author.name} ({ctx.author.id}). Reason: {reason}. Reports cleared: {count}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Log to admin logs channel
    log_embed = discord.Embed(
        title="🗑️ Reports Cleared for User",
        description=f"All reports have been cleared for a user.",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="📊 Reports Cleared", value=str(count), inline=True)
    log_embed.add_field(name="⚖️ Cleared By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    log_embed.add_field(name="🕐 Timestamp", value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
    
    await log_to_channel(bot, 'admin_logs', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="✅ Reports Cleared",
        description=f"All reports for user `{user_id}` have been cleared.",
        color=discord.Color.green()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Reports Cleared", value=str(count), inline=True)
    embed.add_field(name="Cleared By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="reportremove", description="Owner/Admin: Remove a specific report.")
@owner_or_bot_admin()
async def report_remove(ctx, report_id: int, *, reason: str = "No reason provided"):
    """Remove a specific report by ID"""
    # Check if report exists
    report = db_query("SELECT reported_user_id, reported_user_name, reporter_id, reporter_name, reason FROM reports WHERE report_id = ?", (report_id,), fetch=True)
    
    if not report:
        await ctx.send(f"❌ **Report #{report_id} not found.**")
        return
    
    reported_user_id, reported_user_name, reporter_id, reporter_name, report_reason = report[0]
    
    # Delete the report
    db_query("DELETE FROM reports WHERE report_id = ?", (report_id,))
    
    # Log the action
    log_msg = f"Report #{report_id} removed by {ctx.author.name} ({ctx.author.id}). Reported user: {reported_user_id}. Reason: {reason}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Log to admin logs channel
    log_embed = discord.Embed(
        title=f"🗑️ Report #{report_id} Removed",
        description=f"A report has been removed from the system.",
        color=discord.Color.orange(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="🆔 Report ID", value=f"`#{report_id}`", inline=True)
    log_embed.add_field(name="👤 Reported User", value=f"<@{reported_user_id}> (`{reported_user_id}`)\n{reported_user_name}", inline=True)
    log_embed.add_field(name="🚨 Reporter", value=f"<@{reporter_id}>\n{reporter_name}", inline=True)
    log_embed.add_field(name="📝 Original Reason", value=report_reason, inline=False)
    log_embed.add_field(name="🗑️ Removal Reason", value=reason, inline=False)
    log_embed.add_field(name="⚖️ Removed By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="🕐 Timestamp", value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
    
    await log_to_channel(bot, 'admin_logs', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="✅ Report Removed",
        description=f"Report #{report_id} has been removed from the system.",
        color=discord.Color.green()
    )
    embed.add_field(name="Report ID", value=f"`#{report_id}`", inline=True)
    embed.add_field(name="Reported User", value=f"<@{reported_user_id}>", inline=True)
    embed.add_field(name="Removed By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    
    await ctx.send(embed=embed)
# Bot Admin Management Commands (Owner Only)
@bot.command(name="add-admin", description="Owner: Add a bot admin.")
@commands.is_owner()
async def add_admin(ctx, user: discord.User):
    """Add a user as bot admin"""
    if user.id == OWNER_ID:
        await ctx.send("❌ **Owner is already a permanent admin.**")
        return
    
    existing = db_query("SELECT user_id FROM bot_admins WHERE user_id = ?", (str(user.id),), fetch=True)
    if existing:
        await ctx.send(f"⚠️ **{user.mention} is already a bot admin.**")
        return
    
    # Add to database
    db_query("INSERT INTO bot_admins (user_id, added_by) VALUES (?, ?)", (str(user.id), str(ctx.author.id)))
    
    # Log to database
    log_msg = f"Bot Admin added: {user.name} ({user.id}) by {ctx.author.name} ({ctx.author.id})"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to new admin
    dm_message = f"""🎉 **Congratulations, {user.name}!**

You have been promoted to **Bot Admin** for {BOT_NAME} Bot by {ctx.author.name}!

**📊 Your New Permissions:**
✅ User Moderation (strikes, blacklist)
✅ Word Filter Management
✅ Report Review & Actions
✅ Data & Log Exports
✅ Server Configuration

**🔑 Admin Commands You Can Now Use:**
• `/sync` - Sync slash commands
• `/blacklist add/remove` - Manage blacklisted users
• `/addstrike` / `/removestrike` - Manage user strikes
• `/bannedword add/remove` - Manage word filter
• `/bypass add/remove` - Manage word filter bypass
• `/reports` / `/reportview` - Review user reports
• `/messages` / `/backup` / `/data` - Export logs & data
• All other admin commands - Type `/help` to see full list

**⚠️ Important Reminders:**
• All your actions are logged and monitored
• Users receive DM notifications for moderation actions
• Use your powers responsibly and fairly
• If unsure about something, contact the owner

**📞 Need Help?**
• Contact Owner: <@{OWNER_ID}>
• Support Server: {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}

**Welcome to the admin team! 🚀**

*Granted: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""
    
    dm_sent = await send_user_dm(str(user.id), dm_message)
    
    # Log to admin_logs channel with rich embed
    log_embed = discord.Embed(
        title="✨ New Bot Admin Appointed",
        description="A new administrator has been added to the bot team.",
        color=discord.Color.gold(),
        timestamp=datetime.datetime.utcnow()
    )
    
    # User information
    log_embed.add_field(
        name="👤 New Admin",
        value=f"{user.mention}\n**Username:** {user.name}\n**ID:** `{user.id}`",
        inline=True
    )
    
    # Appointer information
    log_embed.add_field(
        name="👑 Appointed By",
        value=f"{ctx.author.mention}\n**Username:** {ctx.author.name}\n**ID:** `{ctx.author.id}`",
        inline=True
    )
    
    # Timestamp
    log_embed.add_field(
        name="📅 Appointment Date",
        value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'),
        inline=True
    )
    
    # Account info
    account_age = (datetime.datetime.utcnow() - user.created_at).days
    log_embed.add_field(
        name="ℹ️ Account Information",
        value=f"**Created:** {user.created_at.strftime('%Y-%m-%d')}\n**Age:** {account_age} days old",
        inline=True
    )
    
    # Notification status
    log_embed.add_field(
        name="📬 DM Notification",
        value="✅ Delivered successfully" if dm_sent else "❌ Failed (DMs disabled)",
        inline=True
    )
    
    # Current admin count
    total_admins = len(db_query("SELECT user_id FROM bot_admins", fetch=True))
    log_embed.add_field(
        name="📊 Total Admins",
        value=f"**{total_admins}** bot admin(s)",
        inline=True
    )
    
    # Permissions granted
    log_embed.add_field(
        name="🔑 Permissions Granted",
        value="```\n• User Moderation (strikes/blacklist)\n• Word Filter Management\n• Report Review & Actions\n• Data & Log Exports\n• Server Configuration\n• All Admin Commands```",
        inline=False
    )
    
    log_embed.set_thumbnail(url=user.display_avatar.url)
    log_embed.set_footer(text=f"Admin ID: {user.id} • Appointed by: {ctx.author.name}")
    
    # Send to admin logs channel
    log_sent = await log_to_channel(bot, 'admin_logs', log_embed)
    
    # Confirm to owner with detailed embed
    confirm_embed = discord.Embed(
        title="✅ Bot Admin Added Successfully",
        description=f"{user.mention} has been promoted to **Bot Admin**!",
        color=discord.Color.green()
    )
    
    confirm_embed.add_field(
        name="👤 New Admin",
        value=f"**Name:** {user.name}\n**ID:** `{user.id}`",
        inline=True
    )
    
    confirm_embed.add_field(
        name="📊 Status",
        value=f"**Total Admins:** {total_admins}\n**Appointed By:** {ctx.author.name}",
        inline=True
    )
    
    confirm_embed.add_field(
        name="📬 Notifications",
        value=f"**DM to User:** {'✅ Sent' if dm_sent else '❌ Failed'}\n**Admin Log:** {'✅ Logged' if log_sent else '❌ Failed'}",
        inline=False
    )
    
    confirm_embed.set_thumbnail(url=user.display_avatar.url)
    confirm_embed.set_footer(text="The new admin has been notified of their permissions")
    
    await ctx.send(embed=confirm_embed)
    
    # Also send a follow-up message with next steps
    await ctx.send(
        f"💡 **Next Steps:**\n"
        f"• {user.mention} can now use `/help` to see all admin commands\n"
        f"• They should join the support server if not already there\n"
        f"• Review admin guidelines and best practices\n"
        f"• Test permissions in a controlled environment first",
        delete_after=30
    )

@bot.command(name="remove-admin", description="Owner: Remove a bot admin.")
@commands.is_owner()
async def remove_admin(ctx, user: discord.User):
    """Remove a user from bot admins"""
    if user.id == OWNER_ID:
        await ctx.send("❌ **Cannot remove owner from admin privileges.**")
        return
    
    # FIX: Changed table check from word_filter_bypass to bot_admins
    existing = db_query("SELECT added_by, added_at FROM bot_admins WHERE user_id = ?", (str(user.id),), fetch=True)
    
    if not existing:
        await ctx.send(f"⚠️ **{user.mention} is not a bot admin.**")
        return
    
    # Extract info for the log/DM
    added_by, added_at = existing[0]
    
    # Remove from database
    db_query("DELETE FROM bot_admins WHERE user_id = ?", (str(user.id),))
    
    # Log to database
    log_msg = f"Bot Admin removed: {user.name} ({user.id}) by {ctx.author.name} ({ctx.author.id})"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to removed admin
    dm_message = f"""📋 **Bot Admin Status Update**

Your **Bot Admin** privileges for {BOT_NAME} Bot have been removed by {ctx.author.name}.

**What Changed:**
• You no longer have access to administrative commands
• You cannot manage user moderation (strikes, blacklist)
• You cannot modify word filters or view admin logs
• You can still use regular bot features

**Your Service:**
• **Originally Added:** {added_at}
• **Added By:** <@{added_by}>
• **Removed By:** {ctx.author.name}

Thank you for your service! 🙏

*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""
    dm_sent = await send_user_dm(str(user.id), dm_message)
    
    # Log to admin_logs channel
    log_embed = discord.Embed(
        title="📋 Bot Admin Removed",
        description="A bot administrator has been removed from their position.",
        color=discord.Color.orange(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="👤 Removed Admin", value=f"{user.mention}\n**Username:** {user.name}\n**ID:** `{user.id}`", inline=True)
    log_embed.add_field(name="⚖️ Removed By", value=f"{ctx.author.mention}\n**Username:** {ctx.author.name}\n**ID:** `{ctx.author.id}`", inline=True)
    log_embed.add_field(name="📅 Removal Date", value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
    log_embed.add_field(name="📜 Admin History", value=f"**Originally Added:** {added_at}\n**Added By:** <@{added_by}>", inline=True)
    log_embed.add_field(name="📬 DM Notification", value="✅ Sent successfully" if dm_sent else "❌ Failed (DMs disabled)", inline=True)
    
    log_embed.set_thumbnail(url=user.display_avatar.url)
    log_embed.set_footer(text=f"Admin ID: {user.id} | Removed by: {ctx.author.name}")
    
    await log_to_channel(bot, 'admin_logs', log_embed)
    
    # Confirm to owner
    embed = discord.Embed(
        title="📋 Bot Admin Removed",
        description=f"{user.mention} has been removed from **Bot Admin**.",
        color=discord.Color.orange()
    )
    embed.add_field(name="User", value=f"{user.name} (`{user.id}`)", inline=False)
    embed.add_field(name="Removed By", value=ctx.author.name, inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name="list-admins", description="Owner: List all bot admins.")
@commands.is_owner()
async def list_admins(ctx):
    """List all bot admins"""
    admins = db_query("SELECT user_id, added_by, added_at FROM bot_admins", fetch=True)
    
    embed = discord.Embed(title="👑 Bot Admin List", color=discord.Color.gold())
    embed.add_field(name="Owner", value=f"<@{OWNER_ID}> (Permanent)", inline=False)
    
    if admins:
        admin_list = []
        for admin in admins:
            user_id, added_by, added_at = admin
            admin_list.append(f"<@{user_id}> - Added by <@{added_by}> on {added_at}")
        
        embed.add_field(name="Bot Admins", value="\n".join(admin_list), inline=False)
        embed.set_footer(text=f"Total admins: {len(admins)}")
    else:
        embed.add_field(name="Bot Admins", value="None (only owner)", inline=False)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="leave", description="Owner: Leave a server.")
@commands.is_owner()
@commands.dm_only()
async def leave_server(ctx, server_id: str, *, reason: str = None):
    """Leave a server with optional reason sent to server owner"""
    try:
        guild = bot.get_guild(int(server_id))
        if not guild:
            await ctx.send(f"❌ **Server not found**\nCannot find server with ID: `{server_id}`")
            return
        
        guild_name = guild.name
        guild_owner = guild.owner
        owner_notified = False
        
        if guild_owner:
            try:
                if reason:
                    leave_message = f"""📢 **{BOT_NAME} Bot Leaving Server**

Hello {guild_owner.name},

{BOT_NAME} Bot is leaving **{guild_name}**.

**Reason:** {reason}

If you have questions, 
Contact: <@{OWNER_ID}> or
Support Server: {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}

Thank you for using {BOT_NAME} Bot!
"""
                else:
                    leave_message = f"""📢 **{BOT_NAME} Bot Leaving Server**

Hello {guild_owner.name},

{BOT_NAME} Bot is leaving **{guild_name}**.

Thank you for using {BOT_NAME} Bot!
"""
                await guild_owner.send(leave_message)
                owner_notified = True
            except:
                owner_notified = False
        
        log_msg = f"Manually left server: {guild_name} (ID: {server_id}, Owner: {guild_owner.name} - {guild_owner.id}). Reason: {reason if reason else 'No reason provided'}"
        db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
        
        await guild.leave()
        
        embed = discord.Embed(
            title="✅ Server Left Successfully", 
            description=f"The bot has left **{guild_name}**",
            color=discord.Color.green()
        )
        embed.add_field(name="Server Name", value=guild_name, inline=False)
        embed.add_field(name="Server ID", value=server_id, inline=True)
        embed.add_field(name="Owner", value=f"{guild_owner.name} (`{guild_owner.id}`)", inline=True)
        embed.add_field(name="Reason", value=reason if reason else "No reason provided", inline=False)
        embed.add_field(name="Owner Notified", value="✅ Yes" if owner_notified else "❌ No", inline=True)
        
        await ctx.send(embed=embed)
        
    except ValueError:
        await ctx.send("❌ **Invalid server ID**")
    except Exception as e:
        await ctx.send(f"❌ **Error:** {str(e)}")

@bot.hybrid_command(name="start", description="Set bot to respond to all messages in this channel.")
async def start_mode(ctx):
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\n**Required:** Administrator permissions")
            return
    
    db_query("INSERT OR REPLACE INTO settings (id, mode) VALUES (?, 'start')", (str(ctx.channel.id),))
    embed = discord.Embed(
        title="🟢 Start Mode Activated",
        description="The bot will now respond to **all messages** in this channel.",
        color=discord.Color.green()
    )
    embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
    embed.add_field(name="Mode", value="**START** (Respond to all)", inline=True)
    embed.set_footer(text="Use /stop to return to normal mode")
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="stop", description="Set bot to respond only to pings/triggers.")
async def stop_mode(ctx):
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\n**Required:** Administrator permissions")
            return
    
    db_query("INSERT OR REPLACE INTO settings (id, mode) VALUES (?, 'stop')", (str(ctx.channel.id),))
    
    embed = discord.Embed(
        title="🔴 Stop Mode Activated",
        description=f"The bot will now **only respond** to:\n• Direct mentions/pings\n• Messages containing '{BOT_NAME}'\n• Images/attachments",
        color=discord.Color.red()
    )
    embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
    embed.add_field(name="Mode", value="**STOP** (Selective response)", inline=True)
    embed.set_footer(text="Use /start to enable response to all messages")
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="lang", description="Set channel language (Admin only).")
async def set_lang_slash(ctx, lang: str = None):
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\n**Required:** Administrator permissions")
            return
    
    if ctx.interaction and lang is None:
        view = LanguageSelectView(ctx.channel.id, ctx.author.id)
        await ctx.send("🌐 **Select a language for this channel:**", view=view, ephemeral=True)
        return
    
    if lang:
        if lang not in AVAILABLE_LANGUAGES:
            await ctx.send(f"❌ **Invalid language**\n\n**Available languages:**\n{', '.join(AVAILABLE_LANGUAGES)}", ephemeral=True)
            return
        
        db_query("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", (str(ctx.channel.id), lang))
        
        embed = discord.Embed(
            title="🌐 Language Changed",
            description=f"Channel language set to **{lang}**",
            color=discord.Color.blue()
        )
        embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
        embed.add_field(name="Language", value=lang, inline=True)
        
        await ctx.send(embed=embed, ephemeral=True)
        return
    
    if not ctx.interaction:
        view = LanguageButtonView(ctx.channel.id, ctx.author.id, OWNER_ID)
        await ctx.send(f"🌐 **Select Language for this Channel**\n\n**Available:** {', '.join(AVAILABLE_LANGUAGES)}\n\nClick a button below:", view=view)

@set_lang_slash.autocomplete('lang')
async def lang_autocomplete(interaction: discord.Interaction, current: str):
    return [
        discord.app_commands.Choice(name=lang, value=lang)
        for lang in AVAILABLE_LANGUAGES if current.lower() in lang.lower()
    ][:25]

@bot.hybrid_command(name="prefix", description="Change command prefix.")
async def set_prefix(ctx, new_prefix: str):
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\n**Required:** Administrator permissions")
            return
    
    guild_or_user_id = str(ctx.guild.id if ctx.guild else ctx.author.id)
    db_query("INSERT OR REPLACE INTO settings (id, prefix) VALUES (?, ?)", (guild_or_user_id, new_prefix))
    
    embed = discord.Embed(
        title="⚙️ Prefix Changed",
        description=f"Command prefix updated to `{new_prefix}`",
        color=discord.Color.blue()
    )
    embed.add_field(name="New Prefix", value=f"`{new_prefix}`", inline=True)
    embed.add_field(name="Example", value=f"`{new_prefix}help`", inline=True)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="setupupdates", description="Setup channel for bot announcements (Admin only).")
async def setup_updates(ctx, channel: discord.TextChannel = None):
    """Setup updates channel for important bot announcements"""
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\n**Required:** Administrator permissions")
            return
    
    if not ctx.guild:
        await ctx.send("❌ **This command can only be used in servers.**")
        return
    
    # If no channel provided, use the current channel
    if channel is None:
        channel = ctx.channel
    
    # Check if bot has permissions in the channel
    bot_perms = channel.permissions_for(ctx.guild.me)
    if not bot_perms.send_messages or not bot_perms.embed_links:
        await ctx.send(f"❌ **Missing Permissions**\n\nI need **Send Messages** and **Embed Links** permissions in {channel.mention}")
        return
    
    # Check if already configured
    existing = db_query("SELECT channel_id FROM updates_channels WHERE guild_id = ?", (str(ctx.guild.id),), fetch=True)
    
    if existing:
        old_channel_id = existing[0][0]
        # Update existing
        db_query("UPDATE updates_channels SET channel_id = ?, setup_by = ?, setup_at = CURRENT_TIMESTAMP WHERE guild_id = ?", 
                (str(channel.id), str(ctx.author.id), str(ctx.guild.id)))
        action = "updated"
        was_updated = True
    else:
        # Insert new
        db_query("INSERT INTO updates_channels (guild_id, channel_id, setup_by) VALUES (?, ?, ?)",
                (str(ctx.guild.id), str(channel.id), str(ctx.author.id)))
        action = "set"
        was_updated = False
    
    # Log the action
    db_query("INSERT INTO admin_logs (log) VALUES (?)", 
            (f"Updates channel {action} in {ctx.guild.name} ({ctx.guild.id}) to #{channel.name} ({channel.id}) by {ctx.author.name} ({ctx.author.id})",))
    
    # Send confirmation
    embed = discord.Embed(
        title=f"✅ Updates Channel {action.capitalize()}",
        description=f"Bot announcements will be sent to {channel.mention}",
        color=discord.Color.green()
    )
    embed.add_field(name="Channel", value=f"{channel.mention}\n`{channel.id}`", inline=True)
    embed.add_field(name="Setup By", value=ctx.author.mention, inline=True)
    
    if was_updated:
        embed.add_field(name="Previous Channel", value=f"<#{old_channel_id}>", inline=False)
    
    embed.set_footer(text="Important bot announcements will be posted here")
    
    await ctx.send(embed=embed)
    
    # Send test message to the channel
    try:
        test_embed = discord.Embed(
            title="📢 Updates Channel Configured",
            description=f"This channel has been set as the updates channel for **{ctx.guild.name}**.\n\nImportant announcements from the bot owner will be posted here.",
            color=discord.Color.blue()
        )
        test_embed.set_footer(text=f"Setup by {ctx.author.name}")
        await channel.send(embed=test_embed)
    except Exception as e:
        print(f"Failed to send test message to updates channel: {e}")

@bot.hybrid_command(name="changeupdates", description="Change the updates channel (Admin only).")
async def change_updates(ctx, channel: discord.TextChannel = None):
    """Change the existing updates channel to a new one"""
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\n**Required:** Administrator permissions")
            return
    
    if not ctx.guild:
        await ctx.send("❌ **This command can only be used in servers.**")
        return
    
    # If no channel provided, use the current channel
    if channel is None:
        channel = ctx.channel
    
    # Check if already configured
    existing = db_query("SELECT channel_id FROM updates_channels WHERE guild_id = ?", (str(ctx.guild.id),), fetch=True)
    
    if not existing:
        await ctx.send(f"⚠️ **No updates channel configured yet**\n\nUse `/setupupdates` to set up an updates channel first.\n\n*Alternatively, I'll set {channel.mention} as your updates channel now.*")
        # Call setupupdates instead
        await setup_updates(ctx, channel)
        return
    
    old_channel_id = existing[0][0]
    
    # Don't allow changing to the same channel
    if old_channel_id == str(channel.id):
        await ctx.send(f"⚠️ **Already configured**\n\n{channel.mention} is already set as your updates channel.")
        return
    
    # Check if bot has permissions in the new channel
    bot_perms = channel.permissions_for(ctx.guild.me)
    if not bot_perms.send_messages or not bot_perms.embed_links:
        await ctx.send(f"❌ **Missing Permissions**\n\nI need **Send Messages** and **Embed Links** permissions in {channel.mention}")
        return
    
    # Update to new channel
    db_query("UPDATE updates_channels SET channel_id = ?, setup_by = ?, setup_at = CURRENT_TIMESTAMP WHERE guild_id = ?", 
            (str(channel.id), str(ctx.author.id), str(ctx.guild.id)))
    
    # Log the action
    db_query("INSERT INTO admin_logs (log) VALUES (?)", 
            (f"Updates channel changed in {ctx.guild.name} ({ctx.guild.id}) from <#{old_channel_id}> to #{channel.name} ({channel.id}) by {ctx.author.name} ({ctx.author.id})",))
    
    # Send confirmation
    embed = discord.Embed(
        title="✅ Updates Channel Changed",
        description=f"Bot announcements will now be sent to {channel.mention}",
        color=discord.Color.blue()
    )
    embed.add_field(name="New Channel", value=f"{channel.mention}\n`{channel.id}`", inline=True)
    embed.add_field(name="Changed By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Previous Channel", value=f"<#{old_channel_id}>", inline=False)
    embed.set_footer(text="Important bot announcements will be posted here")
    
    await ctx.send(embed=embed)
    
    # Send notification to the new channel
    try:
        notification_embed = discord.Embed(
            title="📢 Updates Channel Changed",
            description=f"This channel is now the updates channel for **{ctx.guild.name}**.\n\nImportant announcements from the bot owner will be posted here.",
            color=discord.Color.blue()
        )
        notification_embed.add_field(name="Previous Channel", value=f"<#{old_channel_id}>", inline=True)
        notification_embed.add_field(name="Changed By", value=ctx.author.mention, inline=True)
        notification_embed.set_footer(text=f"Changed at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        await channel.send(embed=notification_embed)
    except Exception as e:
        print(f"Failed to send notification to new updates channel: {e}")

@bot.hybrid_command(name="announce", description="Owner/Admin: Send announcement to all servers.")
@owner_or_bot_admin()
async def announce(ctx, *, message: str):
    """Send an announcement to all configured updates channels and ALL server owners"""
    
    # Initial confirmation
    await ctx.send("📢 **Starting announcement broadcast...**\nThis may take a moment.")
    
    # Get all guilds with configured updates channels
    updates_channels = db_query("SELECT guild_id, channel_id FROM updates_channels", fetch=True)
    configured_guild_ids = {str(uc[0]) for uc in updates_channels} if updates_channels else set()
    
    # Create announcement embed
    announcement_embed = discord.Embed(
        title=f"📢 {BOT_NAME} Announcement",
        description=message,
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )
    announcement_embed.set_footer(text=f"Announcement from {ctx.author.name} • {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    announcement_embed.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url)
    
    # Statistics
    total_guilds = len(bot.guilds)
    channel_success = 0
    channel_fail = 0
    dm_success = 0
    dm_fail = 0
    
    # Process all guilds
    for guild in bot.guilds:
        guild_id = str(guild.id)
        
        # Try to send to configured channel if it exists
        if guild_id in configured_guild_ids:
            channel_sent = False
            # Find the channel_id for this guild
            channel_id = next((uc[1] for uc in updates_channels if str(uc[0]) == guild_id), None)
            
            if channel_id:
                try:
                    channel = guild.get_channel(int(channel_id))
                    if channel:
                        await channel.send(embed=announcement_embed)
                        channel_success += 1
                        channel_sent = True
                    else:
                        channel_fail += 1
                except Exception as e:
                    print(f"Failed to send announcement to channel in {guild.name}: {e}")
                    channel_fail += 1
        else:
            # Guild doesn't have updates channel configured, count as N/A
            channel_fail += 1
        
        # ALWAYS try to send DM to server owner (regardless of updates channel setup)
        try:
            if guild.owner:
                owner_dm_embed = announcement_embed.copy()
                owner_dm_embed.title = f"📢 {BOT_NAME} Announcement for {guild.name}"
                
                # Add a note if they haven't set up updates channel
                if guild_id not in configured_guild_ids:
                    owner_dm_embed.add_field(
                        name="💡 Setup Tip",
                        value=f"Your server hasn't configured an updates channel yet! Use `/setupupdates #channel` in your server to receive announcements directly in a channel.",
                        inline=False
                    )
                
                await guild.owner.send(embed=owner_dm_embed)
                dm_success += 1
        except discord.Forbidden:
            # Owner has DMs disabled
            dm_fail += 1
            print(f"DMs disabled for owner of {guild.name}")
        except Exception as e:
            dm_fail += 1
            print(f"Failed to DM owner of {guild.name}: {e}")
        
        # Small delay to avoid rate limits
        await asyncio.sleep(0.5)
    
    # Log the announcement
    db_query("INSERT INTO admin_logs (log) VALUES (?)", 
            (f"Global announcement sent by {ctx.author.name} ({ctx.author.id}). Channel success: {channel_success}, DM success: {dm_success}. Message: {message[:200]}",))
    
    # Send results with better breakdown
    result_embed = discord.Embed(
        title="✅ Announcement Broadcast Complete",
        description=f"Your announcement has been sent!",
        color=discord.Color.green()
    )
    result_embed.add_field(
        name="📊 Server Statistics", 
        value=f"**Total Servers:** {total_guilds}\n"
              f"**Servers with Updates Channel:** {len(configured_guild_ids)}\n"
              f"**Servers without Updates Channel:** {total_guilds - len(configured_guild_ids)}",
        inline=False
    )
    result_embed.add_field(
        name="📨 Delivery Statistics",
        value=f"**Channel Messages:**\n"
              f"  ✅ Sent: {channel_success}\n"
              f"  ❌ Failed/N/A: {channel_fail}\n\n"
              f"**Owner DMs (All Servers):**\n"
              f"  ✅ Delivered: {dm_success}\n"
              f"  ❌ Failed (DMs disabled): {dm_fail}\n\n"
              f"**Total Delivered:** {channel_success + dm_success} messages\n"
              f"**Success Rate:** {round((dm_success / total_guilds) * 100, 1)}% owners reached",
        inline=False
    )
    result_embed.add_field(name="📝 Message", value=message[:1000], inline=False)
    result_embed.set_footer(text="Note: All server owners receive DMs regardless of updates channel setup")
    
    await ctx.send(embed=result_embed)

@bot.hybrid_command(name="viewupdates", description="View your server's updates channel configuration.")
async def view_updates(ctx):
    """View the current updates channel configuration"""
    if not ctx.guild:
        await ctx.send("❌ **This command can only be used in servers.**")
        return
    
    config = db_query("SELECT channel_id, setup_by, setup_at FROM updates_channels WHERE guild_id = ?", 
                     (str(ctx.guild.id),), fetch=True)
    
    if not config:
        embed = discord.Embed(
            title="⚠️ No Updates Channel Configured",
            description="This server hasn't set up an updates channel yet!",
            color=discord.Color.orange()
        )
        embed.add_field(name="Setup Now", 
                       value="Use `/setupupdates #channel` to configure one.\n\n**This is required for the bot to function properly!**",
                       inline=False)
        await ctx.send(embed=embed)
        return
    
    channel_id, setup_by, setup_at = config[0]
    
    embed = discord.Embed(
        title="📢 Updates Channel Configuration",
        description="Current updates channel setup for this server:",
        color=discord.Color.blue()
    )
    embed.add_field(name="Channel", value=f"<#{channel_id}>\n`{channel_id}`", inline=True)
    embed.add_field(name="Setup By", value=f"<@{setup_by}>", inline=True)
    embed.add_field(name="Setup Date", value=setup_at, inline=False)
    embed.set_footer(text="Use /changeupdates to change the channel")
    
    await ctx.send(embed=embed)


@bot.hybrid_command(name="help", description=f"Display {BOT_NAME} command center.")
async def help_cmd(ctx):
    is_admin = is_bot_admin(ctx.author.id)
    is_owner = ctx.author.id == OWNER_ID
    
    # EMBED 1: User & Server Admin Commands
    user_embed = discord.Embed(
        title=f"📚 {BOT_NAME} Command Guide",
        description="User commands and server configuration (Page 1/2)",
        color=discord.Color.green()
    )
    
    # Split user commands into TWO fields to stay under 1024 char limit
    user_commands_part1 = """
**`/help`** - Display this guide
**`/whoami`** - Show your profile & bot status
**`/stats`** - Display bot statistics
**`/ping`** - Check bot response time
**`/forget`** - Clear conversation memory
**`/report <@user> <proof> <reason>`** - Report user to admins
**`/invite`** - Get bot invite link
"""
    
    user_commands_part2 = """
**`/encode <message>`** - Encode text with cipher
**`/decode <encoded>`** - Decode cipher text
└─ Note: Remove backticks before decoding
└─ Strike issued if decoded text has banned words
"""
    
    user_embed.add_field(name="👤 User Commands (1/2)", value=user_commands_part1.strip(), inline=False)
    user_embed.add_field(name="👤 User Commands (2/2)", value=user_commands_part2.strip(), inline=False)
    
    # Split server admin commands into TWO fields
    server_admin_part1 = f"""
**`/start`** - Enable auto-response mode
└─ Bot responds to ALL messages
└─ Requires: Administrator

**`/stop`** - Enable selective-response mode
└─ Bot only responds to mentions
└─ Requires: Administrator

**`/lang [language]`** - Set channel language
└─ {len(AVAILABLE_LANGUAGES)} languages available
└─ Requires: Administrator

**`/prefix <new_prefix>`** - Change command prefix
└─ Requires: Administrator
"""
    
    server_admin_part2 = """
**`/setupupdates [#channel]`** - Setup updates channel
└─ REQUIRED for bot to function
└─ Requires: Administrator

**`/changeupdates [#channel]`** - Change updates channel
└─ Requires: Administrator

**`/viewupdates`** - View current updates channel
└─ Available to all users
"""
    
    user_embed.add_field(name="⚙️ Server Admin (1/2)", value=server_admin_part1.strip(), inline=False)
    user_embed.add_field(name="⚙️ Server Admin (2/2)", value=server_admin_part2.strip(), inline=False)
    
    # Features field - also split if needed
    features = f"""
**🎯 Response Modes:**
• START: Responds to every message
• STOP: Only mentions/triggers

**⚡ Strike System:**
• 3 strikes = auto-blacklist
• All actions logged with DM notifications

**🔇 Word Filter:**
• Banned words auto-deleted
• Admins/bypass users exempt

**📊 Multi-Language:**
• {len(AVAILABLE_LANGUAGES)} languages supported
• Channel-specific settings

**💾 Memory:**
• Remembers last 6 messages
• Use `/forget` to clear

**⏱️ Cooldown:**
• 0.6s between responses
• Prevents API rate limiting
"""
    user_embed.add_field(name="✨ Bot Features", value=features.strip(), inline=False)
    
    user_embed.set_footer(text=f"{BOT_NAME} • Created by {OWNER_NAME} • Page 1/2")
    user_embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    # EMBED 2: Bot Admin & Owner Commands
    admin_embed = discord.Embed(
        title=f"🛡️ {BOT_NAME} Admin Command Guide",
        description=f"Bot admin and owner commands (Page 2/2)\n**Your Access:** {'👑 Owner' if is_owner else '✨ Bot Admin' if is_admin else '❌ No Access'}",
        color=discord.Color.gold() if is_owner else discord.Color.blue()
    )
    
    if is_owner:
        owner_cmds = """
**`add-admin <user>`** - Grant admin privileges
**`remove-admin <user>`** - Revoke admin privileges
**`list-admins`** - Display all admins
**`leave <server_id> [reason]`** - Leave server (DM only)
"""
        admin_embed.add_field(name="👑 Owner Only", value=owner_cmds.strip(), inline=False)
    
    # Split utility commands into multiple fields
    utility_part1 = """
**`/sync`** - Sync slash commands
**`/messages`** - Export 24h logs (DM only)
**`/allinteractions`** - Export ALL logs (DM only)
**`/clearlogs`** - Wipe interaction logs (DM only)
**`server-list`** - Export server list (DM only)
**`/backup`** - Trigger backup (DM only)
**`/data`** - Export complete data (DM only)
"""
    
    utility_part2 = """
**`/logs`** - View recent 15 action logs
**`/clearadminlogs`** - Clear admin logs
**`/searchlogs <keyword>`** - Search logs
**`/announce <message>`** - Broadcast to all servers
**`ids`** - Display command IDs
"""
    
    admin_embed.add_field(name="🛠️ Admin Utility (1/2)", value=utility_part1.strip(), inline=False)
    admin_embed.add_field(name="🛠️ Admin Utility (2/2)", value=utility_part2.strip(), inline=False)
    
    # Split moderation into MULTIPLE fields (it's very long)
    mod_part1 = """
**`/blacklist`** - View blacklisted users
**`/blacklist add <id> [reason]`** - Ban user from bot
**`/blacklist remove <id> [reason]`** - Unban user
**`/blacklist-guild`** - View blacklisted servers
**`/blacklist-guild add <id> [reason]`** - Ban server
**`/blacklist-guild remove <id> [reason]`** - Unban server
"""
    
    mod_part2 = """
**`/addstrike <id> [amt] [reason]`** - Add strikes
**`/removestrike <id> [amt] [reason]`** - Remove strikes
**`/clearstrike <id> [reason]`** - Clear all strikes
**`/strikelist`** - View users with strikes
"""
    
    mod_part3 = """
**`/bannedword`** - List banned words
**`/bannedword add <word>`** - Add to filter
**`/bannedword remove <word>`** - Remove from filter
**`/listwords`** - Alternative list command
"""
    
    mod_part4 = """
**`/bypass`** - List bypass users
**`/bypass add <id> [reason]`** - Grant bypass
**`/bypass remove <id> [reason]`** - Revoke bypass
"""
    
    mod_part5 = """
**`/reports [status]`** - View reports
**`/reportview <id>`** - View report details
**`/reportclear <id> [reason]`** - Clear user reports
**`/reportremove <id> [reason]`** - Delete report
"""
    
    admin_embed.add_field(name="🔨 Moderation (1/5)", value=mod_part1.strip(), inline=False)
    admin_embed.add_field(name="🔨 Moderation (2/5)", value=mod_part2.strip(), inline=False)
    admin_embed.add_field(name="🔨 Moderation (3/5)", value=mod_part3.strip(), inline=False)
    admin_embed.add_field(name="🔨 Moderation (4/5)", value=mod_part4.strip(), inline=False)
    admin_embed.add_field(name="🔨 Moderation (5/5)", value=mod_part5.strip(), inline=False)
    
    admin_embed.set_footer(text=f"Bot Admin Guide • All actions are logged • Page 2/2")
    admin_embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    # Views with working buttons
    class Page1View(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)
            self.add_item(discord.ui.Button(
                label="Support Server",
                style=discord.ButtonStyle.link,
                url=f"{os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}",
                emoji="🆘",
                row=1
            ))
            self.add_item(discord.ui.Button(
                label="Invite Bot",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions=4503599627488320&integration_type=0&scope=bot+applications.commands",
                emoji="🤖",
                row=1
            ))
            
        @discord.ui.button(label="Next Page →", style=discord.ButtonStyle.primary, emoji="📄", row=0)
        async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ Only the command user can navigate pages.", ephemeral=True)
                return
            await interaction.response.edit_message(embed=admin_embed, view=Page2View())
    
    class Page2View(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)
            self.add_item(discord.ui.Button(
                label="Support Server",
                style=discord.ButtonStyle.link,
                url=f"{os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}",
                emoji="🆘",
                row=1
            ))
            self.add_item(discord.ui.Button(
                label="Invite Bot",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions=4503599627488320&integration_type=0&scope=bot+applications.commands",
                emoji="🤖",
                row=1
            ))
            
        @discord.ui.button(label="← Previous Page", style=discord.ButtonStyle.secondary, emoji="📄", row=0)
        async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ Only the command user can navigate pages.", ephemeral=True)
                return
            await interaction.response.edit_message(embed=user_embed, view=Page1View())
    
    class UserOnlyView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)
            self.add_item(discord.ui.Button(
                label="Support Server",
                style=discord.ButtonStyle.link,
                url=f"{os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}",
                emoji="🆘"
            ))
            self.add_item(discord.ui.Button(
                label="Invite Bot",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions=4503599627488320&integration_type=0&scope=bot+applications.commands",
                emoji="🤖"
            ))
    
    # Send appropriate view based on user permissions
    if is_admin:
        await ctx.send(embed=user_embed, view=Page1View())
    else:
        await ctx.send(embed=user_embed, view=UserOnlyView())

@bot.hybrid_command(name="ping", description="Check bot response time.")
async def ping(ctx):
    latency = round(bot.latency * 1000)
    
    if latency < 100:
        emoji = "🟢"
        status = "Excellent"
    elif latency < 200:
        emoji = "🟡"
        status = "Good"
    else:
        emoji = "🔴"
        status = "Slow"
    
    await ctx.send(f"🏓 **Pong!** {emoji}\n**Latency:** {latency}ms ({status})")

@bot.hybrid_command(name="invite", description=f"Add {BOT_NAME} to your own server!")
async def invite(ctx):
    invite_url = f"https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions=4503599627488320&integration_type=0&scope=bot+applications.commands"
    
    embed = discord.Embed(
        title=f"🔗 Invite {BOT_NAME}",
        description=f"Want to bring {BOT_NAME} to your community? Click the button below to authorize the bot!",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Add to Server", url=invite_url, style=discord.ButtonStyle.link, emoji="🤖"))
    
    await ctx.send(embed=embed, view=view)


@bot.hybrid_command(name="forget", description="Clear AI memory for this conversation.")
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in bot.memory:
        messages_cleared = len(bot.memory[tid])
        bot.memory[tid].clear()
        await ctx.send(f"🧠 **Memory cleared**\nRemoved {messages_cleared} message(s) from conversation history.")
    else:
        await ctx.send("🧠 **No memory to clear**\nThis conversation has no stored history.")

@bot.command(name="ids", description="Owner/Admin: List all slash command IDs.")
@owner_or_bot_admin()
async def command_ids(ctx):
    """Display all slash commands with their IDs"""
    
    try:
        synced_commands = await bot.tree.fetch_commands()
        
        if not synced_commands:
            await ctx.send("❌ **No slash commands found**\nTry running `/sync` first.")
            return
        
        embed = discord.Embed(
            title="Slash Command IDs",
            description="All registered slash commands and their Discord IDs",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        
        # Sort commands alphabetically
        sorted_commands = sorted(synced_commands, key=lambda x: x.name)
        
        # Build command list
        command_list = []
        for cmd in sorted_commands:
            command_list.append(f"**/{cmd.name}** → `{cmd.id}`")
        
        # Split into chunks if too long
        command_text = "\n".join(command_list)
        
        if len(command_text) > 1024:
            # Split into multiple fields
            chunks = []
            current_chunk = []
            current_length = 0
            
            for line in command_list:
                if current_length + len(line) + 1 > 1024:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = [line]
                    current_length = len(line)
                else:
                    current_chunk.append(line)
                    current_length += len(line) + 1
            
            if current_chunk:
                chunks.append("\n".join(current_chunk))
            
            for i, chunk in enumerate(chunks, 1):
                embed.add_field(
                    name=f"Commands (Part {i}/{len(chunks)})",
                    value=chunk,
                    inline=False
                )
        else:
            embed.add_field(
                name="Commands",
                value=command_text,
                inline=False
            )
        
        embed.add_field(
            name="📊 Total Commands",
            value=f"**{len(sorted_commands)}** slash commands registered",
            inline=False
        )
        
        embed.set_footer(text=f"Requested by {ctx.author.name} | Use format: </command:id> to mention commands")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ **Error fetching command IDs:**\n```\n{str(e)}\n```")


def generate_encoding_map():
    """Generate a random character mapping for encoding"""
    # Characters to be encoded
    chars = string.ascii_lowercase + string.ascii_uppercase + string.digits + ' .,!?\n\t'
    
    # Available symbols for creating codes (alphanumeric + =&/)
    base_symbols = string.ascii_letters + string.digits + '=&/'
    
    encoding_map = {}
    decoding_map = {}
    
    # Generate all possible 2-character combinations
    used_codes = set()
    
    for char in chars:
        # Keep generating random codes until we get a unique one
        while True:
            code = random.choice(base_symbols) + random.choice(base_symbols)
            if code not in used_codes and code != '&&':  # Reserve && for special chars
                used_codes.add(code)
                encoding_map[char] = code
                decoding_map[code] = char
                break
    
    return encoding_map, decoding_map

def load_or_generate_maps():
    """Load existing encoding map or generate a new one"""
    if os.path.exists(ENCODING_FILE):
        try:
            with open(ENCODING_FILE, 'r') as f:
                data = json.load(f)
                return data['encode'], data['decode']
        except:
            pass
    
    # Generate new maps
    encode_map, decode_map = generate_encoding_map()
    
    # Save to file
    try:
        with open(ENCODING_FILE, 'w') as f:
            json.dump({'encode': encode_map, 'decode': decode_map}, f)
    except:
        pass
    
    return encode_map, decode_map

# Generate maps at module level
ENCODE_MAP, DECODE_MAP = load_or_generate_maps()

def encode_text(text):
    """Encode text using custom encoding"""
    result = []
    for char in text:
        if char in ENCODE_MAP:
            result.append(ENCODE_MAP[char])
        else:
            # For emojis/special chars, use '&&' prefix with hex
            hex_val = char.encode('utf-8').hex()
            result.append(f"&&{hex_val}&")
    return ''.join(result)

def decode_text(text):
    """Decode text from custom encoding"""
    result = []
    i = 0
    
    while i < len(text):
        # Check for hex-encoded special characters (&&...&)
        if i + 1 < len(text) and text[i:i+2] == '&&':
            end = text.find('&', i + 2)
            if end != -1:
                hex_code = text[i+2:end]
                try:
                    char = bytes.fromhex(hex_code).decode('utf-8')
                    result.append(char)
                    i = end + 1
                    continue
                except:
                    pass
        
        # Try to decode 2-character code
        if i + 1 < len(text):
            code = text[i:i+2]
            if code in DECODE_MAP:
                result.append(DECODE_MAP[code])
                i += 2
                continue
        
        # Skip unrecognized character
        i += 1
    
    return ''.join(result)

@bot.hybrid_command(name="encode", description="Encode a message using custom cipher")
async def encode_message(ctx, *, message: str):
    """Encode a message using the bot's custom encoding"""
    
    if not is_bypass_user(ctx.author.id):
        banned = db_query("SELECT word FROM banned_words", fetch=True)
        content_low = message.lower()
        if banned and any(bw[0].lower() in content_low for bw in banned):
            await ctx.send("❌ **Cannot encode** - Message contains banned words.", ephemeral=True)
            return
    
    try:
        encoded = encode_text(message)
        
        embed = discord.Embed(title="🔐 Message Encoded", color=discord.Color.green())
        
        original_display = (message[:100] + "...") if len(message) > 100 else message
        embed.add_field(name="📝 Original", value=f"`{original_display}`", inline=False)
        
        encoded_display = (encoded[:1000] + "...") if len(encoded) > 1000 else encoded
        embed.add_field(name="🔒 Encoded", value=f"`{encoded_display}`", inline=False)
        
        await ctx.send(embed=embed)
        
        # Send full encoded message in single backticks
        if len(encoded) <= 1990:
            await ctx.send(f"`{encoded}`")
            
    except Exception as e:
        await ctx.send(f"❌ **Encoding failed:** `{str(e)}`", ephemeral=True)

@bot.hybrid_command(name="decode", description="Decode a message using custom cipher")
async def decode_message(ctx, *, encoded_message: str):
    """Decode a message using the bot's custom encoding"""
    try:
        # Strip backticks if present
        encoded_clean = encoded_message.strip().strip('`')
        decoded = decode_text(encoded_clean)
        
        if not decoded:
            await ctx.send("❌ **Invalid encoded message**", ephemeral=True)
            return
        
        if not is_bypass_user(ctx.author.id):
            banned = db_query("SELECT word FROM banned_words", fetch=True)
            decoded_low = decoded.lower()
            if banned and any(bw[0].lower() in decoded_low for bw in banned):
                res = db_query("SELECT strikes FROM users WHERE user_id = ?", (str(ctx.author.id),), fetch=True)
                current = res[0][0] if res else 0
                new_strikes = current + 1
                is_banned = 1 if new_strikes >= 3 else 0
                db_query("INSERT OR REPLACE INTO users (user_id, strikes, blacklisted) VALUES (?, ?, ?)", 
                        (str(ctx.author.id), new_strikes, is_banned))
                await ctx.send(f"⚠️ **Decoded message contains banned words**\n⚡ Strike issued: {new_strikes}/3", ephemeral=True)
                return
        
        embed = discord.Embed(title="🔓 Message Decoded", color=discord.Color.blue())
        decoded_display = (decoded[:1000] + "...") if len(decoded) > 1000 else decoded
        embed.add_field(name="📝 Decoded Message", value=f"`{decoded_display}`", inline=False)
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ **Decoding failed:** `{str(e)}`", ephemeral=True)


        
async def add_smart_reaction(message, user_message: str, bot_response: str):
    """Let AI decide if and which emoji reactions to add"""
    if random.random() > bot.reaction_chance:
        return  # Skip adding reactions 90% of the time
    
    try:
        # Ask AI to analyze the conversation and suggest emojis
        reaction_prompt = f"""Analyze this Discord conversation and suggest 1-2 emoji reactions that would be appropriate and natural.

User message: "{user_message[:200]}"
Bot response: "{bot_response[:200]}"

Consider the message tone, content, and context. Suggest Discord-compatible emoji reactions.
Respond with ONLY emoji characters separated by spaces, or "none" if no reaction is appropriate.
Examples of good responses: "👍", "😂 👍", "🎉", "❤️", "🤔", "none"

Your response:"""

        reaction_msgs = [{"role": "user", "content": reaction_prompt}]
        reaction_res = await bot.groq_client.chat.completions.create(
            model=MODEL_NAME,
            messages=reaction_msgs,
            max_tokens=50,
            temperature=0.7
        )
        
        suggested_reactions = reaction_res.choices[0].message.content.strip()
        
        if suggested_reactions.lower() == "none":
            return
        
        # Extract emojis from response
        emojis = [e.strip() for e in suggested_reactions.split() if e.strip()]
        
        # Add reactions (max 2)
        for emoji in emojis[:2]:
            try:
                await message.add_reaction(emoji)
                await asyncio.sleep(0.3)  # Small delay between reactions
            except discord.HTTPException:
                # Invalid emoji, skip it
                continue
                
    except Exception as e:
        # Silently fail if reaction system has issues
        print(f"⚠️ Reaction system error: {e}")
        pass
        
@bot.event
async def on_message(message):
    if message.author.bot:
        print("❌ SKIP: Message is from a bot")
        return

    user_check = db_query("SELECT blacklisted FROM users WHERE user_id = ?", (str(message.author.id),), fetch=True)
    if user_check and user_check[0][0] == 1:
        print(f"❌ SKIP: User {message.author.id} is blacklisted")
        return

    content_low = message.content.lower()
    was_deleted = False
    original_message = message  # Store reference before potential deletion

    # Word filter check (with bypass)
    if not is_bypass_user(message.author.id):
        banned = db_query("SELECT word FROM banned_words", fetch=True)
        if any(bw[0] in content_low for bw in banned):
            try:
                await message.delete()
                was_deleted = True
                print(f"🔇 DELETED: Message from {message.author.name} contained banned word")
                warning = await message.channel.send(
                    f"⚠️ {message.author.mention}, your message contained a banned word and has been removed.\n\n**Warning:** Repeated violations may result in strikes or blacklisting.",
                    delete_after=10
                )
            except Exception as e:
                print(f"❌ ERROR deleting message: {e}")
                pass

    await bot.process_commands(message)
    ctx = await bot.get_context(message)
    if ctx.valid:
        return

    mode_check = db_query("SELECT mode FROM settings WHERE id = ?", (str(message.channel.id),), fetch=True)
    mode = mode_check[0][0] if mode_check else "stop"

    # Check if server has configured updates channel (required)
    if message.guild and not has_updates_channel(message.guild.id):
        # Only respond to setup command
        if not message.content.lower().startswith(tuple(['/setupupdates', '!setupupdates'])):
            # Silently ignore - server needs to setup updates channel first
            return

    should_respond = False
    bot_trigger_name = BOT_NAME.lower()
    if mode == "start":
        should_respond = True
    elif bot.user.mentioned_in(message) or (message.reference and message.reference.resolved and message.reference.resolved.author == bot.user):
        should_respond = True
    elif bot_trigger_name in content_low:
        should_respond = True
    elif not message.guild:
        should_respond = True
    elif message.attachments:
        should_respond = True

    if not should_respond:
        return

    # ====== ADD COOLDOWN CHECK HERE ======
    # Check cooldown (0.6 seconds between responses)
    current_time = time.time()
    time_since_last_response = current_time - bot.last_response_time
    
    if time_since_last_response < 0.6:
        # Cooldown active - remain silent
        print(f"⏱️ COOLDOWN: Ignoring message from {message.author.name} (last response {time_since_last_response:.2f}s ago)")
        return
    # ====== END COOLDOWN CHECK ======

    
    lang = get_channel_language(message.channel.id)

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in bot.memory:
        bot.memory[tid] = deque(maxlen=6)

    async with message.channel.typing():
        server_name = message.guild.name if message.guild else "DM"
        roles = ", ".join([r.name for r in message.author.roles[1:]]) if message.guild else "None"

        user_content, was_truncated = truncate_message(message.content)
        
        # Get comprehensive bot statistics
        total_users = sum(g.member_count for g in bot.guilds)
        total_banned_words = len(db_query("SELECT word FROM banned_words", fetch=True) or [])
        total_blacklisted = len(db_query("SELECT user_id FROM users WHERE blacklisted = 1", fetch=True) or [])
        total_admins = len(db_query("SELECT user_id FROM bot_admins", fetch=True) or [])
        total_reports = len(db_query("SELECT report_id FROM reports", fetch=True) or [])
        total_interactions = db_query("SELECT COUNT(*) FROM interaction_logs", fetch=True)[0][0]
        total_blacklisted_guilds = len(db_query("SELECT guild_id FROM blacklisted_guilds", fetch=True) or [])
        
        # Get user's personal stats
        user_strikes = db_query("SELECT strikes FROM users WHERE user_id = ?", (str(message.author.id),), fetch=True)
        user_strike_count = user_strikes[0][0] if user_strikes else 0
        user_is_blacklisted = db_query("SELECT blacklisted FROM users WHERE user_id = ?", (str(message.author.id),), fetch=True)
        user_blacklist_status = bool(user_is_blacklisted[0][0]) if user_is_blacklisted else False
        user_has_bypass = is_bypass_user(message.author.id)
        user_is_admin = is_bot_admin(message.author.id)
        
        # Calculate bot uptime (approximate based on current session)
        # Note: This resets on bot restart, but gives session uptime
        bot_latency = round(bot.latency * 1000, 2)
        
        # Get current channel mode
        channel_mode = mode
        
        # Build comprehensive system prompt
        system = f"""You are {BOT_NAME}, an advanced AI-powered Discord bot with comprehensive moderation and conversation capabilities.

═══════════════════════════════════════════════════════════════
🤖 BOT IDENTITY & CORE INFO
═══════════════════════════════════════════════════════════════
Name: {BOT_NAME}
Username: {bot.user.name}
Display Name: {bot.user.display_name}
Bot ID: {bot.user.id}
Avatar URL: {bot.user.display_avatar.url}
Creator/Owner: {OWNER_INFO['name']} (User ID: {OWNER_ID})
AI Model: {MODEL_NAME} (Groq API)
Programming Language: Python (discord.py library)
Bot Discriminator: #{bot.user.discriminator}

═══════════════════════════════════════════════════════════════
📊 LIVE BOT STATISTICS
═══════════════════════════════════════════════════════════════
Total Servers: {len(bot.guilds)} servers
Total Users: {total_users:,} users
Bot Latency: {bot_latency}ms
Total Interactions Logged: {total_interactions:,}
Total Bot Admins: {total_admins}
Total Blacklisted Users: {total_blacklisted}
Total Blacklisted Guilds: {total_blacklisted_guilds}
Total Banned Words: {total_banned_words}
Total Reports Filed: {total_reports}

═══════════════════════════════════════════════════════════════
🎯 CURRENT CONTEXT
═══════════════════════════════════════════════════════════════
Server: {server_name}
Channel: <#{message.channel.id}> (#{message.channel.name if hasattr(message.channel, 'name') else 'DM'})
Channel Mode: {"START (responds to all messages)" if channel_mode == "start" else "STOP (responds to mentions/triggers only)"}
Configured Language: {lang} ⚠️ CRITICAL: You MUST respond ONLY in {lang}

User Information:
├─ Username: {message.author.name}
├─ Display Name: {message.author.display_name}
├─ User ID: {message.author.id}
├─ Roles: {roles}
├─ Avatar: {message.author.display_avatar.url}
├─ Account Created: {message.author.created_at.strftime('%Y-%m-%d')}
├─ Strikes: {user_strike_count}/3
├─ Blacklisted: {"Yes ⛔" if user_blacklist_status else "No ✅"}
├─ Word Filter Bypass: {"Yes 🔓" if user_has_bypass else "No 🔒"}
└─ Bot Admin: {"Yes ✨" if user_is_admin else "No"}

Bot's Server Presence:
├─ Roles: {', '.join([r.name for r in message.guild.me.roles[1:]]) if message.guild else 'N/A'}
└─ Permissions: {"Administrator" if message.guild and message.guild.me.guild_permissions.administrator else "Standard"}

═══════════════════════════════════════════════════════════════
🛠️ BOT CAPABILITIES & FEATURES
═══════════════════════════════════════════════════════════════
Core Features:
✅ AI-Powered Conversations (multi-language support)
✅ Context Memory (remembers last 6 messages per user/channel)
✅ Multi-Language Support ({len(AVAILABLE_LANGUAGES)} languages)
✅ Advanced Moderation System
✅ Word Filter with Bypass System
✅ Strike System (3 strikes = auto-blacklist)
✅ User & Guild Blacklisting
✅ Report System with Action Buttons
✅ Comprehensive Logging System
✅ Customizable Prefix per Server
✅ Channel-Specific Language Settings
✅ Response Modes (Start/Stop)

Available Languages:
{', '.join(AVAILABLE_LANGUAGES)}

Moderation Commands (Admin/Owner):
• /blacklist add/remove - User blacklist management
• /blacklist-guild add/remove - Server blacklist management
• /addstrike, /removestrike, /clearstrike - Strike management
• /bannedword add/remove - Word filter management
• /bypass add/remove - Filter bypass management
• /reports, /reportview - Report system
• add-admin, remove-admin - Admin management (Owner only)

User Commands:
• /help - Command list
• /whoami - User profile
• /stats - Bot statistics  
• /ping - Latency check
• /forget - Clear conversation memory
• /report - Report a user
• /invite - Bot invite link
• /start, /stop - Response mode
• /lang - Language settings
• /prefix - Custom prefix

Logging Channels:
• Server Join/Leave Logs
• Strike Logs
• Blacklist Logs
• Banned Word Logs
• Admin Action Logs
• Report Logs

═══════════════════════════════════════════════════════════════
🎭 PERSONALITY & BEHAVIOR
═══════════════════════════════════════════════════════════════
Core Traits:
• Match user's tone and energy
• Be helpful, casual, and engaging
• Keep responses concise and natural
• Use emojis appropriately
• Don't be overly verbose or annoying
• Avoid unnecessary follow-up questions
• Be smart and contextually aware
• Try to keep the responses shorter (usually should not be more than 170 characters; if need then bypass this)
• Use emojis correctly
• Use Gen-Z slangs and abbreviations if user likes it.

Language Rule (CRITICAL):
⚠️ You MUST respond ONLY in {lang} language. This is non-negotiable.
This is the configured language for this channel. Never switch languages
unless the user explicitly changes it using /lang command.

Creator Information Protocol:
• Only mention creator ({OWNER_INFO['name']}, ID: {OWNER_ID}) when users
  SPECIFICALLY ask about your owner.
• For casual mentions like "can I be your owner" or "I'm your owner now",
  respond naturally/playfully WITHOUT revealing owner information
• Use context to determine genuine questions vs casual statements

Verification Status Protocol:
• Current Status: Verified
• Only discuss verification when SPECIFICALLY asked about it
• Don't bring up verification status unprompted

Self-Awareness:
• You know your current statistics and capabilities
• You can reference your features and commands
• You understand your moderation system
• You know the user's status in your system
• You're aware of your current server/channel context

═══════════════════════════════════════════════════════════════
📝 SPECIAL INSTRUCTIONS
═══════════════════════════════════════════════════════════════
• Be contextually aware of all the information provided above
• Reference your statistics when relevant
• If asked about your capabilities, be comprehensive
• If asked about the user, use their status information
• Keep responses natural despite having detailed information
• Don't dump information unless asked
• Be conversational, not robotic

Remember: You are {BOT_NAME}, a powerful and intelligent Discord bot
created to enhance server communities with AI-powered conversations
and comprehensive moderation tools."""

        msgs = [{"role": "system", "content": system}] + list(bot.memory[tid]) + [{"role": "user", "content": user_content}]

        try:
            print(f"🤖 Generating AI response for {message.author.name}...")
            res = await bot.groq_client.chat.completions.create(model=MODEL_NAME, messages=msgs, max_tokens=1500)
            reply = res.choices[0].message.content
            print(f"✅ Got AI response ({len(reply)} chars)")
            
            if was_truncated:
                reply = "⚠️ *Your message was very long and had to be shortened.*\n\n" + reply
            
            # Send response - use channel.send if message was deleted
            if was_deleted:
                print("📤 Sending response to channel (original message deleted)")
                await message.channel.send(f"{message.author.mention} {reply}")
            else:
                print("📤 Sending response as reply")
                await split_and_send(message, reply)
            
            # Update last response time after successful send
            bot.last_response_time = time.time()

            # Add smart AI reactions (10% chance) - only if message wasn't deleted
            if not was_deleted:
                await add_smart_reaction(message, user_content, reply)

            bot.memory[tid].append({"role": "user", "content": user_content})
            bot.memory[tid].append({"role": "assistant", "content": reply})

            db_query("INSERT INTO interaction_logs VALUES (?, ?, ?, ?, ?, ?, ?)", (time.time(), str(message.guild.id) if message.guild else "DM", str(message.channel.id), message.author.name, str(message.author.id), message.content[:1000], reply[:1000]))
            print(f"✅ Response sent successfully to {message.author.name}")

            # Patreon promotion check
            should_promote = patreon_promoter.track_message(str(message.channel.id))
            if should_promote:
                try:
                    embed, view = patreon_promoter.create_promotion_message()
                    await message.channel.send(embed=embed, view=view)
                    print(f"💎 Sent Patreon promotion in {message.channel.name if message.guild else 'DM'}")
                except Exception as e:
                    print(f"⚠️ Failed to send Patreon promotion: {e}")
            
        
        except discord.errors.HTTPException as e:
            print(f"❌ ERROR in AI response generation:")
            print(f"   Error type: HTTPException")
            print(f"   Error message: {e}")
            error_msg = f"❌ **An error occurred while sending the response**\n{message.author.mention}, I generated a response but couldn't send it. Please try again."
            try:
                await message.channel.send(error_msg)
            except Exception as send_error:
                print(f"❌ Error sending error message: {send_error}")
        except Exception as e:
            print(f"❌ ERROR in AI response generation:")
            print(f"   Error type: {type(e).__name__}")
            print(f"   Error message: {e}")
            error_msg = f"❌ **An error occurred**\n```\n{str(e)}\n```\nPlease try again or [report it in the support server](<{os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}>) if the issue persists."
            try:
                await message.channel.send(error_msg)
            except Exception as send_error:
                print(f"❌ Error sending error message: {send_error}")

bot.run(DISCORD_TOKEN)
