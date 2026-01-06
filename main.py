import discord
from discord.ext import commands
from discord import app_commands
import os
from openai import OpenAI  # Aapka preferred snippet use kiya
from collections import deque
from groq import Groq

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
# Aapka snippet style client setup
client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)
MODEL_NAME = "llama-3.1-8b-instant"

OWNER = {"name": "Ψ.1nOnly.Ψ", "id": "1081876265683927080"}

# --- MEMORY STORAGE ---
channel_memory = {} 
channel_languages = {}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Slash commands synced and ready!")

bot = MyBot()

def get_groq_response(messages_history):
    try:
        # Aapke snippet ka logical application
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages_history,
            temperature=0.7,
            max_tokens=250
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Groq API Error: {e}")
        return None

# --- COMMANDS ---

@bot.hybrid_command(name="lang", description="Change AI Language")
@app_commands.describe(language="Example: Hindi, English, Spanish")
async def lang(ctx, language: str):
    channel_languages[ctx.channel.id] = language
    # Memory clear takki context mix na ho
    if ctx.channel.id in channel_memory:
        channel_memory[ctx.channel.id].clear()
    await ctx.reply(f"🌐 Language updated to **{language}** for this channel.")

# --- AI MESSAGE HANDLER ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Process Commands
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # Language Logic
    current_lang = channel_languages.get(message.channel.id)
    if not current_lang:
        current_lang = "Hinglish" if message.guild and message.guild.id == 1349281907765936188 else "English"

    # Memory Management
    if message.channel.id not in channel_memory:
        channel_memory[message.channel.id] = deque(maxlen=8) # Last 4 pairs of chat

    respect = f"User is your Boss {OWNER['name']}. Be polite." if str(message.author.id) == OWNER['id'] else ""
    
    # System Prompt with Instructions
    sys_prompt = f"Role: Helpful Assistant. Reply ONLY in {current_lang}. {respect} Keep it short."

    # Preparing Messages for Groq
    messages_payload = [{"role": "system", "content": sys_prompt}]
    for m in channel_memory[message.channel.id]:
        messages_payload.append(m)
    messages_payload.append({"role": "user", "content": message.content})

    async with message.channel.typing():
        response_text = get_groq_response(messages_payload)

        if response_text:
            # Update Memory
            channel_memory[message.channel.id].append({"role": "user", "content": message.content})
            channel_memory[message.channel.id].append({"role": "assistant", "content": response_text})
            
            await message.reply(response_text)

if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
