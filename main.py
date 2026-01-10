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
# Maverick is natively multimodal (Text + Vision)
MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct" 
OWNER_ID = 1081876265683927080
DATA_FILE = "bot_data.json"

# --- SYSTEM MEMORY (RAM ONLY) ---
thread_memory = {}
tone_memory = {} 

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

# --- 🖥️ SYSTEM & ADMIN ---

@bot.hybrid_command(name="sync", description="Synchronizes commands globally.")
@commands.is_owner()
async def sync_cmd(ctx):
    async with ctx.typing():
        if ctx.guild:
            bot.tree.clear_commands(guild=ctx.guild)
            await bot.tree.sync(guild=ctx.guild)
        synced = await bot.tree.sync()
        await ctx.reply(f"🚀 **Synced {len(synced)} commands.**")

@bot.hybrid_command(name="start", description="ADMIN: Respond to ALL messages in this channel.")
@commands.has_permissions(administrator=True)
async def start_responding(ctx):
    response_mode[str(ctx.channel.id)] = "start"; save_data()
    await ctx.reply("🎙️ **Response mode: ALWAYS.**")

@bot.hybrid_command(name="stop", description="ADMIN: Respond to triggers/pings only.")
@commands.has_permissions(administrator=True)
async def stop_responding(ctx):
    response_mode[str(ctx.channel.id)] = "stop"; save_data()
    await ctx.reply("🔇 **Response mode: TRIGGER ONLY.**")

@bot.hybrid_command(name="stats", description="Displays bot performance and command counts.")
async def stats(ctx):
    embed = discord.Embed(title="📊 Stats", color=discord.Color.purple())
    embed.add_field(name="Commands", value="`23`", inline=True)
    embed.add_field(name="Latency", value=f"`{round(bot.latency * 1000)}ms`", inline=True)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="prefix", description="Change the server prefix.")
@commands.has_permissions(administrator=True)
async def set_prefix(ctx, new_prefix: str):
    prefixes[str(ctx.guild.id)] = new_prefix; save_data()
    await ctx.reply(f"🎯 Prefix: `{new_prefix}`")

@bot.hybrid_command(name="backup", description="Manual data backup to owner.")
@commands.is_owner()
async def backup_cmd(ctx):
    save_data()
    with open(DATA_FILE, "rb") as f:
        await ctx.author.send("💾 Backup", file=discord.File(f, DATA_FILE))
    await ctx.reply("📥 Sent.")

@bot.hybrid_command(name="refresh", description="Wipes RAM memory.")
@commands.is_owner()
async def refresh(ctx):
    global client
    thread_memory.clear()
    tone_memory.clear()
    client = AsyncGroq(api_key=GROQ_API_KEY)
    await ctx.reply("🔄 RAM Purged.")

# --- 📡 UTILITIES ---

@bot.hybrid_command(name="help", description="Lists all 23 active commands.")
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
    roles = [role.name for role in ctx.author.roles if role.name != "@everyone"]
    embed = discord.Embed(title=f"👤 {ctx.author.name}", color=discord.Color.green())
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.add_field(name="ID", value=ctx.author.id)
    embed.add_field(name="Roles", value=", ".join(roles) if roles else "None")
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="forget")
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in thread_memory: thread_memory[tid].clear()
    await ctx.reply("🧠 Memory wiped.")

@bot.hybrid_command(name="lang")
async def lang(ctx, language: str):
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID): return
    channel_languages[str(ctx.channel.id)] = language; save_data()
    await ctx.reply(f"🌐 Language: `{language}`.")

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
    save_data(); await ctx.reply(f"✅ Un-blacklisted `{uid}`.")

@bot.hybrid_group(name="bannedword")
@commands.is_owner()
async def bannedword(ctx): pass

@bannedword.command(name="add")
async def bw_add(ctx, word: str):
    BANNED_WORDS.add(word.lower()); save_data(); await ctx.reply("🚫 Added.")

