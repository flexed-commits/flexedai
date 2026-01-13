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

# Discord message limits
MAX_MESSAGE_LENGTH = 2000
MAX_INPUT_TOKENS = 8000  # Conservative limit for input

# Available languages constant
AVAILABLE_LANGUAGES = [
    "English", "Hindi", "Hinglish", "Spanish", "French", 
    "German", "Portuguese", "Italian", "Japanese", "Korean",
    "Chinese", "Russian", "Arabic", "Turkish", "Dutch"
]

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

    # New table for bot admins
    c.execute('''CREATE TABLE IF NOT EXISTS bot_admins (
        user_id TEXT PRIMARY KEY,
        added_by TEXT,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
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

    cutoff = time.time() - 86400
    c.execute("SELECT * FROM interaction_logs WHERE timestamp > ? ORDER BY timestamp DESC", (cutoff,))
    interactions = c.fetchall()
    data['interaction_logs'] = [{"timestamp": i[0], "guild_id": i[1], "channel_id": i[2], "user_name": i[3], "user_id": i[4], "prompt": i[5], "response": i[6]} for i in interactions]

    conn.close()
    return data

# --- UTILITY FUNCTIONS ---
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
    
    # Split by paragraphs first to maintain readability
    paragraphs = content.split('\n\n')
    current_chunk = ""
    chunks = []
    
    for para in paragraphs:
        # If a single paragraph is too long, split by sentences
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
    
    # Send first chunk as reply, rest as follow-ups
    first_message = await message.reply(chunks[0])
    
    for chunk in chunks[1:]:
        await message.channel.send(chunk)
        await asyncio.sleep(0.5)  # Small delay to maintain order

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

@tasks.loop(hours=24)
async def daily_backup_task():
    try:
        owner = await bot.fetch_user(OWNER_ID)
        db_data = export_db_to_json()
        timestamp = int(time.time())
        filename = f"backup_{timestamp}.json"

        with open(filename, "w") as f:
            json.dump(db_data, f, indent=2)

        embed = discord.Embed(title="📦 24-Hour Database Backup", description=f"**Timestamp:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", color=discord.Color.green())
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
        
        await interaction.response.send_message(f"🌐 Language set to **{selected_lang}**.", ephemeral=True)
        self.view.stop()
# Language Button View (for prefix command)
class LanguageButtonView(discord.ui.View):
    def __init__(self, channel_id, author_id, owner_id):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.author_id = author_id
        self.owner_id = owner_id
        self.message = None
        
        # Create buttons in rows (5 per row max)
        for i, lang in enumerate(AVAILABLE_LANGUAGES):
            button = discord.ui.Button(
                label=lang,
                style=discord.ButtonStyle.primary,
                custom_id=f"lang_{lang}",
                row=i // 5  # Distribute across rows
            )
            button.callback = self.create_callback(lang)
            self.add_item(button)
    
    def create_callback(self, lang):
        async def callback(interaction: discord.Interaction):
            # Check if user is admin or owner
            if interaction.user.id != self.owner_id:
                if not interaction.guild or not interaction.user.guild_permissions.administrator:
                    await interaction.response.send_message("❌ Only admins and bot owner can change language settings.", ephemeral=True)
                    return
            
            # Set the language
            db_query("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", (str(self.channel_id), lang))
            
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            # Update the message with disabled buttons
            await interaction.response.edit_message(
                content=f"🌐 Language set to **{lang}** by {interaction.user.mention}.",
                view=self
            )
            
            # Send ephemeral confirmation
            await interaction.followup.send(f"✅ Language set to **{lang}**.", ephemeral=True)
            
            self.stop()
        
        return callback

# Permission checker decorator
def owner_or_bot_admin():
    async def predicate(ctx):
        if ctx.author.id == OWNER_ID:
            return True
        if is_bot_admin(ctx.author.id):
            return True
        await ctx.send("❌ **Permission Denied**\nThis command requires: **Bot Owner** or **Bot Admin** privileges.")
        return False
    return commands.check(predicate)

@bot.hybrid_command(name="sync", description="Owner/Admin: Sync slash commands.")
@owner_or_bot_admin()
async def sync(ctx):
    await bot.tree.sync()
    await ctx.send("🚀 Commands synced globally.")

@bot.hybrid_command(name="allinteractions", description="Owner/Admin: Export ALL interaction logs.")
@owner_or_bot_admin()
@commands.dm_only()
async def all_interactions(ctx):
    rows = db_query("SELECT * FROM interaction_logs ORDER BY timestamp DESC", fetch=True)

    if not rows:
        await ctx.send("❌ No interaction logs found.")
        return

    data = [{"timestamp": r[0], "guild_id": r[1], "channel_id": r[2], "user_name": r[3], "user_id": r[4], "prompt": r[5], "response": r[6]} for r in rows]
    fname = f"all_logs_{int(time.time())}.json"

    with open(fname, "w") as f: 
        json.dump(data, f, indent=2)

    await ctx.send(f"📊 Exported {len(data)} total interactions.", file=discord.File(fname))
    os.remove(fname)

@bot.hybrid_command(name="messages", description="Owner/Admin: Export interaction logs (last 24h).")
@owner_or_bot_admin()
@commands.dm_only()
async def messages(ctx):
    cutoff = time.time() - 86400
    rows = db_query("SELECT * FROM interaction_logs WHERE timestamp > ? ORDER BY timestamp DESC", (cutoff,), fetch=True)
    data = [{"timestamp": r[0], "guild_id": r[1], "channel_id": r[2], "user_name": r[3], "user_id": r[4], "prompt": r[5], "response": r[6]} for r in rows]
    fname = f"logs_{int(time.time())}.json"

    with open(fname, "w") as f: 
        json.dump(data, f, indent=2)

    await ctx.send(file=discord.File(fname))
    os.remove(fname)

@bot.hybrid_command(name="clearlogs", description="Owner/Admin: Wipe interaction logs.")
@owner_or_bot_admin()
@commands.dm_only()
async def clear_logs(ctx):
    db_query("DELETE FROM interaction_logs")
    await ctx.send("🗑️ Interaction logs cleared.")

@bot.command(name="server-list", description="Owner/Admin: Export server list.")
@owner_or_bot_admin()
@commands.dm_only()
async def server_list(ctx):
    guilds = [{"id": str(g.id), "name": g.name, "member_count": g.member_count} for g in bot.guilds]
    fname = f"servers_{int(time.time())}.json"

    with open(fname, "w") as f:
        json.dump(guilds, f, indent=2)

    await ctx.send(file=discord.File(fname))
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
        "server_configurations": {},
        "channel_configurations": {},
        "statistics": {
            "total_strikes_issued": 0,
            "total_blacklists": 0,
            "total_banned_words": 0,
            "channels_in_start_mode": 0,
            "channels_in_stop_mode": 0
        }
    }

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

    c.execute("SELECT word FROM banned_words")
    banned = c.fetchall()
    data['banned_words'] = [w[0] for w in banned]
    data['statistics']['total_banned_words'] = len(data['banned_words'])

    c.execute("SELECT user_id, added_by, added_at FROM bot_admins")
    admins = c.fetchall()
    data['bot_admins'] = [{"user_id": a[0], "added_by": a[1], "added_at": a[2]} for a in admins]

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

    c.execute("SELECT COUNT(*) FROM interaction_logs")
    interaction_count = c.fetchone()[0]
    data['bot_info']['total_interactions_logged'] = interaction_count

    c.execute("SELECT log, timestamp FROM admin_logs ORDER BY timestamp DESC LIMIT 100")
    logs = c.fetchall()
    data['admin_logs_recent'] = [{"log": l[0], "timestamp": l[1]} for l in logs]

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

    embed.add_field(name="📊 Servers", value=data['bot_info']['total_servers'], inline=True)
    embed.add_field(name="👥 Users Tracked", value=data['bot_info']['total_users_tracked'], inline=True)
    embed.add_field(name="💬 Total Interactions", value=data['bot_info']['total_interactions_logged'], inline=True)

    embed.add_field(name="🚫 Blacklisted Users", value=data['statistics']['total_blacklists'], inline=True)
    embed.add_field(name="⚡ Total Strikes Issued", value=data['statistics']['total_strikes_issued'], inline=True)
    embed.add_field(name="🔇 Banned Words", value=data['statistics']['total_banned_words'], inline=True)

    embed.add_field(name="🟢 Channels (Start Mode)", value=data['statistics']['channels_in_start_mode'], inline=True)
    embed.add_field(name="🔴 Channels (Stop Mode)", value=data['statistics']['channels_in_stop_mode'], inline=True)
    embed.add_field(name="⚙️ Server Configs", value=len(data['server_configurations']), inline=True)

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

    embed = discord.Embed(title="📦 Manual Database Backup", description=f"**Timestamp:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", color=discord.Color.blue())
    embed.add_field(name="Users", value=len(db_data['users']), inline=True)
    embed.add_field(name="Banned Words", value=len(db_data['banned_words']), inline=True)
    embed.add_field(name="Interactions (24h)", value=len(db_data['interaction_logs']), inline=True)

    await ctx.send(embed=embed, file=discord.File(filename))
    os.remove(filename)

@bot.hybrid_group(name="blacklist", description="Owner/Admin: Manage user access.", invoke_without_command=True)
@owner_or_bot_admin()
async def blacklist_group(ctx):
    res = db_query("SELECT user_id FROM users WHERE blacklisted = 1", fetch=True)
    ids = ", ".join([r[0] for r in res]) if res else "None"
    await ctx.send(f"📋 **Blacklisted Users:** `{ids}`")

@blacklist_group.command(name="add")
@owner_or_bot_admin()
async def bl_add(ctx, user_id: str, *, reason: str = "No reason provided"):
    db_query("INSERT OR REPLACE INTO users (user_id, blacklisted) VALUES (?, 1)", (user_id,))
    log_msg = f"User {user_id} BLACKLISTED by {ctx.author.name}. Reason: {reason}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_sent = await send_user_dm(user_id, f"🚫 **You have been blacklisted from FlexedAI Bot**\n\n**Reason:** {reason}\n\nYou can no longer use the bot.")
    
    await ctx.send(f"🚫 `{user_id}` has been blacklisted.\n**Reason:** {reason}\n**DM Sent:** {'✅ Yes' if dm_sent else '❌ Failed'}")

@blacklist_group.command(name="remove")
@owner_or_bot_admin()
async def bl_rem(ctx, user_id: str, *, reason: str = "No reason provided"):
    db_query("UPDATE users SET blacklisted = 0 WHERE user_id = ?", (user_id,))
    log_msg = f"User {user_id} removed from blacklist by {ctx.author.name}. Reason: {reason}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_sent = await send_user_dm(user_id, f"✅ **Your blacklist has been removed**\n\n**Reason:** {reason}\n\nYou can now use FlexedAI Bot again.")
    
    await ctx.send(f"✅ `{user_id}` restored.\n**Reason:** {reason}\n**DM Sent:** {'✅ Yes' if dm_sent else '❌ Failed'}")

@bot.hybrid_command(name="addstrike", description="Owner/Admin: Add strikes to a user.")
@owner_or_bot_admin()
async def add_strike(ctx, user_id: str, amount: int = 1, *, reason: str = "No reason provided"):
    res = db_query("SELECT strikes FROM users WHERE user_id = ?", (user_id,), fetch=True)
    current_strikes = res[0][0] if res else 0
    new_strikes = current_strikes + amount
    is_banned = 1 if new_strikes >= 3 else 0

    db_query("INSERT OR REPLACE INTO users (user_id, strikes, blacklisted) VALUES (?, ?, ?)", (user_id, new_strikes, is_banned))

    log_msg = f"Strike to {user_id} by {ctx.author.name}. Total: {new_strikes}/3. Reason: {reason}"
    if is_banned:
        log_msg += f" User {user_id} AUTO-BANNED."

    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_message = f"⚡ **You have received {amount} strike(s)**\n\n**Reason:** {reason}\n**Total Strikes:** {new_strikes}/3"
    if is_banned:
        dm_message += "\n\n🚫 **You have been automatically blacklisted** for reaching 3 strikes. You can no longer use the bot."
    
    dm_sent = await send_user_dm(user_id, dm_message)
    
    await ctx.send(f"⚡ {log_msg}\n**DM Sent:** {'✅ Yes' if dm_sent else '❌ Failed'}")

@bot.hybrid_command(name="removestrike", description="Owner/Admin: Remove strikes from a user.")
@owner_or_bot_admin()
async def remove_strike(ctx, user_id: str, amount: int = 1, *, reason: str = "No reason provided"):
    res = db_query("SELECT strikes FROM users WHERE user_id = ?", (user_id,), fetch=True)

    if not res or res[0][0] == 0:
        await ctx.send(f"⚠️ User `{user_id}` has no strikes to remove.")
        return

    current_strikes = res[0][0]
    new_strikes = max(0, current_strikes - amount)
    is_banned = 1 if new_strikes >= 3 else 0

    db_query("UPDATE users SET strikes = ?, blacklisted = ? WHERE user_id = ?", (new_strikes, is_banned, user_id))

    log_msg = f"Removed {amount} strike(s) from {user_id} by {ctx.author.name}. Total: {new_strikes}/3. Reason: {reason}"
    was_unbanned = current_strikes >= 3 and new_strikes < 3
    if was_unbanned:
        log_msg += f" User {user_id} unbanned."

    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_message = f"✅ **{amount} strike(s) have been removed from your account**\n\n**Reason:** {reason}\n**Remaining Strikes:** {new_strikes}/3"
    if was_unbanned:
        dm_message += "\n\n🎉 **Your blacklist has been lifted!** You can use the bot again."
    
    dm_sent = await send_user_dm(user_id, dm_message)
    
    await ctx.send(f"✅ {log_msg}\n**DM Sent:** {'✅ Yes' if dm_sent else '❌ Failed'}")

@bot.hybrid_command(name="strikelist", description="Owner/Admin: View all users with strikes.")
@owner_or_bot_admin()
async def strike_list(ctx):
    res = db_query("SELECT user_id, strikes FROM users WHERE strikes > 0", fetch=True)
    text = "\n".join([f"<@{r[0]}>: {r[1]}/3" for r in res]) if res else "No active strikes."
    await ctx.send(embed=discord.Embed(title="⚡ Strike Ledger", description=text, color=discord.Color.orange()))

@bot.hybrid_command(name="clearstrike", description="Owner/Admin: Clear all strikes for a user.")
@owner_or_bot_admin()
async def clear_strike(ctx, user_id: str):
    db_query("UPDATE users SET strikes = 0, blacklisted = 0 WHERE user_id = ?", (user_id,))
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (f"Strikes cleared for {user_id} by {ctx.author.name}.",))
    await ctx.send(f"✅ Strikes reset for `{user_id}`.")

@bot.hybrid_group(name="bannedword", invoke_without_command=True)
@owner_or_bot_admin()
async def bw_group(ctx):
    res = db_query("SELECT word FROM banned_words", fetch=True)
    words = ', '.join([r[0] for r in res]) if res else 'None'
    await ctx.send(f"📋 **Banned Words:** `{words}`")

@bw_group.command(name="add")
@owner_or_bot_admin()
async def bw_add(ctx, word: str):
    db_query("INSERT OR IGNORE INTO banned_words VALUES (?)", (word.lower(),))
    await ctx.send(f"🚫 `{word}` added to filter.")

@bw_group.command(name="remove")
@owner_or_bot_admin()
async def bw_rem(ctx, word: str):
    db_query("DELETE FROM banned_words WHERE word = ?", (word.lower(),))
    await ctx.send(f"✅ `{word}` removed from filter.")

@bot.hybrid_command(name="listwords", description="Owner/Admin: List all banned words.")
@owner_or_bot_admin()
async def list_words(ctx):
    await bw_group.invoke(ctx)
@bot.hybrid_command(name="logs", description="Owner/Admin: View recent moderation logs.")
@owner_or_bot_admin()
async def view_logs(ctx):
    res = db_query("SELECT log, timestamp FROM admin_logs ORDER BY timestamp DESC LIMIT 15", fetch=True)
    text = "\n".join([f"[{r[1]}] {r[0]}" for r in res]) if res else "No logs."
    await ctx.send(f"```\n{text}\n```")

@bot.hybrid_command(name="clearadminlogs", description="Owner/Admin: Clear all admin logs.")
@owner_or_bot_admin()
async def clear_admin_logs(ctx):
    db_query("DELETE FROM admin_logs")
    await ctx.send("🗑️ Admin logs cleared.")

@bot.hybrid_command(name="searchlogs", description="Owner/Admin: Search interaction logs.")
@owner_or_bot_admin()
async def search_logs(ctx, keyword: str):
    rows = db_query("SELECT * FROM interaction_logs WHERE prompt LIKE ? OR response LIKE ? ORDER BY timestamp DESC LIMIT 20", (f"%{keyword}%", f"%{keyword}%"), fetch=True)

    if not rows:
        await ctx.send(f"❌ No results for `{keyword}`.")
        return

    text = "\n".join([f"[{r[3]}]: {r[5][:50]}..." for r in rows])
    await ctx.send(f"```\n{text}\n```")

# Bot Admin Management Commands (Owner Only)
@bot.command(name="add-admin", description="Owner: Add a bot admin.")
@commands.is_owner()
async def add_admin(ctx, user: discord.User):
    """Add a user as bot admin"""
    if user.id == OWNER_ID:
        await ctx.send("❌ Owner is already a permanent admin.")
        return
    
    # Check if already admin
    existing = db_query("SELECT user_id FROM bot_admins WHERE user_id = ?", (str(user.id),), fetch=True)
    if existing:
        await ctx.send(f"⚠️ {user.mention} is already a bot admin.")
        return
    
    # Add to database
    db_query("INSERT INTO bot_admins (user_id, added_by) VALUES (?, ?)", (str(user.id), str(ctx.author.id)))
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (f"User {user.id} ({user.name}) promoted to Bot Admin by {ctx.author.name}",))
    
    # Send DM to new admin
    dm_message = f"""🎉 **Congratulations!**

You have been promoted to **Bot Admin** for FlexedAI Bot by {ctx.author.name}.

As a Bot Admin, you now have access to advanced moderation and management commands including:
• User moderation (blacklist, strikes)
• Word filtering
• Log management
• Data exports
• And more!

Use `/help` to see all available commands.
"""
    dm_sent = await send_user_dm(str(user.id), dm_message)
    
    await ctx.send(f"✅ {user.mention} has been promoted to **Bot Admin**!\n**DM Sent:** {'✅ Yes' if dm_sent else '❌ Failed'}")

@bot.command(name="remove-admin", description="Owner: Remove a bot admin.")
@commands.is_owner()
async def remove_admin(ctx, user: discord.User):
    """Remove a user from bot admins"""
    if user.id == OWNER_ID:
        await ctx.send("❌ Cannot remove owner from admin privileges.")
        return
    
    # Check if is admin
    existing = db_query("SELECT user_id FROM bot_admins WHERE user_id = ?", (str(user.id),), fetch=True)
    if not existing:
        await ctx.send(f"⚠️ {user.mention} is not a bot admin.")
        return
    
    # Remove from database
    db_query("DELETE FROM bot_admins WHERE user_id = ?", (str(user.id),))
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (f"User {user.id} ({user.name}) removed from Bot Admin by {ctx.author.name}",))
    
    # Send DM to removed admin
    dm_message = f"""📋 **Bot Admin Status Update**

Your **Bot Admin** privileges for FlexedAI Bot have been removed by {ctx.author.name}.

You no longer have access to moderation and management commands.

Thank you for your service!
"""
    dm_sent = await send_user_dm(str(user.id), dm_message)
    
    await ctx.send(f"✅ {user.mention} has been removed from **Bot Admin**.\n**DM Sent:** {'✅ Yes' if dm_sent else '❌ Failed'}")

@bot.command(name="list-admins", description="Owner: List all bot admins.")
@commands.is_owner()
async def list_admins(ctx):
    """List all bot admins"""
    admins = db_query("SELECT user_id, added_by, added_at FROM bot_admins", fetch=True)
    
    if not admins:
        await ctx.send("📋 **Bot Admins:** None (only owner)")
        return
    
    embed = discord.Embed(title="👑 Bot Admin List", color=discord.Color.gold())
    embed.add_field(name="Owner", value=f"<@{OWNER_ID}> (Permanent)", inline=False)
    
    admin_list = []
    for admin in admins:
        user_id, added_by, added_at = admin
        admin_list.append(f"<@{user_id}> - Added by <@{added_by}> on {added_at}")
    
    if admin_list:
        embed.add_field(name="Bot Admins", value="\n".join(admin_list), inline=False)
    
    await ctx.send(embed=embed)

# Leave Server Command (Owner Only, DM Only)
@bot.hybrid_command(name="leave", description="Owner: Leave a server.")
@commands.is_owner()
@commands.dm_only()
async def leave_server(ctx, server_id: str, *, reason: str = None):
    """Leave a server with optional reason sent to server owner"""
    try:
        guild = bot.get_guild(int(server_id))
        if not guild:
            await ctx.send(f"❌ Server with ID `{server_id}` not found.")
            return
        
        guild_name = guild.name
        owner = guild.owner
        
        # Send message to server owner if reason provided
        if reason and owner:
            try:
                leave_message = f"""📢 **FlexedAI Bot Leaving Server**

Hello {owner.name},

FlexedAI Bot is leaving **{guild_name}**.

**Reason:** {reason}

If you have any questions, please contact the bot owner.

Thank you for using FlexedAI Bot!
"""
                await owner.send(leave_message)
                owner_notified = True
            except:
                owner_notified = False
        else:
            owner_notified = False
        
        # Leave the server
        await guild.leave()
        
        # Log the action
        log_msg = f"Left server: {guild_name} (ID: {server_id}). Reason: {reason if reason else 'No reason provided'}"
        db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
        
        # Confirm to owner
        embed = discord.Embed(title="✅ Server Left", color=discord.Color.green())
        embed.add_field(name="Server Name", value=guild_name, inline=False)
        embed.add_field(name="Server ID", value=server_id, inline=False)
        embed.add_field(name="Reason", value=reason if reason else "No reason provided", inline=False)
        embed.add_field(name="Owner Notified", value="✅ Yes" if owner_notified else "❌ No", inline=False)
        
        await ctx.send(embed=embed)
        
    except ValueError:
        await ctx.send("❌ Invalid server ID. Please provide a valid numeric ID.")
    except Exception as e:
        await ctx.send(f"❌ Error leaving server: {str(e)}")

@bot.hybrid_command(name="start", description="Set bot to respond to all messages in this channel.")
async def start_mode(ctx):
    # Check permissions
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\nThis command requires: **Administrator** permissions.")
            return
    
    db_query("INSERT OR REPLACE INTO settings (id, mode) VALUES (?, 'start')", (str(ctx.channel.id),))
    await ctx.send("✅ Bot will now respond to all messages in this channel.")

@bot.hybrid_command(name="stop", description="Set bot to respond only to pings/triggers.")
async def stop_mode(ctx):
    # Check permissions
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\nThis command requires: **Administrator** permissions.")
            return
    
    db_query("INSERT OR REPLACE INTO settings (id, mode) VALUES (?, 'stop')", (str(ctx.channel.id),))
    await ctx.send("✅ Bot will only respond to pings, 'flexedai', or images.")

# Slash command version with dropdown
@bot.hybrid_command(name="lang", description="Set channel language (Admin only).")
async def set_lang_slash(ctx, lang: str = None):
    # Check permissions (owner bypass)
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\nThis command requires: **Administrator** permissions.")
            return
    
    # If called as slash command without parameter, show dropdown
    if ctx.interaction and lang is None:
        view = LanguageSelectView(ctx.channel.id, ctx.author.id)
        await ctx.send("🌐 Select a language:", view=view, ephemeral=True)
        return
    
    # If lang parameter provided (for slash command)
    if lang:
        if lang not in AVAILABLE_LANGUAGES:
            await ctx.send(f"❌ Invalid language. Available: {', '.join(AVAILABLE_LANGUAGES)}", ephemeral=True)
            return
        
        db_query("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", (str(ctx.channel.id), lang))
        await ctx.send(f"🌐 Language set to **{lang}**.", ephemeral=True)
        return
    
    # If called as prefix command (!lang), show buttons (admin/owner only)
    if not ctx.interaction:
        view = LanguageButtonView(ctx.channel.id, ctx.author.id, OWNER_ID)
        await ctx.send(f"🌐 **Available Languages:** {', '.join(AVAILABLE_LANGUAGES)}\n\nClick a button below to select:", view=view)

# Autocomplete for slash command
@set_lang_slash.autocomplete('lang')
async def lang_autocomplete(interaction: discord.Interaction, current: str):
    return [
        discord.app_commands.Choice(name=lang, value=lang)
        for lang in AVAILABLE_LANGUAGES if current.lower() in lang.lower()
    ][:25]  # Discord limits to 25 choices

@bot.hybrid_command(name="prefix", description="Change command prefix.")
async def set_prefix(ctx, new_prefix: str):
    # Check permissions (owner bypass)
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\nThis command requires: **Administrator** permissions.")
            return
    
    guild_or_user_id = str(ctx.guild.id if ctx.guild else ctx.author.id)
    db_query("INSERT OR REPLACE INTO settings (id, prefix) VALUES (?, ?)", (guild_or_user_id, new_prefix))
    await ctx.send(f"⚙️ Prefix updated to `{new_prefix}`")

@bot.hybrid_command(name="help", description="Display command center.")
async def help_cmd(ctx):
    is_admin = is_bot_admin(ctx.author.id)
    
    embed = discord.Embed(title="📡 FlexedAI Command Center", color=discord.Color.blue())
    
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="👑 Owner Only", value="`add-admin`, `remove-admin`, `list-admins`, `leave` (DM only)", inline=False)
    
    if is_admin:
        embed.add_field(name="🛡️ Owner/Admin Commands", value="`sync`, `messages`, `clearlogs`, `server-list`, `backup`, `data`, `allinteractions` (DM only)", inline=False)
        embed.add_field(name="🔨 Moderation", value="`/blacklist`, `/addstrike`, `/removestrike`, `/strikelist`, `/clearstrike`, `/bannedword`, `/logs`, `/searchlogs`", inline=False)
    
    embed.add_field(name="⚙️ Settings", value="`/start`, `/stop`, `/lang`, `/prefix` (Admin required)", inline=False)
    embed.add_field(name="📊 Utilities", value="`/help`, `/whoami`, `/stats`, `/ping`, `/forget`", inline=False)
    
    if is_admin:
        embed.set_footer(text="✨ You have Bot Admin privileges")
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="whoami", description="Show your Discord profile.")
async def whoami(ctx):
    user = ctx.author
    roles = ", ".join([r.name for r in user.roles[1:]]) if ctx.guild else "N/A"
    
    embed = discord.Embed(title=f"👤 {user.name}", color=user.color)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=user.id, inline=False)
    embed.add_field(name="Roles", value=roles, inline=False)
    
    # Show admin status
    if user.id == OWNER_ID:
        embed.add_field(name="Bot Status", value="👑 **Bot Owner**", inline=False)
    elif is_bot_admin(user.id):
        embed.add_field(name="Bot Status", value="✨ **Bot Admin**", inline=False)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="stats", description="Check bot statistics.")
async def stats(ctx):
    latency = round(bot.latency * 1000, 2)
    guild_count = len(bot.guilds)
    await ctx.send(f"📊 **Latency:** {latency}ms | **Servers:** {guild_count}")

@bot.hybrid_command(name="ping", description="Check bot response time.")
async def ping(ctx):
    await ctx.send(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

@bot.hybrid_command(name="forget", description="Clear AI memory for this conversation.")
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in bot.memory:
        bot.memory[tid].clear()
    await ctx.send("🧠 Memory cleared for this conversation.")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_check = db_query("SELECT blacklisted FROM users WHERE user_id = ?", (str(message.author.id),), fetch=True)
    if user_check and user_check[0][0] == 1:
        return

    content_low = message.content.lower()
    banned = db_query("SELECT word FROM banned_words", fetch=True)
    if any(bw[0] in content_low for bw in banned):
        try:
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention}, your message contained a banned word.", delete_after=5)
        except:
            pass
        return

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
    elif "flexedai" in content_low:
        should_respond = True
    elif not message.guild:
        should_respond = True
    elif message.attachments:
        should_respond = True

    if not should_respond:
        return

    # Check for verification question
    verification_keywords = [
        "are you verified", "are you a verified bot", "is this bot verified",
        "verified bot", "discord verified", "are you official",
        "official bot", "verified badge"
    ]
    
    if any(keyword in content_low for keyword in verification_keywords):
        verification_response = """✅ **Yes, I can be a verified bot!**

**Discord Bot Verification** is a badge that indicates a bot has been verified by Discord. To qualify for verification, a bot must meet these requirements:

🔹 **Be in 75+ servers** (I'm currently in {} servers)
🔹 **Properly use Discord's API**
🔹 **Follow Discord's Terms of Service**
🔹 **Have a clear purpose and functionality**

Verified bots display a ✓ checkmark badge next to their name. Verification helps users trust that the bot is legitimate and maintained by its developers.

If you'd like to know more about my features, use `/help`!
""".format(len(bot.guilds))
        
        await message.reply(verification_response)
        return

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in bot.memory:
        bot.memory[tid] = deque(maxlen=6)

    async with message.channel.typing():
        res_lang = db_query("SELECT language FROM settings WHERE id = ?", (str(message.channel.id),), fetch=True)
        lang = res_lang[0][0] if res_lang else "English"

        server_name = message.guild.name if message.guild else "DM"
        roles = ", ".join([r.name for r in message.author.roles[1:]]) if message.guild else "None"

        # Truncate incoming message if too long
        user_content, was_truncated = truncate_message(message.content)
        
        system = f"""You are FlexedAI, a smart Discord bot. 
Basic Info about configuration, user and server: 
Language: {lang} (STRICT: You MUST respond in {lang} language ONLY. Do not switch languages unless the user explicitly uses the /lang or !lang command to change it.)
Server: {server_name}
Username: {message.author.name}
Roles: {roles}
Display Name: {message.author.display_name}
Profile Picture: {message.author.display_avatar.url}
Current Channel: <#{ctx.channel.id}>

Bot's Info:
Bot's Display Name: {bot.user.display_name}
Bot's Username: {bot.user.name}
Bot ID: {bot.user.id}
Bot's Server Roles: {ctx.guild.me.roles if ctx.guild else 'N/A'}
Bot's Avatar: {bot.user.display_avatar.url}

Match the user's tone and energy. Be helpful, casual, and engaging.
Have shorter responses, No idiot talks.
Just don't make silly mistakes. Try to be engaging not annoying.
To make responses shorter start to do this: Do not ask questions at the end of response like *What else can I help you with?*, *What do you want me to know?* etc."""

        msgs = [{"role": "system", "content": system}] + list(bot.memory[tid]) + [{"role": "user", "content": user_content}]

        try:
            res = await bot.groq_client.chat.completions.create(model=MODEL_NAME, messages=msgs, max_tokens=1500)
            reply = res.choices[0].message.content
            
            # Add truncation notice if message was truncated
            if was_truncated:
                reply = "⚠️ *Your message was very long and had to be shortened.*\n\n" + reply
            
            # Split and send response if it's too long
            await split_and_send(message, reply)

            bot.memory[tid].append({"role": "user", "content": user_content})
            bot.memory[tid].append({"role": "assistant", "content": reply})

            db_query("INSERT INTO interaction_logs VALUES (?, ?, ?, ?, ?, ?, ?)", (time.time(), str(message.guild.id) if message.guild else "DM", str(message.channel.id), message.author.name, str(message.author.id), message.content[:1000], reply[:1000]))
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            await message.reply(error_msg)

bot.run(DISCORD_TOKEN)
