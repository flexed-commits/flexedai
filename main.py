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
# Note: Ensure this model name is correct in your Groq console
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
                "violations": data.get("violations", {}),
                "prefixes": data.get("prefixes", {})
            }
    except (FileNotFoundError, json.JSONDecodeError):
        return {"blacklist": set(), "banned_words": set(), "languages": {}, "logs": [], "violations": {}, "prefixes": {}}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump({
            "blacklist": list(BLACKLISTED_USERS),
            "banned_words": list(BANNED_WORDS),
            "languages": channel_languages,
            "logs": log_history,
            "violations": violations_storage,
            "prefixes": prefixes
        }, f, indent=4)

# Data Initialization
data = load_data()
BLACKLISTED_USERS = data["blacklist"]
BANNED_WORDS = data["banned_words"]
channel_languages = data["languages"]
log_history = data["logs"]
violations_storage = data["violations"]
prefixes = data["prefixes"]

client = AsyncGroq(api_key=GROQ_API_KEY)

# --- BOT CLASS ---

def get_prefix(bot, message):
    if not message.guild:
        return "/"
    return prefixes.get(str(message.guild.id), "/")

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix=get_prefix, intents=intents, help_command=None)
        self.start_time = time.time()

    async def setup_hook(self):
        self.daily_backup.start()
        print(f"✅ {self.user} Online | Hybrid System Active")

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
        await ctx.reply(f"❌ Missing Permissions: `{', '.join(error.missing_permissions)}`", ephemeral=True)

# --- 🖥️ SYSTEM COMMANDS ---

@bot.hybrid_command(name="sync", description="Force synchronizes slash commands to the current server and globally.")
@commands.is_owner()
async def sync_cmd(ctx):
    async with ctx.typing():
        if ctx.guild:
            bot.tree.copy_global_to(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)
        await bot.tree.sync()
        await ctx.reply("🚀 **Commands Synchronized.**")

@bot.hybrid_command(name="prefix", description="Sets a custom command prefix for this server.")
@commands.has_permissions(administrator=True)
async def set_prefix(ctx, new_prefix: str):
    prefixes[str(ctx.guild.id)] = new_prefix
    save_data()
    await ctx.reply(f"🎯 Prefix updated to: `{new_prefix}`")

@bot.hybrid_command(name="backup", description="Triggers an immediate data backup and sends it to the owner.")
@commands.is_owner()
async def backup_cmd(ctx):
    save_data()
    with open(DATA_FILE, "rb") as f:
        await ctx.author.send("💾 **Manual Backup**", file=discord.File(f, DATA_FILE))
    await ctx.reply("📥 Data packaged and sent to your DMs.")

@bot.hybrid_command(name="refresh", description="Wipes AI short-term memory and re-initializes the Groq client.")
@commands.is_owner()
async def refresh(ctx):
    global client
    thread_memory.clear()
    client = AsyncGroq(api_key=GROQ_API_KEY)
    await ctx.reply("🔄 **AI RAM purged and client re-initialized.**")

# --- 📡 UTILITIES ---

