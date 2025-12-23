import discord
import os
from openai import OpenAI

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
# Use Groq API Key from environment or paste it here
GROQ_API_KEY = os.getenv('GROQ_API_KEY') or "gsk_your_key_here"

client_ai = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

OWNER = {
    "name": "Ψ.1nOnly.Ψ",
    "username": ".flexed.",
    "id": "1081876265683927080",
    "pfp": "https://cdn.discordapp.com/avatars/1081876265683927080/a2671291fa7a3f13e03022eeeac15ef2.webp?size=2048",
    "link": "https://discord.com/users/1081876265683927080"
}

SYSTEM_PROMPT = f"You are a helpful assistant. Owner: {OWNER['name']}. If asked for PFP, show {OWNER['pfp']}."

# --- DISCORD SETUP ---
intents = discord.Intents.default()
intents.message_content = True 
discord_client = discord.Client(intents=intents)

@discord_client.event
async def on_ready():
    print(f'✅ Bot is online as {discord_client.user}')

@discord_client.event
async def on_message(message):
    if message.author == discord_client.user:
        return

    # Optional: Only respond to mentions or specific prefixes
    # if not discord_client.user.mentioned_in(message): return

    async with message.channel.typing():
        try:
            # Using Groq's Chat Completion
            chat_completion = client_ai.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": message.content}
                ],
                model="llama3-8b-8192", # Or "llama3-70b-8192" / "mixtral-8x7b-32768"
            )

            # Extract the text
            final_text = chat_completion.choices[0].message.content

            # Discord has a 2000 character limit per message
            if len(final_text) > 2000:
                for i in range(0, len(final_text), 2000):
                    await message.channel.send(final_text[i:i+2000])
            else:
                await message.channel.send(final_text)

        except Exception as e:
            print(f"CRASH ERROR: {e}")
            await message.channel.send(f"⚠️ Bot encountered an error: {e}")

discord_client.run(DISCORD_TOKEN)
