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
        # FIX: Removed the global tree.sync() here to prevent duplicates
        # You should only use the manual /sync once to register them
        self.daily_backup.start()
        print(f"✅ {self.user} is ONLINE | Duplicate Bug Fixed")

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            with open(DATA_FILE, "rb") as f:
                await owner.send("📦 **Daily Backup**", file=discord.File(f, DATA_FILE))
        except: pass

bot = MyBot()

# --- GLOBAL ERROR HANDLER ---

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.reply("❌ **Access Denied**: Only the bot owner can use this command.", ephemeral=True)
    elif isinstance(error, commands.MissingPermissions):
        perms = ", ".join(error.missing_permissions)
        await ctx.reply(f"❌ **Permission Error**: You need `{perms}` to do that.", ephemeral=True)
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏳ **Cooldown**: Try again in {error.retry_after:.2f}s.", ephemeral=True)
    else:
        print(f"Unhandled Error: {error}")

# --- 🖥️ SYSTEM / SYNC ---

@bot.hybrid_command(name="sync", description="Brute-force syncs slash commands. Clears duplicates.")
@commands.is_owner()
async def sync_cmd(ctx):
    async with ctx.typing():
        # Clear existing global commands to fix duplication
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        
        # Sync specifically to this guild for immediate result
        if ctx.guild:
            bot.tree.copy_global_to(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)
            
        await ctx.reply("🚀 **Brute Force Sync Successful.** Global duplicates cleared.")

# --- 📡 USER UTILITIES ---

@bot.hybrid_command(name="help", description="Displays all commands.")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 Master Command Center", color=discord.Color.blue())
    embed.add_field(name="📡 Utilities", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami` ", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="👑 Owner & Censor", value="`/sync`, `/blacklist`, `/unblacklist`, `/bannedword add`, `/bannedword remove`, `/listwords`, `/logs`, `/clearstrikes`, `/addstrike`, `/backup`, `/refresh` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="uptime", description="Detailed online duration.")
async def uptime(ctx):
    uptime_sec = int(time.time() - bot.start_time)
    days, rem = divmod(uptime_sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    formatted = f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds)}s"
    embed = discord.Embed(title="🚀 Bot Uptime", description=f"Running for: `{formatted}`", color=discord.Color.gold())
    await ctx.reply(embed=embed)

# ... (Add ping, forget, whoami, lang, blacklist, unblacklist here using @commands.is_owner() for admin ones) ...

# --- 🛡️ BANNED WORD GROUP ---

@bot.hybrid_group(name="bannedword", description="Manage censored words.")
@commands.is_owner()
async def bannedword(ctx): pass

@bannedword.command(name="add", description="Add word to filter.")
async def bw_add(ctx, word: str):
    BANNED_WORDS.add(word.lower().strip())
    save_data()
    await ctx.reply(f"🚫 Added `{word}` to filter.")

@bannedword.command(name="remove", description="Remove word from filter.")
async def bw_remove(ctx, word: str):
    word = word.lower().strip()
    if word in BANNED_WORDS:
        BANNED_WORDS.remove(word)
        save_data()
        await ctx.reply(f"✅ Removed `{word}`.")
    else: await ctx.reply("❌ Word not found.")

# --- 🛡️ CENSOR MGMT ---

@bot.hybrid_command(name="logs")
@commands.is_owner()
async def logs(ctx):
    if not log_history: return await ctx.reply("📋 Logs empty.")
    text = "".join([f"📅 `{e['time']}` | 👤 `{e['user']}` | 🚫 **{e['trigger']}**\n" for e in log_history[:5]])
    await ctx.reply(embed=discord.Embed(title="📜 Logs", description=text, color=discord.Color.orange()))

@bot.hybrid_command(name="clearstrikes")
@commands.is_owner()
async def clearstrikes(ctx, user_id: str):
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

    try:
        async with message.channel.typing():
            res = await client.chat.completions.create(
                model=MODEL_NAME, 
                messages=[{"role":"system","content":"Mirror tone. Censor slurs."}] + list(thread_memory[tid]) + [{"role":"user","content":message.content}],
                temperature=0.7
            )
            output = res.choices[0].message.content
            if output:
                # Censorship/Loophole Logic...
                await message.reply(output)
                thread_memory[tid].append({"role":"user","content":message.content})
                thread_memory[tid].append({"role":"assistant","content":output})
                save_data()
    except Exception as e: print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
