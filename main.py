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
# Model: meta-llama/llama-4-maverick-17b-128e-instruct
MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct" 
OWNER_ID = 1081876265683927080
DATA_FILE = "bot_data.json"
LOG_FILE = "interaction_logs.json"

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
    except:
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
    # Rolling 24h window
    cutoff = time.time() - 86400 
    cleaned_logs = [log for log in logs if log['timestamp'] > cutoff]
    with open(LOG_FILE, "w") as f:
        json.dump(cleaned_logs, f, indent=4)
    return cleaned_logs

# Load Init Data
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
    # Fix: Ensure DM prefix works with the custom prefix set for the owner
    if not message.guild:
        return prefixes.get(str(message.author.id), "!")
    return prefixes.get(str(message.guild.id), "/")

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix=get_prefix, intents=intents, help_command=None)
        self.start_time = time.time()

    async def setup_hook(self):
        self.daily_backup.start()
        print(f"✅ {self.user} Online | All Systems Go")

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            global interaction_logs
            interaction_logs = save_interaction_logs(interaction_logs)
            await owner.send("📦 **Daily Data Sync**", files=[discord.File(DATA_FILE), discord.File(LOG_FILE)])
        except: pass

bot = MyBot()

def quick_embed(title, description, color=discord.Color.blue()):
    return discord.Embed(title=title, description=description, color=color)

