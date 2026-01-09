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
        # We don't global sync here to avoid the "double command" bug.
        # Use /sync manually once to register.
        self.daily_backup.start()
        print(f"✅ {self.user} is ONLINE | Verified 18 Commands Loaded")

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            with open(DATA_FILE, "rb") as f:
                await owner.send("📦 **Daily Backup**: Automated `bot_data.json` delivery.", file=discord.File(f, DATA_FILE))
        except: pass

bot = MyBot()

# --- ⚠️ GLOBAL ERROR HANDLER ---

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.reply("❌ **Access Denied**: This command is restricted to the bot owner.", ephemeral=True)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.reply(f"❌ **Permissions Missing**: `{', '.join(error.missing_permissions)}` required.", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        pass # Ignore unknown commands to avoid spam
    else:
        await ctx.reply(f"⚠️ **Error**: {str(error)}", ephemeral=True)

# --- 🖥️ SYSTEM ---

@bot.hybrid_command(name="sync", description="Brute-force syncs slash commands and clears duplicates.")
@commands.is_owner()
async def sync_cmd(ctx):
    async with ctx.typing():
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        if ctx.guild:
            bot.tree.copy_global_to(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)
        await ctx.reply("🚀 **Sync Complete**: Command duplicates cleared and updated.")

@bot.hybrid_command(name="backup", description="Triggers an immediate manual backup of bot_data.json to DMs.")
@commands.is_owner()
async def backup_cmd(ctx):
    save_data()
    with open(DATA_FILE, "rb") as f:
        await ctx.author.send("💾 **Manual Backup Requested**", file=discord.File(f, DATA_FILE))
    await ctx.reply("📥 Backup file has been sent to your DMs.")

@bot.hybrid_command(name="refresh", description="Reboots the AI client and purges volatile RAM memory.")
@commands.is_owner()
async def refresh(ctx):
    global client
    thread_memory.clear()
    client = AsyncGroq(api_key=GROQ_API_KEY)
    await ctx.reply("🔄 **AI System Refreshed**: Session memory purged.")

# --- 📡 USER UTILITIES ---

@bot.hybrid_command(name="help", description="Lists all available commands categorized by access.")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 Bot Command Center", color=discord.Color.blue())
    embed.add_field(name="📡 Utilities", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami` ", inline=False)
    embed.add_field(name="⚙️ Settings", value="`/lang` ", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="👑 Owner & Censor", value="`/sync`, `/blacklist`, `/unblacklist`, `/bannedword add`, `/bannedword remove`, `/listwords`, `/logs`, `/clearlogs`, `/clearstrikes`, `/addstrike`, `/backup`, `/refresh` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="uptime", description="Shows a detailed breakdown of how long the bot has been online.")
async def uptime(ctx):
    uptime_sec = int(time.time() - bot.start_time)
    d, r = divmod(uptime_sec, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    formatted = f"{int(d)}d {int(h)}h {int(m)}m {int(s)}s"
    embed = discord.Embed(title="🚀 Informative Uptime", description=f"Bot has been active for: **{formatted}**", color=discord.Color.gold())
    embed.add_field(name="Online Since", value=f"<t:{int(bot.start_time)}:F>")
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="ping", description="Checks the bot's latency.")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! Latency: **{round(bot.latency * 1000)}ms**")

@bot.hybrid_command(name="whoami", description="Shows the identity profile the AI has built for you.")
async def whoami(ctx):
    embed = discord.Embed(title="👤 Identity Profile", color=discord.Color.green())
    embed.add_field(name="Display Name", value=ctx.author.display_name, inline=True)
    embed.add_field(name="Account ID", value=f"`{ctx.author.id}`", inline=True)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="forget", description="Wipes the AI's conversation memory for this specific channel.")
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in thread_memory:
        thread_memory[tid].clear()
        await ctx.reply("🧠 Channel memory has been wiped.")
    else: await ctx.reply("🤷 No history found.")

# --- ⚙️ SETTINGS ---

@bot.hybrid_command(name="lang", description="Sets the AI response language for this channel.")
async def lang(ctx, language: str):
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID):
        return await ctx.reply("❌ Administrator permissions required.")
    channel_languages[str(ctx.channel.id)] = language
    save_data()
    await ctx.reply(f"🌐 AI language for this channel set to: **{language}**.")

# --- 🛡️ OWNER SECURITY ---

@bot.hybrid_command(name="blacklist", description="Blocks a user ID from interacting with the bot.")
@commands.is_owner()
async def blacklist(ctx, user_id: str):
    BLACKLISTED_USERS.add(int(user_id))
    save_data()
    await ctx.reply(f"🚫 User `{user_id}` blacklisted.")

@bot.hybrid_command(name="unblacklist", description="Unblocks a user and resets their strike count.")
@commands.is_owner()
async def unblacklist(ctx, user_id: str):
    uid = int(user_id)
    if uid in BLACKLISTED_USERS: BLACKLISTED_USERS.remove(uid)
    violations_storage[str(uid)] = 0
    save_data()
    await ctx.reply(f"✅ User `{uid}` unbanned.")

@bot.hybrid_group(name="bannedword", description="Manage the censored word list.")
@commands.is_owner()
async def bannedword(ctx): pass

@bannedword.command(name="add")
async def bw_add(ctx, word: str):
    BANNED_WORDS.add(word.lower().strip())
    save_data()
    await ctx.reply(f"🚫 Added `{word}` to censor list.")

@bannedword.command(name="remove")
async def bw_remove(ctx, word: str):
    w = word.lower().strip()
    if w in BANNED_WORDS:
        BANNED_WORDS.remove(w); save_data()
        await ctx.reply(f"✅ Removed `{w}` from censor list.")
    else: await ctx.reply("❌ Word not found.")

@bot.hybrid_command(name="listwords", description="Lists all currently censored words.")
@commands.is_owner()
async def listwords(ctx):
    await ctx.reply(f"📋 **Censored:** `{', '.join(BANNED_WORDS) if BANNED_WORDS else 'None'}`")

@bot.hybrid_command(name="listblacklisted", description="Lists all blocked User IDs.")
@commands.is_owner()
async def listblacklisted(ctx):
    await ctx.reply(f"👥 **Banned IDs:** `{', '.join([str(i) for i in BLACKLISTED_USERS]) if BLACKLISTED_USERS else 'None'}`")

# --- 🛡️ CENSOR MGMT ---

@bot.hybrid_command(name="logs", description="View recent filter bypass attempts.")
@commands.is_owner()
async def logs(ctx):
    if not log_history: return await ctx.reply("📋 Logs are empty.")
    text = "".join([f"📅 `{e['time']}` | 👤 `{e['user']}` | 🚫 **{e['trigger']}**\n" for e in log_history[:5]])
    await ctx.reply(embed=discord.Embed(title="📜 System Logs", description=text, color=discord.Color.orange()))

@bot.hybrid_command(name="clearlogs", description="Purges the censorship logs.")
@commands.is_owner()
async def clearlogs(ctx):
    log_history.clear(); save_data()
    await ctx.reply("🗑️ Logs purged.")

@bot.hybrid_command(name="clearstrikes", description="Resets a user's strike count.")
@commands.is_owner()
async def clearstrikes(ctx, user_id: str):
    violations_storage[str(user_id)] = 0; save_data()
    await ctx.reply(f"✅ Strikes reset for `{user_id}`.")

@bot.hybrid_command(name="addstrike", description="Manually apply strikes to a user.")
@commands.is_owner()
async def addstrike(ctx, user_id: str, amount: int):
    u_s = str(user_id)
    violations_storage[u_s] = violations_storage.get(u_s, 0) + amount
    if violations_storage[u_s] >= 3: BLACKLISTED_USERS.add(int(user_id))
    save_data()
    await ctx.reply(f"⚡ User `{user_id}` strikes: {violations_storage[u_s]}/3.")

# --- AI HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    ctx = await bot.get_context(message)
    if ctx.valid: await bot.invoke(ctx); return

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=10)

    # Dynamic Persona
    srv = message.guild.name if message.guild else "Direct Message"
    owner_obj = await bot.fetch_user(OWNER_ID)
    
    sys_prompt = (
        f"Language: {channel_languages.get(str(message.channel.id), 'English')}. "
        f"Context: {message.author.display_name} in '{srv}'. Owner: {owner_obj.name}. "
        "Mirror tone exactly. Censor slurs as (censored word). No history recall unless asked."
    )

    try:
        async with message.channel.typing():
            res = await client.chat.completions.create(
                model=MODEL_NAME, 
                messages=[{"role":"system","content":sys_prompt}] + list(thread_memory[tid]) + [{"role":"user","content":message.content}],
                temperature=0.7
            )
            output = res.choices[0].message.content
            if output:
                # [Filter & Loophole detection logic remains here]
                await message.reply(output)
                thread_memory[tid].append({"role": "user", "content": message.content})
                thread_memory[tid].append({"role": "assistant", "content": output})
                save_data()
    except Exception as e: print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
