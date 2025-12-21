import discord
import os
import asyncio
from dotenv import load_dotenv
from openai import OpenAI  # Perplexity's official Python integration method
from collections import deque
import time

# --- CONFIG ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')

if not DISCORD_TOKEN or not PERPLEXITY_API_KEY:
    print("❌ Missing Tokens in .env")
    exit(1)

# Initialize Perplexity Client via OpenAI SDK
client = OpenAI(api_key=PERPLEXITY_API_KEY, base_url="https://api.perplexity.ai")
MODEL_ID = "sonar-pro" 

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

active_channels = {}
message_history = {}
current_topic = {} # {channel_id: {"topic": str, "user_id": int, "timestamp": float}}

def smart_split_message(text, max_length=2000):
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
    print(f'✅ Perplexity Bot Online: {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    channel_id = message.channel.id
    clean_text = message.content.strip()
    is_admin = message.author.guild_permissions.administrator

    # --- 1. ADMIN TASK: CREATE CHANNEL ---
    if is_admin and "create" in clean_text.lower() and "channel" in clean_text.lower():
        try:
            # Extract name: "create staff channel" -> "staff"
            name = clean_text.lower().replace("create", "").replace("channel", "").strip().replace(" ", "-")
            if name:
                new_chan = await message.guild.create_text_channel(name)
                await message.reply(f"Done. Created {new_chan.mention}")
                return
        except Exception as e:
            await message.reply(f"Couldn't do it: {e}")
            return

    # Toggle Auto-reply
    if is_admin and clean_text.lower() in ["!start", "!stop"]:
        active_channels[channel_id] = (clean_text.lower() == "!start")
        await message.reply(f"Auto-reply is **{'ON' if active_channels[channel_id] else 'OFF'}**.")
        return

    # Check if bot should respond
    if not (isinstance(message.channel, discord.DMChannel) or bot.user.mentioned_in(message) or active_channels.get(channel_id, False)):
        return

    # --- 2. TOPIC LOCK LOGIC ---
    now = time.time()
    if channel_id in current_topic:
        topic_data = current_topic[channel_id]
        # If a different user talks within 2 minutes of the last topic message
        if message.author.id != topic_data["user_id"] and (now - topic_data["timestamp"]) < 120:
            await message.reply(f"I'm currently mid-chat with someone else about '{topic_data['topic']}'. Want to keep talking about that or wait a sec?")
            return

    # Set/Update topic
    current_topic[channel_id] = {
        "topic": clean_text[:30], 
        "user_id": message.author.id,
        "timestamp": now
    }

    if channel_id not in message_history:
        message_history[channel_id] = deque(maxlen=5)

    async with message.channel.typing():
        try:
            # --- 3. SYSTEM PROMPT (No citations, short responses) ---
            # Added "Directly answer" and "No brackets" for Perplexity
            api_messages = [{
                "role": "system", 
                "content": (
                    "You are a helpful, very brief assistant. "
                    "CRITICAL: Never use citations, footnotes, or bracketed numbers like [1] or [2]. "
                    "Keep your responses short (1-3 sentences max). "
                    "Be conversational and avoid long explanations."
                )
            }]

            for hist in message_history[channel_id]:
                api_messages.append(hist)
            api_messages.append({"role": "user", "content": clean_text})

            # Perplexity API Call
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=api_messages
            )

            answer = response.choices[0].message.content

            # Save history
            message_history[channel_id].append({"role": "user", "content": clean_text})
            message_history[channel_id].append({"role": "assistant", "content": answer})

            # Send result
            for chunk in smart_split_message(answer):
                await message.channel.send(chunk)
                await asyncio.sleep(0.5)

        except Exception as e:
            print(f"Perplexity Error: {e}")
            await message.reply("My bad, Perplexity is acting up.")

bot.run(DISCORD_TOKEN)
