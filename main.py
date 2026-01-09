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
        # Soft sync: only updates what changed without wiping
        await self.tree.sync()
        self.daily_backup.start()
        print(f"✅ {self.user} Online | All 18 Commands Initialized")

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            with open(DATA_FILE, "rb") as f:
                await owner.send("📦 **Daily Backup**", file=discord.File(f, DATA_FILE))
        except: pass

bot = MyBot()

# --- ⚠️ ERROR HANDLER ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.reply("❌ **Owner Only Command**", ephemeral=True)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.reply(f"❌ Missing: `{', '.join(error.missing_permissions)}`", ephemeral=True)

# --- 🖥️ SYSTEM ---

@bot.hybrid_command(name="sync", description="Brute-force syncs slash commands without wiping them.")
@commands.is_owner()
async def sync_cmd(ctx):
    async with ctx.typing():
        # Syncing directly to the guild is faster for testing
        if ctx.guild:
            bot.tree.copy_global_to(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)
        # Still sync globally for other servers
        await bot.tree.sync()
        await ctx.reply("🚀 **Brute Force Sync Complete.** Try restarting your Discord app if they don't appear.")

@bot.hybrid_command(name="backup", description="Manual backup of bot_data.json.")
@commands.is_owner()
async def backup_cmd(ctx):
    save_data()
    with open(DATA_FILE, "rb") as f:
        await ctx.author.send("💾 **Manual Backup**", file=discord.File(f, DATA_FILE))
    await ctx.reply("📥 Sent to DMs.")

@bot.hybrid_command(name="refresh", description="Refreshes AI client and purges RAM.")
@commands.is_owner()
async def refresh(ctx):
    global client
    thread_memory.clear()
    client = AsyncGroq(api_key=GROQ_API_KEY)
    await ctx.reply("🔄 **AI System Refreshed.**")

# --- 📡 USER UTILITIES ---

@bot.hybrid_command(name="help", description="Lists all 18 active commands.")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 Master Command Center", color=discord.Color.blue())
    embed.add_field(name="📡 Utilities", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami` ", inline=False)
    embed.add_field(name="⚙️ Settings", value="`/lang` ", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="👑 Security", value="`/blacklist`, `/unblacklist`, `/bannedword add`, `/bannedword remove`, `/listwords`, `/listblacklisted` ", inline=False)
        embed.add_field(name="🛡️ Censor", value="`/logs`, `/clearlogs`, `/clearstrikes`, `/addstrike` ", inline=False)
        embed.add_field(name="🖥️ System", value="`/sync`, `/backup`, `/refresh` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="uptime", description="Informative bot uptime.")
async def uptime(ctx):
    s = int(time.time() - bot.start_time)
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    await ctx.reply(f"🚀 **Uptime**: `{int(d)}d {int(h)}h {int(m)}m {int(s)}s`")

@bot.hybrid_command(name="ping")
async def ping(ctx): await ctx.reply(f"🏓 **{round(bot.latency * 1000)}ms**")

@bot.hybrid_command(name="whoami")
async def whoami(ctx):
    embed = discord.Embed(title="👤 Profile", color=discord.Color.green())
    embed.add_field(name="Name", value=ctx.author.display_name)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="forget")
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in thread_memory: thread_memory[tid].clear()
    await ctx.reply("🧠 Memory wiped.")

# --- ⚙️ SETTINGS ---

@bot.hybrid_command(name="lang")
async def lang(ctx, language: str):
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID): return
    channel_languages[str(ctx.channel.id)] = language
    save_data()
    await ctx.reply(f"🌐 Language set to `{language}`.")

# --- 👑 OWNER SECURITY ---

@bot.hybrid_command(name="blacklist")
@commands.is_owner()
async def blacklist(ctx, user_id: str):
    BLACKLISTED_USERS.add(int(user_id)); save_data()
    await ctx.reply(f"🚫 User `{user_id}` blacklisted.")

@bot.hybrid_command(name="unblacklist")
@commands.is_owner()
async def unblacklist(ctx, user_id: str):
    uid = int(user_id)
    if uid in BLACKLISTED_USERS: BLACKLISTED_USERS.remove(uid)
    violations_storage[str(uid)] = 0; save_data()
    await ctx.reply(f"✅ User `{uid}` unbanned.")

@bot.hybrid_group(name="bannedword")
@commands.is_owner()
async def bannedword(ctx): pass

@bannedword.command(name="add")
async def bw_add(ctx, word: str):
    BANNED_WORDS.add(word.lower()); save_data()
    await ctx.reply(f"🚫 Added `{word}`.")

@bannedword.command(name="remove")
async def bw_remove(ctx, word: str):
    w = word.lower()
    if w in BANNED_WORDS: BANNED_WORDS.remove(w); save_data(); await ctx.reply(f"✅ Removed `{w}`.")
    else: await ctx.reply("❌ Not found.")

@bot.hybrid_command(name="listwords")
@commands.is_owner()
async def listwords(ctx):
    await ctx.reply(f"📋 **Censored**: `{', '.join(BANNED_WORDS) if BANNED_WORDS else 'None'}`")

@bot.hybrid_command(name="listblacklisted")
@commands.is_owner()
async def listblacklisted(ctx):
    await ctx.reply(f"👥 **Banned IDs**: `{', '.join([str(i) for i in BLACKLISTED_USERS]) if BLACKLISTED_USERS else 'None'}`")

# --- 🛡️ CENSOR MGMT ---

@bot.hybrid_command(name="logs")
@commands.is_owner()
async def logs(ctx):
    if not log_history: return await ctx.reply("📋 Logs empty.")
    text = "".join([f"📅 `{e['time']}` | 👤 `{e['user']}` | 🚫 **{e['trigger']}**\n" for e in log_history[:5]])
    await ctx.reply(embed=discord.Embed(title="📜 Logs", description=text, color=discord.Color.orange()))

@bot.hybrid_command(name="clearlogs")
@commands.is_owner()
async def clearlogs(ctx):
    log_history.clear(); save_data(); await ctx.reply("🗑️ Logs purged.")

@bot.hybrid_command(name="clearstrikes")
@commands.is_owner()
async def clearstrikes(ctx, user_id: str):
    violations_storage[str(user_id)] = 0; save_data(); await ctx.reply(f"✅ Strikes reset for `{user_id}`.")

@bot.hybrid_command(name="addstrike")
@commands.is_owner()
async def addstrike(ctx, user_id: str, amount: int):
    u = str(user_id)
    violations_storage[u] = violations_storage.get(u, 0) + amount
    if violations_storage[u] >= 3: BLACKLISTED_USERS.add(int(user_id))
    save_data(); await ctx.reply(f"⚡ `{user_id}` strikes: {violations_storage[u]}/3.")

# --- AI HANDLER ---
@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    ctx = await bot.get_context(message)
    if ctx.valid: await bot.invoke(ctx); return
    # AI logic...
    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=10)
    try:
        async with message.channel.typing():
            res = await client.chat.completions.create(
                model=MODEL_NAME, 
                messages=[{"role":"system","content":"Mirror tone."}] + list(thread_memory[tid]) + [{"role":"user","content":message.content}],
                temperature=0.7
            )
            output = res.choices[0].message.content
            if output:
                await message.reply(output)
                thread_memory[tid].append({"role":"user","content":message.content})
                thread_memory[tid].append({"role":"assistant","content":output})
    except Exception as e: print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