@bot.hybrid_command(name="help", description="Displays the full list of available commands and categories.")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 Command Center", color=discord.Color.blue(), description="Use commands with `/` or the server prefix.")
    embed.add_field(name="📡 Utilities", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami`, `/prefix` ", inline=False)
    embed.add_field(name="⚙️ Settings", value="`/lang` ", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="👑 Security", value="`/blacklist`, `/unblacklist`, `/bannedword add`, `/bannedword remove`, `/listwords`, `/listblacklisted` ", inline=False)
        embed.add_field(name="🛡️ Censor", value="`/logs`, `/clearlogs`, `/clearstrikes`, `/addstrike` ", inline=False)
        embed.add_field(name="🖥️ System", value="`/sync`, `/backup`, `/refresh` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="uptime", description="Shows how long the bot has been running since the last restart.")
async def uptime(ctx):
    s = int(time.time() - bot.start_time)
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    await ctx.reply(f"🚀 **Uptime**: `{int(d)}d {int(h)}h {int(m)}m {int(s)}s`")

@bot.hybrid_command(name="ping", description="Measures the connection latency between Discord and the bot.")
async def ping(ctx): 
    await ctx.reply(f"🏓 **Pong!** `{round(bot.latency * 1000)}ms`")

@bot.hybrid_command(name="whoami", description="Displays detailed information about your Discord profile.")
async def whoami(ctx):
    roles = [role.name for role in ctx.author.roles if role.name != "@everyone"]
    embed = discord.Embed(title=f"👤 {ctx.author}'s Profile", color=discord.Color.green())
    embed.add_field(name="Display Name", value=ctx.author.display_name, inline=True)
    embed.add_field(name="User ID", value=ctx.author.id, inline=True)
    embed.add_field(name="Roles", value=", ".join(roles) if roles else "None", inline=False)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="forget", description="Clears the AI's conversation history for this specific channel.")
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in thread_memory: thread_memory[tid].clear()
    await ctx.reply("🧠 **Memory wiped.** I no longer remember our previous messages here.")

# --- ⚙️ SETTINGS ---

@bot.hybrid_command(name="lang", description="Sets the primary language for AI responses in this channel.")
async def lang(ctx, language: str):
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID): 
        return await ctx.reply("❌ Admin permissions required.")
    channel_languages[str(ctx.channel.id)] = language
    save_data()
    await ctx.reply(f"🌐 AI response language for this channel set to `{language}`.")

# --- 👑 OWNER SECURITY ---

@bot.hybrid_command(name="blacklist", description="Prevents a user from using the bot or AI features.")
@commands.is_owner()
async def blacklist(ctx, user_id: str):
    BLACKLISTED_USERS.add(int(user_id)); save_data()
    await ctx.reply(f"🚫 User `{user_id}` has been blacklisted.")

@bot.hybrid_command(name="unblacklist", description="Removes a user from the blacklist and resets their strikes.")
@commands.is_owner()
async def unblacklist(ctx, user_id: str):
    uid = int(user_id)
    if uid in BLACKLISTED_USERS: BLACKLISTED_USERS.remove(uid)
    violations_storage[str(uid)] = 0; save_data()
    await ctx.reply(f"✅ User `{uid}` is now un-blacklisted.")

@bot.hybrid_group(name="bannedword", description="Manage words that the bot should filter.")
@commands.is_owner()
async def bannedword(ctx): pass

@bannedword.command(name="add", description="Add a new word to the global censor list.")
async def bw_add(ctx, word: str):
    BANNED_WORDS.add(word.lower()); save_data()
    await ctx.reply(f"🚫 Added `{word}` to banned words.")

@bannedword.command(name="remove", description="Remove a word from the global censor list.")
async def bw_remove(ctx, word: str):
    w = word.lower()
    if w in BANNED_WORDS: 
        BANNED_WORDS.remove(w); save_data()
        await ctx.reply(f"✅ Removed `{w}` from banned words.")
    else: await ctx.reply("❌ Word not found in list.")

@bot.hybrid_command(name="listwords", description="Shows all words currently being censored.")
@commands.is_owner()
async def listwords(ctx):
    await ctx.reply(f"📋 **Censored Words**: `{', '.join(BANNED_WORDS) if BANNED_WORDS else 'None'}`")

@bot.hybrid_command(name="listblacklisted", description="Shows all user IDs currently blacklisted.")
@commands.is_owner()
async def listblacklisted(ctx):
    await ctx.reply(f"👥 **Blacklisted IDs**: `{', '.join([str(i) for i in BLACKLISTED_USERS]) if BLACKLISTED_USERS else 'None'}`")

# --- 🛡️ CENSOR MGMT ---

@bot.hybrid_command(name="logs", description="Displays the last 5 filter violation logs.")
@commands.is_owner()
async def logs(ctx):
    if not log_history: return await ctx.reply("📋 Violation logs are currently empty.")
    text = "".join([f"📅 `{e['time']}` | 👤 `{e['user']}` | 🚫 **{e['trigger']}**\n" for e in log_history[:5]])
    await ctx.reply(embed=discord.Embed(title="📜 Security Logs", description=text, color=discord.Color.orange()))

@bot.hybrid_command(name="clearlogs", description="Permanently deletes all stored security logs.")
@commands.is_owner()
async def clearlogs(ctx):
    log_history.clear(); save_data(); await ctx.reply("🗑️ Logs purged.")

@bot.hybrid_command(name="clearstrikes", description="Resets the violation count for a specific user.")
@commands.is_owner()
async def clearstrikes(ctx, user_id: str):
    violations_storage[str(user_id)] = 0; save_data(); await ctx.reply(f"✅ strikes reset for `{user_id}`.")

@bot.hybrid_command(name="addstrike", description="Manually issues strikes to a user. 3 strikes result in a blacklist.")
@commands.is_owner()
async def addstrike(ctx, user_id: str, amount: int):
    u = str(user_id)
    violations_storage[u] = violations_storage.get(u, 0) + amount
    if violations_storage[u] >= 3: BLACKLISTED_USERS.add(int(user_id))
    save_data(); await ctx.reply(f"⚡ `{user_id}` now has {violations_storage[u]}/3 strikes.")

# --- AI HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    
    # Process commands (Prefix or Slash)
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # --- AI Context Injection ---
    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=10)
    
    # Gather user/server info for the AI
    user_roles = [r.name for r in message.author.roles if r.name != "@everyone"]
    lang_pref = channel_languages.get(str(message.channel.id), "Default")
    
    system_prompt = (
        f"You are a helpful assistant. Mirror the user's tone.\n"
        f"USER INFO: Name: {message.author.display_name}, Username: {message.author.name}, ID: {message.author.id}, "
        f"Roles: {', '.join(user_roles)}, Avatar URL: {message.author.display_avatar.url}.\n"
        f"CONTEXT: Server: {message.guild.name if message.guild else 'DMs'}, Channel: {message.channel.name if message.guild else 'DMs'}.\n"
        f"LANGUAGE PREFERENCE: {lang_pref}."
    )

    try:
        async with message.channel.typing():
            msgs = [{"role": "system", "content": system_prompt}] + list(thread_memory[tid]) + [{"role": "user", "content": message.content}]
            res = await client.chat.completions.create(
                model=MODEL_NAME, 
                messages=msgs,
                temperature=0.7
            )
            output = res.choices[0].message.content
            if output:
                await message.reply(output)
                thread_memory[tid].append({"role": "user", "content": message.content})
                thread_memory[tid].append({"role": "assistant", "content": output})
    except Exception as e: 
        print(f"AI Error: {e}")

bot.run(DISCORD_TOKEN)
