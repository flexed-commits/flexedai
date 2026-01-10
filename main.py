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

VALID_LANGUAGES = ["english", "hindi", "hinglish", "spanish", "french", "german", "italian", "portuguese", "chinese", "japanese", "korean"]

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
        return {"blacklist": set(), "banned_words": set(), "languages": {}, "violations": {}, "prefixes": {}, "response_mode": {}, "admin_logs": []}

def load_interaction_logs():
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                return json.load(f)
        return []
    except (json.JSONDecodeError):
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
    cutoff = time.time() - 86400 
    cleaned_logs = [log for log in logs if log['timestamp'] > cutoff]
    with open(LOG_FILE, "w") as f:
        json.dump(cleaned_logs, f, indent=4)
    return cleaned_logs

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
        print(f"✅ {self.user} Online | All Commands Fixed & Active")

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            global interaction_logs
            interaction_logs = save_interaction_logs(interaction_logs)
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
    await ctx.send(embed=quick_embed("🧹 Purge", "Logs wiped.", discord.Color.red()))

@bot.command(name="server-list")
@commands.is_owner()
@commands.dm_only()
async def server_list_dm(ctx):
    data = {g.name: {"id": g.id, "members": g.member_count} for g in bot.guilds}
    with open("servers.json", "w") as f: json.dump(data, f, indent=4)
    await ctx.send(file=discord.File("servers.json")); os.remove("servers.json")

# --- HYBRID COMMANDS ---

@bot.hybrid_command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 Master Center", color=discord.Color.blue())
    embed.add_field(name="📡 Utilities", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami`, `/prefix`, `/stats`, `/searchlogs` ", inline=False)
    embed.add_field(name="🎙️ Control", value="`/start`, `/stop`, `/lang` ", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="🛡️ Security", value="`/blacklist add/remove`, `/list blacklist`, `/bannedword add/remove`, `/listwords`, `/addstrike`, `/clearstrike`, `/strikelist`, `/logs`, `/clearadminlogs` ", inline=False)
        embed.add_field(name="🖥️ System", value="`/sync`, `/backup`, `/refresh` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_group(name="blacklist")
@commands.is_owner()
async def blacklist_group(ctx): pass

@blacklist_group.command(name="add")
async def bl_add(ctx, user_id: str):
    BLACKLISTED_USERS.add(int(user_id)); save_data()
    await ctx.reply(embed=quick_embed("🚫 Blacklist", f"User `{user_id}` added.", discord.Color.red()))

@blacklist_group.command(name="remove")
async def bl_remove(ctx, user_id: str):
    uid = int(user_id)
    if uid in BLACKLISTED_USERS: BLACKLISTED_USERS.remove(uid)
    save_data()
    await ctx.reply(embed=quick_embed("✅ Un-blacklisted", f"User `{uid}` removed.", discord.Color.green()))

@bot.hybrid_command(name="list")
@commands.is_owner()
async def list_blacklist(ctx, target: str):
    if target.lower() == "blacklist":
        bl = ", ".join([str(u) for u in BLACKLISTED_USERS]) or "None"
        await ctx.reply(embed=quick_embed("📋 Blacklist", f"`{bl}`"))

@bot.hybrid_command(name="addstrike")
@commands.is_owner()
async def add_strike(ctx, user_id: str, amount: int):
    u_str = str(user_id)
    violations_storage[u_str] = violations_storage.get(u_str, 0) + amount
    admin_logs.append(f"[{datetime.datetime.now()}] Strike added to {user_id}. Total: {violations_storage[u_str]}/3.")
    if violations_storage[u_str] >= 3:
        BLACKLISTED_USERS.add(int(user_id))
        admin_logs.append(f"[{datetime.datetime.now()}] User {user_id} BANNED.")
        save_data(); return await ctx.reply(embed=quick_embed("⚡ BAN", f"User `{user_id}` reached 3/3 strikes and is BANNED.", discord.Color.red()))
    save_data(); await ctx.reply(f"⚡ Strike recorded. `{user_id}`: {violations_storage[u_str]}/3.")

@bot.hybrid_command(name="clearstrike")
@commands.is_owner()
async def clear_strike(ctx, user_id: str):
    violations_storage[str(user_id)] = 0; save_data()
    await ctx.reply(embed=quick_embed("✅ Reset", f"Strikes for `{user_id}` wiped."))

@bot.hybrid_group(name="bannedword")
@commands.is_owner()
async def bw_group(ctx): pass

@bw_group.command(name="add")
async def bw_add(ctx, word: str):
    BANNED_WORDS.add(word.lower()); save_data(); await ctx.reply(f"🚫 Added `{word}`.")

@bw_group.command(name="remove")
async def bw_remove(ctx, word: str):
    if word.lower() in BANNED_WORDS: BANNED_WORDS.remove(word.lower())
    save_data(); await ctx.reply(f"✅ Removed `{word}`.")

@bot.hybrid_command(name="searchlogs")
@commands.is_owner()
async def search_logs(ctx, keyword: str):
    res = [l for l in interaction_logs if keyword.lower() in l['prompt'].lower() or keyword.lower() in l['response'].lower()]
    text = "\n\n".join([f"**{l['user_name']}**: {l['prompt'][:50]}..." for l in res[:5]]) or "No results."
    await ctx.reply(embed=quick_embed("🔍 Search", text))

# --- AI HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    ctx = await bot.get_context(message)
    if ctx.valid: await bot.invoke(ctx); return

    mode = response_mode.get(str(message.channel.id), "stop")
    is_pinged = bot.user.mentioned_in(message) and not message.mention_everyone
    images = [a for a in message.attachments if a.content_type and a.content_type.startswith('image')]
    if mode == "stop" and not (is_pinged or images): return

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=6)

    current_lang = channel_languages.get(str(message.channel.id), "English")
    user_roles = [r.name for r in message.author.roles if r.name != "@everyone"]

    system_prompt = (
        f"You are FlexedAI. Mirror the user's tone/energy EXACTLY. Respond ONLY in {current_lang}. Concise.\n"
        f"CONTEXT: Server: {message.guild.name if message.guild else 'DMs'}, Channel: {message.channel.name if message.guild else 'DMs'}.\n"
        f"USER: {message.author.display_name} (@{message.author.name}), ID: {message.author.id}, PFP: {message.author.display_avatar.url}, Roles: {', '.join(user_roles)}."
    )

    try:
        async with message.channel.typing():
            user_text = message.content or "Analyze image."
            payload = [{"type": "text", "text": user_text}]
            for img in images: payload.append({"type": "image_url", "image_url": {"url": img.url}})
            msgs = [{"role": "system", "content": system_prompt}]
            for m in thread_memory[tid]: msgs.append(m)
            msgs.append({"role": "user", "content": payload})
            res = await client.chat.completions.create(model=MODEL_NAME, messages=msgs, temperature=0.8)
            output = res.choices[0].message.content
            if output:
                await message.reply(output)
                thread_memory[tid].append({"role": "user", "content": user_text})
                thread_memory[tid].append({"role": "assistant", "content": output})
                global interaction_logs
                interaction_logs.append({
                    "timestamp": time.time(), "guild_id": message.guild.id if message.guild else None,
                    "channel_id": message.channel.id, "user_name": message.author.name,
                    "user_id": message.author.id, "prompt": user_text, "response": output
                })
                interaction_logs = save_interaction_logs(interaction_logs)
    except Exception as e: print(f"AI Error: {e}")

# (Include remaining standard commands from previousTurn: lang, sync, backup, stats, uptime, whoami, forget, refresh)

bot.run(DISCORD_TOKEN)
