import discord, os, time, datetime, json, re
from discord.ext import commands, tasks
from discord import app_commands
from groq import AsyncGroq 
from collections import deque

# --- CONFIG & DATA ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct" 
OWNER_ID = 1081876265683927080
DATA_FILE, LOG_FILE = "bot_data.json", "interaction_logs.json"

def load_json(fp, default):
    try:
        with open(fp, "r") as f: return json.load(f)
    except: return default

data = load_json(DATA_FILE, {})
BLACKLISTED = set(data.get("bl", []))
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
    with open(DATA_FILE, "w") as f:
        json.dump({"bl": list(BLACKLISTED), "bw": list(BANNED_WORDS), "langs": LANGS, 
                   "strikes": STRIKES, "pfx": PREFIXES, "modes": MODES, "alogs": ADMIN_LOGS}, f, indent=2)
    global interaction_logs
    cutoff = time.time() - 86400
    interaction_logs = [l for l in interaction_logs if l['timestamp'] > cutoff]
    with open(LOG_FILE, "w") as f: json.dump(interaction_logs, f)

def get_prefix(bot, msg):
    return PREFIXES.get(str(msg.guild.id if msg.guild else msg.author.id), "!") if msg.guild or msg.author.id == OWNER_ID else "/"

bot = commands.Bot(command_prefix=get_prefix, intents=discord.Intents.all(), help_command=None)
bot.start_time = time.time()

# --- ERROR HANDLER ---
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NotOwner): await ctx.send("❌ **Owner Only.**")
    elif isinstance(error, commands.MissingPermissions): await ctx.send(f"⚠️ Missing: `{error.missing_permissions}`")

@bot.tree.error
async def on_app_error(intx, error):
    if isinstance(error, app_commands.CheckFailure): await intx.response.send_message("❌ **Owner Only.**", ephemeral=True)

# --- OWNER ONLY (PREFIX) ---
@bot.command()
@commands.is_owner()
async def sync(ctx):
    fmt = await bot.tree.sync()
    await ctx.send(f"🚀 Synced {len(fmt)} commands.")

@bot.command()
@commands.is_owner()
@commands.dm_only()
async def messages(ctx):
    with open("export.json", "w") as f: json.dump(interaction_logs, f, indent=2)
    await ctx.send(file=discord.File("export.json"))
    os.remove("export.json")

# --- HYBRID COMMANDS (OWNER) ---
@bot.hybrid_group(name="blacklist")
@commands.is_owner()
async def bl_grp(ctx): pass

@bl_grp.command(name="add")
async def bl_add(ctx, user_id: str):
    BLACKLISTED.add(int(user_id)); save_all(); await ctx.reply(f"🚫 {user_id} blacklisted.")

@bl_grp.command(name="remove")
async def bl_rem(ctx, user_id: str):
    BLACKLISTED.discard(int(user_id)); save_all(); await ctx.reply(f"✅ {user_id} removed.")

@bot.hybrid_command(name="list")
@commands.is_owner()
async def list_cmd(ctx, target: str):
    if target == "blacklist": await ctx.reply(f"📋 `{list(BLACKLISTED)}` or None")

@bot.hybrid_command(name="addstrike")
@commands.is_owner()
async def strike_add(ctx, user_id: str, amt: int):
    u = str(user_id)
    STRIKES[u] = STRIKES.get(u, 0) + amt
    ADMIN_LOGS.append(f"[{datetime.datetime.now()}] Strike {user_id}: {STRIKES[u]}/3")
    if STRIKES[u] >= 3:
        BLACKLISTED.add(int(user_id)); STRIKES[u] = 3; await ctx.reply(f"⚡ BANNED {user_id}")
    else: await ctx.reply(f"⚡ Strike recorded ({STRIKES[u]}/3)")
    save_all()

@bot.hybrid_command(name="strikelist")
@commands.is_owner()
async def s_list(ctx): await ctx.reply(f"⚡ Strikes: {STRIKES}")

@bot.hybrid_command(name="clearstrike")
@commands.is_owner()
async def s_clear(ctx, user_id: str):
    STRIKES[str(user_id)] = 0; save_all(); await ctx.reply("✅ Wiped.")

@bot.hybrid_group(name="bannedword")
@commands.is_owner()
async def bw_grp(ctx): pass

