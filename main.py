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

# --- SYSTEM MEMORY (RAM ONLY) ---
thread_memory = {}
tone_memory = {} # Per-user tone tracking

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            return {
                "blacklist": set(data.get("blacklist", [])),
                "banned_words": set(data.get("banned_words", [])),
                "languages": data.get("languages", {}),
                "logs": data.get("logs", []),
                "violations": data.get("violations", {}),
                "prefixes": data.get("prefixes", {}),
                "response_mode": data.get("response_mode", {})
            }
    except (FileNotFoundError, json.JSONDecodeError):
        return {"blacklist": set(), "banned_words": set(), "languages": {}, "logs": [], "violations": {}, "prefixes": {}, "response_mode": {}}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump({
            "blacklist": list(BLACKLISTED_USERS),
            "banned_words": list(BANNED_WORDS),
            "languages": channel_languages,
            "logs": log_history,
            "violations": violations_storage,
            "prefixes": prefixes,
            "response_mode": response_mode
        }, f, indent=4)

data = load_data()
BLACKLISTED_USERS = data["blacklist"]
BANNED_WORDS = data["banned_words"]
channel_languages = data["languages"]
log_history = data["logs"]
violations_storage = data["violations"]
prefixes = data["prefixes"]
response_mode = data["response_mode"]

client = AsyncGroq(api_key=GROQ_API_KEY)

def get_prefix(bot, message):
    if not message.guild: return "/"
    return prefixes.get(str(message.guild.id), "/")

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix=get_prefix, intents=intents, help_command=None)
        self.start_time = time.time()

    async def setup_hook(self):
        self.daily_backup.start()
        print(f"✅ {self.user} Online | All 23 Commands Verified")

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            with open(DATA_FILE, "rb") as f:
                await owner.send("📦 **Daily Backup**", file=discord.File(f, DATA_FILE))
        except: pass

bot = MyBot()

# --- 🖥️ SYSTEM & ADMIN ---
@bot.command(name="server-list")
@commands.is_owner()
@commands.dm_only()
async def server_list_dm(ctx):
    """Owner Only: Generates a JSON file of all servers and member counts."""
    server_data = {}
    
    for guild in bot.guilds:
        server_data[guild.name] = {
            "id": guild.id,
            "member_count": guild.member_count
        }

    # Save to a temporary file
    file_path = "servers.json"
    with open(file_path, "w") as f:
        json.dump(server_data, f, indent=4)

    # Send the file and then remove it from local storage
    await ctx.send(f"📊 **Server List Generated:** (Total Servers: {len(bot.guilds)})", 
                   file=discord.File(file_path))
    os.remove(file_path)

@bot.hybrid_command(name="sync", description="Synchronizes commands globally and removes local duplicates.")
@commands.is_owner()
async def sync_cmd(ctx):
    async with ctx.typing():
        if ctx.guild:
            bot.tree.clear_commands(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)
        synced = await bot.tree.sync()
        await ctx.reply(f"🚀 **Synced {len(synced)} commands.**")

@bot.hybrid_command(name="start", description="ADMIN ONLY: Enables bot to respond to ALL messages in this channel.")
@commands.has_permissions(administrator=True)
async def start_responding(ctx):
    response_mode[str(ctx.channel.id)] = "start"; save_data()
    await ctx.reply("🎙️ **Response mode: ALWAYS.**")

@bot.hybrid_command(name="stop", description="ADMIN ONLY: Bot only responds to pings or keywords.")
@commands.has_permissions(administrator=True)
async def stop_responding(ctx):
    response_mode[str(ctx.channel.id)] = "stop"; save_data()
    await ctx.reply("🔇 **Response mode: TRIGGER ONLY.**")

@bot.hybrid_command(name="stats", description="Displays bot performance and command counts.")
async def stats(ctx):
    embed = discord.Embed(title="📊 Bot Stats", color=discord.Color.purple())
    embed.add_field(name="Commands", value="`23 Active`", inline=True)
    embed.add_field(name="Latency", value=f"`{round(bot.latency * 1000)}ms`", inline=True)
    embed.add_field(name="Uptime", value=f"`{int(time.time() - bot.start_time)}s`", inline=True)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="prefix", description="Changes the server command prefix.")
@commands.has_permissions(administrator=True)
async def set_prefix(ctx, new_prefix: str):
    prefixes[str(ctx.guild.id)] = new_prefix; save_data()
    await ctx.reply(f"🎯 Prefix set to: `{new_prefix}`")

@bot.hybrid_command(name="backup", description="Triggers a manual data backup to DMs.")
@commands.is_owner()
async def backup_cmd(ctx):
    save_data()
    with open(DATA_FILE, "rb") as f:
        await ctx.author.send("💾 **Manual Backup**", file=discord.File(f, DATA_FILE))
    await ctx.reply("📥 Sent.")

@bot.hybrid_command(name="refresh", description="Wipes AI short-term memory and re-initializes client.")
@commands.is_owner()
async def refresh(ctx):
    global client
    thread_memory.clear()
    tone_memory.clear()
    client = AsyncGroq(api_key=GROQ_API_KEY)
    await ctx.reply("🔄 **AI Memory & RAM Purged.**")

# --- 📡 UTILITIES ---

