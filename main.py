# Feel free to use my code; Just make sure to edit the hardcoded ids.

import discord
from discord.ext import commands, tasks
import os, time, datetime, json, sqlite3, asyncio
from groq import AsyncGroq 
from collections import deque

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct" 
OWNER_ID = 1081876265683927080
DB_FILE = "bot_data.db"
JSON_FILE = "bot_data.json"
INTERACTION_JSON = "interaction_logs.json"

# Logging Channels
LOG_CHANNELS = {
    'server_join_leave': 1460868218670420009,
    'strikes': 1460868262932906080,
    'blacklist': 1460868307602378814,
    'banned_words': 1460868341345419275,
    'admin_logs': 1460868388695052442,
    'reports': 1460868441878691922 # Using admin logs channel for reports
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
    'name': 'Ψ.1nOnly.Ψ',
    'id': OWNER_ID,
    'bio': 'Creator and maintainer of flexedAI Discord Bot'
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
        prefix TEXT DEFAULT "!", 
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
    # New table for word filter bypass
    c.execute('''CREATE TABLE IF NOT EXISTS word_filter_bypass (
        user_id TEXT PRIMARY KEY,
        added_by TEXT,
        reason TEXT,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # New table for reports
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
    # New Table for blacklisted guilds
    c.execute('''CREATE TABLE IF NOT EXISTS blacklisted_guilds (
    guild_id TEXT PRIMARY KEY,
    guild_name TEXT,
    blacklisted_by TEXT,
    reason TEXT,
    blacklisted_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
        await message.reply(content)
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
    
    await message.reply(chunks[0])
    
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
    return res[0][0] if res and res[0][0] else "!"

class FlexedBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=get_prefix, intents=discord.Intents.all(), help_command=None)
        self.groq_client = AsyncGroq(api_key=GROQ_API_KEY)
        self.memory = {}

    async def setup_hook(self):
        self.daily_backup.start()
        print(f"✅ {self.user} Online | All Commands Locked & Loaded")
        print(f"🔄 Daily backup task started")

bot = FlexedBot()

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
                    f"""🚫 **flexedAI Bot - Blacklisted Server**

Hello {guild.owner.name},

Your server **{guild.name}** is blacklisted from using flexedAI Bot.

**Reason:** {reason}

The bot has automatically left your server. You cannot re-add this bot while blacklisted.

**Appeal:** Contact <@{OWNER_ID}>
**Join the Support Server:** https://discord.com/invite/XMvPq7W5N4
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
        description=f"flexedAI has been added to a new server!",
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

Thank you for adding **flexedAI Bot** to **{guild.name}**!

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

💡 **Need Help?**
Contact the bot owner: <@{OWNER_ID}>
Join the Support Server: https://discord.com/invite/XMvPq7W5N4
Enjoy using flexedAI! 🎉
"""
        await guild.owner.send(welcome_msg)
    except:
        pass  # Owner has DMs disabled
@bot.event
async def on_guild_remove(guild):
    """Log when bot leaves a server"""
    embed = discord.Embed(
        title="🔴 Bot Left Server",
        description=f"flexedAI has been removed from a server.",
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
                content=f"🌐 Language set to **{lang}** by {interaction.user.mention}.",
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
        f"🚫 **You have been blacklisted from flexedAI Bot**\n\n**Reason:** {reason}\n\n**What this means:**\n• You can no longer use any bot commands\n• The bot will not respond to your messages\n• This action has been logged by bot administrators\n\n**Believe this is a mistake?**\nContact the bot owner: <@{OWNER_ID}>\n**Join the Support Server:** https://discord.com/invite/XMvPq7W5N4\n\n*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*"
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
                dm_message = f"""🚫 **flexedAI Bot - Server Blacklisted**

Hello {guild.owner.name},

Your server **{guild_name}** has been blacklisted from using flexedAI Bot.

**Reason:** {reason}

**What this means:**
• The bot will leave your server immediately
• Your server cannot re-add the bot
• This is a permanent restriction

**Appeal Process:**
If you believe this is a mistake, contact: <@{OWNER_ID}>
**Join the Support Server:** https://discord.com/invite/XMvPq7W5N4
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
            description=f"A server has been permanently blacklisted.",
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
            description=f"Server has been permanently blacklisted.",
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
    # Confirm to command user
    embed = discord.Embed(
        title="✅ User Unblacklisted",
        description=f"User `{user_id}` has been removed from the blacklist.",
        color=discord.Color.green()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Actioned By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="DM Notification", value="✅ Sent" if dm_sent else "❌ Failed (DMs disabled)", inline=True)
    
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
        dm_message += "🚫 **ACCOUNT SUSPENDED**\n\nYou have reached 3 strikes and have been automatically blacklisted from flexedAI Bot.\n\n**What this means:**\n• You can no longer use the bot\n• All access has been revoked\n• This is a permanent suspension unless appealed\n\n**Appeal Process:**\nContact the bot owner: <@!1081876265683927080>"
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
        dm_message += "🎉 **ACCOUNT RESTORED**\n\nYour blacklist has been lifted! You can now use flexedAI Bot again.\n\n**Remember:**\n• Follow community guidelines\n• Avoid accumulating more strikes\n• Be respectful and follow the rules\n\nWelcome back!"
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

You have been granted permission to bypass the word filter in flexedAI Bot.

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
            dm_message += "🚫 **ACCOUNT SUSPENDED**\n\nYou have reached 3 strikes and have been automatically blacklisted from flexedAI Bot.\n\n**Appeal Process:**\nContact the bot owner: <@{OWNER_ID}>"
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
        dm_message = f"🚫 **You have been blacklisted from flexedAI Bot**\n\n**Reason:** Action taken from user report #{self.report_id}\n\n**What this means:**\n• You can no longer use any bot commands\n• The bot will not respond to your messages\n• This action has been logged by bot administrators\n\n**Believe this is a mistake?**\nContact the bot owner: <@{OWNER_ID}>\n\n*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*"
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

You have been promoted to **Bot Admin** for flexedAI Bot by {ctx.author.name}!

As a Bot Admin, you now have access to all moderation and management commands.

**📊 Key Responsibilities:**
• Manage user strikes and blacklists
• Monitor and moderate banned words
• Review user reports
• Export data and logs
• Maintain bot integrity

**⚠️ Important:**
• Use your powers responsibly
• All actions are logged
• Users receive notifications for moderation actions
• Contact <@{OWNER_ID}> for questions

Type `/help` to see all available commands.

Welcome to the team! 🚀

*Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""
    dm_sent = await send_user_dm(str(user.id), dm_message)
    
    # Log to admin_logs channel
    log_embed = discord.Embed(
        title="✨ Bot Admin Added",
        description="A new bot administrator has been appointed.",
        color=discord.Color.gold(),
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name="👤 New Admin", value=f"{user.mention}\n**Username:** {user.name}\n**ID:** `{user.id}`", inline=True)
    log_embed.add_field(name="👑 Appointed By", value=f"{ctx.author.mention}\n**Username:** {ctx.author.name}\n**ID:** `{ctx.author.id}`", inline=True)
    log_embed.add_field(name="📅 Appointed Date", value=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
    log_embed.add_field(name="ℹ️ Account Info", value=f"**Account Created:** {user.created_at.strftime('%Y-%m-%d')}\n**Account Age:** {(datetime.datetime.utcnow() - user.created_at).days} days", inline=True)
    log_embed.add_field(name="📬 DM Notification", value="✅ Sent successfully" if dm_sent else "❌ Failed (DMs disabled)", inline=True)
    log_embed.add_field(name="🔑 Permissions Granted", value="• User moderation (strikes, blacklist)\n• Word filter management\n• Report review\n• Data exports\n• Admin log access", inline=False)
    
    log_embed.set_thumbnail(url=user.display_avatar.url)
    log_embed.set_footer(text=f"Admin ID: {user.id} | Added by: {ctx.author.name}")
    
    await log_to_channel(bot, 'admin_logs', log_embed)
    
    # Confirm to owner
    embed = discord.Embed(
        title="✅ Bot Admin Added",
        description=f"{user.mention} has been promoted to **Bot Admin**!",
        color=discord.Color.gold()
    )
    embed.add_field(name="User", value=f"{user.name} (`{user.id}`)", inline=False)
    embed.add_field(name="Added By", value=ctx.author.name, inline=True)
    embed.add_field(name="DM Notification", value="✅ Sent successfully" if dm_sent else "❌ Failed (DMs disabled)", inline=True)
    embed.set_thumbnail(url=user.display_avatar.url)
    
    await ctx.send(embed=embed)


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

Your **Bot Admin** privileges for flexedAI Bot have been removed by {ctx.author.name}.

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
                    leave_message = f"""📢 **flexedAI Bot Leaving Server**

Hello {guild_owner.name},

flexedAI Bot is leaving **{guild_name}**.

**Reason:** {reason}

If you have questions, 
Contact: <@{OWNER_ID}> or
Support Server: https://discord.com/invite/XMvPq7W5N4

Thank you for using flexedAI Bot!
"""
                else:
                    leave_message = f"""📢 **flexedAI Bot Leaving Server**

Hello {guild_owner.name},

flexedAI Bot is leaving **{guild_name}**.

Thank you for using flexedAI Bot!
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
        description="The bot will now **only respond** to:\n• Direct mentions/pings\n• Messages containing 'flexedAI'\n• Images/attachments",
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

@bot.hybrid_command(name="help", description="Display command center.")
async def help_cmd(ctx):
    is_admin = is_bot_admin(ctx.author.id)
    
    embed = discord.Embed(
        title="📡 flexedAI Command Center",
        description="Here are all the commands you have access to:",
        color=discord.Color.blue()
    )
    
    # 1. OWNER SECTION
    if ctx.author.id == OWNER_ID:
        embed.add_field(
            name="👑 Owner Only Commands", 
            value="`add-admin`, `remove-admin`, `list-admins`, `leave` (DM only)", 
            inline=False
        )

    # 2. ADMIN/MODERATOR SECTION
    if is_admin:
        embed.add_field(
            name="🛡️ Owner/Admin Commands (DM Only)", 
            value="`sync`, `messages`, `clearlogs`, `server-list`, `backup`, `data`, `allinteractions`", 
            inline=False
        )
        embed.add_field(
            name="🔨 Moderation Commands", 
            value="`/blacklist`, `/addstrike`, `/removestrike`, `/strikelist`, `/clearstrike`, `/bannedword`, `/bypass`, `/logs`, `/searchlogs`, `/clearadminlogs`, `/reports`, `/reportview`", 
            inline=False
        )
        embed.add_field(
            name="⚙️ Settings (Admin Required)", 
            value="`/start`, `/stop`, `/lang`, `/prefix`", 
            inline=False
        )
        embed.set_footer(text="✨ You have Bot Admin privileges")
    else:
        # 3. REGULAR USER SECTION (Added for non-admins)
        embed.set_footer(text="Use /report to flag misbehavior to admins")

    # 4. GENERAL UTILITY SECTION (Available to everyone)
    embed.add_field(
        name="📊 Utility Commands", 
        value="`/help`, `/whoami`, `/stats`, `/ping`, `/forget`, `/report`", 
        inline=False
    )
    
    embed.add_field(
        name="ℹ️ About the Owner",
        value=f"Bot created and maintained by <@{OWNER_ID}>",
        inline=False
    )
    
    # Send the final built embed
    await ctx.send(embed=embed)

@bot.hybrid_command(name="whoami", description="Show your Discord profile.")
async def whoami(ctx):
    user = ctx.author
    roles = ", ".join([r.name for r in user.roles[1:]]) if ctx.guild else "N/A"
    
    embed = discord.Embed(
        title=f"👤 {user.name}",
        description=f"Here's your profile information:",
        color=user.color
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="User ID", value=f"`{user.id}`", inline=False)
    embed.add_field(name="Display Name", value=user.display_name, inline=True)
    embed.add_field(name="Server Roles", value=roles if roles != "N/A" else "None", inline=False)
    
    if user.id == OWNER_ID:
        embed.add_field(name="Bot Status", value="👑 **Bot Owner**", inline=False)
    elif is_bot_admin(user.id):
        embed.add_field(name="Bot Status", value="✨ **Bot Admin**", inline=False)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="stats", description="Check bot statistics.")
async def stats(ctx):
    latency = round(bot.latency * 1000, 2)
    guild_count = len(bot.guilds)
    
    embed = discord.Embed(
        title="📊 Bot Statistics",
        color=discord.Color.blue()
    )
    embed.add_field(name="🏓 Latency", value=f"{latency}ms", inline=True)
    embed.add_field(name="🌐 Servers", value=guild_count, inline=True)
    embed.add_field(name="👥 Users", value=sum(g.member_count for g in bot.guilds), inline=True)
    
    await ctx.send(embed=embed)

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
        
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_check = db_query("SELECT blacklisted FROM users WHERE user_id = ?", (str(message.author.id),), fetch=True)
    if user_check and user_check[0][0] == 1:
        return

    # Define content_low early so it's available for all checks
    content_low = message.content.lower()
    
    # Track if the message was deleted to avoid "404 Not Found" on replies
    was_deleted = False

    # Word filter check (with bypass)
    if not is_bypass_user(message.author.id):
        banned = db_query("SELECT word FROM banned_words", fetch=True)
        if any(bw[0] in content_low for bw in banned):
            try:
                await message.delete()
                was_deleted = True
                warning = await message.channel.send(
                    f"⚠️ {message.author.mention}, your message contained a banned word and has been removed.\n\n**Warning:** Repeated violations may result in strikes or blacklisting.",
                    delete_after=10
                )
            except:
                pass
            # Note: We continue here so it can still trigger AI/Owner responses even if deleted

    await bot.process_commands(message)
    ctx = await bot.get_context(message)
    if ctx.valid:
        return

    mode_check = db_query("SELECT mode FROM settings WHERE id = ?", (str(message.channel.id),), fetch=True)
    mode = mode_check[0][0] if mode_check else "stop"

    should_respond = False

    if mode == "start":
        should_respond = True
    elif bot.user.mentioned_in(message) or (message.reference and message.reference.resolved and message.reference.resolved.author == bot.user):
        should_respond = True
    elif "flexedAI" in content_low:
        should_respond = True
    elif not message.guild:
        should_respond = True
    elif message.attachments:
        should_respond = True

    if not should_respond:
        return

    lang = get_channel_language(message.channel.id)

    # Check for owner-related questions
    owner_keywords = [
        "who created you", "who made you", "who is your owner", "who owns you",
        "your creator", "your owner", "who built you", "who developed you"
    ]
    
    if any(keyword in content_low for keyword in owner_keywords):
        owner_response = f"""👑 **About My Owner**

I was created and am maintained by <@{OWNER_ID}>!

**Owner Information:**
• **Name:** {OWNER_INFO['name']}
• **User ID:** `{OWNER_ID}`
• **Role:** Bot Creator & Primary Developer

My owner built me to be a helpful, intelligent AI assistant for Discord communities. They continue to maintain and improve my features to serve users better.

If you have any questions, feedback, or issues, you can contact them directly!
"""
        if was_deleted:
            await message.channel.send(owner_response)
        else:
            await message.reply(owner_response)
        return

    # Check for verification question
    verification_keywords = [
        "are you verified", "are you a verified bot", "is this bot verified",
        "verified bot", "discord verified", "are you official",
        "official bot", "verified badge"
    ]
    
    if any(keyword in content_low for keyword in verification_keywords):
        verification_response = f"""✅ **Verification Status**

**Discord Bot Verification** is a badge that indicates a bot has been verified by Discord. To qualify for verification, a bot must meet these requirements:

🔹 **Be in 75+ servers** (I'm currently in {len(bot.guilds)} servers)
🔹 **Properly use Discord's API**
🔹 **Follow Discord's Terms of Service**
🔹 **Have a clear purpose and functionality**

Verified bots display a ✓ checkmark badge next to their name. Verification helps users trust that the bot is legitimate and maintained by its developers.

If you'd like to know more about my features, use `/help`!
"""
        if was_deleted:
            await message.channel.send(verification_response)
        else:
            await message.reply(verification_response)
        return

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in bot.memory:
        bot.memory[tid] = deque(maxlen=6)

    async with message.channel.typing():
        server_name = message.guild.name if message.guild else "DM"
        roles = ", ".join([r.name for r in message.author.roles[1:]]) if message.guild else "None"

        user_content, was_truncated = truncate_message(message.content)
        
        system = f"""You are flexedAI, a smart Discord bot created by {OWNER_INFO['name']} (ID: {OWNER_ID}).

Basic Info about configuration, user and server: 
Language: {lang} (CRITICAL: You MUST respond ONLY in {lang} language. This is the configured language for this channel. Do not switch languages under any circumstances unless the user explicitly changes it using the /lang or !lang command.)
Server: {server_name}
Username: {message.author.name}
Roles: {roles}
Display Name: {message.author.display_name}
Profile Picture: {message.author.display_avatar.url}
Current Channel: <#{message.channel.id}>

Bot's Info:
Bot's Display Name: {bot.user.display_name}
Bot's Username: {bot.user.name}
Bot ID: {bot.user.id}
Bot's Server Roles: {message.guild.me.roles if message.guild else 'N/A'}
Bot's Avatar: {bot.user.display_avatar.url}
Bot Owner: {OWNER_INFO['name']} (ID: {OWNER_ID})

Match the user's tone and energy. Be helpful, casual, and engaging.
Have shorter responses. No unnecessary verbosity.
Just don't make silly mistakes. Try to be engaging, not annoying.
Do not ask questions at the end of responses like "What else can I help you with?" or "What do you want me to know?" etc.

If asked about your creator or owner, mention that you were created by {OWNER_INFO['name']} (User ID: {OWNER_ID}).
Take use of emojis too, accordingly.
REMEMBER: Respond ONLY in {lang} language.
Don't tell your owner's name or id unless asked.
Make your responses shorter, don't ask questions at the end of the response. Try to be more chill, be aware of the guild emojis too."""

        msgs = [{"role": "system", "content": system}] + list(bot.memory[tid]) + [{"role": "user", "content": user_content}]

        try:
            res = await bot.groq_client.chat.completions.create(model=MODEL_NAME, messages=msgs, max_tokens=1500)
            reply = res.choices[0].message.content
            
            if was_truncated:
                reply = "⚠️ *Your message was very long and had to be shortened.*\n\n" + reply
            
            # Logic to handle sending the response even if the original message is deleted
            if was_deleted:
                # Prepend mention since we can't 'reply' to a ghost message
                final_reply = f"{message.author.mention} {reply}"
                # Use simple send instead of split_and_send which relies on message reference
                await message.channel.send(final_reply)
            else:
                await split_and_send(message, reply)

            bot.memory[tid].append({"role": "user", "content": user_content})
            bot.memory[tid].append({"role": "assistant", "content": reply})

            db_query("INSERT INTO interaction_logs VALUES (?, ?, ?, ?, ?, ?, ?)", (time.time(), str(message.guild.id) if message.guild else "DM", str(message.channel.id), message.author.name, str(message.author.id), message.content[:1000], reply[:1000]))
        except Exception as e:
            error_msg = f"❌ **An error occurred**\n```\n{str(e)}\n```\nPlease try again or contact <@{OWNER_ID}> if the issue persists."
            if was_deleted:
                await message.channel.send(error_msg)
            else:
                await message.reply(error_msg)

bot.run(DISCORD_TOKEN)
