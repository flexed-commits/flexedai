import discord
from bytez import Bytez
import os

# --- CONFIGURATION ---
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
model = sdk.model("anthropic/claude-sonnet-4-5")

# Setup Bot
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'✅ Bot is live as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    async with message.channel.typing():
        try:
            # FIX: Only assign to ONE variable. 
            # Most modern SDKs return the result directly.
            result = model.run([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message.content}
            ])

            # Check if the result itself is an error or a list
            if isinstance(result, list) and len(result) > 0:
                response_text = result[0].get('content', "I couldn't generate a response.")
            else:
                response_text = str(result)

            await message.channel.send(response_text)

        except Exception as e:
            await message.channel.send(f"❌ An error occurred: {e}")

client.run(DISCORD_TOKEN)
