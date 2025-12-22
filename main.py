import discord
from bytez import Bytez

# --- CONFIGURATION ---
DISCORD_TOKEN = 'YOUR_DISCORD_BOT_TOKEN_HERE'
BYTEZ_KEY = '61139c556078e162dbada319d9a5b925'

# Owner Data
OWNER = {
    "name": "Ψ.1nOnly.Ψ",
    "username": ".flexed.",
    "id": "1081876265683927080",
    "pfp": "https://cdn.discordapp.com/avatars/1081876265683927080/a2671291fa7a3f13e03022eeeac15ef2.webp?size=2048",
    "link": "https://discord.com/users/1081876265683927080"
}

# System Instructions for the AI
SYSTEM_PROMPT = f"""
You are a helpful AI assistant. Your creator/owner is {OWNER['name']}.
If a user asks about your owner, follow these rules:
1. If they ask for "everything" or general info, tell them his name ({OWNER['name']}), username ({OWNER['username']}), and ID.
2. If they specifically ask for his "PFP" or "profile picture", provide this link: {OWNER['pfp']}
3. If they ask for his "ID", provide: {OWNER['id']}
4. If they ask for his "link" or "profile", provide: {OWNER['link']}
5. Always be respectful to {OWNER['name']}.
"""

# Initialize Bytez
sdk = Bytez(BYTEZ_KEY)
model = sdk.model("anthropic/claude-3-5-sonnet")

# Setup Bot
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'Bot is live as {client.user}')

@client.event
async def on_message(message):
    # Don't let the bot reply to itself
    if message.author == client.user:
        return

    # The bot will respond to any message that mentions it or starts with "bot"
    if client.user.mentioned_in(message) or message.content.lower().startswith("bot"):
        async with message.channel.typing():
            clean_content = message.content.replace(f'<@!{client.user.id}>', '').strip()
            
            output, error = model.run([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": clean_content}
            ])

            if error:
                await message.channel.send(f"Error: {error}")
            else:
                # Handle list or string output from Bytez
                response = output[0]['content'] if isinstance(output, list) else output
                await message.channel.send(response)

client.run(DISCORD_TOKEN)
