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
        await self.tree.sync()
        self.daily_backup.start()
        print(f"✅ {self.user} is ONLINE\nCommands Restored: 18")

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            with open(DATA_FILE, "rb") as f:
                await owner.send("📦 **Daily Backup**", file=discord.File(f, DATA_FILE))
        except: pass

bot = MyBot()

# --- 📡 USER UTILITIES ---

@bot.hybrid_command(name="help", description="Displays a categorized list of all available commands.")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 Bot Command Center", color=discord.Color.blue())
    embed.add_field(name="📡 User Utilities", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami` ", inline=False)
    embed.add_field(name="⚙️ Settings", value="`/lang`", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="👑 Owner Security", value="`/blacklist`, `/unblacklist`, `/bannedword add`, `/bannedword remove`, `/listwords`, `/listblacklisted` ", inline=False)
        embed.add_field(name="🛡️ Censor Mgmt", value="`/logs`, `/clearlogs`, `/clearstrikes`, `/addstrike` ", inline=False)
        embed.add_field(name="🖥️ System", value="`/sync`, `/backup`, `/refresh` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="ping", description="Checks the bot's latency and response time.")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! Latency: **{round(bot.latency * 1000)}ms**")

@bot.hybrid_command(name="uptime", description="Shows how long the bot has been active since the last restart.")
async def uptime(ctx):
    uptime_sec = int(time.time() - bot.start_time)
    days, rem = divmod(uptime_sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    
    formatted_time = f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds)}s"
    embed = discord.Embed(title="🚀 Informative Uptime", color=discord.Color.gold())
    embed.add_field(name="Active Duration", value=f"`{formatted_time}`")
    embed.add_field(name="Start Timestamp", value=f"<t:{int(bot.start_time)}:F>")
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="forget", description="Wipes the AI's conversation memory for this channel.")
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in thread_memory:
        thread_memory[tid].clear()
        await ctx.reply("🧠 Channel memory has been successfully wiped.")
    else:
        await ctx.reply("🤷 No conversation history found.")

@bot.hybrid_command(name="whoami", description="Shows the identity and metadata the AI knows about you.")
async def whoami(ctx):
    embed = discord.Embed(title="👤 Identity Profile", color=discord.Color.green())
    embed.add_field(name="Display Name", value=ctx.author.display_name, inline=True)
    embed.add_field(name="Account ID", value=f"`{ctx.author.id}`", inline=True)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    await ctx.reply(embed=embed)

# --- ⚙️ SETTINGS ---

@bot.hybrid_command(name="lang", description="Sets the primary language for AI responses in this channel.")
async def lang(ctx, language: str):
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID):
        return await ctx.reply("❌ Administrator permissions required.")
    channel_languages[str(ctx.channel.id)] = language
    save_data()
    await ctx.reply(f"🌐 AI language for this channel set to: **{language}**.")

# --- 👑 OWNER SECURITY (with BannedWord Separation) ---

@bot.hybrid_group(name="bannedword", description="Manage the word censorship list.")
async def bannedword(ctx):
    pass

@bannedword.command(name="add", description="Add a new word to the censorship filter.")
async def bw_add(ctx, word: str):
    if ctx.author.id != OWNER_ID: return
    BANNED_WORDS.add(word.lower().strip())
    save_data()
    await ctx.reply(f"🚫 Added `{word}` to the censorship list.")

@bannedword.command(name="remove", description="Remove a word from the censorship filter.")
async def bw_remove(ctx, word: str):
    if ctx.author.id != OWNER_ID: return
    word = word.lower().strip()
    if word in BANNED_WORDS:
        BANNED_WORDS.remove(word)
        save_data()
        await ctx.reply(f"✅ Removed `{word}` from the censorship list.")
    else:
        await ctx.reply("❌ Word not found in the filter.")

@bot.hybrid_command(name="blacklist", description="Blocks a user ID from interacting with the bot.")
async def blacklist(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    BLACKLISTED_USERS.add(int(user_id))
    save_data()
    await ctx.reply(f"🚫 User `{user_id}` has been blacklisted.")

@bot.hybrid_command(name="unblacklist", description="Unblocks a user and resets their strikes.")
async def unblacklist(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    uid = int(user_id)
    if uid in BLACKLISTED_USERS: BLACKLISTED_USERS.remove(uid)
    violations_storage[str(uid)] = 0
    save_data()
    await ctx.reply(f"✅ User `{uid}` is now unblocked.")

@bot.hybrid_command(name="listwords", description="Displays all words currently in the censorship filter.")
async def listwords(ctx):
    if ctx.author.id != OWNER_ID: return
    await ctx.reply(f"📋 **Censored Words:** `{', '.join(BANNED_WORDS) if BANNED_WORDS else 'None'}`")

@bot.hybrid_command(name="listblacklisted", description="Lists all User IDs currently blocked from the bot.")
async def listblacklisted(ctx):
    if ctx.author.id != OWNER_ID: return
    await ctx.reply(f"👥 **Banned IDs:** `{', '.join([str(i) for i in BLACKLISTED_USERS]) if BLACKLISTED_USERS else 'None'}`")

# --- 🛡️ CENSOR MGMT ---

@bot.hybrid_command(name="logs", description="View the most recent filter bypass attempts.")
async def logs(ctx):
    if ctx.author.id != OWNER_ID: return
    if not log_history: return await ctx.reply("📋 Logs are currently empty.")
    text = "".join([f"📅 `{e['time']}` | 👤 `{e['user']}`\n🚫 **{e['trigger']}**\n" for e in log_history[:5]])
    await ctx.reply(embed=discord.Embed(title="📜 Censorship Logs", description=text, color=discord.Color.orange()))

@bot.hybrid_command(name="clearlogs", description="Clears the history of censorship logs.")
async def clearlogs(ctx):
    if ctx.author.id != OWNER_ID: return
    log_history.clear()
    save_data()
    await ctx.reply("🗑️ Logs have been purged.")

@bot.hybrid_command(name="clearstrikes", description="Resets a user's strike count back to zero.")
async def clearstrikes(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    violations_storage[str(user_id)] = 0
    save_data()
    await ctx.reply(f"✅ Strikes reset for `{user_id}`.")

@bot.hybrid_command(name="addstrike", description="Manually apply a strike count to a specific user.")
async def addstrike(ctx, user_id: str, amount: int):
    if ctx.author.id != OWNER_ID: return
    uid_s = str(user_id)
    violations_storage[uid_s] = violations_storage.get(uid_s, 0) + amount
    if violations_storage[uid_s] >= 3: BLACKLISTED_USERS.add(int(user_id))
    save_data()
    await ctx.reply(f"⚡ User `{user_id}` now has {violations_storage[uid_s]}/3 strikes.")

# --- 🖥️ SYSTEM ---

@bot.hybrid_command(name="sync", description="Brute-force syncs slash commands with Discord globally and locally.")
async def sync_cmd(ctx):
    if ctx.author.id != OWNER_ID: return
    async with ctx.typing():
        await bot.tree.sync()
        if ctx.guild:
            bot.tree.copy_global_to(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)
        await ctx.reply("🚀 **Brute Force Sync Successful.**")

@bot.hybrid_command(name="backup", description="Triggers a manual backup of the bot_data.json file to your DMs.")
async def backup_cmd(ctx):
    if ctx.author.id != OWNER_ID: return
    save_data()
    with open(DATA_FILE, "rb") as f:
        await ctx.author.send("💾 **Manual Backup Requested**", file=discord.File(f, DATA_FILE))
    await ctx.reply("📥 Check your DMs for the backup.")

@bot.hybrid_command(name="refresh", description="Reboots the AI client and purges temporary session memory.")
async def refresh(ctx):
    if ctx.author.id != OWNER_ID: return
    global client
    thread_memory.clear()
    client = AsyncGroq(api_key=GROQ_API_KEY)
    await ctx.reply("🔄 **AI Refresh Complete.**")

# --- AI HANDLER (Simplified for clarity) ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    ctx = await bot.get_context(message)
    if ctx.valid: await bot.invoke(ctx); return
    # AI response logic continues here...

bot.run(DISCORD_TOKEN)
