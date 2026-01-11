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

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, strikes INTEGER DEFAULT 0, blacklisted INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS banned_words (word TEXT PRIMARY KEY)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (id TEXT PRIMARY KEY, prefix TEXT, language TEXT DEFAULT "English", mode TEXT DEFAULT "start")')
    c.execute('CREATE TABLE IF NOT EXISTS admin_logs (log TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS interaction_logs (timestamp REAL, guild_id TEXT, channel_id TEXT, user_name TEXT, user_id TEXT, prompt TEXT, response TEXT)')
    conn.commit()
    conn.close()

def db_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(query, params)
        return c.fetchall() if fetch else None

init_db()

async def get_prefix(bot, message):
    res = db_query("SELECT prefix FROM settings WHERE id = ?", (str(message.guild.id if message.guild else message.author.id),), fetch=True)
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

@bot.hybrid_command(name="messages", description="Owner: Export interaction logs.")
@commands.is_owner()
async def messages(ctx):
    rows = db_query("SELECT * FROM interaction_logs WHERE timestamp > ?", (time.time() - 86400,), fetch=True)
    data = {"logs": [list(r) for r in rows]}
    fname = f"logs_{int(time.time())}.json"
    with open(fname, "w") as f: json.dump(data, f, indent=4)
    await ctx.send(file=discord.File(fname))
    os.remove(fname)

# --- BLACKLIST SYSTEM ---
@bot.hybrid_group(name="blacklist", description="Owner: Manage user access.")
@commands.is_owner()
async def blacklist_group(ctx):
    res = db_query("SELECT user_id FROM users WHERE blacklisted = 1", fetch=True)
    ids = ", ".join([r[0] for r in res]) or "None"
    await ctx.send(f"📋 Blacklisted: `{ids}`")

@blacklist_group.command(name="add")
async def bl_add(ctx, user_id: str):
    db_query("INSERT OR REPLACE INTO users (user_id, blacklisted) VALUES (?, 1)", (user_id,))
    await ctx.send(f"🚫 `{user_id}` has been blacklisted.")

@blacklist_group.command(name="remove")
async def bl_rem(ctx, user_id: str):
    db_query("UPDATE users SET blacklisted = 0 WHERE user_id = ?", (user_id,))
    await ctx.send(f"✅ `{user_id}` restored.")

# --- STRIKE SYSTEM ---
@bot.hybrid_command(name="addstrike")
@commands.is_owner()
async def add_strike(ctx, user_id: str, amount: int = 1):
    res = db_query("SELECT strikes FROM users WHERE user_id = ?", (user_id,), fetch=True)
    s = (res[0][0] if res else 0) + amount
    db_query("INSERT OR REPLACE INTO users (user_id, strikes, blacklisted) VALUES (?, ?, ?)", (user_id, s, 1 if s >= 3 else 0))
    await ctx.send(f"⚡ Strike recorded: {s}/3. (Auto-ban at 3)")

@bot.hybrid_command(name="strikelist")
@commands.is_owner()
async def strike_list(ctx):
    res = db_query("SELECT user_id, strikes FROM users WHERE strikes > 0", fetch=True)
    text = "\n".join([f"<@{r[0]}>: {r[1]}/3" for r in res]) or "No active strikes."
    await ctx.send(embed=discord.Embed(title="⚡ Strike Ledger", description=text))

@bot.hybrid_command(name="clearstrike")
@commands.is_owner()
async def clear_strike(ctx, user_id: str):
    db_query("UPDATE users SET strikes = 0 WHERE user_id = ?", (user_id,))
    await ctx.send(f"✅ Strikes reset for `{user_id}`.")

# --- WORD FILTER ---
@bot.hybrid_group(name="bannedword")
@commands.is_owner()
async def bw_group(ctx):
    res = db_query("SELECT word FROM banned_words", fetch=True)
    await ctx.send(f"📋 Banned: `{', '.join([r[0] for r in res]) or 'None'}`")

@bw_group.command(name="add")
async def bw_add(ctx, word: str):
    db_query("INSERT OR IGNORE INTO banned_words VALUES (?)", (word.lower(),))
    await ctx.send(f"🚫 `{word}` added to filter.")

@bw_group.command(name="remove")
async def bw_rem(ctx, word: str):
    db_query("DELETE FROM banned_words WHERE word = ?", (word.lower(),))
    await ctx.send(f"✅ Filter removed.")

# --- SETTINGS & LOGS ---
@bot.hybrid_command(name="setlang")
@commands.is_owner()
async def set_lang(ctx, lang: str):
    db_query("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", (str(ctx.channel.id), lang))
    await ctx.send(f"🌐 Language set to `{lang}`.")

@bot.hybrid_command(name="setprefix")
@commands.is_owner()
async def set_prefix(ctx, prefix: str):
    db_query("INSERT OR REPLACE INTO settings (id, prefix) VALUES (?, ?)", (str(ctx.guild.id if ctx.guild else ctx.author.id), prefix))
    await ctx.send(f"⚙️ Prefix updated to `{prefix}`.")

@bot.hybrid_command(name="logs")
@commands.is_owner()
async def view_logs(ctx):
    res = db_query("SELECT log, timestamp FROM admin_logs ORDER BY timestamp DESC LIMIT 15", fetch=True)
    text = "\n".join([f"[{r[1]}] {r[0]}" for r in res]) or "No logs."
    await ctx.send(f"```\n{text}\n```")

# --- AI & CENSORSHIP HANDLER ---
@bot.event
async def on_message(message):
    if message.author.bot: return

    # 1. Censor Banned Words
    content_low = message.content.lower()
    banned = db_query("SELECT word FROM banned_words", fetch=True)
    if any(bw[0] in content_low for bw in banned):
        try: await message.delete()
        except: pass
        return

    # 2. Command Processing
    await bot.process_commands(message)
    ctx = await bot.get_context(message)
    if ctx.valid: return

    # 3. AI Reply Logic
    if bot.user.mentioned_in(message) or "flexedai" in content_low or not message.guild:
        tid = f"{message.channel.id}-{message.author.id}"
        if tid not in bot.memory: bot.memory[tid] = deque(maxlen=6)
        
        async with message.channel.typing():
            res_lang = db_query("SELECT language FROM settings WHERE id = ?", (str(message.channel.id),), fetch=True)
            lang = res_lang[0][0] if res_lang else "English"
            
            system = f"You are FlexedAI. Language: {lang}. User: {message.author.name}."
            msgs = [{"role": "system", "content": system}] + list(bot.memory[tid]) + [{"role": "user", "content": message.content}]
            
            res = await bot.groq_client.chat.completions.create(model=MODEL_NAME, messages=msgs)
            reply = res.choices[0].message.content
            await message.reply(reply)
            
            bot.memory[tid].append({"role": "user", "content": message.content})
            bot.memory[tid].append({"role": "assistant", "content": reply})
            db_query("INSERT INTO interaction_logs VALUES (?, ?, ?, ?, ?, ?, ?)", (time.time(), str(message.guild.id) if message.guild else "DM", str(message.channel.id), message.author.name, str(message.author.id), message.content, reply))

bot.run(DISCORD_TOKEN)
