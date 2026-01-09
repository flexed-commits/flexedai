import discord
from discord.ext import commands
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

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"blacklist": [], "banned_words": []}

def save_data(bl, bw):
    with open(DATA_FILE, "w") as f:
        json.dump({"blacklist": list(bl), "banned_words": list(bw)}, f, indent=4)

storage = load_data()
BLACKLISTED_USERS = set(storage.get("blacklist", []))
BANNED_WORDS = set(storage.get("banned_words", []))

client = AsyncGroq(api_key=GROQ_API_KEY)
user_memory = {}
channel_languages = {}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="/", intents=intents)
        self.start_time = time.time()

    async def setup_hook(self):
        await self.tree.sync()
        print(f"\n🚀 {self.user} is ONLINE!")
        print("="*30)
        print("📁 REGISTERED COMMANDS:")
        for command in self.walk_commands():
            print(f" -> {command.name}")
        print("="*30 + "\n")

bot = MyBot()

# --- UTILITY COMMANDS (Restored) ---

@bot.hybrid_command(name="ping", description="Check latency")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! **{round(bot.latency * 1000)}ms**")

@bot.hybrid_command(name="uptime", description="Check bot uptime")
async def uptime(ctx):
    uptime_sec = int(round(time.time() - bot.start_time))
    text = str(datetime.timedelta(seconds=uptime_sec))
    await ctx.reply(f"🚀 Uptime: **{text}**")

@bot.hybrid_command(name="lang", description="Change AI Language")
async def lang(ctx, language: str):
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID):
        return await ctx.reply("❌ Admin permissions required.", ephemeral=True)
    channel_languages[ctx.channel.id] = language
    await ctx.reply(f"🌐 Language updated to **{language}**.")

@bot.hybrid_command(name="forget", description="Clear your conversation memory")
async def forget(ctx):
    cid, uid = ctx.channel.id, ctx.author.id
    if cid in user_memory and uid in user_memory[cid]:
        user_memory[cid][uid].clear()
        await ctx.reply("🧠 Memory wiped for this channel.")
    else:
        await ctx.reply("🤷 No memory found to clear.")

@bot.hybrid_command(name="refresh", description="OWNER ONLY: Full system reset")
async def refresh(ctx):
    if ctx.author.id != OWNER_ID: return
    global client
    user_memory.clear()
    client = AsyncGroq(api_key=GROQ_API_KEY)
    await ctx.reply("🔄 **Deep Refresh Complete.** API reset and memory purged.")

# --- ADMIN COMMANDS ---

@bot.hybrid_command(name="blacklist", description="OWNER ONLY: Block user")
async def blacklist(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    uid = int(user_id)
    if uid in BLACKLISTED_USERS:
        BLACKLISTED_USERS.remove(uid)
        msg = f"✅ User `{uid}` unblocked."
    else:
        BLACKLISTED_USERS.add(uid)
        msg = f"🚫 User `{uid}` blacklisted."
    save_data(BLACKLISTED_USERS, BANNED_WORDS)
    await ctx.reply(msg)

@bot.hybrid_command(name="bannedword", description="OWNER ONLY: Add/Remove censor word")
async def bannedword(ctx, word: str):
    if ctx.author.id != OWNER_ID: return
    w = word.lower().strip()
    if w in BANNED_WORDS:
        BANNED_WORDS.remove(w)
        msg = f"✅ Word `{w}` removed."
    else:
        BANNED_WORDS.add(w)
        msg = f"🚫 Word `{w}` added to censor."
    save_data(BLACKLISTED_USERS, BANNED_WORDS)
    await ctx.reply(msg)

# --- AI HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS:
        return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    cid, uid = message.channel.id, message.author.id
    if cid not in user_memory: user_memory[cid] = {}
    if uid not in user_memory[cid]: user_memory[cid][uid] = deque(maxlen=10)

    sys_prompt = (
        f"Role: Human. Language: {channel_languages.get(cid, 'English')}. "
        "FILTER: Replace any profanity/illegal terms with '(censored word)' automatically."
    )
    if uid == OWNER_ID: sys_prompt += " User is Boss."

    messages_payload = [{"role": "system", "content": sys_prompt}]
    for m in user_memory[cid][uid]: messages_payload.append(m)
    messages_payload.append({"role": "user", "content": message.content or "Analyze."})

    try:
        async with message.channel.typing():
            response = await client.chat.completions.create(
                model=MODEL_NAME, messages=messages_payload, temperature=0.4
            )
            response_text = response.choices[0].message.content

            if response_text:
                # Force JSON filter censor
                final_output = response_text
                for word in BANNED_WORDS:
                    final_output = re.compile(re.escape(word), re.IGNORECASE).sub("(censored word)", final_output)

                # Collapse check for bypasses
                collapsed = "".join(c for c in final_output.lower() if c.isalnum())
                if any(w in collapsed for w in BANNED_WORDS): return

                user_memory[cid][uid].append({"role": "user", "content": message.content})
                user_memory[cid][uid].append({"role": "assistant", "content": final_output})
                await message.reply(final_output)
    except Exception as e:
        print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
