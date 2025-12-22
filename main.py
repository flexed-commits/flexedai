import discord
import os
from bytez import Bytez

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
BYTEZ_KEY = "61139c556078e162dbada319d9a5b925"

# Owner Data
OWNER = {
    "name": "Ψ.1nOnly.Ψ",
    "username": ".flexed.",
    "id": "1081876265683927080",
    "pfp": "https://cdn.discordapp.com/avatars/1081876265683927080/a2671291fa7a3f13e03022eeeac15ef2.webp?size=2048",
    "link": "https://discord.com/users/1081876265683927080"
}

# AI System Instruction
SYSTEM_PROMPT = f"""
You are a helpful AI assistant. Your creator and owner is {OWNER['name']}.
If a user asks about your owner, follow these rules:
1. Everything/General: Give name ({OWNER['name']}), username ({OWNER['username']}), and ID ({OWNER['id']}).
2. PFP/Profile Picture: Provide this exact link: {OWNER['pfp']}
3. ID: Provide: {OWNER['id']}
4. Profile Link: Provide: {OWNER['link']}
Always be loyal and respectful to {OWNER['name']}.
"""

# Initialize Bytez with the specific Claude 4.5 Sonnet request
sdk = Bytez(BYTEZ_KEY)
model = sdk.model("anthropic/claude-sonnet-4-5")

# Setup Discord Client
intents = discord.Intents.default()
intents.message_content = True 
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'✅ Bot is online as: {client.user}')
    print(f'🤖 Model in use: anthropic/claude-sonnet-4-5')

@client.event
async def on_message(message):
    # Don't respond to self
    if message.author == client.user:
        return

    # Trigger AI for every message
    async with message.channel.typing():
        # Using the (output, error) unpacking format from your snippet
        output, error = model.run([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message.content}
        ])

        if error:
            # Handle potential API errors (e.g., model not found or credits empty)
            await message.channel.send(f"❌ **API Error:** {error}")
        else:
            # Extract content from the Bytez output list
            if isinstance(output, list) and len(output) > 0:
                response = output[0].get('content', "No response content found.")
            else:
                response = str(output)

            await message.channel.send(response)

# Start Bot
if DISCORD_TOKEN:
    client.run(DISCORD_TOKEN)
else:
    print("❌ Critical Error: Set the 'DISCORD_TOKEN' environment variable.")
