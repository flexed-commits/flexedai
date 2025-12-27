import discord
from discord.ext import commands
from discord import app_commands
import os
import time
import requests

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
MIMO_API_KEY = os.getenv("MIMO_OPENAI_API_KEY")
MIMO_URL = "https://ai.mimo.org/v1/openai/message"

OWNER = {
    "name": "Ψ.1nOnly.Ψ",
    "id": "1081876265683927080",
}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Slash commands synced for {self.user}")

bot = MyBot()
channel_threads = {}
channel_languages = {}

def get_mimo_response(user_message, thread_id, system_prompt):
    headers = {"api-key": MIMO_API_KEY}
    full_message = f"System Instruction: {system_prompt}\nUser: {user_message}"
    body = {"message": full_message}
    if thread_id:
        body["threadId"] = thread_id

    try:
        response = requests.post(MIMO_URL, headers=headers, json=body, timeout=15)
        response.raise_for_status() # Check for HTTP errors
        return response.json()
    except Exception as e:
        print(f"Mimo Error: {e}")
        return None

# --- COMMANDS ---

@bot.hybrid_command(name="lang", description="Change AI language")
@app_commands.describe(language="Example: Hindi, English, Hinglish")
async def lang(ctx, language: str):
    # Store language in global dict
    channel_languages[ctx.channel.id] = language
    await ctx.reply(f"🌐 Language updated to **{language}** for this channel.")

@bot.command()
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

# --- AI MESSAGE HANDLER ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 1. Process Prefix Commands First
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # 2. Language Logic Fix
    # Pehle saved language check karo, agar nahi hai toh default set karo
    current_lang = channel_languages.get(message.channel.id)
    
    if not current_lang:
        # Default for specific guild
        if message.guild and message.guild.id == 1349281907765936188:
            current_lang = "Hinglish"
        else:
            current_lang = "English"

    respect = ""
    if str(message.author.id) == OWNER['id']:
        respect = f"User is your Boss {OWNER['name']}. Be polite."

    sys_prompt = f"Reply ONLY in {current_lang}. {respect} Keep it very short."

    # 3. API Response handling
    async with message.channel.typing():
        t_id = channel_threads.get(message.channel.id)
        data = get_mimo_response(message.content, t_id, sys_prompt)

        # DEBUG: Print data to console if it fails
        if data and "response" in data:
            channel_threads[message.channel.id] = data.get("threadId")
            await message.reply(data["response"])
        elif data and "message" in data: # Some APIs use 'message' key
             await message.reply(data["message"])
        else:
            print(f"API Response Layout: {data}") # Console check for debugging

if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
