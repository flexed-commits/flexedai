import discord
import os
import asyncio
import re
from discord.ext import commands
from dotenv import load_dotenv
from perplexity import Perplexity
from collections import deque

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')

client = Perplexity(api_key=PERPLEXITY_API_KEY)
MODEL_ID = "sonar-pro"

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# Using a dictionary to track the "active" topic per channel
channel_topics = {} 
# (channel_id, user_id) history
message_history = {}

def clean_citations(text):
    """Removes [1], [2], etc. from the response."""
    return re.sub(r'\[\d+\]', '', text).strip()

@bot.event
async def on_ready():
    print(f'✅ Connected as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    channel_id = message.channel.id
    user_id = message.author.id
    clean_text = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()

    # --- 1. ADMIN TASK: CREATE CHANNEL ---
    if clean_text.lower().startswith("create channel"):
        if message.author.guild_permissions.manage_channels:
            try:
                name = clean_text.replace("create channel", "").strip() or "new-channel"
                new_chan = await message.guild.create_text_channel(name=name)
                response_text = f"✅ Created channel: {new_chan.mention}"
                await message.reply(response_text)
                
                # Update history to prevent 400 error (User -> Assistant flow)
                hist_key = (channel_id, user_id)
                if hist_key not in message_history: message_history[hist_key] = deque(maxlen=6)
                message_history[hist_key].append({"role": "user", "content": clean_text})
                message_history[hist_key].append({"role": "assistant", "content": response_text})
                return
            except Exception as e:
                await message.reply(f"❌ Failed: {e}")
                return
        else:
            await message.reply("❌ Admin perms required.")
            return

    # --- 2. TOPIC ISOLATION LOGIC ---
    # Check if someone else is already talking about something in this channel
    current_topic = channel_topics.get(channel_id)
    
    # If there's an active topic and a NEW user hops in
    if current_topic and current_topic['user_id'] != user_id:
        await message.reply(f"I'm currently helping {current_topic['user_name']} with '{current_topic['topic']}'. Do you want to join that or start something new?")
        # Logic ends here to prevent mixing histories unless they confirm
        return

    # Update the "Global" channel topic focus
    channel_topics[channel_id] = {
        'user_id': user_id,
        'user_name': message.author.display_name,
        'topic': clean_text[:30] # Simple snippet of the text as the topic
    }

    # --- 3. PERPLEXITY API CALL ---
    async with message.channel.typing():
        try:
            hist_key = (channel_id, user_id)
            if hist_key not in message_history:
                message_history[hist_key] = deque(maxlen=6)

            # System prompt to force brevity and no citations
            sys_msg = "You are a concise assistant. No citations [n]. No sources. Short answers only."
            
            api_messages = [{"role": "system", "content": sys_msg}]
            for h in message_history[hist_key]:
                api_messages.append(h)
            api_messages.append({"role": "user", "content": clean_text})

            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=api_messages
            )

            answer = clean_citations(response.choices[0].message.content)

            # Store history
            message_history[hist_key].append({"role": "user", "content": clean_text})
            message_history[hist_key].append({"role": "assistant", "content": answer})

            await message.reply(answer, mention_author=False)

        except Exception as e:
            print(f"Error: {e}")
            await message.reply("⚠️ Conversation error. History cleared.")
            message_history[hist_key] = deque(maxlen=6)

bot.run(DISCORD_TOKEN)
