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

channel_topics = {} 
message_history = {}

def clean_citations(text):
    """Removes [1], [2], etc. and markdown links."""
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\(http[s]?://\S+\)', '', text)
    return text.strip()

async def handle_public_tasks(message, clean_text):
    """Logic for server info and management available to EVERYONE."""
    cmd = clean_text.lower()
    guild = message.guild

    # --- SERVER INFO ---
    if "server info" in cmd:
        info = (
            f"**Server:** {guild.name}\n"
            f"**Owner:** {guild.owner}\n"
            f"**Members:** {guild.member_count}\n"
            f"**Boosts:** {guild.premium_subscription_count}"
        )
        await message.reply(info)
        return True

    # --- LIST CHANNELS ---
    if "list" in cmd and "channels" in cmd:
        channels = [f"#{c.name}" for c in guild.text_channels]
        # Discord has a 2000 char limit, so we join carefully
        response = f"**Channels:** {', '.join(channels)}"
        if len(response) > 1950: response = response[:1950] + "..."
        await message.reply(response)
        return True

    # --- USER INFO ---
    if "user info" in cmd or "who is" in cmd:
        target = message.mentions[0] if message.mentions else message.author
        info = (
            f"**User:** {target.display_name}\n"
            f"**ID:** {target.id}\n"
            f"**Joined:** {target.joined_at.strftime('%Y-%m-%d') if target.joined_at else 'Unknown'}\n"
            f"**Top Role:** {target.top_role.name}"
        )
        await message.reply(info)
        return True

    # --- ROLE INFO ---
    if "role info" in cmd or "list roles" in cmd:
        roles = [r.name for r in guild.roles if r.name != "@everyone"]
        await message.reply(f"**Roles:** {', '.join(roles)}")
        return True

    # --- CREATE CHANNEL (Now Public) ---
    if "create channel" in cmd:
        name = cmd.split("channel")[-1].strip().replace(" ", "-") or "new-chat"
        try:
            new_chan = await guild.create_text_channel(name=name)
            await message.reply(f"✅ Created {new_chan.mention}")
        except Exception as e:
            await message.reply(f"❌ I need 'Manage Channels' permission to do that.")
        return True

    return False

@bot.event
async def on_ready():
    print(f'✅ Connected: {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    channel_id = message.channel.id
    user_id = message.author.id
    clean_text = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()

    # 1. Check for Public Commands first
    if await handle_public_tasks(message, clean_text):
        return

    # 2. Topic Isolation: Check if a different user is interrupting
    if channel_id in channel_topics:
        active = channel_topics[channel_id]
        if active['user_id'] != user_id:
            # Only reply with the warning once per topic switch
            await message.reply(f"Wait, I'm currently talking to **{active['user_name']}** about '{active['topic']}'. Did you want to follow up on that or ask something new?")

    # Update active topic
    channel_topics[channel_id] = {
        'user_id': user_id, 
        'user_name': message.author.display_name, 
        'topic': clean_text[:30]
    }

    # 3. Chat API
    async with message.channel.typing():
        try:
            hist_key = (channel_id, user_id)
            if hist_key not in message_history:
                message_history[hist_key] = deque(maxlen=4)

            # Strict brevity and no citations system prompt
            sys_msg = (
                "You are a very brief assistant. "
                "CRITICAL: Never use citations like [1] or [2]. No source links. "
                "Answers must be 1-2 sentences only."
            )
            
            api_messages = [{"role": "system", "content": sys_msg}]
            for h in message_history[hist_key]:
                api_messages.append(h)
            api_messages.append({"role": "user", "content": clean_text})

            response = client.chat.completions.create(model=MODEL_ID, messages=api_messages)
            answer = clean_citations(response.choices[0].message.content)

            # Store clean history
            message_history[hist_key].append({"role": "user", "content": clean_text})
            message_history[hist_key].append({"role": "assistant", "content": answer})

            await message.reply(answer, mention_author=False)

        except Exception as e:
            print(f"Error: {e}")
            await message.reply("⚠️ Service busy. Try again.")

bot.run(DISCORD_TOKEN)
