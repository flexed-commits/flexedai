import discord
from discord.ext import commands
from discord import app_commands
import os
import time
import datetime
import asyncio
from groq import AsyncGroq # Fixed: Using Async version
from collections import deque

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

# Fixed: Initialize Async client
client = AsyncGroq(api_key=GROQ_API_KEY)

MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct"
OWNER_ID = 1081876265683927080

# --- MEMORY STORAGE ---
# Structure: {channel_id: {user_id: deque([messages])}}
user_memory = {} 
channel_languages = {}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        self.start_time = time.time()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ {self.user} is online and Shards are healthy!")

bot = MyBot()

# --- HELPER FUNCTIONS ---

# Fixed: This is now an async function
async def get_groq_response(messages_history):
    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages_history,
            temperature=0.7,
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ Groq API Error: {e}")
        return None

# --- UTILITY COMMANDS ---

@bot.hybrid_command(name="ping", description="Check latency")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! **{round(bot.latency * 1000)}ms**")

# ... (Uptime and Shard commands remain the same) ...

# --- AI MESSAGE HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # 1. Threaded Memory logic
    cid, uid = message.channel.id, message.author.id
    if cid not in user_memory: user_memory[cid] = {}
    if uid not in user_memory[cid]: 
        user_memory[cid][uid] = deque(maxlen=12) # Slightly larger for better tone tracking

    current_lang = channel_languages.get(cid, "English")
    is_boss = uid == OWNER_ID

    # 2. Advanced System Prompt for Tone Mirroring
    sys_prompt = (
        f"Role: Human conversation partner. "
        f"Constraint 1: Reply ONLY in {current_lang}. "
        f"Constraint 2: Strictly mirror the User's tone (slang, brevity, or formality). "
        f"Constraint 3: No AI filler or disclaimers. "
        f"Knowledge: 2026 current events. "
    )
    if is_boss:
        sys_prompt += " Special: You are speaking to your creator, Ψ.1nOnly.Ψ. Be fiercely loyal."

    # 3. Payload Construction
    messages_payload = [{"role": "system", "content": sys_prompt}]
    
    # Add historical thread for this specific user
    for m in user_memory[cid][uid]:
        messages_payload.append(m)

    # Current message (Text + Images)
    content_list = [{"type": "text", "text": message.content or "Analyze this."}]
    if message.attachments:
        for attachment in message.attachments:
            if any(attachment.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg', 'webp']):
                content_list.append({"type": "image_url", "image_url": {"url": attachment.url}})
    
    messages_payload.append({"role": "user", "content": content_list})

    # 4. Non-blocking Response
    try:
        async with message.channel.typing():
            # This 'await' allows the bot to keep up with Discord while waiting for AI
            response_text = await get_groq_response(messages_payload)

            if response_text:
                # Store text-only version for history to save tokens
                user_memory[cid][uid].append({"role": "user", "content": message.content or "[Image]"})
                user_memory[cid][uid].append({"role": "assistant", "content": response_text})
                await message.reply(response_text)
    except Exception as e:
        print(f"Error: {e}")

if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