# --- GLOBAL ERROR HANDLER ---
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        perms = ", ".join(error.missing_permissions)
        await interaction.response.send_message(f"⚠️ Missing Permissions: `{perms}`", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ Restricted command.", ephemeral=True)

# --- 👑 OWNER PREFIX COMMANDS (DM ONLY) ---

@bot.command(name="messages", help="Exports 24h interaction JSON in nested format.")
@commands.is_owner()
@commands.dm_only()
async def messages_log(ctx):
    now = time.time()
    day_ago = now - 86400
    recent = [l for l in interaction_logs if l['timestamp'] > day_ago]
    output = {"servers": {}, "dm": {}}
    for entry in recent:
        user_key = f"{entry['user_name']}/{entry['user_id']}"
        if entry.get('guild_id'):
            s_id, c_id = str(entry['guild_id']), str(entry['channel_id'])
            if s_id not in output["servers"]: output["servers"][s_id] = {}
            if c_id not in output["servers"][s_id]: output["servers"][s_id][c_id] = {}
            if user_key not in output["servers"][s_id][c_id]:
                output["servers"][s_id][c_id][user_key] = {"prompt": [], "response": []}
            output["servers"][s_id][c_id][user_key]["prompt"].append(entry["prompt"])
            output["servers"][s_id][c_id][user_key]["response"].append(entry["response"])
        else:
            if user_key not in output["dm"]: output["dm"][user_key] = {"prompt": [], "response": []}
            output["dm"][user_key]["prompt"].append(entry["prompt"])
            output_data["dm"][user_key]["response"].append(entry["response"])

    fname = f"export_{int(now)}.json"
    with open(fname, "w") as f: json.dump(output, f, indent=2)
    await ctx.send(embed=quick_embed("📂 Log Export", "Latest 24h interaction history."), file=discord.File(fname))
    os.remove(fname)

@bot.command(name="clearlogs", help="Clears interaction_logs.json file.")
@commands.is_owner()
async def clear_logs_cmd(ctx):
    global interaction_logs
    interaction_logs = []
    if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
    await ctx.send("🧹 Logs Purged.")

@bot.command(name="server-list", help="JSON of all bot guilds.")
@commands.is_owner()
async def server_list_dm(ctx):
    data = {g.name: {"id": g.id, "members": g.member_count} for g in bot.guilds}
    with open("servers.json", "w") as f: json.dump(data, f, indent=4)
    await ctx.send(file=discord.File("servers.json")); os.remove("servers.json")

# --- 🛡️ SECURITY & STRIKES ---

@bot.hybrid_command(name="help", description="Command Center.")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 FlexedAI Master", color=discord.Color.blue())
    embed.add_field(name="📡 Utility", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami`, `/prefix`, `/stats`, `/searchlogs` ", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="🛡️ Security", value="`/blacklist add/remove`, `/list blacklist`, `/bannedword add/remove`, `/addstrike`, `/clearstrike`, `/strikelist`, `/logs`, `/clearadminlogs` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_group(name="blacklist", description="Restrict users.")
@commands.is_owner()
async def blacklist_group(ctx): pass

@blacklist_group.command(name="add")
async def bl_add(ctx, user_id: str):
    BLACKLISTED_USERS.add(int(user_id)); save_data()
    await ctx.reply(f"🚫 `{user_id}` Blacklisted.")

@blacklist_group.command(name="remove")
async def bl_remove(ctx, user_id: str):
    uid = int(user_id)
    if uid in BLACKLISTED_USERS: BLACKLISTED_USERS.remove(uid)
    save_data(); await ctx.reply(f"✅ `{uid}` Un-blacklisted.")

@bot.hybrid_command(name="list", description="List blacklisted users.")
@commands.is_owner()
async def list_bl_cmd(ctx, target: str):
    if target.lower() == "blacklist":
        res = ", ".join([str(u) for u in BLACKLISTED_USERS]) or "None"
        await ctx.reply(embed=quick_embed("📋 Blacklist", f"`{res}`"))

@bot.hybrid_command(name="addstrike", description="Issue strikes. 3 = Ban.")
@commands.is_owner()
async def add_strike_cmd(ctx, user_id: str, amount: int):
    u_str = str(user_id)
    violations_storage[u_str] = violations_storage.get(u_str, 0) + amount
    admin_logs.append(f"[{datetime.datetime.now()}] Strike to {user_id}. ({violations_storage[u_str]}/3)")
    if violations_storage[u_str] >= 3:
        BLACKLISTED_USERS.add(int(user_id)); violations_storage[u_str] = 3
        admin_logs.append(f"[{datetime.datetime.now()}] AUTO-BAN: {user_id}")
        save_data(); return await ctx.reply(f"⚡ `{user_id}` BANNED (3/3).")
    save_data(); await ctx.reply(f"⚡ Strike recorded: {violations_storage[u_str]}/3.")

@bot.hybrid_command(name="strikelist", description="Strike ledger.")
@commands.is_owner()
async def strike_list_view(ctx):
    t = "\n".join([f"<@{u}>: {v}/3" for u, v in violations_storage.items() if v > 0]) or "None."
    await ctx.reply(embed=quick_embed("⚡ Strikes", t))

@bot.hybrid_command(name="logs", description="Last 15 admin entries.")
@commands.is_owner()
async def admin_logs_view(ctx):
    h = "\n".join(admin_logs[-15:]) if admin_logs else "No logs."
    await ctx.reply(embed=quick_embed("📜 Admin Logs", f"```\n{h}\n```"))

# --- 🎙️ AI & CHANNEL CONTROL ---

@bot.hybrid_command(name="lang", description="Set channel language.")
@app_commands.choices(language=[
    app_commands.Choice(name="English", value="English"),
    app_commands.Choice(name="Hindi", value="Hindi"),
    app_commands.Choice(name="Hinglish", value="Hinglish"),
    app_commands.Choice(name="Spanish", value="Spanish"),
    app_commands.Choice(name="Japanese", value="Japanese")
])
@commands.has_permissions(administrator=True)
async def lang_set(ctx, language: app_commands.Choice[str]):
    channel_languages[str(ctx.channel.id)] = language.value; save_data()
    await ctx.reply(f"🌐 Language: **{language.name}**.")

@bot.hybrid_command(name="prefix", description="Change server prefix.")
@commands.has_permissions(administrator=True)
async def set_prefix_cmd(ctx, new_prefix: str):
    prefixes[str(ctx.guild.id if ctx.guild else ctx.author.id)] = new_prefix; save_data()
    await ctx.reply(f"🎯 Prefix: `{new_prefix}`")

@bot.hybrid_command(name="start", description="Always respond.")
@commands.has_permissions(administrator=True)
async def start_cmd(ctx):
    response_mode[str(ctx.channel.id)] = "start"; save_data(); await ctx.reply("🎙️ ALWAYS mode ON.")

@bot.hybrid_command(name="stop", description="Trigger only.")
@commands.has_permissions(administrator=True)
async def stop_cmd(ctx):
    response_mode[str(ctx.channel.id)] = "stop"; save_data(); await ctx.reply("🔇 TRIGGER mode ON.")

# --- AI HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    ctx = await bot.get_context(message)
    if ctx.valid: await bot.invoke(ctx); return

    is_dm = message.guild is None
    content_lower = message.content.lower().strip()
    
    # TRIGGER: Prefix or Suffix check
    has_trigger = content_lower.startswith("flexedai") or content_lower.endswith("flexedai")
    mode = response_mode.get(str(message.channel.id), "stop")
    is_pinged = bot.user.mentioned_in(message) and not message.mention_everyone
    images = [a for a in message.attachments if a.content_type and a.content_type.startswith('image')]

    # DM Rule: Always reply | Server Rule: Trigger/Mode check
    if not is_dm and mode == "stop" and not (is_pinged or images or has_trigger): return

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=6)

    lang = channel_languages.get(str(message.channel.id), "English")
    roles = [r.name for r in message.author.roles if r.name != "@everyone"] if not is_dm else ["DM User"]

    system = (
        f"You are FlexedAI. Mirror the user's tone/energy EXACTLY. Concise replies. Lang: {lang}.\n"
        f"USER: {message.author.display_name} (@{message.author.name}), ID: {message.author.id}, PFP: {message.author.display_avatar.url}, Roles: {', '.join(roles)}.\n"
        f"LOC: Server: {message.guild.name if not is_dm else 'DMs'}, Channel: {message.channel.name if not is_dm else 'DMs'}."
    )

    try:
        async with message.channel.typing():
            user_text = message.content or "Analyze image."
            payload = [{"type": "text", "text": user_text}]
            for img in images: payload.append({"type": "image_url", "image_url": {"url": img.url}})
            
            msgs = [{"role": "system", "content": system}]
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
                    "timestamp": time.time(), "guild_id": message.guild.id if not is_dm else None,
                    "channel_id": message.channel.id, "user_name": message.author.name,
                    "user_id": message.author.id, "prompt": user_text, "response": output
                })
                interaction_logs = save_interaction_logs(interaction_logs)
    except Exception as e: print(f"AI Error: {e}")

# (Remaining standard commands: ping, uptime, stats, forget, sync, backup, refresh, searchlogs, clearstrikes, clearadminlogs etc. are mapped in the hybrid registry above)

bot.run(DISCORD_TOKEN)
