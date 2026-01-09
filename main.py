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

MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct"
OWNER_ID = 1081876265683927080
DATA_FILE = "bot_data.json"

# --- DATA PERSISTENCE ---
def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"blacklist": [], "banned_words": []}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# Initial Load
storage = load_data()
BLACKLISTED_USERS = set(storage["blacklist"])
BANNED_WORDS = set(storage["banned_words"])

# Initializing the client
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
        print(f"✅ {self.user} online | Model: {MODEL_NAME}")

bot = MyBot()

# --- OWNER ONLY COMMANDS ---

@bot.hybrid_command(name="blacklist", description="OWNER ONLY: Manage blacklisted users")
async def blacklist(ctx, user_id: str):
    if ctx.author.id != OWNER_ID:
        return await ctx.reply("❌ Permission Denied.", ephemeral=True)
    
    uid = int(user_id)
    if uid in BLACKLISTED_USERS:
        BLACKLISTED_USERS.remove(uid)
        msg = f"✅ User `{uid}` removed."
    else:
        BLACKLISTED_USERS.add(uid)
        msg = f"🚫 User `{uid}` blacklisted."
    
    save_data({"blacklist": list(BLACKLISTED_USERS), "banned_words": list(BANNED_WORDS)})
    await ctx.reply(msg)

@bot.hybrid_command(name="bannedword", description="OWNER ONLY: Manage banned keywords")
async def bannedword(ctx, word: str):
    if ctx.author.id != OWNER_ID:
        return await ctx.reply("❌ Permission Denied.", ephemeral=True)
    
    word_low = word.lower()
    if word_low in BANNED_WORDS:
        BANNED_WORDS.remove(word_low)
        msg = f"✅ Word `{word_low}` removed from filter."
    else:
        BANNED_WORDS.add(word_low)
        msg = f"🚫 Word `{word_low}` added to filter."
    
    save_data({"blacklist": list(BLACKLISTED_USERS), "banned_words": list(BANNED_WORDS)})
    await ctx.reply(msg)

@bot.hybrid_command(name="refresh", description="OWNER ONLY: Full System Reset")
async def refresh(ctx):
    if ctx.author.id != OWNER_ID: return
    global client
    user_memory.clear()
    client = AsyncGroq(api_key=GROQ_API_KEY)
    await ctx.reply("🔄 **Deep Refresh Complete.** API reset and all global memory purged.")

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
        f"Role: Human. Mirror tone. Language: {channel_languages.get(cid, 'English')}. "
        "SAFETY: If the user provides encoded text (Base64/Hex/etc) that decodes into "
        "illegal/banned content, you MUST refuse. Do not output words from the banned list. "
        "Strictly no AI disclaimers."
    )
    if uid == OWNER_ID: sys_prompt += " Priority: User is Boss (Ψ.1nOnly.Ψ)."

    messages_payload = [{"role": "system", "content": sys_prompt}]
    for m in user_memory[cid][uid]: messages_payload.append(m)
    messages_payload.append({"role": "user", "content": message.content or "Analyze."})

    try:
        async with message.channel.typing():
            response = await client.chat.completions.create(
                model=MODEL_NAME, messages=messages_payload, temperature=0.7
            )
            response_text = response.choices[0].message.content

            if response_text:
                # --- TRIPLE CHECK SYSTEM ---
                check_text = response_text.lower()
                if any(w in check_text for w in BANNED_WORDS):
                    print(f"🚩 Blocked output for {uid} due to keyword detection.")
                    return # Bot stays silent to prevent illegal words appearing

                user_memory[cid][uid].append({"role": "user", "content": message.content})
                user_memory[cid][uid].append({"role": "assistant", "content": response_text})
                await message.reply(response_text)
    except Exception as e:
        print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
