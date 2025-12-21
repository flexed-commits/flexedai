import discord
import os
from dotenv import load_dotenv
from google import genai 
from google.genai import types

# --- CONFIG ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Initialize the new SDK Client
client = genai.Client(api_key=GEMINI_API_KEY)

# UPDATED: Using the Gemini 2.0 Flash Model ID
MODEL_ID = "gemini-2.0-flash" 

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# Global toggle: Bot starts "OFF" by default
is_active = False

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    print(f'🚀 Model active: {MODEL_ID}')

@bot.event
async def on_message(message):
    global is_active

    # 1. Standard safety checks
    if message.author == bot.user or message.author.bot:
        return

    # Check if the bot was pinged
    bot_mentioned = bot.user.mentioned_in(message)
    
    # Clean the input
    clean_content = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
    command_check = clean_content.lower()

    # 2. ADMIN COMMANDS
    if bot_mentioned and command_check in ["start", "stop"]:
        if message.author.guild_permissions.administrator:
            if command_check == "start":
                is_active = True
                await message.channel.send(f"🟢 **{MODEL_ID} is now ONLINE.**")
            else:
                is_active = False
                await message.channel.send(f"🔴 **{MODEL_ID} is now OFFLINE.**")
            return
        else:
            await message.channel.send("❌ Administrator permissions required.")
            return

    # 3. GLOBAL SILENCE LOGIC
    is_dm = isinstance(message.channel, discord.DMChannel)
    if not is_dm:
        if not is_active or not bot_mentioned:
            return

    # 4. AI GENERATION
    if not clean_content:
        return

    async with message.channel.typing():
        # Updated Safety Categories for Gemini 2.0
        safety_config = [
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        ]

        try:
            # Generate content using the SDK
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=clean_content,
                config=types.GenerateContentConfig(safety_settings=safety_config)
            )
            
            if response.text:
                text = response.text
                # Discord character limit handler
                if len(text) > 2000:
                    for i in range(0, len(text), 2000):
                        await message.channel.send(text[i:i+2000])
                else:
                    await message.channel.send(text)
            else:
                await message.channel.send("⚠️ No text generated.")
        
        except Exception as e:
            print(f"Error: {e}")
            await message.channel.send(f"⚠️ Error: {str(e)}")

bot.run(DISCORD_TOKEN)
