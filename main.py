import discord
import os
import asyncio
from dotenv import load_dotenv
from openai import OpenAI # Perplexity uses the OpenAI-compatible SDK
from collections import deque

# --- CONFIG ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')

if not DISCORD_TOKEN or not PERPLEXITY_API_KEY:
    print("❌ Missing Tokens")
    exit(1)

# Perplexity uses the OpenAI client structure
client = OpenAI(api_key=PERPLEXITY_API_KEY, base_url="https://api.perplexity.ai")
MODEL_ID = "sonar-pro" 

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

active_channels = {}
message_history = {}
current_topic = {} # Tracks {channel_id: {"topic": str, "user_id": int}}

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
    print(f'✅ Bot Online as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    channel_id = message.channel.id
    clean_text = message.content.strip()
    is_admin = message.author.guild_permissions.administrator

    # --- 1. ADMIN TASK HANDLER ---
    if is_admin and "create" in clean_text.lower() and "channel" in clean_text.lower():
        try:
            name = clean_text.lower().replace("create", "").replace("channel", "").strip().replace(" ", "-")
            new_channel = await message.guild.create_text_channel(name)
            await message.reply(f"✅ Created channel: {new_channel.mention}")
            return
        except Exception as e:
            await message.reply(f"❌ Failed to create channel: {e}")
            return

    # Toggle Auto-reply
    if is_admin and clean_text.lower() in ["!start", "!stop"]:
        active_channels[channel_id] = (clean_text.lower() == "!start")
        await message.reply(f"Auto-reply: **{'ON' if active_channels[channel_id] else 'OFF'}**")
        return

    if not (isinstance(message.channel, discord.DMChannel) or bot.user.mentioned_in(message) or active_channels.get(channel_id, False)):
        return

    # --- 2. TOPIC LOCK LOGIC ---
    # If someone else jumps in while a topic is active
    if channel_id in current_topic:
        topic_data = current_topic[channel_id]
        if message.author.id != topic_data["user_id"]:
            await message.reply(f"I'm currently helping someone else with '{topic_data['topic']}'. Do you want to discuss that, or should we wait?")
            return

    # Update current topic (simplified to the last thing asked)
    current_topic[channel_id] = {"topic": clean_text[:30], "user_id": message.author.id}

    if channel_id not in message_history:
        message_history[channel_id] = deque(maxlen=6)

    async with message.channel.typing():
        try:
            # --- 3. SYSTEM PROMPT (No citations, short responses) ---
            api_messages = [{
                "role": "system", 
                "content": "You are a concise assistant. STRIKE RULES: 1. NEVER use citations like [1] or [2]. 2. Do not provide sources. 3. Keep responses very short and conversational. 4. Do not use bolding for every other word."
            }]
            
            for hist in message_history[channel_id]:
                api_messages.append(hist)
            api_messages.append({"role": "user", "content": clean_text})

            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=api_messages
            )

            answer = response.choices[0].message.content

            # History Management
            message_history[channel_id].append({"role": "user", "content": clean_text})
            message_history[channel_id].append({"role": "assistant", "content": answer})

            for chunk in smart_split_message(answer):
                await message.channel.send(chunk)
                await asyncio.sleep(0.5)

        except Exception as e:
            print(f"Error: {e}")
            await message.reply("⚠️ Service temporarily unavailable.")

bot.run(DISCORD_TOKEN)
