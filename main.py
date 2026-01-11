import discord, os, time, datetime, json, re
from discord.ext import commands, tasks
from discord import app_commands
from groq import AsyncGroq 
from collections import deque

# --- CONFIG & DATA ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
# Model check: llama-4 doesn't exist in 2026 yet, using llama-3.1-70b-versatile
MODEL_NAME = "llama-3.1-70b-versatile" 
OWNER_ID = 1081876265683927080
DATA_FILE, LOG_FILE = "bot_data.json", "interaction_logs.json"

def load_json(fp, default):
    if not os.path.exists(fp): return default
    try:
        with open(fp, "r") as f: 
            content = f.read()
            return json.loads(content) if content else default
    except: return default

data = load_json(DATA_FILE, {})
# We use strings for keys in JSON, so we convert them back to sets/ints here
BLACKLISTED = set(int(x) for x in data.get("bl", []))
BANNED_WORDS = set(data.get("bw", []))
LANGS = data.get("langs", {})
STRIKES = data.get("strikes", {})
PREFIXES = data.get("pfx", {})
MODES = data.get("modes", {})
ADMIN_LOGS = data.get("alogs", [])
interaction_logs = load_json(LOG_FILE, [])

client = AsyncGroq(api_key=GROQ_API_KEY)
thread_memory = {}

def save_all():
    payload = {
        "bl": list(BLACKLISTED), "bw": list(BANNED_WORDS), "langs": LANGS, 
        "strikes": STRIKES, "pfx": PREFIXES, "modes": MODES, "alogs": ADMIN_LOGS
    }
    with open(DATA_FILE, "w") as f: json.dump(payload, f, indent=2)
    
    global interaction_logs
    cutoff = time.time() - 86400
    interaction_logs = [l for l in interaction_logs if l['timestamp'] > cutoff]
    with open(LOG_FILE, "w") as f: json.dump(interaction_logs, f)

def get_prefix(bot, msg):
    # Check Server Prefix -> Check User/DM Prefix -> Default to "!"
    key = str(msg.guild.id if msg.guild else msg.author.id)
    return PREFIXES.get(key, "!")

bot = commands.Bot(command_prefix=get_prefix, intents=discord.Intents.all(), help_command=None)
bot.start_time = time.time()

# --- UTILS ---
def is_banned_content(text):
    if not text: return False
    return any(word.lower() in text.lower() for word in BANNED_WORDS)

# --- ERROR HANDLERS ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NotOwner): await ctx.send("❌ **Access Denied:** Owner only.")
    elif isinstance(error, commands.MissingPermissions): await ctx.send(f"⚠️ Missing Perms: `{error.missing_permissions}`")
    elif isinstance(error, commands.PrivateMessageOnly): await ctx.send("📥 This command is DM-only.")

# --- 1-3. OWNER MAINTENANCE ---
@bot.command()
@commands.is_owner()
async def sync(ctx):
    fmt = await bot.tree.sync()
    await ctx.send(f"🚀 Synced {len(fmt)} commands globally.")

@bot.command()
@commands.is_owner()
@commands.dm_only()
async def messages(ctx):
    out = {"servers": {}, "dm": {}}
    for l in interaction_logs:
        u_key = f"{l.get('user_name', 'Unknown')}/{l['user_id']}"
        if l.get('guild_id'):
            s_id, c_id = str(l['guild_id']), str(l['channel_id'])
            out["servers"].setdefault(s_id, {}).setdefault(c_id, {}).setdefault(u_key, {"prompts": [], "resps": []})
            out["servers"][s_id][c_id][u_key]["prompts"].append(l['prompt'])
            out["servers"][s_id][c_id][u_key]["resps"].append(l['response'])
        else:
            out["dm"].setdefault(u_key, {"prompts": [], "resps": []})
            out["dm"][u_key]["prompts"].append(l['prompt'])
    with open("nested_logs.json", "w") as f: json.dump(out, f, indent=2)
    await ctx.send(file=discord.File("nested_logs.json"))
    os.remove("nested_logs.json")

