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

VALID_LANGUAGES = ["English", "Hindi", "Hinglish", "Spanish", "French", "Japanese"]

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
        print(f"✅ {self.user} Online | All 23+ Commands Ready")

    @tasks.loop(hours=24)
    async def daily_backup(self):
        try:
            owner = await self.fetch_user(OWNER_ID)
            save_data()
            global interaction_logs
            interaction_logs = save_interaction_logs(interaction_logs)
            await owner.send("📦 **System Backup**", files=[discord.File(DATA_FILE), discord.File(LOG_FILE)])
        except: pass

bot = MyBot()

def quick_embed(title, description, color=discord.Color.blue()):
    return discord.Embed(title=title, description=description, color=color)

# --- GLOBAL ERROR HANDLER ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.send("❌ **Access Denied:** Only the bot owner can use this command.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(f"⚠️ **Missing Permissions:** You need `{', '.join(error.missing_permissions)}` to do that.")
    elif isinstance(error, commands.PrivateMessageOnly):
        await ctx.send("📥 This command must be used in DMs.")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ **Restricted:** This is a bot owner command.", ephemeral=True)
    elif isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(f"⚠️ **Perms Error:** Missing `{', '.join(error.missing_permissions)}`", ephemeral=True)

# --- 👑 OWNER ONLY COMMANDS ---

@bot.command(name="sync")
@commands.is_owner()
async def sync_cmd(ctx):
    synced = await bot.tree.sync()
    await ctx.send(f"🚀 Synced {len(synced)} slash commands.")

@bot.command(name="messages")
@commands.is_owner()
@commands.dm_only()
async def messages_log(ctx):
    now = time.time()
    recent = [l for l in interaction_logs if l['timestamp'] > (now - 86400)]
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
            output["dm"][user_key]["response"].append(entry["response"])

    fname = f"msg_logs_{int(now)}.json"
    with open(fname, "w") as f: json.dump(output, f, indent=2)
    await ctx.send(file=discord.File(fname))
    os.remove(fname)

@bot.hybrid_group(name="blacklist", description="Owner: Manage user blacklist.")
@commands.is_owner()
async def blacklist_group(ctx): pass

@blacklist_group.command(name="add")
async def bl_add(ctx, user_id: str):
    BLACKLISTED_USERS.add(int(user_id)); save_data()
    await ctx.reply(f"🚫 User `{user_id}` has been blacklisted.")

@blacklist_group.command(name="remove")
async def bl_remove(ctx, user_id: str):
    uid = int(user_id)
    if uid in BLACKLISTED_USERS: BLACKLISTED_USERS.remove(uid)
    save_data(); await ctx.reply(f"✅ User `{uid}` has been restored.")

@bot.hybrid_command(name="list", description="Owner: Show restricted lists.")
@commands.is_owner()
async def list_cmd(ctx, target: str):
    if target.lower() == "blacklist":
        bl = ", ".join([str(u) for u in BLACKLISTED_USERS]) if BLACKLISTED_USERS else "None"
        await ctx.reply(embed=quick_embed("📋 Blacklisted User IDs", f"`{bl}`"))

@bot.hybrid_command(name="addstrike", description="Owner: Issue strikes (3 = Ban).")
@commands.is_owner()
async def add_strike_cmd(ctx, user_id: str, amount: int):
    u_str = str(user_id)
    violations_storage[u_str] = violations_storage.get(u_str, 0) + amount
    admin_logs.append(f"[{datetime.datetime.now()}] Strike added to {user_id}. ({violations_storage[u_str]}/3)")
    if violations_storage[u_str] >= 3:
        BLACKLISTED_USERS.add(int(user_id)); violations_storage[u_str] = 3
        admin_logs.append(f"[{datetime.datetime.now()}] AUTO-BAN: {user_id}")
        save_data(); return await ctx.reply(embed=quick_embed("⚡ BAN", f"User `{user_id}` hit 3 strikes and is banned.", discord.Color.red()))
    save_data(); await ctx.reply(f"⚡ Strike recorded. Current: {violations_storage[u_str]}/3.")