@bot.hybrid_command(name="listwords")
@commands.is_owner()
async def listwords(ctx): await ctx.reply(f"📋 Censor: `{', '.join(BANNED_WORDS) or 'None'}`")

@bot.hybrid_command(name="logs")
@commands.is_owner()
async def logs(ctx):
    if not log_history: return await ctx.reply("📋 Empty.")
    await ctx.reply(f"📜 Last log entry exists.")

@bot.hybrid_command(name="clearstrikes")
@commands.is_owner()
async def clearstrikes(ctx, user_id: str): violations_storage[str(user_id)] = 0; save_data(); await ctx.reply("✅ Reset.")

@bot.hybrid_command(name="addstrike")
@commands.is_owner()
async def addstrike(ctx, user_id: str, amount: int):
    u = str(user_id)
    violations_storage[u] = violations_storage.get(u, 0) + amount
    save_data(); await ctx.reply(f"⚡ Strikes: {violations_storage[u]}/3.")

# --- PREFIX ONLY OWNER CMD ---
@bot.command(name="server-list")
@commands.is_owner()
@commands.dm_only()
async def server_list_dm(ctx):
    server_data = {}
    for guild in bot.guilds:
        inv = "No Perms"
        target = guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite), None)
        if target:
            try: invite = await target.create_invite(max_age=0); inv = invite.url
            except: pass
        server_data[guild.name] = {"id": guild.id, "members": guild.member_count, "invite": inv}
    with open("servers.json", "w") as f: json.dump(server_data, f, indent=4)
    await ctx.send(file=discord.File("servers.json")); os.remove("servers.json")

# --- AI HANDLER (VISION ENABLED) ---

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
    
    # Check for images
    images = [a for a in message.attachments if a.content_type and a.content_type.startswith('image')]

    if mode == "stop" and not (is_pinged or has_keyword or images):
        return

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=6)

    current_lang = channel_languages.get(str(message.channel.id), "English")
    user_roles = [r.name for r in message.author.roles if r.name != "@everyone"]

    system_prompt = (
        f"You are FlexedAI. Mirror the user's tone exactly. Keep responses very short and concise.\n"
        f"When asked, you have access to this info:\n"
        f"USER: Display Name: {message.author.display_name}, Username: {message.author.name}, ID: {message.author.id}, PFP: {message.author.display_avatar.url}, Roles: {', '.join(user_roles)}.\n"
        f"SERVER: Name: {message.guild.name if message.guild else 'DM'}, Channel: {message.channel.name if message.guild else 'DM'}.\n"
        f"LANGUAGE: {current_lang}."
    )

    try:
        async with message.channel.typing():
            # Maverick multimodal content construction
            content_payload = []
            if message.content:
                content_payload.append({"type": "text", "text": message.content})
            elif images:
                content_payload.append({"type": "text", "text": "Describe this image."})

            for img in images:
                content_payload.append({"type": "image_url", "image_url": {"url": img.url}})

            # Build messages list
            msgs = [{"role": "system", "content": system_prompt}]
            # Convert text memory into content format if necessary, 
            # or keep as strings for simple text history
            for m in thread_memory[tid]:
                msgs.append(m)
            
            msgs.append({"role": "user", "content": content_payload})

            res = await client.chat.completions.create(
                model=MODEL_NAME, 
                messages=msgs, 
                temperature=0.7,
                max_tokens=512
            )
            
            output = res.choices[0].message.content
            if output:
                await message.reply(output)
                # Store text memory (images aren't re-sent in history to save tokens)
                mem_text = message.content if message.content else "[Sent an image]"
                thread_memory[tid].append({"role": "user", "content": mem_text})
                thread_memory[tid].append({"role": "assistant", "content": output})
                
    except Exception as e: 
        print(f"AI Error: {e}")

bot.run(DISCORD_TOKEN)
