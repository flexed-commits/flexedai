import discord
import google.generativeai as genai
import os
from dotenv import load_dotenv

# --- CONFIG ---
load_dotenv()  # This loads the variables from the .env file
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user: return

    is_dm = isinstance(message.channel, discord.DMChannel)
    
    # Context building
    context = ""
    if message.guild:
        context = f"Server: {message.guild.name}."

    prompt = f"{context}\nUser: {message.content}"
    
    # Safety Settings
    safety = [
        {
            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", 
            "threshold": "BLOCK_NONE" if is_dm else "BLOCK_MEDIUM_AND_ABOVE"
        }
    ]

    try:
        response = model.generate_content(prompt, safety_settings=safety)
        if response.text:
            await message.channel.send(response.text)
    except Exception as e:
        print(f"Error: {e}")
        await message.channel.send("I encountered an error processing that.")

bot.run(DISCORD_TOKEN)
