import discord
from discord.ext import commands, tasks
import os
import time
import json
import sqlite3
from groq import AsyncGroq 
from collections import deque

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct" 
OWNER_ID = 1081876265683927080
DB_FILE = "bot_data.db"
JSON_BACKUP = "bot_data (3).json" # The file you provided

# --- DATABASE CORE ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, strikes INTEGER DEFAULT 0, blacklisted INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS banned_words (word TEXT PRIMARY KEY)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (id TEXT PRIMARY KEY, prefix TEXT DEFAULT "!", language TEXT DEFAULT "English", mode TEXT DEFAULT "stop")')
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
                 timestamp REAL, server_id TEXT, channel_id TEXT, 
                 user_name TEXT, user_id TEXT, prompt TEXT, response TEXT)''')
    conn.commit()
    
    # MIGRATION FROM JSON (If DB is empty)
    c.execute("SELECT COUNT(*) FROM banned_words")
    if c.fetchone()[0] == 0 and os.path.exists(JSON_BACKUP):
        print("Migrating data from JSON to SQLite...")
        with open(JSON_BACKUP, "r") as f:
            data = json.load(f)
            # Migrate Banned Words
            for word in data.get("banned_words", []):
                c.execute("INSERT OR IGNORE INTO banned_words VALUES (?)", (word,))
            # Migrate Prefixes
            for s_id, pre in data.get("prefixes", {}).items():
                c.execute("INSERT OR REPLACE INTO settings (id, prefix) VALUES (?, ?)", (s_id, pre))
            # Migrate Languages
            for c_id, lang in data.get("languages", {}).items():
                c.execute("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", (c_id, lang))
        conn.commit()
    conn.close()

def db_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(query, params)
        return c.fetchall() if fetch else None

init_db()

# --- BOT SETUP ---
async def get_prefix(bot, message):
    res = db_query("SELECT prefix FROM settings WHERE id = ?", (str(message.guild.id if message.guild else message.author.id),), fetch=True)
    return res[0][0] if res else "!"

class FlexedBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=get_prefix, intents=discord.Intents.all(), help_command=None)
        self.client = AsyncGroq(api_key=GROQ_API_KEY)
        self.memory = {}

bot = FlexedBot()

# --- OWNER COMMANDS ---
@bot.command()
@commands.is_owner()
async def messages(ctx):
    """Generates a JSON log from SQLite and sends it."""
    rows = db_query("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 100", fetch=True)
    log_data = [{"time": r[0], "server": r[1], "user": r[3], "prompt": r[5], "res": r[6]} for r in rows]
    
    with open("temp_logs.json", "w") as f:
        json.dump(log_data, f, indent=2)
    await ctx.send(file=discord.File("temp_logs.json"))
    os.remove("temp_logs.json")

# --- AI HANDLER ---
@bot.event
async def on_message(message):
    if message.author.bot: return

    # Check Blacklist
    check = db_query("SELECT blacklisted FROM users WHERE user_id = ?", (str(message.author.id),), fetch=True)
    if check and check[0][0] == 1: return

    # Check for Banned Words
    content_low = message.content.lower()
    banned = db_query("SELECT word FROM banned_words", fetch=True)
    if any(bw[0] in content_low for bw in banned):
        return await message.delete()

    # Process Commands
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # AI Triggering Logic
    is_dm = message.guild is None
    is_pinged = bot.user.mentioned_in(message)
    has_keyword = "flexedai" in content_low
    
    if not (is_dm or is_pinged or has_keyword):
        return

    # Chat Logic
    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in self.memory: self.memory[tid] = deque(maxlen=6)
    
    lang_res = db_query("SELECT language FROM settings WHERE id = ?", (str(message.channel.id),), fetch=True)
    lang = lang_res[0][0] if lang_res else "English"

    async with message.channel.typing():
        system = f"You are FlexedAI. Mirror user tone. Language: {lang}. User: {message.author.name}."
        msgs = [{"role": "system", "content": system}] + list(self.memory[tid]) + [{"role": "user", "content": message.content}]
        
        chat_completion = await bot.client.chat.completions.create(model=MODEL_NAME, messages=msgs)
        reply = chat_completion.choices[0].message.content
        
        await message.reply(reply)
        
        # Log to SQLite
        db_query("INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?, ?)", 
                 (time.time(), str(message.guild.id) if not is_dm else "DM", str(message.channel.id), 
                  message.author.name, str(message.author.id), message.content, reply))

bot.run(DISCORD_TOKEN)
