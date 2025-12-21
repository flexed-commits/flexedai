import discord
import os
import asyncio
from dotenv import load_dotenv
from perplexity import Perplexity
from collections import deque

# --- CONFIG ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')

if not DISCORD_TOKEN or not PERPLEXITY_API_KEY:
    print("❌ Missing Tokens")
    exit(1)

client = Perplexity(api_key=PERPLEXITY_API_KEY)
MODEL_ID = "sonar-pro"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True 
bot = discord.Client(intents=intents)

active_channels = {}
# Context is now tracked by (channel_id, user_id) to keep topics private
user_contexts = {} 

def smart_split_message(text, max_length=2000):
    if len(text) <= max_length: return [text]
    chunks = []
    remaining = text
    while remaining:
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
    print(f'✅ Bot Online: {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    channel_id = message.channel.id
    user_id = message.author.id
    is_dm = isinstance(message.channel, discord.DMChannel)
    bot_mentioned = bot.user.mentioned_in(message)
    clean_text = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()

    # 1. ADMIN TASKS (Channel Creation)
    if clean_text.lower().startswith("create channel"):
        if message.author.guild_permissions.manage_channels:
            channel_name = clean_text.lower().replace("create channel", "").strip()
            new_channel = await message.guild.create_text_channel(name=channel_name)
            await message.reply(f"✅ Created channel: {new_channel.mention}")
            return
        else:
            await message.reply("❌ You don't have permissions to manage channels.")
            return

    # Toggle Auto-reply
    if not is_dm and bot_mentioned and clean_text.lower() in ["start", "stop"]:
        if message.author.guild_permissions.administrator:
            active_channels[channel_id] = (clean_text.lower() == "start")
            await message.reply(f"System: Auto-reply {'ENABLED' if active_channels[channel_id] else 'DISABLED'}.")
            return

    if not (is_dm or bot_mentioned or active_channels.get(channel_id, False)):
        return

    # 2. TOPIC ISOLATION (Per-User/Channel Key)
    context_key = (channel_id, user_id)
    if context_key not in user_contexts:
        user_contexts[context_key] = {"history": deque(maxlen=5), "last_topic": None}

    # Check if a different user is interrupting the bot
    # (Simple logic: if a user hasn't talked for a while, remind them of the context)
    current_context = user_contexts[context_key]

    async with message.channel.typing():
        try:
            # 3. NO CITATIONS & SMALL RESPONSES (System Prompt)
            system_prompt = (
                "You are a concise AI. IMPORTANT: Do not include citations, "
                "bracketed numbers [1][2], or source lists. Keep responses very short and direct. "
                f"Current topic focus for this user: {current_context['last_topic'] or 'General'}"
            )

            api_messages = [{"role": "system", "content": system_prompt}]
            for hist in current_context["history"]:
                api_messages.append(hist)
            api_messages.append({"role": "user", "content": clean_text})

            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=api_messages
            )

            answer = response.choices[0].message.content
            
            # Clean citations just in case the model ignores instructions
            import re
            answer = re.sub(r'\[\d+\]', '', answer)

            # Update private history
            current_context["history"].append({"role": "user", "content": clean_text})
            current_context["history"].append({"role": "assistant", "content": answer})
            
            # Split and send
            chunks = smart_split_message(answer)
            for chunk in chunks:
                await message.reply(chunk, mention_author=False)
                await asyncio.sleep(0.5)

        except Exception as e:
            print(f"Error: {e}")
            await message.reply("⚠️ Service busy.")

bot.run(DISCORD_TOKEN)
