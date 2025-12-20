import discord
import os
from dotenv import load_dotenv
from google import genai 
from google.genai import types

# --- CONFIG ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_ID = "gemini-1.5-flash"

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# Global toggle to track if the bot is "active"
is_active = False

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')

@bot.event
async def on_message(message):
    global is_active

    # 1. Ignore own messages or other bots
    if message.author == bot.user or message.author.bot:
        return

    # 2. Check for Pings (Mentions)
    bot_mentioned = bot.user.mentioned_in(message)
    
    # If the bot isn't mentioned and it's not a DM, ignore everything
    if not bot_mentioned and not isinstance(message.channel, discord.DMChannel):
        return

    # Clean the input text
    clean_content = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip().lower()

    # 3. ADMIN TOGGLE LOGIC
    # Only users with 'administrator' permission can start/stop the bot
    if bot_mentioned and ("start" in clean_content or "stop" in clean_content):
        if message.author.guild_permissions.administrator:
            if "start" in clean_content:
                is_active = True
                await message.channel.send("🚀 **Bot activated.** I will now respond to pings.")
            else:
                is_active = False
                await message.channel.send("💤 **Bot deactivated.** Use `start` to re-enable.")
            return
        else:
            await message.channel.send("❌ You need **Administrator** permissions to use that command.")
            return

    # 4. ACTIVE STATE CHECK
    # If the bot is off and it's not a DM, stay silent
    if not is_active and not isinstance(message.channel, discord.DMChannel):
        return

    # 5. GENERATE RESPONSE
    if not clean_content:
        return

    async with message.channel.typing():
        safety_config = [
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            types.SafetySetting(
                category="HARM_CATEGORY_SEXUALLY_EXPLICIT", 
                threshold="BLOCK_NONE" if isinstance(message.channel, discord.DMChannel) else "BLOCK_ONLY_HIGH"
            ),
        ]

        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=f"User {message.author.display_name} says: {clean_content}",
                config=types.GenerateContentConfig(safety_settings=safety_config)
            )
            
            if response.text:
                text = response.text
                if len(text) > 2000:
                    for i in range(0, len(text), 2000):
                        await message.channel.send(text[i:i+2000])
                else:
                    await message.channel.send(text)
        
        except Exception as e:
            print(f"Error: {e}")
            await message.channel.send(f"⚠️ Error occurred during generation.")

bot.run(DISCORD_TOKEN)
