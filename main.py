import discord
from discord.ext import commands, tasks
import os
import time
import datetime
import json
import re
from groq import AsyncGroq 
from collections import deque

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct"
OWNER_ID = 1081876265683927080
DATA_FILE = "bot_data.json"

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            raw_mem = data.get("memory", {})
            fixed_mem = {int(cid): {int(uid): deque(msgs, maxlen=10) for uid, msgs in users.items()} for cid, users in raw_mem.items()}
            return {
                "blacklist": set(data.get("blacklist", [])),
                "banned_words": set(data.get("banned_words", [])),
                "languages": data.get("languages", {}),
                "memory": fixed_mem,
                "logs": data.get("logs", []),
                "violations": data.get("violations", {})
            }
    except (FileNotFoundError, json.JSONDecodeError):
        return {"blacklist": set(), "banned_words": set(), "languages": {}, "memory": {}, "logs": [], "violations": {}}

def save_data():
    serializable_mem = {str(cid): {str(uid): list(msgs) for uid, msgs in users.items()} for cid, users in user_memory.items()}
    with open(DATA_FILE, "w") as f:
        json.dump({
            "blacklist": list(BLACKLISTED_USERS),
            "banned_words": list(BANNED_WORDS),
            "languages": channel_languages,
            "memory": serializable_mem,
            "logs": log_history,
            "violations": violations_storage
        }, f, indent=4)

# Load State
data = load_data()
BLACKLISTED_USERS = data["blacklist"]
BANNED_WORDS = data["banned_words"]
channel_languages = data["languages"]
user_memory = data["memory"]
log_history = data["logs"]
violations_storage = data["violations"]

client = AsyncGroq(api_key=GROQ_API_KEY)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="/", intents=intents, help_command=None)
        self.start_time = time.time()

    async def setup_hook(self):
        await self.tree.sync()
        self.daily_backup.start() # Start the daily backup loop
        print(f"✅ {self.user} is live!")

    # --- DAILY BACKUP TASK ---
    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data() # Ensure data is fresh before sending
            with open(DATA_FILE, "rb") as file:
                await owner.send("📦 **Daily Backup**: Here is your current `bot_data.json` file.", file=discord.File(file, DATA_FILE))
            print("📤 Daily backup sent to owner.")
        except Exception as e:
            print(f"❌ Backup failed: {e}")

    @daily_backup.before_loop
    async def before_backup(self):
        await self.wait_until_ready()

bot = MyBot()

# --- OWNER COMMANDS ---

@bot.hybrid_command(name="backup", description="OWNER ONLY: Manually trigger a JSON backup")
async def backup(ctx):
    if ctx.author.id != OWNER_ID: return
    try:
        save_data()
        with open(DATA_FILE, "rb") as file:
            await ctx.author.send("💾 **Manual Backup**: Current `bot_data.json`.", file=discord.File(file, DATA_FILE))
        await ctx.reply("📥 Backup sent to your DMs.")
    except Exception as e:
        await ctx.reply(f"❌ Error: {e}")

# ... (Include all other 14 commands here: help, ping, addstrike, logs, etc.) ...

# --- AI HANDLER ---
@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    ctx = await bot.get_context(message)
    if ctx.valid: await bot.invoke(ctx); return

    cid, uid = message.channel.id, message.author.id
    if cid not in user_memory: user_memory[cid] = {}
    if uid not in user_memory[cid]: user_memory[cid][uid] = deque(maxlen=10)

    try:
        async with message.channel.typing():
            res = await client.chat.completions.create(
                model=MODEL_NAME, 
                messages=[{"role":"system","content":f"Language: {channel_languages.get(str(cid), 'English')}."}] + list(user_memory[cid][uid]) + [{"role":"user","content":message.content}],
                temperature=0.3
            )
            output = res.choices[0].message.content
            if output:
                # [Censorship and Loophole Logic same as before]
                user_memory[cid][uid].append({"role": "user", "content": message.content})
                user_memory[cid][uid].append({"role": "assistant", "content": output})
                save_data()
                await message.reply(output)
    except Exception as e: print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