@bw_grp.command(name="add")
async def bw_a(ctx, word: str): BANNED_WORDS.add(word.lower()); save_all(); await ctx.reply(f"🚫 `{word}` added.")

@bot.hybrid_command(name="listwords")
@commands.is_owner()
async def bw_l(ctx): await ctx.reply(f"📋 `{list(BANNED_WORDS)}`")

@bot.hybrid_command(name="logs")
@commands.is_owner()
async def l_view(ctx): await ctx.reply(f"📜 Logs: ```{ADMIN_LOGS[-10:]}```")

@bot.hybrid_command(name="clearadminlogs")
@commands.is_owner()
async def l_clr(ctx): ADMIN_LOGS.clear(); save_all(); await ctx.reply("🧹 Wiped.")

@bot.hybrid_command(name="searchlogs")
@commands.is_owner()
async def l_srch(ctx, key: str):
    r = [l for l in interaction_logs if key.lower() in l['prompt'].lower()]
    await ctx.reply(f"🔍 Found {len(r)} matches.")

# --- UTILS (ADMIN/USER) ---
@bot.hybrid_command()
async def prefix(ctx, new: str):
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID): return
    PREFIXES[str(ctx.guild.id if ctx.guild else ctx.author.id)] = new; save_all(); await ctx.reply(f"🎯 Prefix: `{new}`")

@bot.hybrid_command()
@app_commands.choices(l=[app_commands.Choice(name=i, value=i) for i in ["English", "Hindi", "Hinglish"]])
async def lang(ctx, l: app_commands.Choice[str]):
    if not ctx.author.guild_permissions.administrator: return
    LANGS[str(ctx.channel.id)] = l.value; save_all(); await ctx.reply(f"🌐 {l.name}")

@bot.hybrid_command()
async def start(ctx):
    if not ctx.author.guild_permissions.administrator: return
    MODES[str(ctx.channel.id)] = "start"; save_all(); await ctx.reply("🎙️ ALWAYS mode.")

@bot.hybrid_command()
async def stop(ctx):
    if not ctx.author.guild_permissions.administrator: return
    MODES[str(ctx.channel.id)] = "stop"; save_all(); await ctx.reply("🔇 TRIGGER mode.")

@bot.hybrid_command()
async def whoami(ctx): await ctx.reply(f"👤 {ctx.author.name} | ID: {ctx.author.id}")

@bot.hybrid_command()
async def stats(ctx): await ctx.reply(f"📊 Latency: {round(bot.latency*1000)}ms")

@bot.hybrid_command()
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in thread_memory: thread_memory[tid].clear()
    await ctx.reply("🧠 Wiped.")

# --- AI HANDLER ---
@bot.event
async def on_message(msg):
    if msg.author.bot or msg.author.id in BLACKLISTED: return
    ctx = await bot.get_context(msg)
    if ctx.valid: await bot.invoke(ctx); return

    is_dm = not msg.guild
    txt = msg.content.lower().strip()
    trigger = txt.startswith("flexedai") or txt.endswith("flexedai") or bot.user.mentioned_in(msg)
    if not is_dm and MODES.get(str(msg.channel.id), "stop") == "stop" and not (trigger or msg.attachments): return

    tid = f"{msg.channel.id}-{msg.author.id}"
    if tid not in thread_memory: thread_memory[tid] = deque(maxlen=6)
    
    sys_p = f"Mirror user tone. Concise. Lang: {LANGS.get(str(msg.channel.id), 'English')}. User: {msg.author.name} (ID: {msg.author.id})."
    
    try:
        async with msg.channel.typing():
            payload = [{"type": "text", "text": msg.content or "Analyze"}]
            for a in msg.attachments:
                if a.content_type.startswith("image"): payload.append({"type": "image_url", "image_url": {"url": a.url}})
            
            hist = [{"role": "system", "content": sys_p}]
            for h in thread_memory[tid]: hist.append(h)
            hist.append({"role": "user", "content": payload})

            resp = await client.chat.completions.create(model=MODEL_NAME, messages=hist)
            out = resp.choices[0].message.content
            if out:
                await msg.reply(out)
                thread_memory[tid].append({"role": "user", "content": msg.content})
                thread_memory[tid].append({"role": "assistant", "content": out})
                interaction_logs.append({"timestamp": time.time(), "user_id": msg.author.id, "prompt": msg.content, "response": out})
    except Exception as e: print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
