import discord
from discord.ext import commands
from discord import app_commands
import os
import time
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
            return json.load(f)
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

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="/", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"\n🚀 {self.user} is now ONLINE!")
        print("="*30)
        print("📁 REGISTERED COMMANDS:")
        # This loop prints every command the bot knows to the terminal
        for command in self.walk_commands():
            print(f" -> {command.name} (Prefix)")
        for cmd in self.tree.get_commands():
            print(f" -> /{cmd.name} (Slash)")
        print("="*30 + "\n")

bot = MyBot()

# --- OWNER ONLY COMMANDS ---

@bot.hybrid_command(name="blacklist", description="OWNER ONLY: Block/Unblock a user")
async def blacklist(ctx, user_id: str):
    if ctx.author.id != OWNER_ID:
        return await ctx.reply("❌ Owner restricted.", ephemeral=True)
    
    uid = int(user_id)
    if uid in BLACKLISTED_USERS:
        BLACKLISTED_USERS.remove(uid)
        msg = f"✅ User `{uid}` removed from blacklist."
    else:
        BLACKLISTED_USERS.add(uid)
        msg = f"🚫 User `{uid}` blacklisted."
    
    save_data(BLACKLISTED_USERS, BANNED_WORDS)
    await ctx.reply(msg)

@bot.hybrid_command(name="bannedword", description="OWNER ONLY: Add/Remove word to censor")
async def bannedword(ctx, word: str):
    if ctx.author.id != OWNER_ID:
        return await ctx.reply("❌ Owner restricted.", ephemeral=True)
    
    w = word.lower().strip()
    if w in BANNED_WORDS:
        BANNED_WORDS.remove(w)
        msg = f"✅ Removed `{w}` from filter."
    else:
        BANNED_WORDS.add(w)
        msg = f"🚫 Added `{w}` to filter."
    
    save_data(BLACKLISTED_USERS, BANNED_WORDS)
    await ctx.reply(msg)

@bot.hybrid_command(name="listwords", description="OWNER ONLY: View all banned words")
async def listwords(ctx):
    if ctx.author.id != OWNER_ID: return
    words = ", ".join(BANNED_WORDS) if BANNED_WORDS else "None"
    await ctx.reply(f"📋 **Current Banned Words:**\n`{words}`")

# --- AI MESSAGE HANDLER ---

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

    # Improved System Prompt for Mavericks's censoring logic
    sys_prompt = (
        "Role: Human helper. Mirror tone. "
        "FILTER: If your output contains profanity, slurs, or illegal terms, "
        "replace the word with '(censored word)'. Do this automatically."
    )
    if uid == OWNER_ID: sys_prompt += " Priority: User is Boss."

    messages_payload = [{"role": "system", "content": sys_prompt}]
    for m in user_memory[cid][uid]: messages_payload.append(m)
    messages_payload.append({"role": "user", "content": message.content or "Analyze."})

    try:
        async with message.channel.typing():
            response = await client.chat.completions.create(
                model=MODEL_NAME, 
                messages=messages_payload, 
                temperature=0.4
            )
            response_text = response.choices[0].message.content

            if response_text:
                # 1. Manual Replacement from JSON
                final_output = response_text
                for word in BANNED_WORDS:
                    pattern = re.compile(re.escape(word), re.IGNORECASE)
                    final_output = pattern.sub("(censored word)", final_output)

                # 2. Block if bypass detected (spaces/dots)
                collapsed = "".join(char for char in final_output.lower() if char.isalnum())
                if any(w in collapsed for w in BANNED_WORDS):
                    return 

                user_memory[cid][uid].append({"role": "user", "content": message.content})
                user_memory[cid][uid].append({"role": "assistant", "content": final_output})
                await message.reply(final_output)
                
    except Exception as e:
        print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
