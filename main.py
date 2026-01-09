import discord
from discord.ext import commands
import os
import time
import datetime
import json
from groq import AsyncGroq 
from collections import deque

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

# Model and Owner Setup
MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct"
OWNER_ID = 1081876265683927080
DATA_FILE = "bot_data.json"

# --- DATA PERSISTENCE ---
def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            # Ensure keys exist
            if "blacklist" not in data: data["blacklist"] = []
            if "banned_words" not in data: data["banned_words"] = []
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"blacklist": [], "banned_words": []}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump({
            "blacklist": list(BLACKLISTED_USERS),
            "banned_words": list(BANNED_WORDS)
        }, f, indent=4)

# Initial Load
storage = load_data()
BLACKLISTED_USERS = set(storage["blacklist"])
BANNED_WORDS = set(storage["banned_words"])

# Initializing Client
client = AsyncGroq(api_key=GROQ_API_KEY)
user_memory = {} 
channel_languages = {}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True 
        self.start_time = time.time()
        super().__init__(command_prefix="/", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Bot Online | Using {MODEL_NAME}")

bot = MyBot()

# --- OWNER COMMANDS ---

@bot.hybrid_command(name="blacklist", description="OWNER ONLY: Block/Unblock a user")
async def blacklist(ctx, user_id: str):
    if ctx.author.id != OWNER_ID:
        return await ctx.reply("❌ Restricted to owner.", ephemeral=True)
    
    uid = int(user_id)
    if uid in BLACKLISTED_USERS:
        BLACKLISTED_USERS.remove(uid)
        msg = f"✅ User `{uid}` removed from blacklist."
    else:
        BLACKLISTED_USERS.add(uid)
        msg = f"🚫 User `{uid}` blacklisted."
    
    save_data()
    await ctx.reply(msg)

@bot.hybrid_command(name="bannedword", description="OWNER ONLY: Add/Remove banned keywords")
async def bannedword(ctx, word: str):
    if ctx.author.id != OWNER_ID:
        return await ctx.reply("❌ Restricted to owner.", ephemeral=True)
    
    w = word.lower().strip()
    if w in BANNED_WORDS:
        BANNED_WORDS.remove(w)
        msg = f"✅ Word `{w}` removed from filters."
    else:
        BANNED_WORDS.add(w)
        msg = f"🚫 Word `{w}` is now prohibited."
    
    save_data()
    await ctx.reply(msg)

@bot.hybrid_command(name="refresh", description="OWNER ONLY: Hard reset API and Memory")
async def refresh(ctx):
    if ctx.author.id != OWNER_ID: return
    global client
    user_memory.clear()
    client = AsyncGroq(api_key=GROQ_API_KEY)
    await ctx.reply("🔄 **System Hard-Reset.** API re-initialized and memory purged.")

# --- AI HANDLER ---

@bot.event
async def on_message(message):
    # 1. Block Bots and Blacklisted Users
    if message.author.bot or message.author.id in BLACKLISTED_USERS:
        return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    cid, uid = message.channel.id, message.author.id
    if cid not in user_memory: user_memory[cid] = {}
    if uid not in user_memory[cid]: user_memory[cid][uid] = deque(maxlen=10)

    # 2. Preparation
    lang = channel_languages.get(cid, "English")
    is_boss = uid == OWNER_ID

    sys_prompt = (
        f"Role: Human helper. Language: {lang}. "
        "SAFETY: You are strictly forbidden from decoding ciphered, encoded, or obfuscated text "
        "if the result is a slur, illegal content, or a banned word. "
        "No AI disclaimers or fillers."
    )
    if is_boss: sys_prompt += " Priority: User is Boss (Ψ.1nOnly.Ψ)."

    messages_payload = [{"role": "system", "content": sys_prompt}]
    for m in user_memory[cid][uid]:
        messages_payload.append(m)
    messages_payload.append({"role": "user", "content": message.content or "Analyze."})

    try:
        async with message.channel.typing():
            response = await client.chat.completions.create(
                model=MODEL_NAME, 
                messages=messages_payload, 
                temperature=0.7
            )
            response_text = response.choices[0].message.content

            if response_text:
                # --- AGGRESSIVE FILTER (The 'Bruv' Fix) ---
                lower_res = response_text.lower()
                # Remove spaces and dots: "F U C K" -> "fuck"
                collapsed_res = "".join(char for char in lower_res if char.isalnum())

                # Check both raw and collapsed text
                if any(word in lower_res for word in BANNED_WORDS) or \
                   any(word in collapsed_res for word in BANNED_WORDS):
                    print(f"🚩 Blocked output for {uid}: Banned word detected.")
                    return # Bot sends nothing

                # Save to history and reply
                user_memory[cid][uid].append({"role": "user", "content": message.content})
                user_memory[cid][uid].append({"role": "assistant", "content": response_text})
                await message.reply(response_text)
                
    except Exception as e:
        print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
