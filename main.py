import discord
import google.generativeai as genai

# --- CONFIG ---
DISCORD_TOKEN = 'YOUR_DISCORD_BOT_TOKEN'
GEMINI_API_KEY = 'YOUR_GEMINI_API_KEY'

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') # Termux-friendly version

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

@bot.event
async def on_message(message):
    if message.author == bot.user: return

    is_dm = isinstance(message.channel, discord.DMChannel)
    
    # Server context
    context = ""
    if message.guild:
        context = f"Server: {message.guild.name}. Channels: {[c.name for c in message.guild.text_channels]}"

    prompt = f"{context}\nNSFW Allowed: {is_dm}\nUser: {message.content}"
    
    # Simple Safety Settings
    safety = [
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE" if is_dm else "BLOCK_MEDIUM_AND_ABOVE"}
    ]

    response = model.generate_content(prompt, safety_settings=safety)
    await message.channel.send(response.text)

bot.run(DISCORD_TOKEN)
