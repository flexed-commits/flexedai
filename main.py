import discord
from bytez import Bytez
import os

# --- CONFIGURATION ---
# In Termux, you can set this by typing: export DISCORD_TOKEN='your_token_here'
# Or just replace os.getenv with your string like: DISCORD_TOKEN = 'your_actual_token'
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
BYTEZ_KEY = '61139c556078e162dbada319d9a5b925'

# Owner Data
OWNER = {
    "name": "Ψ.1nOnly.Ψ",
    "username": ".flexed.",
    "id": "1081876265683927080",
    "pfp": "https://cdn.discordapp.com/avatars/1081876265683927080/a2671291fa7a3f13e03022eeeac15ef2.webp?size=2048",
    "link": "https://discord.com/users/1081876265683927080"
}

SYSTEM_PROMPT = f"""
You are a helpful AI assistant. Your creator/owner is {OWNER['name']}.
If a user asks about your owner, follow these rules:
1. If they ask for "everything" or general info, tell them his name, username, and ID.
2. If they specifically ask for his "PFP" or "profile picture", provide: {OWNER['pfp']}
3. If they ask for his "ID", provide: {OWNER['id']}
4. If they ask for his "link" or "profile", provide: {OWNER['link']}
5. Always be respectful to {OWNER['name']}.
"""

# Initialize Bytez
sdk = Bytez(BYTEZ_KEY)
model = sdk.model("anthropic/claude-3-5-sonnet")

# Setup Bot
intents = discord.Intents.default()
intents.message_content = True  # CRITICAL: Must be enabled in Discord Dev Portal
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'✅ Bot is live as {client.user}')

@client.event
async def on_message(message):
    # 1. Ignore messages from the bot itself to prevent infinite loops
    if message.author == client.user:
        return

    # 2. Respond to EVERY message (No pings or "bot" prefix required)
    async with message.channel.typing():
        # Clean the content (in case there are pings to remove)
        clean_content = message.content.strip()
        
        # If the message is empty (like just an image), don't trigger the AI
        if not clean_content:
            return

        output, error = model.run([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": clean_content}
        ])

        if error:
            await message.channel.send(f"❌ API Error: {error}")
        else:
            # Handle Bytez output format
            response = output[0]['content'] if isinstance(output, list) else output
            await message.channel.send(response)

client.run(DISCORD_TOKEN)