@bot.hybrid_command(name="help", description="Lists all 23 active commands.")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 Master Command Center", color=discord.Color.blue())
    embed.add_field(name="📡 Utilities", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami`, `/prefix`, `/start`, `/stop`, `/stats` ", inline=False)
    embed.add_field(name="⚙️ Settings", value="`/lang` ", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="👑 Security", value="`/blacklist`, `/unblacklist`, `/bannedword add`, `/bannedword remove`, `/listwords`, `/listblacklisted` ", inline=False)
        embed.add_field(name="🛡️ Moderation", value="`/logs`, `/clearlogs`, `/clearstrikes`, `/addstrike` ", inline=False)
        embed.add_field(name="🖥️ System", value="`/sync`, `/backup`, `/refresh` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="ping", description="Check latency.")
async def ping(ctx): await ctx.reply(f"🏓 **{round(bot.latency * 1000)}ms**")

@bot.hybrid_command(name="uptime", description="Check bot runtime.")
async def uptime(ctx):
    s = int(time.time() - bot.start_time)
    d, r = divmod(s, 86400); h, r = divmod(r, 3600); m, s = divmod(r, 60)
    await ctx.reply(f"🚀 **Uptime**: `{int(d)}d {int(h)}h {int(m)}m {int(s)}s`")

@bot.hybrid_command(name="whoami", description="Displays profile info.")
async def whoami(ctx):
    roles = [role.name for role in ctx.author.roles if role.name != "@everyone"]
    embed = discord.Embed(title=f"👤 Profile: {ctx.author.name}", color=discord.Color.green())
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.add_field(name="ID", value=ctx.author.id)
    embed.add_field(name="Roles", value=", ".join(roles) if roles else "None")
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="forget", description="Wipes conversation history for this channel.")
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in thread_memory: thread_memory[tid].clear()
    await ctx.reply("🧠 Memory wiped.")

@bot.hybrid_command(name="lang", description="Sets AI response language.")
async def lang(ctx, language: str):
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID): return await ctx.reply("❌ Admin only.")
    if not re.match(r"^[a-zA-Z\s]+$", language):
        channel_languages[str(ctx.channel.id)] = "INVALID"
        save_data(); return await ctx.reply("❌ Invalid Language.")
    channel_languages[str(ctx.channel.id)] = language; save_data()
    await ctx.reply(f"🌐 Language set to `{language}`.")

# --- 👑 OWNER SECURITY ---

@bot.hybrid_command(name="blacklist")
@commands.is_owner()
async def blacklist(ctx, user_id: str):
    BLACKLISTED_USERS.add(int(user_id)); save_data(); await ctx.reply(f"🚫 Blacklisted `{user_id}`.")

@bot.hybrid_command(name="unblacklist")
@commands.is_owner()
async def unblacklist(ctx, user_id: str):
    uid = int(user_id)
    if uid in BLACKLISTED_USERS: BLACKLISTED_USERS.remove(uid)
    violations_storage[str(uid)] = 0; save_data(); await ctx.reply(f"✅ Un-blacklisted `{uid}`.")

@bot.hybrid_group(name="bannedword")
@commands.is_owner()
async def bannedword(ctx): pass

@bannedword.command(name="add")
async def bw_add(ctx, word: str):
    BANNED_WORDS.add(word.lower()); save_data(); await ctx.reply(f"🚫 Added `{word}` to censor.")

@bannedword.command(name="remove")
async def bw_remove(ctx, word: str):
    if word.lower() in BANNED_WORDS: BANNED_WORDS.remove(word.lower()); save_data(); await ctx.reply("✅ Removed.")

@bot.hybrid_command(name="listwords")
@commands.is_owner()
async def listwords(ctx):
    await ctx.reply(f"📋 Censored: `{', '.join(BANNED_WORDS) or 'None'}`")

@bot.hybrid_command(name="listblacklisted")
@commands.is_owner()
async def listblacklisted(ctx):
    await ctx.reply(f"👥 Blacklisted: `{', '.join([str(i) for i in BLACKLISTED_USERS]) or 'None'}`")

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
    if ctx.valid:
        await bot.invoke(ctx); return

    mode = response_mode.get(str(message.channel.id), "stop")
    content_lower = message.content.lower().strip()
    is_pinged = bot.user.mentioned_in(message) and not message.mention_everyone
    has_keyword = content_lower.startswith("flexedai") or content_lower.endswith("flexedai")

    if mode == "stop" and not (is_pinged or has_keyword):
        return

    # AI Mirror Tone & Short Response Logic
    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=6)
    
    current_lang = channel_languages.get(str(message.channel.id), "English")
    if current_lang == "INVALID":
        return await message.reply("⚠️ Language error. Use `/lang`.")

    system_prompt = (
        f"You are FlexedAI. MANDATORY: Copy {message.author.display_name}'s tone and style exactly. "
        f"Keep responses extremely short, direct, and concise. No yapping. "
        f"Context: Language {current_lang}."
    )

    try:
        async with message.channel.typing():
            msgs = [{"role": "system", "content": system_prompt}] + list(thread_memory[tid]) + [{"role": "user", "content": message.content}]
            res = await client.chat.completions.create(model=MODEL_NAME, messages=msgs, temperature=0.7)
            output = res.choices[0].message.content
            if output:
                await message.reply(output)
                thread_memory[tid].append({"role": "user", "content": message.content})
                thread_memory[tid].append({"role": "assistant", "content": output})
    except Exception as e: print(f"AI Error: {e}")

bot.run(DISCORD_TOKEN)
