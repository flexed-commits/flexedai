import discord
from discord.ext import commands, tasks
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

# Memory (Volatile - Resets on bot restart)
thread_memory = {}

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            return {
                "blacklist": set(data.get("blacklist", [])),
                "banned_words": set(data.get("banned_words", [])),
                "languages": data.get("languages", {}),
                "logs": data.get("logs", []),
                "violations": data.get("violations", {})
            }
    except (FileNotFoundError, json.JSONDecodeError):
        return {"blacklist": set(), "banned_words": set(), "languages": {}, "logs": [], "violations": {}}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump({
            "blacklist": list(BLACKLISTED_USERS),
            "banned_words": list(BANNED_WORDS),
            "languages": channel_languages,
            "logs": log_history,
            "violations": violations_storage
        }, f, indent=4)

# Load State
data = load_data()
BLACKLISTED_USERS = data["blacklist"]
BANNED_WORDS = data["banned_words"]
channel_languages = data["languages"]
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
        self.daily_backup.start()
        print(f"\n🚀 {self.user} is ONLINE using {MODEL_NAME}")
        print("="*40)
        for cmd in self.walk_commands():
            print(f" ✅ [Hybrid] /{cmd.name}")
        print("="*40)

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            with open(DATA_FILE, "rb") as file:
                await owner.send("📦 **Daily Backup**: Automated `bot_data.json` delivery.", file=discord.File(file, DATA_FILE))
        except Exception as e: print(f"Backup Error: {e}")

bot = MyBot()

# --- LOGGING HELPER ---

