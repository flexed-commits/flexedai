import discord
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI  # Use the OpenAI SDK

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
BYTEZ_KEY = os.getenv('BYTEZ_KEY')  # Make sure this is in your .env

# Initialize Bytez Client using OpenAI SDK
client = OpenAI(
    api_key=BYTEZ_KEY,
    base_url="https://api.bytez.com/models/v2/openai/v1"
)
MODEL_ID = "Qwen/Qwen3-4B" # As per your snippet
START_TIME = datetime.utcnow()

class ThoughtPartner:
    def __init__(self, user_name, owner_name):
        self.user_name = user_name
        self.owner_name = owner_name
        # Openai-style history: list of dicts
        self.history = [] 

    def get_system_instruction(self):
        return (
            f"You are a helpful AI thought partner for {self.user_name}. Owner: {self.owner_name}. "
            "Traits: Empathetic, concise, and a Grandmaster-level Chess Expert. "
            "Safety: STRICT NO SLURS/SWEARING. Polite and respectful always. "
            "Conciseness: Maximum Info-to-Word ratio. No fluff."
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
    print(f'✨ Bytez Bot Online. Model: {MODEL_ID}')

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
            f"### 🚀 Powered by Bytez\n"
            f"* **Model:** {MODEL_ID}\n"
            f"* **Owner:** {bot.owner_name}\n"
            f"* **Latency:** {latency}ms\n"
            f"* **Uptime:** {get_uptime()}"
        )
        return

    # 2. Main Chat Loop
    async with message.channel.typing():
        try:
            # Prepare the message payload
            messages = [
                {"role": "system", "content": state.get_system_instruction()}
            ]
            
            # Add user message
            messages.append({"role": "user", "content": message.content})

            # Call Bytez API
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=messages,
                temperature=0.7,
                max_tokens=250
            )

            # Extract content
            ai_response = response.choices[0].message.content
            
            if ai_response:
                await message.reply(ai_response, mention_author=False)
            else:
                await message.reply("The model returned an empty response.")

        except Exception as e:
            print(f"Error: {e}")
            await message.reply("I encountered a connection error. Please try again.")

bot.run(DISCORD_TOKEN)
