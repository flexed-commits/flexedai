import discord
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
BYTEZ_KEY = os.getenv('BYTEZ_KEY')

# Initialize Bytez Client
client = OpenAI(
    api_key=BYTEZ_KEY,
    base_url="https://api.bytez.com/models/v2/openai/v1"
)
MODEL_ID = "Qwen/Qwen3-4B"
START_TIME = datetime.utcnow()

# Owner Details
OWNER_INFO = {
    "name": "Ψ.1nOnly.Ψ",
    "id": 1081876265683927080,
    "handle": ".flexed.",
    "pfp": "https://cdn.discordapp.com/avatars/1081876265683927080/a2671291fa7a3f13e03022eeeac15ef2.webp?size=2048"
}

class ThoughtPartner:
    def __init__(self, user_name):
        self.user_name = user_name
        self.history = [] # Stores last 10 messages

    def get_system_instruction(self):
        return (
            f"You are Gemini, a helpful AI thought partner for {self.user_name}. "
            f"Your Owner is {OWNER_INFO['name']} (@{OWNER_INFO['handle']}). "
            "Traits: Empathetic, concise, and a Grandmaster-level Chess Expert (2800 IQ). "
            "Safety: STRICT NO SLURS/SWEARING. Polite and respectful always. "
            "Style: Maximum Info-to-Word ratio. No fluff. No citations."
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
    print(f'✨ {bot.user} is online | Serving {OWNER_INFO["name"]}')

@bot.event
async def on_message(message):
    if message.author.bot: return

    uid = message.author.id
    if uid not in user_states:
        user_states[uid] = ThoughtPartner(message.author.display_name)

    state = user_states[uid]
    clean_msg = message.content.lower().strip()

    # 1. System Stats Command
    if clean_msg in ["/status", "who is your owner?", "ping"]:
        embed = discord.Embed(title="System Status", color=0x2b2d31)
        embed.set_author(name=OWNER_INFO["name"], icon_url=OWNER_INFO["pfp"])
        embed.add_field(name="🚀 Model", value=MODEL_ID, inline=True)
        embed.add_field(name="📡 Latency", value=f"{round(bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="⏳ Uptime", value=get_uptime(), inline=True)
        embed.add_field(name="♟️ Chess IQ", value="2800 (GM)", inline=True)
        await message.reply(embed=embed)
        return

    # 2. Main Chat Loop
    async with message.channel.typing():
        try:
            # Build payload with history
            messages = [{"role": "system", "content": state.get_system_instruction()}]
            
            # Add recent history (last 10 turns)
            messages.extend(state.history[-10:])
            
            # Add current message
            messages.append({"role": "user", "content": message.content})

            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=messages,
                temperature=0.7,
                max_tokens=250
            )

            ai_text = response.choices[0].message.content
            
            # Update history
            state.history.append({"role": "user", "content": message.content})
            state.history.append({"role": "assistant", "content": ai_text})

            await message.reply(ai_text, mention_author=False)

        except Exception as e:
            print(f"Error: {e}")
            await message.reply("`Error: API Connection Failed. Check console.`")

bot.run(DISCORD_TOKEN)
