import discord
from discord.ext import commands
from discord import app_commands
import os
from groq import Groq
from collections import deque

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
client = Groq(api_key=GROQ_API_KEY)

MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct"
OWNER_ID = 1081876265683927080

# --- IMPROVED MEMORY ---
# Structure: {channel_id: {user_id: deque([...])}}
user_memory = {} 
channel_languages = {}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Bot is online!")

bot = MyBot()

def get_groq_response(messages_history):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages_history,
            temperature=0.8, # Slightly higher for more "human" variety
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ Groq Error: {e}")
        return None

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 1. Permission Check (Prevents 403 Errors)
    if message.guild:
        permissions = message.channel.permissions_for(message.guild.me)
        if not permissions.send_messages or not permissions.view_channel:
            return 

    # 2. Process Commands
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # 3. User-Specific Memory Setup
    cid, uid = message.channel.id, message.author.id
    if cid not in user_memory: user_memory[cid] = {}
    if uid not in user_memory[cid]: user_memory[cid][uid] = deque(maxlen=10)

    # 4. Personality & Tone Logic
    current_lang = channel_languages.get(cid, "English")
    # This prompt tells the AI to mirror the user's vibe/tone
    tone_instruction = (
        "Act like a human. Mirror the user's tone (if they are casual, be casual; if professional, be professional). "
        "You have access to real-time information. Improve your visual analysis by being descriptive."
    )
    is_boss = " (He is your Creator/Boss)" if uid == OWNER_ID else ""
    
    sys_prompt = f"{tone_instruction} Reply in {current_lang}. User: {message.author.name}{is_boss}."

    # 5. Build Payload
    content_list = [{"type": "text", "text": message.content or "Analyze this."}]
    if message.attachments:
        for attachment in message.attachments:
            if any(attachment.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg', 'webp']):
                content_list.append({"type": "image_url", "image_url": {"url": attachment.url}})

    messages_payload = [{"role": "system", "content": sys_prompt}]
    for m in user_memory[cid][uid]:
        messages_payload.append(m)
    messages_payload.append({"role": "user", "content": content_list})

    # 6. Response with Error Handling
    try:
        async with message.channel.typing():
            response_text = get_groq_response(messages_payload)
            if response_text:
                user_memory[cid][uid].append({"role": "user", "content": message.content})
                user_memory[cid][uid].append({"role": "assistant", "content": response_text})
                await message.reply(response_text)
    except discord.Forbidden:
        print(f"Cannot send message in {message.channel.id} due to permissions.")
    except Exception as e:
        print(f"Unexpected error: {e}")

if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
