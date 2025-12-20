import discord
import google.generativeai as genai
import os
from dotenv import load_dotenv

# --- CONFIG ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

genai.configure(api_key=GEMINI_API_KEY)

# Use the latest stable model
model = genai.GenerativeModel('gemini-1.5-flash')

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')

@bot.event
async def on_message(message):
    # Don't respond to ourselves or other bots
    if message.author == bot.user or message.author.bot:
        return

    # Trigger: Respond to DMs OR if the bot is @mentioned in a server
    if not isinstance(message.channel, discord.DMChannel) and not bot.user.mentioned_in(message):
        return

    # Remove the bot's mention from the prompt for cleaner input
    clean_content = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
    
    if not clean_content:
        return

    async with message.channel.typing():
        # Context building
        context = f"User: {message.author.display_name}"
        if message.guild:
            context += f" in server '{message.guild.name}'"
        
        prompt = f"Context: {context}\nPrompt: {clean_content}"

        # Modern Safety Settings Format
        safety = {
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE" if isinstance(message.channel, discord.DMChannel) else "BLOCK_ONLY_HIGH",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }

        try:
            response = model.generate_content(prompt, safety_settings=safety)
            
            if response.text:
                # Discord character limit is 2000; split message if needed
                text = response.text
                if len(text) > 2000:
                    for i in range(0, len(text), 2000):
                        await message.channel.send(text[i:i+2000])
                else:
                    await message.channel.send(text)
            else:
                await message.channel.send("The AI returned an empty response (potentially blocked).")
        
        except Exception as e:
            print(f"Error: {e}")
            await message.channel.send(f"⚠️ Error: `{str(e)[:100]}`")

bot.run(DISCORD_TOKEN)
