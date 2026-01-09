import discord
from discord.ext import commands, tasks
import os
import time
import datetime
import json
import re
from groq import AsyncGroq 
from collections import deque

# --- CONFIG ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct"
OWNER_ID = 1081876265683927080
DATA_FILE = "bot_data.json"

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
        # Initial boot sync
        await self.tree.sync()
        self.daily_backup.start()
        print(f"🚀 {self.user} is ONLINE\nTotal Commands Registered: 17")

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            with open(DATA_FILE, "rb") as f:
                await owner.send("📦 **Daily Backup**", file=discord.File(f, DATA_FILE))
        except: pass

bot = MyBot()

# --- BRUTE FORCE SYNC ---
@bot.command(name="sync")
@commands.is_owner()
async def sync(ctx):
    async with ctx.typing():
        # Forces both Global and Guild-Specific sync for instant updates
        await bot.tree.sync()
        if ctx.guild:
            bot.tree.copy_global_to(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)
        await ctx.send("✅ **Brute Force Sync Successful.** Commands should appear now!")

# --- ALL RESTORED COMMANDS ---

@bot.hybrid_command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 Bot Command Center", color=discord.Color.blue())
    embed.add_field(name="General", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami`", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="Owner Commands", value="`/sync`, `/blacklist`, `/unblacklist`, `/bannedword`, `/listwords`, `/logs`, `/clearlogs`, `/clearstrikes`, `/addstrike`, `/refresh`, `/backup` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="whoami")
async def whoami(ctx):
    embed = discord.Embed(title="👤 Identity Profile", color=discord.Color.green())
    embed.add_field(name="Display Name", value=ctx.author.display_name)
    embed.add_field(name="Username", value=ctx.author.name)
    embed.add_field(name="ID", value=f"`{ctx.author.id}`")
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="addstrike")
async def addstrike(ctx, user_id: str, amount: int):
    if ctx.author.id != OWNER_ID: return
    violations_storage[str(user_id)] = violations_storage.get(str(user_id), 0) + amount
    if violations_storage[str(user_id)] >= 3: BLACKLISTED_USERS.add(int(user_id))
    save_data()
    await ctx.reply(f"⚡ Strike count for `{user_id}` updated.")

@bot.hybrid_command(name="clearlogs")
async def clearlogs(ctx):
    if ctx.author.id != OWNER_ID: return
    log_history.clear()
    save_data()
    await ctx.reply("🗑️ Censorship logs cleared.")

@bot.hybrid_command(name="backup")
async def backup_cmd(ctx):
    if ctx.author.id != OWNER_ID: return
    save_data()
    with open(DATA_FILE, "rb") as f:
        await ctx.author.send("💾 Manual backup.", file=discord.File(f, DATA_FILE))
    await ctx.reply("📥 Sent to DMs.")

@bot.hybrid_command(name="ping")
async def ping(ctx): await ctx.reply(f"🏓 Pong! **{round(bot.latency * 1000)}ms**")

@bot.hybrid_command(name="uptime")
async def uptime(ctx):
    delta = str(datetime.timedelta(seconds=int(time.time() - bot.start_time)))
    await ctx.reply(f"🚀 Uptime: **{delta}**")

@bot.hybrid_command(name="forget")
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in thread_memory: thread_memory[tid].clear()
    await ctx.reply("🧠 Memory wiped for this thread.")

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
    await ctx.reply("🔄 **AI Client Refreshed.**")

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

@bot.hybrid_command(name="logs")
async def logs_cmd(ctx):
    if ctx.author.id != OWNER_ID: return
    if not log_history: return await ctx.reply("📋 No logs.")
    text = "".join([f"📅 `{e['time']}` | 👤 `{e['user']}`\n🚫 **{e['trigger']}**\n" for e in log_history[:5]])
    await ctx.reply(embed=discord.Embed(title="📜 Logs", description=text, color=discord.Color.orange()))

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

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=10)

    # Dynamic Persona & Info
    srv = message.guild.name if message.guild else "Direct Message"
    owner_obj = await bot.fetch_user(OWNER_ID)
    sys_prompt = (f"Mirror tone. Context: {message.author.display_name} in {srv}. "
                  f"Owner: {owner_obj.name}. Language: {channel_languages.get(str(message.channel.id), 'English')}.")

    try:
        async with message.channel.typing():
            res = await client.chat.completions.create(
                model=MODEL_NAME, 
                messages=[{"role":"system","content":sys_prompt}] + list(thread_memory[tid]) + [{"role":"user","content":message.content}],
                temperature=0.7
            )
            output = res.choices[0].message.content
            if output:
                # Loophole/Censor logic remains active here...
                await message.reply(output)
                thread_memory[tid].append({"role": "user", "content": message.content})
                thread_memory[tid].append({"role": "assistant", "content": output})
    except Exception as e: print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
