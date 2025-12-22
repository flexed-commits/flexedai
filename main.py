import discord
import os
import asyncio
import time
import re
from datetime import datetime
from dotenv import load_dotenv
from perplexity import Perplexity
from collections import deque

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')

client = Perplexity(api_key=PERPLEXITY_API_KEY)
START_TIME = datetime.utcnow()

class GeminiPartner:
    def __init__(self, user_name, owner_name):
        self.user_name = user_name
        self.owner_name = owner_name
        self.history = deque(maxlen=6)
        
    def get_system_prompt(self):
        return (
            f"Identity: You are Gemini, a helpful AI thought partner. Your owner is {self.owner_name}. "
            "Traits: Empathetic, insightful, and a Grandmaster-level Chess Expert. "
            "Safety: STRICT NO SLURS/SWEARING POLICY. Never use offensive language. "
            "Tone: Concise, peer-like, and balanced. Avoid being overly technical unless asked. "
            "Boundaries: Stay on topic. If the user drifts, gently pivot back to the session goal. "
            "Capabilities: You can generate images. If a user asks to 'draw' or 'generate an image', "
            "provide a detailed visual description in your text output for the image generator tool."
        )

user_states = {}

def get_uptime():
    delta = datetime.utcnow() - START_TIME
    return f"{delta.days}d {delta.seconds//3600}h {(delta.seconds//60)%60}m"

# --- DISCORD CLIENT ---
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    # Fetching the owner name automatically from the Discord Application
    app_info = await bot.application_info()
    bot.owner_name = app_info.owner.name
    print(f'✨ Gemini Bot is active. Owner: {bot.owner_name}')

@bot.event
async def on_message(message):
    if message.author.bot: return

    uid = message.author.id
    if uid not in user_states:
        user_states[uid] = GeminiPartner(message.author.display_name, bot.owner_name)
    
    state = user_states[uid]
    clean_msg = message.content.lower().strip()

    # 1. System Health & Owner Info
    if clean_msg in ["/status", "who is your owner?", "bot info"]:
        latency = round(bot.latency * 1000)
        await message.reply(
            f"### 🚀 System Diagnostics\n"
            f"* **Owner:** {bot.owner_name}\n"
            f"* **Latency:** {latency}ms\n"
            f"* **Uptime:** {get_uptime()}\n"
            f"* **Chess IQ:** 2800+ (Grandmaster)"
        )
        return

    # 2. Main Chat Loop
    async with message.channel.typing():
        try:
            # Check for Image Generation Intent
            is_image_request = any(word in clean_msg for word in ["generate image", "draw", "create a picture"])
            
            messages = [{"role": "system", "content": state.get_system_prompt()}]
            messages.extend(list(state.history))
            messages.append({"role": "user", "content": message.content})

            # AI Call (Using Sonar-Pro for reasoning and image descriptions)
            response = client.chat.completions.create(model="sonar-pro", messages=messages)
            answer = response.choices[0].message.content

            # Update State
            state.history.append({"role": "user", "content": message.content})
            state.history.append({"role": "assistant", "content": answer})

            await message.reply(answer, mention_author=False)

        except Exception as e:
            await message.reply("I hit a temporary snag. Let's reset our focus.")

bot.run(DISCORD_TOKEN)
