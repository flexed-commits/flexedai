import discord
import os
import asyncio
from dotenv import load_dotenv
from perplexity import Perplexity  # New Import
from collections import deque

# --- CONFIG ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY') # Updated key name

# Validate environment variables
if not DISCORD_TOKEN or not PERPLEXITY_API_KEY:
    print("❌ Missing DISCORD_TOKEN or PERPLEXITY_API_KEY in .env file")
    exit(1)

# Initialize Perplexity Client
try:
    # Ensure PERPLEXITY_API_KEY is set in your environment
    client = Perplexity(api_key=PERPLEXITY_API_KEY)
except Exception as e:
    print(f"❌ Failed to initialize Perplexity client: {e}")
    exit(1)

# Recommended Perplexity model for chat/search
MODEL_ID = "sonar-pro" 

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

active_channels = {}
message_history = {}

def smart_split_message(text, max_length=2000):
    """Splits text into Discord-friendly chunks."""
    if len(text) <= max_length: return [text]
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining); break
        split_point = max_length
        for sep in ['\n\n', '\n', '. ', ' ']:
            last_idx = remaining[:max_length].rfind(sep)
            if last_idx > max_length * 0.3:
                split_point = last_idx + len(sep)
                break
        chunks.append(remaining[:split_point].rstrip())
        remaining = remaining[split_point:].lstrip()
    return chunks

@bot.event
async def on_ready():
    print(f'✅ Connected: {bot.user}')
    print(f'🌐 Using Perplexity Model: {MODEL_ID}')

@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    bot_mentioned = bot.user.mentioned_in(message)
    channel_id = message.channel.id
    clean_text = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()

    # Toggle Commands
    if not is_dm and bot_mentioned and clean_text.lower() in ["start", "stop"]:
        if message.author.guild_permissions.administrator:
            active_channels[channel_id] = (clean_text.lower() == "start")
            await message.reply(f"System: Auto-reply is now **{'ENABLED' if active_channels[channel_id] else 'DISABLED'}**.")
            return

    if not (is_dm or bot_mentioned or active_channels.get(channel_id, False)):
        return

    if channel_id not in message_history:
        message_history[channel_id] = deque(maxlen=10)

    async with message.channel.typing():
        try:
            # Prepare messages for Chat Completion
            api_messages = [{"role": "system", "content": f"You are a helpful AI assistant. Model: {MODEL_ID}"}]
            for hist in message_history[channel_id]:
                api_messages.append(hist)
            api_messages.append({"role": "user", "content": clean_text})

            # --- PERPLEXITY API CALL ---
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=api_messages
            )
            
            answer = response.choices[0].message.content

            # History Management
            message_history[channel_id].append({"role": "user", "content": clean_text})
            message_history[channel_id].append({"role": "assistant", "content": answer})

            # Send split reply
            chunks = smart_split_message(answer)
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await message.reply(chunk, mention_author=False)
                else:
                    await message.channel.send(chunk)
                await asyncio.sleep(0.5)

        except Exception as e:
            print(f"Perplexity Error: {e}")
            await message.reply(f"⚠️ Error: {str(e)[:100]}")

bot.run(DISCORD_TOKEN)
