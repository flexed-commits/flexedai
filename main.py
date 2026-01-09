import discord
from discord.ext import commands
import os
import time
import json
from groq import AsyncGroq 
from collections import deque
import re

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

storage = load_data()
BLACKLISTED_USERS = set(storage["blacklist"])
BANNED_WORDS = set(storage["banned_words"])

client = AsyncGroq(api_key=GROQ_API_KEY)
user_memory = {}

bot = commands.Bot(command_prefix="/", intents=discord.Intents.all())

# --- AI HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot or message.author.id in BLACKLISTED_USERS:
        return

    cid, uid = message.channel.id, message.author.id
    if cid not in user_memory: user_memory[cid] = {}
    if uid not in user_memory[cid]: user_memory[cid][uid] = deque(maxlen=10)

    # 1. ENHANCED SYSTEM PROMPT FOR SELF-CENSORING
    sys_prompt = (
        "Role: Human helper. You must mirror the user's tone. "
        "CRITICAL INSTRUCTION: You are equipped with an internal profanity and illegal content filter. "
        "If you generate a response that contains any swear words, slurs, or illegal terms, "
        "you MUST replace that specific word with the exact phrase '(censored word)'. "
        "This applies to ANY language and ANY decoding result. "
        "Do not explain why you are censoring. Just replace the word."
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
                temperature=0.4 # Lower temperature makes the AI follow instructions better
            )
            response_text = response.choices[0].message.content

            if response_text:
                # 2. THE MANUAL JSON OVERRIDE
                # This catches the words in your list even if the AI 'forgets' to self-censor
                final_output = response_text
                for word in BANNED_WORDS:
                    # Case-insensitive replacement using regex to catch the word
                    pattern = re.compile(re.escape(word), re.IGNORECASE)
                    final_output = pattern.sub("(censored word)", final_output)

                # 3. THE LAST RESORT COLLAPSE CHECK
                # If the AI tried to be sneaky with spaces (e.g., "F U C K"), 
                # and that word is in your JSON, we kill the message.
                collapsed = "".join(char for char in final_output.lower() if char.isalnum())
                if any(w in collapsed for w in BANNED_WORDS):
                    # If it's still in there, we don't send it at all
                    return

                # Save and Send
                user_memory[cid][uid].append({"role": "user", "content": message.content})
                user_memory[cid][uid].append({"role": "assistant", "content": final_output})
                await message.reply(final_output)
                
    except Exception as e:
        print(f"Error: {e}")

bot.run(DISCORD_TOKEN)
