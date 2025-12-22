import discord
import os
from bytez import Bytez

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
BYTEZ_KEY = "61139c556078e162dbada319d9a5b925"

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
1. General/Everything: Provide name, username, and ID.
2. PFP/Profile Picture: Provide this link: {OWNER['pfp']}
3. ID: Provide: {OWNER['id']}
4. Link/Profile: Provide: {OWNER['link']}
Always be respectful to {OWNER['name']}.
"""

sdk = Bytez(BYTEZ_KEY)
model = sdk.model("anthropic/claude-sonnet-4-5")

intents = discord.Intents.default()
intents.message_content = True 
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'✅ Bot Online: {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    async with message.channel.typing():
        # --- ROBUST UNPACKING FIX ---
        result = model.run([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message.content}
        ])

        # If the SDK returns (output, error), result will be a tuple
        if isinstance(result, tuple) and len(result) == 2:
            output, error = result
        else:
            # If it returns just one thing, we treat it as output and no error
            output = result
            error = None

        if error:
            await message.channel.send(f"❌ **API Error:** {error}")
        else:
            # Standard Bytez list extraction
            if isinstance(output, list) and len(output) > 0:
                response = output[0].get('content', "No content")
            elif isinstance(output, dict):
                response = output.get('output', str(output))
            else:
                response = str(output)

            await message.channel.send(response)

if DISCORD_TOKEN:
    client.run(DISCORD_TOKEN)
else:
    print("❌ ERROR: Set DISCORD_TOKEN environment variable.")
