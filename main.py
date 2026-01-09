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
            # Reconstruct deques from lists for the memory
            mem = data.get("memory", {})
            reconstructed_mem = {}
            for cid, users in mem.items():
                reconstructed_mem[int(cid)] = {int(uid): deque(msgs, maxlen=10) for uid, msgs in users.items()}
            
            return {
                "blacklist": set(data.get("blacklist", [])),
                "banned_words": set(data.get("banned_words", [])),
                "languages": data.get("languages", {}),
                "memory": reconstructed_mem
            }
    except (FileNotFoundError, json.JSONDecodeError):
        return {"blacklist": set(), "banned_words": set(), "languages": {}, "memory": {}}

def save_data():
    # Convert deques back to lists for JSON compatibility
    serializable_mem = {}
    for cid, users in user_memory.items():
        serializable_mem[str(cid)] = {str(uid): list(msgs) for uid, msgs in users.items()}

    with open(DATA_FILE, "w") as f:
        json.dump({
            "blacklist": list(BLACKLISTED_USERS),
            "banned_words": list(BANNED_WORDS),
            "languages": channel_languages,
            "memory": serializable_mem
        }, f, indent=4)

# Initial Load
storage = load_data()
BLACKLISTED_USERS = storage["blacklist"]
BANNED_WORDS = storage["banned_words"]
channel_languages = storage["languages"]
user_memory = storage["memory"]

client = AsyncGroq(api_key=GROQ_API_KEY)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="/", intents=intents, help_command=None)
        self.start_time = time.time()

    async def setup_hook(self):
        await self.tree.sync()
        print(f"\n🚀 {self.user} Online | Memory Loaded from {DATA_FILE}")

bot = MyBot()

# --- COMMANDS ---

@bot.hybrid_command(name="help")
async def help(ctx):
    embed = discord.Embed(title="🤖 Bot Help", color=discord.Color.blue())
    embed.add_field(name="General", value="`/ping`, `/uptime`, `/forget`", inline=False)
    if ctx.author.id == OWNER_ID:
        embed.add_field(name="Owner", value="`/blacklist`, `/bannedword`, `/listwords`, `/refresh`", inline=False)
    await ctx.reply(embed=embed)

@bot.hybrid_command(name="forget")
async def forget(ctx):
    cid, uid = ctx.channel.id, ctx.author.id
    if cid in user_memory and uid in user_memory[cid]:
        user_memory[cid][uid].clear()
        save_data()
        await ctx.reply("🧠 Memory wiped and saved.")
    else:
        await ctx.reply("🤷 No memory to clear.")

@bot.hybrid_command(name="blacklist")
async def blacklist(ctx, user_id: str):
    if ctx.author.id != OWNER_ID: return
    uid = int(user_id)
    if uid in BLACKLISTED_USERS: BLACKLISTED_USERS.remove(uid)
    else: BLACKLISTED_USERS.add(uid)
    save_data()
    await ctx.reply(f"👤 Blacklist updated for `{uid}`.")

@bot.hybrid_command(name="bannedword")
async def bannedword(ctx, word: str):
    if ctx.author.id != OWNER_ID: return
    w = word.lower().strip()
    if w in BANNED_WORDS: BANNED_WORDS.remove(w)
    else: BANNED_WORDS.add(w)
    save_data()
    await ctx.reply(f"🚫 Word filter updated for `{w}`.")

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

    current_lang = channel_languages.get(str(cid), "English")
    sys_prompt = f"Role: Human. Language: {current_lang}. Censor bad words as '(censored word)'."
    
    messages_payload = [{"role": "system", "content": sys_prompt}]
    for m in user_memory[cid][uid]: messages_payload.append(m)
    messages_payload.append({"role": "user", "content": message.content or "Analyze."})

    try:
        async with message.channel.typing():
            response = await client.chat.completions.create(model=MODEL_NAME, messages=messages_payload, temperature=0.4)
            response_text = response.choices[0].message.content

            if response_text:
                final_output = response_text
                for word in BANNED_WORDS:
                    final_output = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE).sub("(censored word)", final_output)

                user_memory[cid][uid].append({"role": "user", "content": message.content})
                user_memory[cid][uid].append({"role": "assistant", "content": final_output})
                
                # Auto-save to JSON after every interaction
                save_data()
                await message.reply(final_output)
    except Exception as e:
        print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