async def log_violation(user, content, trigger, is_ban=False):
    log_entry = {"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "user": f"{user} ({user.id})", "trigger": trigger, "action": "AUTO-BAN" if is_ban else "CENSORED"}
    log_history.insert(0, log_entry)
    if len(log_history) > 20: log_history.pop()
    save_data()
    try:
        owner = await bot.fetch_user(OWNER_ID)
        embed = discord.Embed(title="🚩 Loophole Detection", color=discord.Color.red(), timestamp=datetime.datetime.now())
        embed.add_field(name="User", value=f"{user} (`{user.id}`)")
        embed.add_field(name="Word", value=trigger)
        embed.add_field(name="Strikes", value=f"{violations_storage.get(str(user.id), 0)}/3")
        await owner.send(embed=embed)
    except: pass

# --- COMMANDS ---

@bot.hybrid_command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 Master Command List", color=discord.Color.blue())
    embed.add_field(name="📡 General", value="`/help`, `/ping`, `/uptime`, `/forget`", inline=False)
    embed.add_field(name="⚙️ Settings", value="`/lang [language]`", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="👑 Owner Only", value="`/blacklist`, `/unblacklist`, `/bannedword`, `/listwords`, `/listblacklisted`, `/logs`, `/clearstrikes`, `/addstrike`, `/refresh`, `/backup` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="addstrike")
async def addstrike(ctx, user_id: str, amount: int):
    if ctx.author.id != OWNER_ID: return
    uid_str = str(user_id)
    violations_storage[uid_str] = violations_storage.get(uid_str, 0) + amount
    if violations_storage[uid_str] >= 3: BLACKLISTED_USERS.add(int(user_id))
    save_data()
    await ctx.reply(f"⚡ Strike count for `{user_id}` updated to {violations_storage[uid_str]}/3.")

@bot.hybrid_command(name="logs")
async def logs(ctx):
    if ctx.author.id != OWNER_ID: return
    if not log_history: return await ctx.reply("📋 No logs found.")
    text = "".join([f"📅 `{e['time']}` | 👤 `{e['user']}`\n🚫 **{e['trigger']}** | ⚡ {e['action']}\n\n" for e in log_history[:5]])
    await ctx.reply(embed=discord.Embed(title="📜 System Logs", description=text, color=discord.Color.orange()))

@bot.hybrid_command(name="backup")
async def backup_cmd(ctx):
    if ctx.author.id != OWNER_ID: return
    save_data()
    with open(DATA_FILE, "rb") as file:
        await ctx.author.send("💾 Manual backup requested.", file=discord.File(file, DATA_FILE))
    await ctx.reply("📥 Sent backup to your DMs.")

@bot.hybrid_command(name="ping")
async def ping(ctx): await ctx.reply(f"🏓 Pong! **{round(bot.latency * 1000)}ms**")

@bot.hybrid_command(name="uptime")
async def uptime(ctx): await ctx.reply(f"🚀 Uptime: **{str(datetime.timedelta(seconds=int(round(time.time() - bot.start_time))))}**")

@bot.hybrid_command(name="forget")
async def forget(ctx):
    thread_id = f"{ctx.channel.id}-{ctx.author.id}"
    if thread_id in thread_memory:
        thread_memory[thread_id].clear()
        await ctx.reply("🧠 Memory wiped for this specific thread.")
    else: await ctx.reply("🤷 No memory found.")

@bot.hybrid_command(name="lang")
async def lang(ctx, language: str):
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID): return
    channel_languages[str(ctx.channel.id)] = language
    save_data()
    await ctx.reply(f"🌐 Language updated to **{language}**.")

@bot.hybrid_command(name="refresh")
async def refresh(ctx):
    if ctx.author.id != OWNER_ID: return
    global client
    thread_memory.clear()
    client = AsyncGroq(api_key=GROQ_API_KEY)
    await ctx.reply("🔄 **AI Client Refreshed.** Memory purged.")

@bot.hybrid_command(name="blacklist")
async def blacklist(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    BLACKLISTED_USERS.add(int(user_id))
    save_data()
    await ctx.reply(f"🚫 User `{user_id}` blacklisted.")

@bot.hybrid_command(name="unblacklist")
async def unblacklist(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    uid = int(user_id)
    if uid in BLACKLISTED_USERS: BLACKLISTED_USERS.remove(uid)
    violations_storage[str(uid)] = 0
    save_data()
    await ctx.reply(f"✅ User `{uid}` unbanned.")

@bot.hybrid_command(name="bannedword")
async def bannedword(ctx, word: str):
    if ctx.author.id != OWNER_ID: return
    w = word.lower().strip()
    if w in BANNED_WORDS: BANNED_WORDS.remove(w)
    else: BANNED_WORDS.add(w)
    save_data()
    await ctx.reply(f"🚫 Filter updated for `{w}`.")

@bot.hybrid_command(name="listwords")
async def listwords(ctx):
    if ctx.author.id != OWNER_ID: return
    await ctx.reply(f"📋 **Banned Words:** `{', '.join(BANNED_WORDS) if BANNED_WORDS else 'None'}`")

@bot.hybrid_command(name="listblacklisted")
async def listblacklisted(ctx):
    if ctx.author.id != OWNER_ID: return
    await ctx.reply(f"👥 **Blacklisted IDs:** `{', '.join([str(i) for i in BLACKLISTED_USERS]) if BLACKLISTED_USERS else 'None'}`")

@bot.hybrid_command(name="clearstrikes")
async def clearstrikes(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    violations_storage[str(user_id)] = 0
    save_data()
    await ctx.reply(f"✅ Strikes reset for `{user_id}`.")

# --- AI HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    ctx = await bot.get_context(message)
    if ctx.valid: await bot.invoke(ctx); return

    thread_id = f"{message.channel.id}-{message.author.id}"
    if thread_id not in thread_memory: thread_memory[thread_id] = deque(maxlen=10)

    # Tone Copying Prompt
    sys_prompt = (
        f"Language: {channel_languages.get(str(message.channel.id), 'English')}. "
        "Mirror the user's tone (humor, slang, length, mood) exactly. "
        "Do NOT recall history unless asked. Censor slurs as (censored word)."
    )

    try:
        async with message.channel.typing():
            res = await client.chat.completions.create(
                model=MODEL_NAME, 
                messages=[{"role":"system","content":sys_prompt}] + list(thread_memory[thread_id]) + [{"role":"user","content":message.content}],
                temperature=0.7
            )
            output = res.choices[0].message.content
            if output:
                # 1. Regex Filter
                clean_output = output
                for w in BANNED_WORDS:
                    clean_output = re.compile(rf'\b{re.escape(w)}\b', re.IGNORECASE).sub("(censored word)", clean_output)

                # 2. Collapsed Loophole Detection
                collapsed = "".join(c for c in clean_output.lower() if c.isalnum())
                for w in BANNED_WORDS:
                    if w in collapsed and w not in clean_output.lower().replace("(censored word)", ""):
                        uid_str = str(message.author.id)
                        violations_storage[uid_str] = violations_storage.get(uid_str, 0) + 1
                        is_ban = violations_storage[uid_str] >= 3
                        if is_ban: BLACKLISTED_USERS.add(message.author.id)
                        await log_violation(message.author, message.content, w, is_ban)
                        return 

                thread_memory[thread_id].append({"role": "user", "content": message.content})
                thread_memory[thread_id].append({"role": "assistant", "content": clean_output})
                save_data()
                await message.reply(clean_output)
    except Exception as e: print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
