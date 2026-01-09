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
        # Ensure command_prefix is set correctly for prefix-style calling
        super().__init__(command_prefix="/", intents=intents, help_command=None)
        self.start_time = time.time()

    async def setup_hook(self):
        # Initial sync on startup
        try:
            await self.tree.sync()
            print("🟢 Global Slash Commands Synced.")
        except Exception as e:
            print(f"🔴 Sync Error on startup: {e}")
        self.daily_backup.start()

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            with open(DATA_FILE, "rb") as f:
                await owner.send("📦 Daily Backup", file=discord.File(f, DATA_FILE))
        except: pass

bot = MyBot()

# --- BRUTE FORCE SYNC COMMAND ---

@bot.command(name="sync")
@commands.is_owner()
async def sync(ctx):
    """Owner Only: Brute forces the slash commands to update."""
    async with ctx.typing():
        try:
            # Syncing globally
            synced = await bot.tree.sync()
            # Also syncing to the current guild for instant results
            if ctx.guild:
                bot.tree.copy_global_to(guild=ctx.guild)
                await bot.tree.sync(guild=ctx.guild)
            await ctx.send(f"🚀 **Brute Force Sync Complete!** Synced {len(synced)} commands globally and to this server.")
            print(f"✅ Manual Sync triggered by {ctx.author}")
        except Exception as e:
            await ctx.send(f"❌ Sync Failed: {e}")

# --- RESTORED COMMANDS ---

@bot.hybrid_command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 Master Command List", color=discord.Color.blue())
    embed.add_field(name="📡 General", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami` ", inline=False)
    embed.add_field(name="👑 Owner Only", value="`/sync`, `/blacklist`, `/unblacklist`, `/bannedword`, `/listwords`, `/logs`, `/clearstrikes`, `/addstrike`, `/backup` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="whoami")
async def whoami(ctx):
    owner = await bot.fetch_user(OWNER_ID)
    embed = discord.Embed(title="👤 Identity Profile", color=discord.Color.green())
    embed.add_field(name="Name", value=ctx.author.display_name)
    embed.add_field(name="ID", value=f"`{ctx.author.id}`")
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="ping")
async def ping(ctx): await ctx.reply(f"🏓 Pong! **{round(bot.latency * 1000)}ms**")

@bot.hybrid_command(name="uptime")
async def uptime(ctx):
    uptime_sec = int(round(time.time() - bot.start_time))
    await ctx.reply(f"🚀 Uptime: **{str(datetime.timedelta(seconds=uptime_sec))}**")

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

@bot.hybrid_command(name="logs")
async def logs(ctx):
    if ctx.author.id != OWNER_ID: return
    if not log_history: return await ctx.reply("📋 No logs.")
    text = "".join([f"📅 `{e['time']}` | 👤 `{e['user']}`\n🚫 **{e['trigger']}**\n" for e in log_history[:5]])
    await ctx.reply(embed=discord.Embed(title="📜 Logs", description=text, color=discord.Color.orange()))

# --- AI HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    
    # Process prefix commands first
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # Handle AI Conversation
    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=10)

    srv = message.guild.name if message.guild else "DM"
    sys_prompt = f"Mirror tone. Context: {message.author.display_name} in {srv}. Language: {channel_languages.get(str(message.channel.id), 'English')}."

    try:
        async with message.channel.typing():
            res = await client.chat.completions.create(
                model=MODEL_NAME, 
                messages=[{"role":"system","content":sys_prompt}] + list(thread_memory[tid]) + [{"role":"user","content":message.content}],
                temperature=0.7
            )
            output = res.choices[0].message.content
            if output:
                # Censorship Logic
                clean_output = output
                for w in BANNED_WORDS:
                    clean_output = re.compile(rf'\b{re.escape(w)}\b', re.IGNORECASE).sub("(censored)", clean_output)
                
                await message.reply(clean_output)
                thread_memory[tid].append({"role": "user", "content": message.content})
                thread_memory[tid].append({"role": "assistant", "content": output})
    except Exception as e: print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
