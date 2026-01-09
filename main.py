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
MODEL_NAME = "meta-llama/llama-3.1-70b-versatile" 
OWNER_ID = 1081876265683927080
DATA_FILE = "bot_data.json"

# --- SYSTEM MEMORY (RAM ONLY) ---
thread_memory = {}
tone_memory = {} # Stores user tone patterns per user ID

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
        print(f"✅ {self.user} Online | 23 Commands Active")

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            with open(DATA_FILE, "rb") as f:
                await owner.send("📦 **Daily Backup**", file=discord.File(f, DATA_FILE))
        except: pass

bot = MyBot()

# --- 🖥️ SYSTEM & ADMIN (All 23 Commands Maintained) ---

@bot.hybrid_command(name="sync", description="Synchronizes commands globally.")
@commands.is_owner()
async def sync_cmd(ctx):
    async with ctx.typing():
        if ctx.guild:
            bot.tree.clear_commands(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)
        synced = await bot.tree.sync()
        await ctx.reply(f"🚀 **Synced {len(synced)} commands.**")

@bot.hybrid_command(name="start", description="ADMIN: Respond to ALL messages.")
@commands.has_permissions(administrator=True)
async def start_responding(ctx):
    response_mode[str(ctx.channel.id)] = "start"; save_data()
    await ctx.reply("🎙️ **Always Responding.**")

@bot.hybrid_command(name="stop", description="ADMIN: Respond to triggers only.")
@commands.has_permissions(administrator=True)
async def stop_responding(ctx):
    response_mode[str(ctx.channel.id)] = "stop"; save_data()
    await ctx.reply("🔇 **Trigger Only.**")

@bot.hybrid_command(name="stats", description="Bot performance stats.")
async def stats(ctx):
    embed = discord.Embed(title="📊 Stats", color=discord.Color.purple())
    embed.add_field(name="Commands", value="`23`", inline=True)
    embed.add_field(name="Latency", value=f"`{round(bot.latency * 1000)}ms`", inline=True)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="prefix", description="Change prefix.")
@commands.has_permissions(administrator=True)
async def set_prefix(ctx, new_prefix: str):
    prefixes[str(ctx.guild.id)] = new_prefix; save_data()
    await ctx.reply(f"🎯 Prefix: `{new_prefix}`")

@bot.hybrid_command(name="backup", description="Manual data backup.")
@commands.is_owner()
async def backup_cmd(ctx):
    save_data()
    with open(DATA_FILE, "rb") as f:
        await ctx.author.send("💾 Backup", file=discord.File(f, DATA_FILE))
    await ctx.reply("📥 Sent.")

@bot.hybrid_command(name="refresh", description="Wipes RAM.")
@commands.is_owner()
async def refresh(ctx):
    global client
    thread_memory.clear()
    tone_memory.clear() # Clear tone memory on refresh
    client = AsyncGroq(api_key=GROQ_API_KEY)
    await ctx.reply("🔄 RAM Purged.")

# --- 📡 UTILITIES ---

@bot.hybrid_command(name="help", description="Lists commands.")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 Master Command Center", color=discord.Color.blue())
    embed.add_field(name="📡 Utilities", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami`, `/prefix`, `/start`, `/stop`, `/stats` ", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="👑 Security", value="`/blacklist`, `/unblacklist`, `/bannedword add`, `/bannedword remove`, `/listwords`, `/listblacklisted` ", inline=False)
        embed.add_field(name="🛡️ Moderation", value="`/logs`, `/clearlogs`, `/clearstrikes`, `/addstrike` ", inline=False)
        embed.add_field(name="🖥️ System", value="`/sync`, `/backup`, `/refresh` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="ping")
async def ping(ctx): await ctx.reply(f"🏓 **{round(bot.latency * 1000)}ms**")

@bot.hybrid_command(name="uptime")
async def uptime(ctx):
    s = int(time.time() - bot.start_time)
    await ctx.reply(f"🚀 **Uptime**: `{s//3600}h {(s%3600)//60}m {s%60}s` ")

@bot.hybrid_command(name="whoami")
async def whoami(ctx):
    embed = discord.Embed(title=f"👤 {ctx.author.name}", color=discord.Color.green())
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.add_field(name="ID", value=ctx.author.id)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="forget")
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in thread_memory: thread_memory[tid].clear()
    if ctx.author.id in tone_memory: del tone_memory[ctx.author.id]
    await ctx.reply("🧠 Memory wiped.")

@bot.hybrid_command(name="lang")
async def lang(ctx, language: str):
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID): return
    channel_languages[str(ctx.channel.id)] = language; save_data()
    await ctx.reply(f"🌐 Language: `{language}`.")