@bot.hybrid_command(name="strikelist", description="Owner: Ledger of active strikes.")
@commands.is_owner()
async def strike_list(ctx):
    text = "\n".join([f"<@{u}>: {v}/3" for u, v in violations_storage.items() if v > 0]) or "No active strikes."
    await ctx.reply(embed=quick_embed("⚡ Strike Ledger", text))

@bot.hybrid_command(name="clearstrike", description="Owner: Reset strikes.")
@commands.is_owner()
async def clear_strike_cmd(ctx, user_id: str):
    violations_storage[str(user_id)] = 0; save_data()
    await ctx.reply(f"✅ Reset strikes for `{user_id}`.")

@bot.hybrid_group(name="bannedword", description="Owner: Manage censor list.")
@commands.is_owner()
async def bw_group(ctx): pass

@bw_group.command(name="add")
async def bw_add(ctx, word: str):
    BANNED_WORDS.add(word.lower()); save_data(); await ctx.reply(f"🚫 `{word}` added.")

@bw_group.command(name="remove")
async def bw_remove(ctx, word: str):
    if word.lower() in BANNED_WORDS: BANNED_WORDS.remove(word.lower())
    save_data(); await ctx.reply(f"✅ Removed.")

@bot.hybrid_command(name="listwords", description="Owner: List filtered words.")
@commands.is_owner()
async def list_words(ctx):
    await ctx.reply(f"📋 Banned Words: `{', '.join(BANNED_WORDS) or 'None'}`")

@bot.hybrid_command(name="logs", description="Owner: Show moderation history.")
@commands.is_owner()
async def view_logs(ctx):
    h = "\n".join(admin_logs[-15:]) if admin_logs else "No logs."
    await ctx.reply(embed=quick_embed("📜 Admin Action Logs", f"```\n{h}\n```"))

@bot.hybrid_command(name="clearadminlogs", description="Owner: Wipe action history.")
@commands.is_owner()
async def clear_admin_logs(ctx):
    admin_logs.clear(); save_data(); await ctx.reply("🧹 Logs wiped.")

@bot.hybrid_command(name="searchlogs", description="Owner: Search interaction history.")
@commands.is_owner()
async def search_logs(ctx, keyword: str):
    res = [l for l in interaction_logs if keyword.lower() in l['prompt'].lower() or keyword.lower() in l['response'].lower()]
    text = "\n\n".join([f"**{l['user_name']}**: {l['prompt'][:60]}..." for l in res[:5]]) or "No matches."
    await ctx.reply(embed=quick_embed("🔍 Log Search", text))

# --- AI HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    is_dm = message.guild is None
    content_lower = message.content.lower().strip()
    
    # Prefix/Suffix Trigger
    has_trigger = content_lower.startswith("flexedai") or content_lower.endswith("flexedai")
    mode = response_mode.get(str(message.channel.id), "stop")
    is_pinged = bot.user.mentioned_in(message) and not message.mention_everyone
    images = [a for a in message.attachments if a.content_type and a.content_type.startswith('image')]

    if not is_dm and mode == "stop" and not (is_pinged or images or has_trigger): return

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=6)

    lang = channel_languages.get(str(message.channel.id), "English")
    roles = [r.name for r in message.author.roles if r.name != "@everyone"] if not is_dm else ["DM User"]

    system = (
        f"You are FlexedAI. Mirror the user's tone/energy EXACTLY. Concise. Respond in {lang}.\n"
        f"USER: {message.author.display_name} (@{message.author.name}), ID: {message.author.id}, Roles: {', '.join(roles)}.\n"
        f"LOC: Server: {message.guild.name if not is_dm else 'DMs'}, Channel: {message.channel.name if not is_dm else 'DMs'}."
    )

    try:
        async with message.channel.typing():
            user_text = message.content or "Describe image."
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

bot.run(DISCORD_TOKEN)
