import discord
import os
import asyncio
import io
import time
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY') # Use the key you provided

# Initialize Gemini 2.0 Client
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_ID = "gemini-2.5-flash"
START_TIME = datetime.utcnow()

class ThoughtPartner:
    def __init__(self, user_name, owner_name):
        self.user_name = user_name
        self.owner_name = owner_name
        self.history = [] # Gemini 2.0 handles history via 'contents' list

    def get_system_instruction(self):
        return (
            f"You are Gemini, a helpful AI thought partner for {self.user_name}. Owner: {self.owner_name}. "
            "Traits: Empathetic, concise, and a Grandmaster-level Chess Expert. "
            "Safety: STRICT NO SLURS/SWEARING. Polite and respectful always. "
            "Conciseness: Maximum Info-to-Word ratio. No fluff. No citations or [1] links. "
            "Capabilities: You can generate images. If asked for a picture, trigger image generation logic."
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
    app_info = await bot.application_info()
    bot.owner_name = app_info.owner.name
    print(f'✨ Gemini 2.5 Online. Owner: {bot.owner_name}')

@bot.event
async def on_message(message):
    if message.author.bot: return

    uid = message.author.id
    if uid not in user_states:
        user_states[uid] = ThoughtPartner(message.author.display_name, bot.owner_name)
    
    state = user_states[uid]
    clean_msg = message.content.lower().strip()

    # 1. System Stats Command
    if clean_msg in ["/status", "who is your owner?", "ping"]:
        latency = round(bot.latency * 1000)
        await message.reply(
            f"### 🚀 Gemini 2.5 Flash\n"
            f"* **Owner:** {bot.owner_name}\n"
            f"* **Latency:** {latency}ms\n"
            f"* **Uptime:** {get_uptime()}\n"
            f"* **Chess IQ:** 2800 (Grandmaster)"
        )
        return

    # 2. Main Chat & Image Generation Loop
    async with message.channel.typing():
        try:
            # Check for Image Intent
            image_keywords = ["generate image", "draw", "create a picture", "show me a"]
            is_image_req = any(kw in clean_msg for kw in image_keywords)

            # Build request
            config = types.GenerateContentConfig(
                system_instruction=state.get_system_instruction(),
                temperature=0.7,
            )

            response = client.models.generate_content(
                model=MODEL_ID,
                contents=message.content,
                config=config
            )

            # Handle Native Image Generation if the model supports it/returns it
            # (Gemini 2.0 can return image bytes directly in some configurations)
            has_image = False
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    img_data = io.BytesIO(part.inline_data.data)
                    file = discord.File(fp=img_data, filename="generated_image.png")
                    await message.reply(content=response.text, file=file)
                    has_image = True
                    break
            
            if not has_image:
                await message.reply(response.text, mention_author=False)

        except Exception as e:
            print(f"Error: {e}")
            await message.reply("I encountered a logic error. Let's restart our conversation.")

bot.run(DISCORD_TOKEN)
