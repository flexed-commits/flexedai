import discord
from discord.ext import commands
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

# Strike tracker for auto-ban
violations = {}

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
                "logs": data.get("logs", [])
            }
    except (FileNotFoundError, json.JSONDecodeError):
        return {"blacklist": set(), "banned_words": set(), "languages": {}, "memory": {}, "logs": []}

def save_data():
    serializable_mem = {str(cid): {str(uid): list(msgs) for uid, msgs in users.items()} for cid, users in user_memory.items()}
    with open(DATA_FILE, "w") as f:
        json.dump({
            "blacklist": list(BLACKLISTED_USERS),
            "banned_words": list(BANNED_WORDS),
            "languages": channel_languages,
            "memory": serializable_mem,
            "logs": log_history
        }, f, indent=4)

# Load State
data = load_data()
BLACKLISTED_USERS = data["blacklist"]
BANNED_WORDS = data["banned_words"]
channel_languages = data["languages"]
user_memory = data["memory"]
log_history = data["logs"]

client = AsyncGroq(api_key=GROQ_API_KEY)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="/", intents=intents, help_command=None)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ {self.user} Online | Logs Active")

bot = MyBot()

# --- LOGGING HELPER ---

async def add_log(user, content, trigger, is_ban=False):
    log_entry = {
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "user": f"{user} ({user.id})",
        "trigger": trigger,
        "action": "AUTO-BAN" if is_ban else "CENSORED"
    }
    log_history.insert(0, log_entry)
    if len(log_history) > 20: log_history.pop()
    save_data()
    
    # Send DM to Owner
    try:
        owner = await bot.fetch_user(OWNER_ID)
        embed = discord.Embed(title="🚩 Loophole Detection", color=discord.Color.red())
        embed.add_field(name="User", value=log_entry["user"])
        embed.add_field(name="Word", value=trigger)
        embed.add_field(name="Input", value=f"```{content}```")
        await owner.send(embed=embed)
    except: pass

# --- COMMANDS ---

@bot.hybrid_command(name="logs", description="OWNER ONLY: Show recent censorship logs")
async def logs(ctx):
    if ctx.author.id != OWNER_ID: return
    if not log_history: return await ctx.reply("📋 No logs recorded yet.")
    
    log_text = ""
    for entry in log_history[:10]:
        log_text += f"📅 **{entry['time']}** | 👤 **{entry['user']}**\n🚫 Word: `{entry['trigger']}` | ⚡ {entry['action']}\n\n"
    
    embed = discord.Embed(title="📜 Recent Censorship Logs", description=log_text, color=discord.Color.orange())
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="unblacklist")
async def unblacklist(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    uid = int(user_id)
    if uid in BLACKLISTED_USERS:
        BLACKLISTED_USERS.remove(uid)
        save_data()
        await ctx.reply(f"✅ `{uid}` unbanned.")
    else:
        await ctx.reply("❌ User not found in blacklist.")

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
                messages=[{"role":"system","content":"Human helper. Mirror tone. Censor slurs as (censored word)."}] + list(user_memory[cid][uid]) + [{"role":"user","content":message.content}],
                temperature=0.4
            )
            output = res.choices[0].message.content
            if output:
                clean_output = output
                for w in BANNED_WORDS:
                    clean_output = re.compile(rf'\b{re.escape(w)}\b', re.IGNORECASE).sub("(censored word)", clean_output)

                collapsed = "".join(c for c in clean_output.lower() if c.isalnum())
                for w in BANNED_WORDS:
                    if w in collapsed and w not in clean_output.lower().replace("(censored word)", ""):
                        violations[uid] = violations.get(uid, 0) + 1
                        is_ban = violations[uid] >= 3
                        if is_ban: BLACKLISTED_USERS.add(uid)
                        await add_log(message.author, message.content, w, is_ban)
                        return 

                user_memory[cid][uid].append({"role": "user", "content": message.content})
                user_memory[cid][uid].append({"role": "assistant", "content": clean_output})
                save_data()
                await message.reply(clean_output)
    except Exception as e: print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
