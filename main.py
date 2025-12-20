import discord
import os
from dotenv import load_dotenv
from google import genai 
from google.genai import types

# --- CONFIG ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Initialize client for google-genai SDK
client = genai.Client(api_key=GEMINI_API_KEY)

# Using Gemini 2.0 Flash Version
MODEL_ID = "gemini-2.0-flash" 

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# Global status: Bot starts as "stopped"
is_active = False

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    print(f'✨ Model: {MODEL_ID}')

@bot.event
async def on_message(message):
    global is_active

    # 1. Ignore bots and own messages
    if message.author == bot.user or message.author.bot:
        return

    # 2. Identify if the bot was mentioned
    bot_mentioned = bot.user.mentioned_in(message)
    
    # Clean the input text for logic checks
    # Removes the <@ID> pings from the string
    clean_content = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
    command_check = clean_content.lower()

    # 3. Handle Admin Activation/Deactivation
    if bot_mentioned and command_check in ["start", "stop"]:
        if message.author.guild_permissions.administrator:
            if command_check == "start":
                is_active = True
                await message.channel.send("⚡ **Gemini 2.0 Flash is now ONLINE.** I will respond to mentions.")
            else:
                is_active = False
                await message.channel.send("💤 **Gemini 2.0 Flash is now OFFLINE.**")
            return
        else:
            # If a non-admin pings start/stop, send one warning then stop
            await message.channel.send("❌ Only an **Administrator** can start/stop this bot.")
            return

    # 4. Filter: Only proceed if active AND pinged
    # (Allowing DMs to work regardless for testing/private use)
    is_dm = isinstance(message.channel, discord.DMChannel)
    
    if not is_dm:
        if not is_active: 
            return # Bot is globally "stopped"
        if not bot_mentioned:
            return # Bot is "started" but this specific message didn't ping it

    # 5. Process AI Response
    if not clean_content:
        return

    async with message.channel.typing():
        # Safety configuration
        safety_config = [
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            types.SafetySetting(
                category="HARM_CATEGORY_SEXUALLY_EXPLICIT", 
                threshold="BLOCK_NONE" if is_dm else "BLOCK_ONLY_HIGH"
            ),
        ]

        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=f"User {message.author.display_name}: {clean_content}",
                config=types.GenerateContentConfig(safety_settings=safety_config)
            )
            
            if response.text:
                text = response.text
                # Discord 2000 character limit split
                if len(text) > 2000:
                    for i in range(0, len(text), 2000):
                        await message.channel.send(text[i:i+2000])
                else:
                    await message.channel.send(text)
        
        except Exception as e:
            print(f"Error: {e}")
            await message.channel.send("⚠️ Failed to reach Gemini 2.0.")

bot.run(DISCORD_TOKEN)
