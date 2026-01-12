import discord
from discord.ext import commands, tasks
import os, time, datetime, json, sqlite3
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

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Create tables
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
    
    conn.commit()
    conn.close()

def migrate_json_to_db():
    """Migrate existing JSON data to SQLite database"""
    if not os.path.exists(JSON_FILE):
        print("⚠️ No bot_data.json found. Skipping migration.")
        return
    
    with open(JSON_FILE, 'r') as f:
        data = json.load(f)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Migrate blacklist
    for user_id in data.get('blacklist', []):
        c.execute("INSERT OR IGNORE INTO users (user_id, blacklisted) VALUES (?, 1)", (str(user_id),))
    
    # Migrate banned words
    for word in data.get('banned_words', []):
        c.execute("INSERT OR IGNORE INTO banned_words (word) VALUES (?)", (word.lower(),))
    
    # Migrate violations (strikes)
    for user_id, strikes in data.get('violations', {}).items():
        # Clean user_id format (remove <@> tags if present)
        clean_id = user_id.replace('<@', '').replace('>', '')
        blacklisted = 1 if strikes >= 3 else 0
        c.execute("INSERT OR REPLACE INTO users (user_id, strikes, blacklisted) VALUES (?, ?, ?)", 
                  (clean_id, strikes, blacklisted))
    
    # Migrate language settings
    for channel_id, lang in data.get('languages', {}).items():
        c.execute("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", 
                  (str(channel_id), lang))
    
    # Migrate prefixes
    for guild_id, prefix in data.get('prefixes', {}).items():
        c.execute("INSERT OR REPLACE INTO settings (id, prefix) VALUES (?, ?)", 
                  (str(guild_id), prefix))
    
    # Migrate response modes
    for channel_id, mode in data.get('response_mode', {}).items():
        c.execute("INSERT OR REPLACE INTO settings (id, mode) VALUES (?, ?)", 
                  (str(channel_id), mode))
    
    # Migrate admin logs
    for log in data.get('admin_logs', []):
        c.execute("INSERT INTO admin_logs (log) VALUES (?)", (log,))
    
    conn.commit()
    conn.close()
    
    # Backup and remove old JSON
    os.rename(JSON_FILE, f"{JSON_FILE}.backup")
    print(f"✅ Migrated bot_data.json → {DB_FILE}")

