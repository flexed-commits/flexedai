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

SYSTEM_PROMPT = f"You are a helpful assistant. Owner: {OWNER['name']}. If asked for PFP, show {OWNER['pfp']}."

sdk = Bytez(BYTEZ_KEY)
model = sdk.model("anthropic/claude-sonnet-4-5")

intents = discord.Intents.default()
intents.message_content = True 
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'✅ Bot is online as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    async with message.channel.typing():
        try:
            # Get raw result from Bytez
            result = model.run([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message.content}
            ])

            # DEBUG: This will show you the exact format in Termux
            print(f"RAW DATA FROM BYTEZ: {result}")

            final_text = ""

            # 1. Handle (output, error) tuple
            if isinstance(result, tuple):
                output, error = result
                if error:
                    final_text = f"❌ API Error: {error}"
                else:
                    result_to_parse = output
            else:
                result_to_parse = result

            # 2. Extract text from list/dict/string
            if not final_text:
                if isinstance(result_to_parse, list) and len(result_to_parse) > 0:
                    item = result_to_parse[0]
                    final_text = item.get('content', str(item)) if isinstance(item, dict) else str(item)
                elif isinstance(result_to_parse, dict):
                    final_text = result_to_parse.get('output', result_to_parse.get('content', str(result_to_parse)))
                else:
                    final_text = str(result_to_parse)

            # 3. Send the message
            if final_text:
                await message.channel.send(final_text)
            else:
                await message.channel.send("⚠️ Received empty response from AI.")

        except Exception as e:
            print(f"CRASH ERROR: {e}")
            await message.channel.send(f"⚠️ Bot encountered a code error: {e}")

client.run(DISCORD_TOKEN)
