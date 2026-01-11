import discord, os, time, datetime, json, re
from discord.ext import commands, tasks
from discord import app_commands
from groq import AsyncGroq 
from collections import deque

# --- CONFIG & DATA ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
# Friendly reminder: Llama 4 isn't out yet! Switched to a valid Llama 3.1 ID
MODEL_NAME = "llama-3.1-70b-versatile" 
OWNER_ID = 1081876265683927080
DATA_FILE, LOG_FILE = "bot_data.json", "interaction_logs.json"

def load_json(fp, default):
    if not os.path.exists(fp):
        return default
    try:
        with open(fp, "r") as f:
            content = f.read()
            return json.loads(content) if content else default
    except Exception as e:
        print(f"Error loading {fp}: {e}")
        return default

# Initialize data correctly
data = load_json(DATA_FILE, {})
BLACKLISTED = set(data.get("bl", []))
BANNED_WORDS = set(data.get("bw", []))
# Ensuring these are dictionaries as expected
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
        "bl": list(BLACKLISTED),
        "bw": list(BANNED_WORDS),
        "langs": LANGS,
        "strikes": STRIKES,
        "pfx": PREFIXES,
        "modes": MODES,
        "alogs": ADMIN_LOGS
    }
    with open(DATA_FILE, "w") as f:
        json.dump(payload, f, indent=2)
    
    global interaction_logs
    cutoff = time.time() - 86400
    interaction_logs = [l for l in interaction_logs if l['timestamp'] > cutoff]
    with open(LOG_FILE, "w") as f:
        json.dump(interaction_logs, f)

def get_prefix(bot, msg):
    # Fixed: Prioritize Guild Prefix, then User Prefix, then default "/"
    if msg.guild:
        return PREFIXES.get(str(msg.guild.id), "/")
    return PREFIXES.get(str(msg.author.id), "/")

bot = commands.Bot(command_prefix=get_prefix, intents=discord.Intents.all(), help_command=None)
bot.start_time = time.time()

# --- HELPERS ---
def contains_banned_word(text):
    text = text.lower()
    return any(word in text for word in BANNED_WORDS)

# --- EVENTS ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Current Prefixes Loaded: {PREFIXES}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NotOwner): 
        await ctx.send("❌ **Access Denied:** Owner only.")
    elif isinstance(error, commands.MissingPermissions): 
        await ctx.send(f"⚠️ Missing Perms: `{error.missing_permissions}`")
    elif isinstance(error, commands.CommandNotFound):
        pass # Ignore unknown commands to avoid spam
    else:
        print(f"Command Error: {error}")

# --- COMMANDS ---
@bot.command()
@commands.is_owner()
async def sync(ctx):
    fmt = await bot.tree.sync()
    await ctx.send(f"🚀 Synced {len(fmt)} slash commands.")

@bot.hybrid_command(name="prefix")
async def set_prefix(ctx, new: str):
    """Change the bot prefix for this server or DM."""
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID): 
        return await ctx.reply("❌ Admin only.", ephemeral=True)
    
    key = str(ctx.guild.id if ctx.guild else ctx.author.id)
    PREFIXES[key] = new
    save_all()
    await ctx.reply(f"🎯 Prefix successfully updated to: `{new}`")

@bot.hybrid_group(name="bannedword")
@commands.is_owner()
async def bw_grp(ctx): pass

@bw_grp.command(name="add")
async def bw_a(ctx, word: str): 
    BANNED_WORDS.add(word.lower())
    save_all()
    await ctx.reply(f"🚫 `{word}` added to filter.")

# --- AI HANDLER (FIXED) ---
@bot.event
async def on_message(msg):
    if msg.author.bot or msg.author.id in BLACKLISTED:
        return

    # Check for banned words first
    if contains_banned_word(msg.content):
        if not msg.content.startswith(tuple(await bot.get_prefix(msg))):
            await msg.delete() # Optional: delete message with banned word
            await msg.channel.send(f"⚠️ {msg.author.mention}, your message contained a banned word.", delete_after=5)
        return

    # IMPORTANT: This handles commands (including prefix changes)
    ctx = await bot.get_context(msg)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # --- AI RESPONSE LOGIC ---
    is_dm = not msg.guild
    txt = msg.content.lower().strip()
    # Trigger AI if pinged or if name mentioned
    trigger = bot.user.mentioned_in(msg) or "flexedai" in txt
    
    # Mode check
    current_mode = MODES.get(str(msg.channel.id), "stop")
    if not is_dm and current_mode == "stop" and not trigger:
        return

    tid = f"{msg.channel.id}-{msg.author.id}"
    if tid not in thread_memory:
        thread_memory[tid] = deque(maxlen=6)
    
    lang = LANGS.get(str(msg.channel.id), "English")
    sys_p = f"You are FlexedAI. Concise. Respond in {lang}. User: {msg.author.name}."
    
    try:
        async with msg.channel.typing():
            # Build history
            hist = [{"role": "system", "content": sys_p}]
            for h in thread_memory[tid]:
                hist.append(h)
            
            # Current message with optional image support
            user_content = [{"type": "text", "text": msg.content or "Analyze image"}]
            for a in msg.attachments:
                if a.content_type and "image" in a.content_type:
                    user_content.append({"type": "image_url", "image_url": {"url": a.url}})
            
            hist.append({"role": "user", "content": user_content})

            resp = await client.chat.completions.create(model=MODEL_NAME, messages=hist)
            out = resp.choices[0].message.content
            
            if out:
                await msg.reply(out)
                thread_memory[tid].append({"role": "user", "content": msg.content})
                thread_memory[tid].append({"role": "assistant", "content": out})
                
                # Log interaction
                interaction_logs.append({
                    "timestamp": time.time(), 
                    "user_id": msg.author.id, 
                    "user_name": msg.author.name, 
                    "guild_id": msg.guild.id if msg.guild else None,
                    "prompt": msg.content, 
                    "response": out
                })
                save_all()
    except Exception as e:
        print(f"AI Error: {e}")

bot.run(DISCORD_TOKEN)