def migrate_interaction_logs():
    """Migrate interaction logs from JSON to database"""
    if not os.path.exists(INTERACTION_JSON):
        print("⚠️ No interaction_logs.json found. Skipping migration.")
        return
    
    with open(INTERACTION_JSON, 'r') as f:
        logs = json.load(f)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    for log in logs:
        c.execute("""INSERT INTO interaction_logs 
                     (timestamp, guild_id, channel_id, user_name, user_id, prompt, response) 
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (log['timestamp'], str(log.get('guild_id', 'DM')), str(log['channel_id']), 
                   log['user_name'], str(log['user_id']), log['prompt'], log['response']))
    
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

# Initialize database and migrate
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
        print(f"✅ {self.user} Online | All Commands Locked & Loaded")

bot = FlexedBot()

# --- 👑 OWNER COMMANDS ---

@bot.hybrid_command(name="sync", description="Owner: Sync slash commands.")
@commands.is_owner()
async def sync(ctx):
    await bot.tree.sync()
    await ctx.send("🚀 Commands synced globally.")

@bot.hybrid_command(name="messages", description="Owner: Export interaction logs (last 24h).")
@commands.is_owner()
async def messages(ctx):
    cutoff = time.time() - 86400  # 24 hours ago
    rows = db_query("SELECT * FROM interaction_logs WHERE timestamp > ? ORDER BY timestamp DESC", 
                    (cutoff,), fetch=True)
    
    data = [{
        "timestamp": r[0],
        "guild_id": r[1],
        "channel_id": r[2],
        "user_name": r[3],
        "user_id": r[4],
        "prompt": r[5],
        "response": r[6]
    } for r in rows]
    
    fname = f"logs_{int(time.time())}.json"
    with open(fname, "w") as f: 
        json.dump(data, f, indent=2)
    
    await ctx.send(file=discord.File(fname))
    os.remove(fname)

@bot.hybrid_command(name="clearlogs", description="Owner: Wipe interaction logs.")
@commands.is_owner()
async def clear_logs(ctx):
    db_query("DELETE FROM interaction_logs")
    await ctx.send("🗑️ Interaction logs cleared.")

@bot.command(name="server-list", description="Owner: Export server list.")
@commands.is_owner()
async def server_list(ctx):
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("⚠️ This command must be run in DMs.")
        return
    
    guilds = [{"id": str(g.id), "name": g.name, "member_count": g.member_count} for g in bot.guilds]
    fname = f"servers_{int(time.time())}.json"
    with open(fname, "w") as f:
        json.dump(guilds, f, indent=2)
    
    await ctx.send(file=discord.File(fname))
    os.remove(fname)

# --- BLACKLIST SYSTEM ---
@bot.hybrid_group(name="blacklist", description="Owner: Manage user access.", invoke_without_command=True)
@commands.is_owner()
async def blacklist_group(ctx):
    res = db_query("SELECT user_id FROM users WHERE blacklisted = 1", fetch=True)
    ids = ", ".join([r[0] for r in res]) if res else "None"
    await ctx.send(f"📋 **Blacklisted Users:** `{ids}`")

@blacklist_group.command(name="add")
async def bl_add(ctx, user_id: str):
    db_query("INSERT OR REPLACE INTO users (user_id, blacklisted) VALUES (?, 1)", (user_id,))
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (f"User {user_id} BLACKLISTED.",))
    await ctx.send(f"🚫 `{user_id}` has been blacklisted.")

@blacklist_group.command(name="remove")
async def bl_rem(ctx, user_id: str):
    db_query("UPDATE users SET blacklisted = 0 WHERE user_id = ?", (user_id,))
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (f"User {user_id} removed from blacklist.",))
    await ctx.send(f"✅ `{user_id}` restored.")

# --- STRIKE SYSTEM ---
@bot.hybrid_command(name="addstrike", description="Owner: Add strikes to a user.")
@commands.is_owner()
async def add_strike(ctx, user_id: str, amount: int = 1):
    res = db_query("SELECT strikes FROM users WHERE user_id = ?", (user_id,), fetch=True)
    current_strikes = res[0][0] if res else 0
    new_strikes = current_strikes + amount
    
    is_banned = 1 if new_strikes >= 3 else 0
    db_query("INSERT OR REPLACE INTO users (user_id, strikes, blacklisted) VALUES (?, ?, ?)", 
             (user_id, new_strikes, is_banned))
    
    log_msg = f"Strike to {user_id}. Total: {new_strikes}/3."
    if is_banned:
        log_msg += f" User {user_id} AUTO-BANNED."
    
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    await ctx.send(f"⚡ {log_msg}")

@bot.hybrid_command(name="removestrike", description="Owner: Remove strikes from a user.")
@commands.is_owner()
async def remove_strike(ctx, user_id: str, amount: int = 1):
    res = db_query("SELECT strikes FROM users WHERE user_id = ?", (user_id,), fetch=True)
    
    if not res or res[0][0] == 0:
        await ctx.send(f"⚠️ User `{user_id}` has no strikes to remove.")
        return
    
    current_strikes = res[0][0]
    new_strikes = max(0, current_strikes - amount)  # Prevent negative strikes
    
    # If strikes drop below 3, remove blacklist
    is_banned = 1 if new_strikes >= 3 else 0
    
    db_query("UPDATE users SET strikes = ?, blacklisted = ? WHERE user_id = ?", 
             (new_strikes, is_banned, user_id))
    
    log_msg = f"Removed {amount} strike(s) from {user_id}. Total: {new_strikes}/3."
    if current_strikes >= 3 and new_strikes < 3:
        log_msg += f" User {user_id} unbanned."
    
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    await ctx.send(f"✅ {log_msg}")

@bot.hybrid_command(name="strikelist", description="Owner: View all users with strikes.")
@commands.is_owner()
async def strike_list(ctx):
    res = db_query("SELECT user_id, strikes FROM users WHERE strikes > 0", fetch=True)
    text = "\n".join([f"<@{r[0]}>: {r[1]}/3" for r in res]) if res else "No active strikes."
    await ctx.send(embed=discord.Embed(title="⚡ Strike Ledger", description=text, color=discord.Color.orange()))

@bot.hybrid_command(name="clearstrike", description="Owner: Clear all strikes for a user.")
@commands.is_owner()
async def clear_strike(ctx, user_id: str):
    db_query("UPDATE users SET strikes = 0, blacklisted = 0 WHERE user_id = ?", (user_id,))
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (f"Strikes cleared for {user_id}.",))
    await ctx.send(f"✅ Strikes reset for `{user_id}`.")

# --- WORD FILTER ---
@bot.hybrid_group(name="bannedword", invoke_without_command=True)
@commands.is_owner()
async def bw_group(ctx):
    res = db_query("SELECT word FROM banned_words", fetch=True)
    words = ', '.join([r[0] for r in res]) if res else 'None'
    await ctx.send(f"📋 **Banned Words:** `{words}`")

@bw_group.command(name="add")
async def bw_add(ctx, word: str):
    db_query("INSERT OR IGNORE INTO banned_words VALUES (?)", (word.lower(),))
    await ctx.send(f"🚫 `{word}` added to filter.")

@bw_group.command(name="remove")
async def bw_rem(ctx, word: str):
    db_query("DELETE FROM banned_words WHERE word = ?", (word.lower(),))
    await ctx.send(f"✅ `{word}` removed from filter.")

@bot.hybrid_command(name="listwords", description="Owner: List all banned words.")
@commands.is_owner()
async def list_words(ctx):
    await bw_group.invoke(ctx)

# --- LOGS ---
@bot.hybrid_command(name="logs", description="Owner: View recent moderation logs.")
@commands.is_owner()
async def view_logs(ctx):
    res = db_query("SELECT log, timestamp FROM admin_logs ORDER BY timestamp DESC LIMIT 15", fetch=True)
    text = "\n".join([f"[{r[1]}] {r[0]}" for r in res]) if res else "No logs."
    await ctx.send(f"```\n{text}\n```")

@bot.hybrid_command(name="clearadminlogs", description="Owner: Clear all admin logs.")
@commands.is_owner()
async def clear_admin_logs(ctx):
    db_query("DELETE FROM admin_logs")
    await ctx.send("🗑️ Admin logs cleared.")

# --- RESPONSE MODE ---
@bot.hybrid_command(name="start", description="Set bot to respond to all messages in this channel.")
async def start_mode(ctx):
    db_query("INSERT OR REPLACE INTO settings (id, mode) VALUES (?, 'start')", (str(ctx.channel.id),))
    await ctx.send("✅ Bot will now respond to all messages in this channel.")

@bot.hybrid_command(name="stop", description="Set bot to respond only to pings/triggers.")
async def stop_mode(ctx):
    db_query("INSERT OR REPLACE INTO settings (id, mode) VALUES (?, 'stop')", (str(ctx.channel.id),))
    await ctx.send("✅ Bot will only respond to pings, 'flexedai', or images.")

# --- LANGUAGE ---
@bot.hybrid_command(name="lang", description="Set channel language.")
async def set_lang(ctx):
    view = discord.ui.View()
    
    async def lang_callback(interaction, lang):
        db_query("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", (str(ctx.channel.id), lang))
        await interaction.response.send_message(f"🌐 Language set to **{lang}**.", ephemeral=True)
    
    for lang in ["English", "Hindi", "Hinglish", "Spanish", "French"]:
        btn = discord.ui.Button(label=lang, style=discord.ButtonStyle.primary)
        btn.callback = lambda i, l=lang: lang_callback(i, l)
        view.add_item(btn)
    
    await ctx.send("🌐 Select a language:", view=view)

# --- PREFIX ---
@bot.hybrid_command(name="prefix", description="Change command prefix.")
async def set_prefix(ctx, new_prefix: str):
    guild_or_user_id = str(ctx.guild.id if ctx.guild else ctx.author.id)
    db_query("INSERT OR REPLACE INTO settings (id, prefix) VALUES (?, ?)", (guild_or_user_id, new_prefix))
    await ctx.send(f"⚙️ Prefix updated to `{new_prefix}`")

# --- UTILITIES ---
@bot.hybrid_command(name="help", description="Display command center.")
async def help_cmd(ctx):
    embed = discord.Embed(title="📡 FlexedAI Command Center", color=discord.Color.blue())
    embed.add_field(name="👑 Owner", value="`sync`, `messages`, `clearlogs`, `server-list`", inline=False)
    embed.add_field(name="🛡️ Moderation", value="`/blacklist`, `/addstrike`, `/removestrike`, `/strikelist`, `/clearstrike`, `/bannedword`, `/logs`", inline=False)
    embed.add_field(name="⚙️ Settings", value="`/start`, `/stop`, `/lang`, `/prefix`", inline=False)
    embed.add_field(name="📊 Utilities", value="`/help`, `/whoami`, `/stats`, `/ping`, `/forget`, `/searchlogs`", inline=False)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="whoami", description="Show your Discord profile.")
async def whoami(ctx):
    user = ctx.author
    roles = ", ".join([r.name for r in user.roles[1:]]) if ctx.guild else "N/A"
    embed = discord.Embed(title=f"👤 {user.name}", color=user.color)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=user.id, inline=False)
    embed.add_field(name="Roles", value=roles, inline=False)
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

@bot.hybrid_command(name="searchlogs", description="Owner: Search interaction logs.")
@commands.is_owner()
async def search_logs(ctx, keyword: str):
    rows = db_query("SELECT * FROM interaction_logs WHERE prompt LIKE ? OR response LIKE ? ORDER BY timestamp DESC LIMIT 20", 
                    (f"%{keyword}%", f"%{keyword}%"), fetch=True)
    
    if not rows:
        await ctx.send(f"❌ No results for `{keyword}`.")
        return
    
    text = "\n".join([f"[{r[3]}]: {r[5][:50]}..." for r in rows])
    await ctx.send(f"```\n{text}\n```")

# --- AI RESPONSE HANDLER ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Check blacklist
    user_check = db_query("SELECT blacklisted FROM users WHERE user_id = ?", (str(message.author.id),), fetch=True)
    if user_check and user_check[0][0] == 1:
        return

    # Censor banned words
    content_low = message.content.lower()
    banned = db_query("SELECT word FROM banned_words", fetch=True)
    if any(bw[0] in content_low for bw in banned):
        try:
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention}, your message contained a banned word.", delete_after=5)
        except:
            pass
        return

    # Process commands first
    await bot.process_commands(message)
    ctx = await bot.get_context(message)
    if ctx.valid:
        return

    # Check response mode
    mode_check = db_query("SELECT mode FROM settings WHERE id = ?", (str(message.channel.id),), fetch=True)
    mode = mode_check[0][0] if mode_check else "stop"
    
    should_respond = False
    
    if mode == "start":
        should_respond = True
    elif bot.user.mentioned_in(message) or message.reference and message.reference.resolved.author == bot.user:
        should_respond = True
    elif "flexedai" in content_low:
        should_respond = True
    elif not message.guild:  # Always respond in DMs
        should_respond = True
    elif message.attachments:  # Respond to images
        should_respond = True
    
    if not should_respond:
        return

    # AI Response
    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in bot.memory:
        bot.memory[tid] = deque(maxlen=6)

    async with message.channel.typing():
        res_lang = db_query("SELECT language FROM settings WHERE id = ?", (str(message.channel.id),), fetch=True)
        lang = res_lang[0][0] if res_lang else "English"

        server_name = message.guild.name if message.guild else "DM"
        roles = ", ".join([r.name for r in message.author.roles[1:]]) if message.guild else "None"
        
        system = f"""You are FlexedAI, a smart Discord bot. 
Language: {lang}
Server: {server_name}
User: {message.author.name}
Roles: {roles}

Match the user's tone and energy. Be helpful, casual, and engaging."""

        msgs = [{"role": "system", "content": system}] + list(bot.memory[tid]) + [{"role": "user", "content": message.content}]

        try:
            res = await bot.groq_client.chat.completions.create(model=MODEL_NAME, messages=msgs, max_tokens=500)
            reply = res.choices[0].message.content
            await message.reply(reply)

            bot.memory[tid].append({"role": "user", "content": message.content})
            bot.memory[tid].append({"role": "assistant", "content": reply})
            
            db_query("INSERT INTO interaction_logs VALUES (?, ?, ?, ?, ?, ?, ?)", 
                     (time.time(), str(message.guild.id) if message.guild else "DM", 
                      str(message.channel.id), message.author.name, str(message.author.id), 
                      message.content, reply))
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")

bot.run(DISCORD_TOKEN)