# --- 👑 SECURITY ---

@bot.hybrid_command(name="blacklist")
@commands.is_owner()
async def blacklist(ctx, user_id: str):
    BLACKLISTED_USERS.add(int(user_id)); save_data(); await ctx.reply(f"🚫 Banned `{user_id}`.")

@bot.hybrid_command(name="unblacklist")
@commands.is_owner()
async def unblacklist(ctx, user_id: str):
    uid = int(user_id)
    if uid in BLACKLISTED_USERS: BLACKLISTED_USERS.remove(uid)
    save_data(); await ctx.reply(f"✅ Unbanned `{uid}`.")

@bot.hybrid_group(name="bannedword")
@commands.is_owner()
async def bannedword(ctx): pass

@bannedword.command(name="add")
async def bw_add(ctx, word: str):
    BANNED_WORDS.add(word.lower()); save_data(); await ctx.reply("🚫 Added.")

@bannedword.command(name="remove")
async def bw_remove(ctx, word: str):
    if word.lower() in BANNED_WORDS: BANNED_WORDS.remove(word.lower()); save_data(); await ctx.reply("✅ Removed.")

@bot.hybrid_command(name="listwords")
@commands.is_owner()
async def listwords(ctx): await ctx.reply(f"📋 Censor: `{', '.join(BANNED_WORDS) or 'None'}`")

@bot.hybrid_command(name="listblacklisted")
@commands.is_owner()
async def listblacklisted(ctx): await ctx.reply(f"👥 Banned: `{', '.join([str(i) for i in BLACKLISTED_USERS]) or 'None'}`")

@bot.hybrid_command(name="logs")
@commands.is_owner()
async def logs(ctx):
    if not log_history: return await ctx.reply("📋 Empty.")
    await ctx.reply(f"📜 Last log: `{log_history[-1]['trigger']}`")

@bot.hybrid_command(name="clearlogs")
@commands.is_owner()
async def clearlogs(ctx): log_history.clear(); save_data(); await ctx.reply("🗑️ Cleared.")

@bot.hybrid_command(name="clearstrikes")
@commands.is_owner()
async def clearstrikes(ctx, user_id: str): violations_storage[str(user_id)] = 0; save_data(); await ctx.reply("✅ Reset.")

@bot.hybrid_command(name="addstrike")
@commands.is_owner()
async def addstrike(ctx, user_id: str, amount: int):
    u = str(user_id)
    violations_storage[u] = violations_storage.get(u, 0) + amount
    save_data(); await ctx.reply(f"⚡ Strike: {violations_storage[u]}/3.")

# --- AI HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    mode = response_mode.get(str(message.channel.id), "stop")
    content_lower = message.content.lower().strip()
    is_pinged = bot.user.mentioned_in(message) and not message.mention_everyone
    has_keyword = content_lower.startswith("flexedai") or content_lower.endswith("flexedai")

    if mode == "stop" and not (is_pinged or has_keyword):
        return

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=6) # Shorter history for faster mirroring
    
    # Store tone pattern in RAM (system memory) if not already detected
    user_id = message.author.id
    current_lang = channel_languages.get(str(message.channel.id), "English")

    system_prompt = (
        f"You are a helpful AI. MANDATORY: You MUST copy the user's tone, vocabulary, and style exactly. "
        f"Keep your responses extremely short and direct. Do not use filler words. "
        f"The user's name is {message.author.display_name}. Language: {current_lang}."
    )

    try:
        async with message.channel.typing():
            msgs = [{"role": "system", "content": system_prompt}] + list(thread_memory[tid]) + [{"role": "user", "content": message.content}]
            res = await client.chat.completions.create(model=MODEL_NAME, messages=msgs, temperature=0.8)
            output = res.choices[0].message.content
            if output:
                await message.reply(output)
                thread_memory[tid].append({"role": "user", "content": message.content})
                thread_memory[tid].append({"role": "assistant", "content": output})
    except Exception as e: print(f"AI Error: {e}")

bot.run(DISCORD_TOKEN)
