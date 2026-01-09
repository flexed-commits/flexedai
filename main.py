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

# RAM Memory (Resets on restart)
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
        print(f"🚀 {self.user} is ONLINE | Commands: 18")

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            with open(DATA_FILE, "rb") as f:
                await owner.send("📦 **Daily Backup**: Automated `bot_data.json` delivery.", file=discord.File(f, DATA_FILE))
        except: pass

bot = MyBot()

# --- LOGGING HELPER ---
async def log_violation(user, content, trigger, is_ban=False):
    log_entry = {"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "user": str(user), "trigger": trigger, "action": "BAN" if is_ban else "CENSOR"}
    log_history.insert(0, log_entry)
    if len(log_history) > 20: log_history.pop()
    save_data()
    try:
        owner = await bot.fetch_user(OWNER_ID)
        await owner.send(f"🚩 **Bypass Attempt**: {user.name} tried `{trigger}`. Strikes: {violations_storage.get(str(user.id), 0)}/3")
    except: pass

# --- 📡 USER UTILITIES ---

@bot.hybrid_command(name="help", description="Displays a categorized list of all available commands.")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 Bot Command Center", color=discord.Color.blue())
    embed.add_field(name="📡 User Utilities", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami` ", inline=False)
    embed.add_field(name="⚙️ Settings", value="`/lang` ", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="👑 Owner Security", value="`/blacklist`, `/unblacklist`, `/bannedword add`, `/bannedword remove`, `/listwords`, `/listblacklisted` ", inline=False)
        embed.add_field(name="🛡️ Censor Mgmt", value="`/logs`, `/clearlogs`, `/clearstrikes`, `/addstrike` ", inline=False)
        embed.add_field(name="🖥️ System", value="`/sync`, `/backup`, `/refresh` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="ping", description="Checks the bot's latency and response time.")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! Latency: **{round(bot.latency * 1000)}ms**")

@bot.hybrid_command(name="uptime", description="Shows how long the bot has been active with detailed duration.")
async def uptime(ctx):
    uptime_sec = int(time.time() - bot.start_time)
    days, rem = divmod(uptime_sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    formatted = f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds)}s"
    embed = discord.Embed(title="🚀 Bot Uptime Information", color=discord.Color.gold())
    embed.add_field(name="Duration", value=f"`{formatted}`", inline=True)
    embed.add_field(name="Online Since", value=f"<t:{int(bot.start_time)}:F>", inline=True)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="forget", description="Wipes the AI's conversation memory for this channel.")
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in thread_memory:
        thread_memory[tid].clear()
        await ctx.reply("🧠 Channel memory has been successfully wiped.")
    else: await ctx.reply("🤷 No conversation history found.")

@bot.hybrid_command(name="whoami", description="Shows the identity and metadata the AI knows about you.")
async def whoami(ctx):
    embed = discord.Embed(title="👤 Identity Profile", color=discord.Color.green())
    embed.add_field(name="Display Name", value=ctx.author.display_name, inline=True)
    embed.add_field(name="Username", value=ctx.author.name, inline=True)
    embed.add_field(name="ID", value=f"`{ctx.author.id}`", inline=True)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    await ctx.reply(embed=embed)

# --- ⚙️ SETTINGS ---

@bot.hybrid_command(name="lang", description="Sets the primary language for AI responses in this channel.")
async def lang(ctx, language: str):
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID): return
    channel_languages[str(ctx.channel.id)] = language
    save_data()
    await ctx.reply(f"🌐 AI language for this channel set to: **{language}**.")

# --- 👑 OWNER SECURITY ---

@bot.hybrid_group(name="bannedword", description="Manage the word censorship list.")
async def bannedword(ctx): pass

@bannedword.command(name="add", description="Add a new word to the censorship filter.")
async def bw_add(ctx, word: str):
    if ctx.author.id != OWNER_ID: return
    BANNED_WORDS.add(word.lower().strip())
    save_data()
    await ctx.reply(f"🚫 Added `{word}` to filter.")

@bannedword.command(name="remove", description="Remove a word from the censorship filter.")
async def bw_remove(ctx, word: str):
    if ctx.author.id != OWNER_ID: return
    word = word.lower().strip()
    if word in BANNED_WORDS:
        BANNED_WORDS.remove(word)
        save_data()
        await ctx.reply(f"✅ Removed `{word}` from filter.")
    else: await ctx.reply("❌ Word not found.")

@bot.hybrid_command(name="blacklist", description="Blocks a user ID from using the bot.")
async def blacklist(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    BLACKLISTED_USERS.add(int(user_id))
    save_data()
    await ctx.reply(f"🚫 User `{user_id}` blacklisted.")

@bot.hybrid_command(name="unblacklist", description="Unblocks a user and resets their strikes.")
async def unblacklist(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    uid = int(user_id)
    if uid in BLACKLISTED_USERS: BLACKLISTED_USERS.remove(uid)
    violations_storage[str(uid)] = 0
    save_data()
    await ctx.reply(f"✅ User `{uid}` unblocked.")

@bot.hybrid_command(name="listwords", description="Displays all censored words.")
async def listwords(ctx):
    if ctx.author.id != OWNER_ID: return
    await ctx.reply(f"📋 **Censored Words:** `{', '.join(BANNED_WORDS) if BANNED_WORDS else 'None'}`")

@bot.hybrid_command(name="listblacklisted", description="Lists all blocked User IDs.")
async def listblacklisted(ctx):
    if ctx.author.id != OWNER_ID: return
    await ctx.reply(f"👥 **Banned IDs:** `{', '.join([str(i) for i in BLACKLISTED_USERS]) if BLACKLISTED_USERS else 'None'}`")

# --- 🛡️ CENSOR MGMT ---

@bot.hybrid_command(name="logs", description="View the most recent filter bypass attempts.")
async def logs(ctx):
    if ctx.author.id != OWNER_ID: return
    if not log_history: return await ctx.reply("📋 Logs empty.")
    text = "".join([f"📅 `{e['time']}` | 👤 `{e['user']}` | 🚫 **{e['trigger']}**\n" for e in log_history[:5]])
    await ctx.reply(embed=discord.Embed(title="📜 Logs", description=text, color=discord.Color.orange()))

@bot.hybrid_command(name="clearlogs", description="Purges the censorship logs.")
async def clearlogs(ctx):
    if ctx.author.id != OWNER_ID: return
    log_history.clear()
    save_data()
    await ctx.reply("🗑️ Logs cleared.")

@bot.hybrid_command(name="clearstrikes", description="Resets a user's strike count.")
async def clearstrikes(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    violations_storage[str(user_id)] = 0
    save_data()
    await ctx.reply(f"✅ Strikes reset for `{user_id}`.")

@bot.hybrid_command(name="addstrike", description="Manually apply a strike to a specific user.")
async def addstrike(ctx, user_id: str, amount: int):
    if ctx.author.id != OWNER_ID: return
    uid_s = str(user_id)
    violations_storage[uid_s] = violations_storage.get(uid_s, 0) + amount
    if violations_storage[uid_s] >= 3: BLACKLISTED_USERS.add(int(user_id))
    save_data()
    await ctx.reply(f"⚡ User `{user_id}`: {violations_storage[uid_s]}/3 strikes.")

# --- 🖥️ SYSTEM ---

@bot.hybrid_command(name="sync", description="Brute-force syncs slash commands.")
async def sync_cmd(ctx):
    if ctx.author.id != OWNER_ID: return
    async with ctx.typing():
        await bot.tree.sync()
        if ctx.guild:
            bot.tree.copy_global_to(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)
        await ctx.reply("🚀 **Sync Successful.**")

@bot.hybrid_command(name="backup", description="Manual JSON backup to DMs.")
async def backup_cmd(ctx):
    if ctx.author.id != OWNER_ID: return
    save_data()
    with open(DATA_FILE, "rb") as f:
        await ctx.author.send("💾 **Manual Backup**", file=discord.File(f, DATA_FILE))
    await ctx.reply("📥 Check DMs.")

@bot.hybrid_command(name="refresh", description="Reboots AI client and purges RAM.")
async def refresh(ctx):
    if ctx.author.id != OWNER_ID: return
    global client
    thread_memory.clear()
    client = AsyncGroq(api_key=GROQ_API_KEY)
    await ctx.reply("🔄 **Refresh Complete.**")

# --- AI HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    ctx = await bot.get_context(message)
    if ctx.valid: await bot.invoke(ctx); return

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=10)

    srv = message.guild.name if message.guild else "Direct Message"
    owner_obj = await bot.fetch_user(OWNER_ID)
    
    sys_prompt = (
        f"Language: {channel_languages.get(str(message.channel.id), 'English')}. "
        f"Context: {message.author.display_name} in server '{srv}'. Owner: {owner_obj.name}. "
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
                clean_output = output
                for w in BANNED_WORDS:
                    clean_output = re.compile(rf'\b{re.escape(w)}\b', re.IGNORECASE).sub("(censored word)", clean_output)

                collapsed = "".join(c for c in clean_output.lower() if c.isalnum())
                for w in BANNED_WORDS:
                    if w in collapsed and w not in clean_output.lower().replace("(censored word)", ""):
                        uid_s = str(message.author.id)
                        violations_storage[uid_s] = violations_storage.get(uid_s, 0) + 1
                        is_b = violations_storage[uid_s] >= 3
                        if is_b: BLACKLISTED_USERS.add(message.author.id)
                        await log_violation(message.author, message.content, w, is_b)
                        return 

                thread_memory[tid].append({"role": "user", "content": message.content})
                thread_memory[tid].append({"role": "assistant", "content": clean_output})
                save_data()
                await message.reply(clean_output)
    except Exception as e: print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
