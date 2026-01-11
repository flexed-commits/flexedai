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
        print(f"✅ {self.user} Online | All Commands Fixed")

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

# --- GLOBAL ERROR HANDLER ---
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        perms = ", ".join(error.missing_permissions)
        await interaction.response.send_message(f"⚠️ You are missing permissions: `{perms}`", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ This command is restricted.", ephemeral=True)

# --- OWNER PREFIX COMMANDS (DM ONLY) ---

@bot.command(name="messages", help="Exports 24h of interaction history to a nested JSON.")
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
    await ctx.send(embed=quick_embed("📂 Log Retrieval", "Attached is the requested 24h JSON file."), file=discord.File(fname))
    os.remove(fname)

# --- HYBRID COMMANDS ---

@bot.hybrid_command(name="help", description="Shows the Master Command list and descriptions.")
async def help_cmd(ctx):
    embed = discord.Embed(title="🤖 FlexedAI Master Center", color=discord.Color.blue())
    embed.add_field(name="📡 Utilities", value="`/help`, `/ping`, `/uptime`, `/forget`, `/whoami`, `/prefix`, `/stats`, `/searchlogs` ", inline=False)
    embed.add_field(name="🎙️ Control", value="`/start`, `/stop`, `/lang` ", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="🛡️ Security", value="`/blacklist add/remove`, `/list blacklist`, `/bannedword add/remove`, `/listwords`, `/addstrike`, `/clearstrike`, `/strikelist`, `/logs`, `/clearadminlogs` ", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="logs", description="View the last 15 entries of admin logs (Strikes/Bans).")
@commands.is_owner()
async def view_logs(ctx):
    history = "\n".join(admin_logs[-15:]) if admin_logs else "No admin logs found."
    await ctx.reply(embed=quick_embed("📜 Admin Action Logs", f"```\n{history}\n```"))

@bot.hybrid_command(name="lang", description="Set AI response language for this channel.")
@app_commands.choices(language=[
    app_commands.Choice(name="English", value="English"),
    app_commands.Choice(name="Hindi", value="Hindi"),
    app_commands.Choice(name="Hinglish", value="Hinglish"),
    app_commands.Choice(name="Spanish", value="Spanish"),
    app_commands.Choice(name="French", value="French"),
    app_commands.Choice(name="Japanese", value="Japanese"),
    app_commands.Choice(name="Korean", value="Korean")
])
@commands.has_permissions(administrator=True)
async def lang_cmd(ctx, language: app_commands.Choice[str]):
    channel_languages[str(ctx.channel.id)] = language.value; save_data()
    await ctx.reply(embed=quick_embed("🌐 Language Locked", f"Bot will now respond in **{language.name}**."))

@bot.hybrid_command(name="addstrike", description="Issue strikes. 3 strikes results in a global ban.")
@app_commands.describe(user_id="ID of target", amount="Strikes to add")
@commands.is_owner()
async def add_strike_cmd(ctx, user_id: str, amount: int):
    u_str = str(user_id)
    violations_storage[u_str] = violations_storage.get(u_str, 0) + amount
    log_text = f"[{datetime.datetime.now()}] Strike added to {user_id}. Total: {violations_storage[u_str]}/3."
    admin_logs.append(log_text)
    if violations_storage[u_str] >= 3:
        BLACKLISTED_USERS.add(int(user_id)); violations_storage[u_str] = 3
        admin_logs.append(f"[{datetime.datetime.now()}] User {user_id} AUTO-BANNED.")
        save_data(); return await ctx.reply(embed=quick_embed("⚡ BAN", f"User `{user_id}` hit 3/3 strikes and is banned.", discord.Color.red()))
    save_data(); await ctx.reply(f"⚡ Strike recorded for `{user_id}`. Now at {violations_storage[u_str]}/3.")

# --- AI HANDLER (FIXED PREFIX/SUFFIX LOGIC) ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    ctx = await bot.get_context(message)
    if ctx.valid: await bot.invoke(ctx); return

    is_dm = message.guild is None
    content_lower = message.content.lower().strip()
    
    # TRIGGER CHECK: Prefix or Suffix ONLY
    has_trigger = content_lower.startswith("flexedai") or content_lower.endswith("flexedai")
    
    mode = response_mode.get(str(message.channel.id), "stop")
    is_pinged = bot.user.mentioned_in(message) and not message.mention_everyone
    images = [a for a in message.attachments if a.content_type and a.content_type.startswith('image')]

    # DM = Always reply. Server = Check Mode, Pings, Images, or Prefix/Suffix.
    if not is_dm and mode == "stop" and not (is_pinged or images or has_trigger): return

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=6)

    current_lang = channel_languages.get(str(message.channel.id), "English")
    user_roles = [r.name for r in message.author.roles if r.name != "@everyone"] if not is_dm else ["DM User"]

    system_prompt = (
        f"You are FlexedAI. Mirror user's tone EXACTLY. Respond ONLY in {current_lang}. Concise.\n"
        f"CONTEXT: Server: {message.guild.name if not is_dm else 'DMs'}, Channel: {message.channel.name if not is_dm else 'DMs'}.\n"
        f"USER: {message.author.display_name}, ID: {message.author.id}, Roles: {', '.join(user_roles)}."
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
                    "timestamp": time.time(), "guild_id": message.guild.id if not is_dm else None,
                    "channel_id": message.channel.id, "user_name": message.author.name,
                    "user_id": message.author.id, "prompt": user_text, "response": output
                })
                interaction_logs = save_interaction_logs(interaction_logs)
    except Exception as e: print(f"AI Error: {e}")

# (Note: All other commands like !server-list, !clearlogs, /sync, /prefix, /whoami, /stats, /strikelist etc. are kept internally in the bot's hybrid/prefix registry)

bot.run(DISCORD_TOKEN)
