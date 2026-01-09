import discord
from discord.ext import commands
from discord import app_commands
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
                "violations": data.get("violations", {}) # Persistent strikes
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
        print(f"✅ {self.user} Online | Using {MODEL_NAME}")
        print(f"📊 Registered {len(self.commands)} commands.")

bot = MyBot()

# --- LOGGING & DM SYSTEM ---

async def log_violation(user, content, trigger, is_ban=False):
    log_entry = {
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "user": f"{user} ({user.id})",
        "trigger": trigger,
        "action": "AUTO-BAN" if is_ban else "CENSORED"
    }
    log_history.insert(0, log_entry)
    if len(log_history) > 20: log_history.pop()
    save_data()

    try:
        owner = await bot.fetch_user(OWNER_ID)
        embed = discord.Embed(
            title="🚩 Loophole Detection" if not is_ban else "🚫 USER BANNED",
            color=discord.Color.red() if not is_ban else discord.Color.dark_red(),
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="User", value=f"{user} (`{user.id}`)")
        embed.add_field(name="Word", value=f"**{trigger}**")
        embed.add_field(name="Strikes", value=f"{violations_storage.get(str(user.id), 0)}/3")
        embed.add_field(name="Content", value=f"```\n{content}\n```")
        await owner.send(embed=embed)
    except Exception as e:
        print(f"❌ DM Log Failed: {e}")

# --- OWNER COMMANDS ---

@bot.hybrid_command(name="clearstrikes", description="OWNER ONLY: Reset user strikes")
async def clearstrikes(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    uid_str = str(user_id)
    if uid_str in violations_storage:
        violations_storage[uid_str] = 0
        save_data()
        await ctx.reply(f"✅ Strikes cleared for `{user_id}`.")
    else:
        await ctx.reply("ℹ️ User has no strikes.")

@bot.hybrid_command(name="unblacklist", description="OWNER ONLY: Unban a user")
async def unblacklist(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    uid = int(user_id)
    if uid in BLACKLISTED_USERS:
        BLACKLISTED_USERS.remove(uid)
        violations_storage[str(uid)] = 0
        save_data()
        await ctx.reply(f"✅ User `{uid}` unbanned and strikes reset.")
    else:
        await ctx.reply("❌ User not in blacklist.")

@bot.hybrid_command(name="logs", description="OWNER ONLY: View recent bypasses")
async def logs(ctx):
    if ctx.author.id != OWNER_ID: return
    if not log_history: return await ctx.reply("📋 No logs.")
    text = "".join([f"📅 `{e['time']}` | 👤 `{e['user']}`\n🚫 **{e['trigger']}** | ⚡ {e['action']}\n\n" for e in log_history[:10]])
    await ctx.reply(embed=discord.Embed(title="📜 Logs", description=text, color=discord.Color.orange()))

# --- UTILITY COMMANDS (ping, uptime, lang, forget) ---
@bot.hybrid_command(name="ping")
async def ping(ctx): await ctx.reply(f"🏓 Pong! **{round(bot.latency * 1000)}ms**")

@bot.hybrid_command(name="uptime")
async def uptime(ctx):
    text = str(datetime.timedelta(seconds=int(round(time.time() - bot.start_time))))
    await ctx.reply(f"🚀 Uptime: **{text}**")

@bot.hybrid_command(name="lang")
async def lang(ctx, language: str):
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID): return
    channel_languages[str(ctx.channel.id)] = language
    save_data()
    await ctx.reply(f"🌐 Language updated to **{language}**.")

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
                messages=[{"role":"system","content":"Human tone. Censor slurs as (censored word)."}] + list(user_memory[cid][uid]) + [{"role":"user","content":message.content}],
                temperature=0.3
            )
            output = res.choices[0].message.content
            if output:
                clean_output = output
                for w in BANNED_WORDS:
                    clean_output = re.compile(rf'\b{re.escape(w)}\b', re.IGNORECASE).sub("(censored word)", clean_output)

                collapsed = "".join(c for c in clean_output.lower() if c.isalnum())
                for w in BANNED_WORDS:
                    if w in collapsed and w not in clean_output.lower().replace("(censored word)", ""):
                        uid_str = str(uid)
                        violations_storage[uid_str] = violations_storage.get(uid_str, 0) + 1
                        is_ban = violations_storage[uid_str] >= 3
                        if is_ban: BLACKLISTED_USERS.add(uid)
                        await log_violation(message.author, message.content, w, is_ban)
                        return 

                user_memory[cid][uid].append({"role": "user", "content": message.content})
                user_memory[cid][uid].append({"role": "assistant", "content": clean_output})
                save_data()
                await message.reply(clean_output)
    except Exception as e: print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
