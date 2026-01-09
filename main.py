import discord  # Fixed: Lowercase import
from discord.ext import commands, tasks
import os
import json
from groq import AsyncGroq 
from collections import deque

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MODEL_NAME = "llama-4-maverick-17b-128e-instruct"
OWNER_ID = 1081876265683927080
DATA_FILE = "bot_data.json"

# This stays in RAM and is NOT saved to disk (Reset on restart)
thread_memory = {}

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            return {
                "blacklist": set(data.get("blacklist", [])),
                "banned_words": set(data.get("banned_words", [])),
                "languages": data.get("languages", {}),
                "logs": data.get("logs", []),
                "violations": data.get("violations", {})
            }
    except (FileNotFoundError, json.JSONDecodeError):
        return {"blacklist": set(), "banned_words": set(), "languages": {}, "logs": [], "violations": {}}

# Load Persistent State
data = load_data()
BLACKLISTED_USERS = data["blacklist"]
BANNED_WORDS = data["banned_words"]
channel_languages = data["languages"]

client = AsyncGroq(api_key=GROQ_API_KEY)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="/", intents=intents, help_command=None)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ {self.user} is live using Llama 4 Maverick!")

bot = MyBot()

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS: return
    
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # Thread-specific memory (User + Channel combo)
    # Restarting the script clears this dictionary
    thread_id = f"{message.channel.id}-{message.author.id}"
    if thread_id not in thread_memory:
        thread_memory[thread_id] = deque(maxlen=10)

    # Tone Copying & Recall Instructions
    system_prompt = (
        f"Language: {channel_languages.get(str(message.channel.id), 'English')}. "
        "CRITICAL INSTRUCTIONS: "
        "1. Analyze the user's tone (humor, slang, length, mood) and mirror it perfectly. "
        "2. Do NOT mention or use previous messages UNLESS the user explicitly asks you to recall "
        "information or says 'what did I say earlier?'"
    )

    try:
        async with message.channel.typing():
            messages = [{"role": "system", "content": system_prompt}]
            # Add history for context, but the prompt tells it to ignore it unless asked
            messages.extend(list(thread_memory[thread_id]))
            messages.append({"role": "user", "content": message.content})

            res = await client.chat.completions.create(
                model=MODEL_NAME, 
                messages=messages,
                temperature=0.7 # Better for tone mimicking
            )
            
            output = res.choices[0].message.content
            if output:
                # Update volatile memory
                thread_memory[thread_id].append({"role": "user", "content": message.content})
                thread_memory[thread_id].append({"role": "assistant", "content": output})
                await message.reply(output)

    except Exception as e:
        print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
