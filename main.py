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
LOG_FILE = "interaction_logs.json"

VALID_LANGUAGES = [
    "english", "hindi", "hinglish", "spanish", "french", 
    "german", "italian", "portuguese", "chinese", "japanese", "korean"
]

# --- DATA PERSISTENCE ---

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            return {
                "blacklist": set(data.get("blacklist", [])),
                "banned_words": set(data.get("banned_words", [])),
                "languages": data.get("languages", {}),
                "violations": data.get("violations", {}),
                "prefixes": data.get("prefixes", {}),
                "response_mode": data.get("response_mode", {}),
                "admin_logs": data.get("admin_logs", [])
            }
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "blacklist": set(), 
            "banned_words": set(), 
            "languages": {}, 
            "violations": {}, 
            "prefixes": {}, 
            "response_mode": {},
            "admin_logs": []
        }

def load_interaction_logs():
    try:
        with open(LOG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump({
            "blacklist": list(BLACKLISTED_USERS),
            "banned_words": list(BANNED_WORDS),
            "languages": channel_languages,
            "violations": violations_storage,
            "prefixes": prefixes,
            "response_mode": response_mode,
            "admin_logs": admin_logs
        }, f, indent=4)

def save_interaction_logs(logs):
    cutoff = time.time() - 172800
    cleaned_logs = [log for log in logs if log['timestamp'] > cutoff]
    with open(LOG_FILE, "w") as f:
        json.dump(cleaned_logs, f, indent=4)
    return cleaned_logs

# Global Data Init
data = load_data()
BLACKLISTED_USERS = data["blacklist"]
BANNED_WORDS = data["banned_words"]
channel_languages = data["languages"]
violations_storage = data["violations"]
prefixes = data["prefixes"]
response_mode = data["response_mode"]
admin_logs = data["admin_logs"]
interaction_logs = load_interaction_logs()

client = AsyncGroq(api_key=GROQ_API_KEY)
thread_memory = {}

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
        print(f"✅ {self.user} Online | All 23+ Features Active")

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            save_interaction_logs(interaction_logs)
            await owner.send("📦 **Daily Backup**", files=[discord.File(DATA_FILE), discord.File(LOG_FILE)])
        except: pass

bot = MyBot()

def quick_embed(title, description, color=discord.Color.blue()):
    return discord.Embed(title=title, description=description, color=color)

# --- OWNER ONLY PREFIX COMMANDS (DM ONLY) ---

@bot.command(name="messages")
@commands.is_owner()
@commands.dm_only()
async def messages_log(ctx):
    now = time.time()
    day_ago = now - 86400
    recent_logs = [log for log in interaction_logs if log['timestamp'] > day_ago]
    
    output_data = {"servers": {}, "dm": {}}
    for entry in recent_logs:
        user_key = f"{entry['user_name']}/{entry['user_id']}"
        if entry.get('guild_id'):
            s_id, c_id = str(entry['guild_id']), str(entry['channel_id'])
            if s_id not in output_data["servers"]: output_data["servers"][s_id] = {}
            if c_id not in output_data["servers"][s_id]: output_data["servers"][s_id][c_id] = {}
            if user_key not in output_data["servers"][s_id][c_id]:
                output_data["servers"][s_id][c_id][user_key] = {"prompt": [], "response": []}
            output_data["servers"][s_id][c_id][user_key]["prompt"].append(entry["prompt"])
            output_data["servers"][s_id][c_id][user_key]["response"].append(entry["response"])
        else:
            if user_key not in output_data["dm"]: output_data["dm"][user_key] = {"prompt": [], "response": []}
            output_data["dm"][user_key]["prompt"].append(entry["prompt"])
            output_data["dm"][user_key]["response"].append(entry["response"])

    fname = f"logs_{int(now)}.json"
    with open(fname, "w") as f: json.dump(output_data, f, indent=2)
    await ctx.send(embed=quick_embed("📂 Log Export", "Interaction history for the past 24 hours."), file=discord.File(fname))
    os.remove(fname)

@bot.command(name="clearlogs")
@commands.is_owner()
@commands.dm_only()
async def clear_logs_cmd(ctx):
    global interaction_logs
    interaction_logs = []
    if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
    await ctx.send(embed=quick_embed("🧹 Purge", "Logs cleared.", discord.Color.red()))

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

# --- HYBRID COMMANDS ---

@bot.hybrid_command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 FlexedAI Master Center", color=discord.Color.blue())
    embed.add_field(name="📡 Utilities", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami`, `/prefix`, `/stats` ", inline=False)
    embed.add_field(name="🎙️ Response Control", value="`/start`, `/stop`, `/lang` ", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="👑 Owner (Prefix Only)", value="`!messages`, `!clearlogs`, `!server-list` ", inline=False)
        embed.add_field(name="🛡️ Security", value="`/blacklist`, `/unblacklist`, `/listblacklisted`, `/bannedword add/remove`, `/listwords`, `/addstrike`, `/strikelist`, `/clearstrikes`, `/logs`, `/clearadminlogs` ", inline=False)
        embed.add_field(name="🖥️ System", value="`/sync`, `/backup`, `/refresh` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="lang")
@commands.has_permissions(administrator=True)
async def set_lang(ctx, language: str):
    l_in = language.lower().strip()
    if l_in not in VALID_LANGUAGES:
        cmd = bot.tree.get_command("lang")
        return await ctx.reply(embed=quick_embed("⚠️ Invalid", f"Use </lang:{cmd.id if cmd else 0}> with: {', '.join(VALID_LANGUAGES).title()}."))
    channel_languages[str(ctx.channel.id)] = language.capitalize(); save_data()
    await ctx.reply(embed=quick_embed("🌐 Language Locked", f"Channel language: **{language.capitalize()}**.", discord.Color.green()))

@bot.hybrid_command(name="start")
@commands.has_permissions(administrator=True)
async def start_resp(ctx):
    response_mode[str(ctx.channel.id)] = "start"; save_data()
    await ctx.reply(embed=quick_embed("🎙️ Mode: Always", "Active for all messages.", discord.Color.green()))

@bot.hybrid_command(name="stop")
@commands.has_permissions(administrator=True)
async def stop_resp(ctx):
    response_mode[str(ctx.channel.id)] = "stop"; save_data()
    await ctx.reply(embed=quick_embed("🔇 Mode: Trigger", "Active for pings/images only.", discord.Color.orange()))

@bot.hybrid_command(name="stats")
async def bot_stats(ctx):
    embed = discord.Embed(title="📊 Stats", color=discord.Color.purple())
    embed.add_field(name="Latency", value=f"`{round(bot.latency * 1000)}ms`")
    embed.add_field(name="Guilds", value=f"`{len(bot.guilds)}`")
    await ctx.reply(embed=embed)

# --- SECURITY & STRIKES ---

@bot.hybrid_command(name="blacklist")
@commands.is_owner()
async def blacklist_user(ctx, user_id: str):
    BLACKLISTED_USERS.add(int(user_id)); save_data()
    await ctx.reply(embed=quick_embed("🚫 Blacklist", f"User `{user_id}` restricted.", discord.Color.red()))

@bot.hybrid_command(name="unblacklist")
@commands.is_owner()
async def unblacklist_user(ctx, user_id: str):
    uid = int(user_id)
    if uid in BLACKLISTED_USERS: BLACKLISTED_USERS.remove(uid)
    save_data()
    await ctx.reply(embed=quick_embed("✅ Restored", f"User `{uid}` access granted.", discord.Color.green()))

@bot.hybrid_command(name="listblacklisted")
@commands.is_owner()
async def list_blacklisted(ctx):
    bl_list = ", ".join([str(u) for u in BLACKLISTED_USERS]) if BLACKLISTED_USERS else "None"
    await ctx.reply(embed=quick_embed("📋 Blacklisted IDs", f"`{bl_list}`"))

@bot.hybrid_group(name="bannedword")
@commands.is_owner()
async def bannedword_group(ctx): pass

@bannedword_group.command(name="add")
async def bw_add(ctx, word: str):
    BANNED_WORDS.add(word.lower()); save_data()
    await ctx.reply(f"🚫 Added `{word}`.")

@bannedword_group.command(name="remove")
async def bw_remove(ctx, word: str):
    word = word.lower()
    if word in BANNED_WORDS: BANNED_WORDS.remove(word)
    save_data()
    await ctx.reply(f"✅ Removed `{word}`.")

@bot.hybrid_command(name="listwords")
@commands.is_owner()
async def list_words(ctx):
    words = ", ".join(BANNED_WORDS) if BANNED_WORDS else "None"
    await ctx.reply(embed=quick_embed("📋 Banned Words", f"`{words}`"))

@bot.hybrid_command(name="addstrike")
@commands.is_owner()
async def add_strike(ctx, user_id: str, amount: int):
    u_id = int(user_id)
    u_str = str(u_id)
    violations_storage[u_str] = violations_storage.get(u_str, 0) + amount
    
    log_entry = f"[{datetime.datetime.now()}] Strike added to {u_id}. Total: {violations_storage[u_str]}/3."
    admin_logs.append(log_entry)

    if violations_storage[u_str] >= 3:
        BLACKLISTED_USERS.add(u_id)
        violations_storage[u_str] = 3
        admin_logs.append(f"[{datetime.datetime.now()}] User {u_id} auto-blacklisted (Strikes: 3/3).")
        save_data()
        return await ctx.reply(embed=quick_embed("⚡ Critical Violation", f"User `{u_id}` reached 3/3 strikes and has been **BANNED**.", discord.Color.red()))
    
    save_data()
    await ctx.reply(f"⚡ Strike recorded for `{u_id}`. Current: `{violations_storage[u_str]}/3`.")

@bot.hybrid_command(name="strikelist")
@commands.is_owner()
async def strike_list(ctx):
    content = "\n".join([f"<@{u}>: {s}/3" for u, s in violations_storage.items() if s > 0]) or "No active strikes."
    await ctx.reply(embed=quick_embed("⚡ Strike Ledger", content))

@bot.hybrid_command(name="logs")
@commands.is_owner()
async def view_logs(ctx):
    history = "\n".join(admin_logs[-15:]) if admin_logs else "No logs available."
    await ctx.reply(embed=quick_embed("📜 Admin Logs (Last 15)", f"```\n{history}\n```"))

@bot.hybrid_command(name="clearadminlogs")
@commands.is_owner()
async def clear_admin_logs(ctx):
    admin_logs.clear(); save_data()
    await ctx.reply(embed=quick_embed("🧹 Purged", "Admin logs wiped."))

# --- UTILITIES ---

@bot.hybrid_command(name="sync")
@commands.is_owner()
async def sync_cmd(ctx):
    await bot.tree.sync(); await ctx.reply("🚀 Synced.")

@bot.hybrid_command(name="backup")
@commands.is_owner()
async def manual_backup(ctx):
    save_data(); await ctx.author.send(files=[discord.File(DATA_FILE), discord.File(LOG_FILE)])
    await ctx.reply("💾 Backup sent to DMs.")

@bot.hybrid_command(name="forget")
async def forget_ctx(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in thread_memory: thread_memory[tid].clear()
    await ctx.reply("🧠 Context cleared.")

@bot.hybrid_command(name="refresh")
@commands.is_owner()
async def refresh_ram(ctx):
    thread_memory.clear(); await ctx.reply("🔄 RAM cleared.")

# --- AI HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx); return

    mode = response_mode.get(str(message.channel.id), "stop")
    is_pinged = bot.user.mentioned_in(message) and not message.mention_everyone
    images = [a for a in message.attachments if a.content_type and a.content_type.startswith('image')]

    if mode == "stop" and not (is_pinged or images): return

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=6)

    current_lang = channel_languages.get(str(message.channel.id), "English")
    system_prompt = (
        f"You are FlexedAI. CRITICAL: Mirror the user's tone, humor, and energy EXACTLY. "
        f"Respond ONLY in {current_lang}. Short, concise replies. "
        f"If Hinglish, use Roman script for Hindi words."
    )

    try:
        async with message.channel.typing():
            user_text = message.content if message.content else "Analyze image."
            content_payload = [{"type": "text", "text": user_text}]
            for img in images: content_payload.append({"type": "image_url", "image_url": {"url": img.url}})

            msgs = [{"role": "system", "content": system_prompt}]
            for m in thread_memory[tid]: msgs.append(m)
            msgs.append({"role": "user", "content": content_payload})

            res = await client.chat.completions.create(model=MODEL_NAME, messages=msgs, temperature=0.8)
            output = res.choices[0].message.content
            
            if output:
                await message.reply(output)
                thread_memory[tid].append({"role": "user", "content": user_text})
                thread_memory[tid].append({"role": "assistant", "content": output})
                
                global interaction_logs
                interaction_logs.append({
                    "timestamp": time.time(),
                    "guild_id": message.guild.id if message.guild else None,
                    "channel_id": message.channel.id,
                    "user_name": message.author.name,
                    "user_id": message.author.id,
                    "prompt": user_text,
                    "response": output
                })
                interaction_logs = save_interaction_logs(interaction_logs)

    except Exception as e: print(f"AI Error: {e}")

bot.run(DISCORD_TOKEN)