@bot.command()
@commands.is_owner()
async def clearlogs(ctx):
    global interaction_logs
    interaction_logs = []; save_all(); await ctx.send("🧹 Interaction logs wiped.")

# --- 4-6. BLACKLIST MGMT ---
@bot.hybrid_group(name="blacklist")
@commands.is_owner()
async def bl_grp(ctx): pass

@bl_grp.command(name="add")
async def bl_add(ctx, user_id: str):
    BLACKLISTED.add(int(user_id)); save_all(); await ctx.reply(f"🚫 {user_id} blacklisted.")

@bl_grp.command(name="remove")
async def bl_rem(ctx, user_id: str):
    BLACKLISTED.discard(int(user_id)); save_all(); await ctx.reply(f"✅ {user_id} un-blacklisted.")

@bot.hybrid_command(name="list")
@commands.is_owner()
async def list_cmd(ctx, target: str):
    if target == "blacklist": await ctx.reply(f"📋 Blacklisted: `{list(BLACKLISTED)}`")

# --- 7-10. STRIKE SYSTEM ---
@bot.hybrid_command(name="addstrike")
@commands.is_owner()
async def strike_add(ctx, user_id: str, amt: int):
    u = str(user_id); STRIKES[u] = STRIKES.get(u, 0) + amt
    ADMIN_LOGS.append(f"[{datetime.datetime.now()}] Strike {user_id}: {STRIKES[u]}/3")
    if STRIKES[u] >= 3:
        BLACKLISTED.add(int(user_id)); await ctx.reply(f"⚡ 3/3 STRIKES: BANNED {user_id}")
    else: await ctx.reply(f"⚡ Strike recorded ({STRIKES[u]}/3)")
    save_all()

@bot.hybrid_command(name="strikelist")
@commands.is_owner()
async def s_list(ctx): await ctx.reply(f"⚡ Strike Ledger: `{STRIKES}`")

@bot.hybrid_command(name="clearstrike")
@commands.is_owner()
async def s_clear(ctx, user_id: str):
    STRIKES[str(user_id)] = 0; save_all(); await ctx.reply(f"✅ Strikes reset for {user_id}.")

# --- 11-14. BANNED WORDS ---
@bot.hybrid_group(name="bannedword")
@commands.is_owner()
async def bw_grp(ctx): pass

@bw_grp.command(name="add")
async def bw_a(ctx, word: str): 
    BANNED_WORDS.add(word.lower()); save_all(); await ctx.reply(f"🚫 `{word}` added.")

@bw_grp.command(name="remove")
async def bw_r(ctx, word: str): 
    BANNED_WORDS.discard(word.lower()); save_all(); await ctx.reply(f"✅ `{word}` removed.")

@bot.hybrid_command(name="listwords")
@commands.is_owner()
async def bw_l(ctx): await ctx.reply(f"📋 Banned Words: `{list(BANNED_WORDS)}`")

# --- 15-18. ADMIN LOGS & SEARCH ---
@bot.hybrid_command(name="logs")
@commands.is_owner()
async def l_view(ctx): 
    res = "\n".join(ADMIN_LOGS[-15:]) or "No logs."
    await ctx.reply(f"📜 **Admin Logs:**\n```{res}```")

@bot.hybrid_command(name="clearadminlogs")
@commands.is_owner()
async def l_clr(ctx): ADMIN_LOGS.clear(); save_all(); await ctx.reply("🧹 Admin logs wiped.")

@bot.hybrid_command(name="searchlogs")
@commands.is_owner()
async def l_srch(ctx, key: str):
    r = [l for l in interaction_logs if key.lower() in l['prompt'].lower()]
    await ctx.reply(f"🔍 Found {len(r)} matches in last 24h.")

