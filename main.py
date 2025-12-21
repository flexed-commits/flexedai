import discord
import os
from dotenv import load_dotenv
from sambanova import SambaNova
import asyncio
from collections import deque

# --- CONFIG ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SAMBANOVA_API_KEY = os.getenv('SAMBANOVA_API_KEY')

# Validate environment variables
if not DISCORD_TOKEN or not SAMBANOVA_API_KEY:
    print("❌ Missing DISCORD_TOKEN or SAMBANOVA_API_KEY in .env file")
    exit(1)

# Initialize SambaNova Client
try:
    client = SambaNova(api_key=SAMBANOVA_API_KEY)
except Exception as e:
    print(f"❌ Failed to initialize SambaNova client: {e}")
    exit(1)

# Exact Model ID as requested
MODEL_ID = "DeepSeek-V3.1"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
bot = discord.Client(intents=intents)

# Track active channels for auto-reply {channel_id: bool}
active_channels = {}
# Track conversation history {channel_id: deque([messages])}
message_history = {}

def smart_split_message(text, max_length=2000):
    """Splits text into Discord-friendly chunks at natural breakpoints."""
    if len(text) <= max_length:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining); break
        chunk = remaining[:max_length]
        # Try splitting at Paragraph > Newline > Sentence > Space
        split_point = max_length
        for sep in ['\n\n', '\n', '. ', ' ']:
            last_idx = chunk.rfind(sep)
            if last_idx > max_length * 0.3:
                split_point = last_idx + len(sep)
                break
        chunks.append(remaining[:split_point].rstrip())
        remaining = remaining[split_point:].lstrip()
    return chunks

async def send_smart_reply(original_message, text):
    """Replies to the user with smart chunking and typing simulation."""
    chunks = smart_split_message(text)
    for i, chunk in enumerate(chunks):
        if not chunk.strip(): continue
        try:
            if i == 0:
                # The first chunk is a formal Discord Reply
                await original_message.reply(chunk, mention_author=False)
            else:
                # Subsequent chunks are sent normally in the same thread/channel
                await original_message.channel.send(chunk)
            
            if i < len(chunks) - 1:
                await asyncio.sleep(0.8) # Natural reading pause
        except Exception as e:
            print(f"Error sending chunk: {e}")

def get_server_context(message):
    """Gathers metadata about the server for AI awareness."""
    if isinstance(message.channel, discord.DMChannel):
        return "Private DM Conversation."
    
    g, c, a = message.guild, message.channel, message.author
    roles = [r.name for r in a.roles if r.name != "@everyone"]
    
    return (
        f"Server: {g.name} | Channel: #{c.name}\n"
        f"User: {a.display_name} | Roles: {', '.join(roles[:5])}\n"
        f"Permissions: {'Admin' if a.guild_permissions.administrator else 'Member'}"
    )

@bot.event
async def on_ready():
    print(f'✅ Connected: {bot.user}')
    print(f'🤖 Model: {MODEL_ID}')

@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    bot_mentioned = bot.user.mentioned_in(message)
    channel_id = message.channel.id
    
    # Clean content
    clean_text = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()

    # Admin Toggle Commands
    if not is_dm and bot_mentioned and clean_text.lower() in ["start", "stop"]:
        if message.author.guild_permissions.administrator:
            active_channels[channel_id] = (clean_text.lower() == "start")
            status = "ENABLED" if active_channels[channel_id] else "DISABLED"
            await message.reply(f"System: Auto-reply is now **{status}**.")
            return
        else:
            await message.reply("❌ Admin permissions required.")
            return

    # Decide to respond
    should_respond = is_dm or bot_mentioned or active_channels.get(channel_id, False)
    if not should_respond:
        return

    # Manage History
    if channel_id not in message_history:
        message_history[channel_id] = deque(maxlen=10) # Remember last 10 exchanges

    async with message.channel.typing():
        try:
            context = get_server_context(message)
            system_prompt = (
                f"You are a helpful AI assistant named {bot.user.name}. "
                f"Context: {context}. Model: {MODEL_ID}. "
                "Provide high-quality, helpful, and engaging responses. "
                "Always respond in a natural, conversational tone."
            )

            # Build messages with history
            api_messages = [{"role": "system", "content": system_prompt}]
            for hist in message_history[channel_id]:
                api_messages.append(hist)
            api_messages.append({"role": "user", "content": clean_text})

            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=api_messages,
                temperature=0.7,
                max_tokens=2000
            )

            answer = response.choices[0].message.content
            
            # Update history
            message_history[channel_id].append({"role": "user", "content": clean_text})
            message_history[channel_id].append({"role": "assistant", "content": answer})

            # Send the reply
            await send_smart_reply(message, answer)

        except Exception as e:
            print(f"API Error: {e}")
            await message.reply(f"⚠️ I encountered an error: {str(e)[:100]}")

bot.run(DISCORD_TOKEN)