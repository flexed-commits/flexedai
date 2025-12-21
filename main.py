import discord
import os
import asyncio
import re
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
intents.guilds = True
intents.members = True 
bot = discord.Client(intents=intents)

# Context Trackers
channel_topics = {} 
message_history = {}

def clean_citations(text):
    """Aggressively removes [1], [2], [n] and markdown links to sources."""
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\(http[s]?://\S+\)', '', text)
    return text.strip()

async def handle_admin_tasks(message, clean_text):
    """
    Checks if an admin is asking for a guild action.
    Returns True if a task was handled, False otherwise.
    """
    if not message.author.guild_permissions.administrator:
        return False

    cmd = clean_text.lower()
    
    # Logic for: "Create a channel named X"
    if "create" in cmd and "channel" in cmd:
        name = cmd.split("channel")[-1].strip().replace(" ", "-") or "new-chat"
        new_chan = await message.guild.create_text_channel(name=name)
        await message.reply(f"✅ Created channel: {new_chan.mention}")
        return True

    # Logic for: "Delete this channel"
    if "delete" in cmd and "this channel" in cmd:
        await message.reply("🗑️ Deleting channel in 3 seconds...")
        await asyncio.sleep(3)
        await message.channel.delete()
        return True

    return False

@bot.event
async def on_ready():
    print(f'✅ Admin-Ready Bot: {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    channel_id = message.channel.id
    user_id = message.author.id
    clean_text = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()

    # --- 1. TRY ADMIN TASKS FIRST ---
    was_admin_task = await handle_admin_tasks(message, clean_text)
    if was_admin_task:
        return

    # --- 2. TOPIC ISOLATION ---
    if channel_id in channel_topics:
        active = channel_topics[channel_id]
        if active['user_id'] != user_id:
            # If a new user joins, prompt them about the current topic
            await message.reply(f"I'm currently mid-topic with **{active['user_name']}** about *'{active['topic']}'*. Did you want to ask about that, or should we switch gears?")
            # We don't return here so they can still get a response, 
            # but we update the topic to the new person now.

    # Update global topic for this channel
    channel_topics[channel_id] = {
        'user_id': user_id,
        'user_name': message.author.display_name,
        'topic': clean_text[:40]
    }

    # --- 3. PERPLEXITY API CALL ---
    async with message.channel.typing():
        try:
            hist_key = (channel_id, user_id)
            if hist_key not in message_history:
                message_history[hist_key] = deque(maxlen=6)

            # Strict System Prompt
            sys_msg = (
                "You are a short, conversational assistant. "
                "CRITICAL: Never use citations like [1] or [2]. "
                "Keep responses under 2-3 sentences. No fluff."
            )
            
            api_messages = [{"role": "system", "content": sys_msg}]
            for h in message_history[hist_key]:
                api_messages.append(h)
            api_messages.append({"role": "user", "content": clean_text})

            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=api_messages
            )

            answer = clean_citations(response.choices[0].message.content)

            # Save history (User -> Assistant)
            message_history[hist_key].append({"role": "user", "content": clean_text})
            message_history[hist_key].append({"role": "assistant", "content": answer})

            await message.reply(answer, mention_author=False)

        except Exception as e:
            print(f"API Error: {e}")
            # If history gets messy, clear it to prevent 400 errors
            message_history[hist_key] = deque(maxlen=6)
            await message.reply("⚠️ Just a hiccup. Ask me again?")

bot.run(DISCORD_TOKEN)