# --- 19-24. UTILITIES & MODES ---
@bot.hybrid_command(name="prefix")
async def change_prefix(ctx, new: str):
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID): 
        return await ctx.reply("❌ Admin only.")
    key = str(ctx.guild.id if ctx.guild else ctx.author.id)
    PREFIXES[key] = new; save_all(); await ctx.reply(f"🎯 Prefix set to: `{new}`")

@bot.hybrid_command()
@app_commands.choices(l=[app_commands.Choice(name=i, value=i) for i in ["English", "Hindi", "Hinglish", "Spanish"]])
async def lang(ctx, l: app_commands.Choice[str]):
    if not ctx.author.guild_permissions.administrator: return
    LANGS[str(ctx.channel.id)] = l.value; save_all(); await ctx.reply(f"🌐 Language: **{l.name}**")

@bot.hybrid_command()
async def start(ctx):
    if not ctx.author.guild_permissions.administrator: return
    MODES[str(ctx.channel.id)] = "start"; save_all(); await ctx.reply("🎙️ **ALWAYS** mode active.")

@bot.hybrid_command()
async def stop(ctx):
    if not ctx.author.guild_permissions.administrator: return
    MODES[str(ctx.channel.id)] = "stop"; save_all(); await ctx.reply("🔇 **TRIGGER** mode active.")

@bot.hybrid_command()
async def whoami(ctx):
    roles = [role.name for role in ctx.author.roles if role.name != "@everyone"]
    await ctx.reply(f"👤 **{ctx.author.name}**\nID: `{ctx.author.id}`\nRoles: `{', '.join(roles) if roles else 'None'}`")

@bot.hybrid_command()
async def stats(ctx): 
    up = int(time.time() - bot.start_time)
    await ctx.reply(f"📊 **Stats:**\nLatency: `{round(bot.latency*1000)}ms`\nUptime: `{up}s`\nServers: `{len(bot.guilds)}` ")

@bot.hybrid_command()
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in thread_memory: thread_memory[tid].clear()
    await ctx.reply("🧠 Memory wiped for this thread.")

# --- AI CORE ---
@bot.event
async def on_message(msg):
    if msg.author.bot or msg.author.id in BLACKLISTED: return
    
    # 1. Check for Banned Words first
    if is_banned_content(msg.content):
        # Allow owner to bypass for testing, otherwise ignore/delete
        if msg.author.id != OWNER_ID:
            return 

    # 2. Process Commands (This is why your prefixes weren't working!)
    ctx = await bot.get_context(msg)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # 3. AI Response Logic
    is_dm = not msg.guild
    txt = msg.content.lower().strip()
    trigger = bot.user.mentioned_in(msg) or "flexedai" in txt
    
    if not is_dm and MODES.get(str(msg.channel.id), "stop") == "stop" and not (trigger or msg.attachments): return

    tid = f"{msg.channel.id}-{msg.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=6)
    
    sys_p = f"You are FlexedAI. Concise. Respond in {LANGS.get(str(msg.channel.id), 'English')}."
    
    try:
        async with msg.channel.typing():
            payload = [{"type": "text", "text": msg.content or "Analyze image"}]
            for a in msg.attachments:
                if a.content_type and "image" in a.content_type:
                    payload.append({"type": "image_url", "image_url": {"url": a.url}})
            
            messages = [{"role": "system", "content": sys_p}]
            for h in thread_memory[tid]: messages.append(h)
            messages.append({"role": "user", "content": payload})

            resp = await client.chat.completions.create(model=MODEL_NAME, messages=messages)
            out = resp.choices[0].message.content
            if out:
                await msg.reply(out)
                thread_memory[tid].append({"role": "user", "content": msg.content})
                thread_memory[tid].append({"role": "assistant", "content": out})
                interaction_logs.append({"timestamp": time.time(), "user_id": msg.author.id, "user_name": msg.author.name, 
                                        "guild_id": msg.guild.id if msg.guild else None, "channel_id": msg.channel.id,
                                        "prompt": msg.content, "response": out})
                save_all()
    except Exception as e: print(f"AI Error: {e}")

bot.run(DISCORD_TOKEN)
