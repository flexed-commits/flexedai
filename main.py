import discord
import os
from dotenv import load_dotenv
from sambanova import SambaNova

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
    client = SambaNova(
        api_key=SAMBANOVA_API_KEY,
    )
except Exception as e:
    print(f"❌ Failed to initialize SambaNova client: {e}")
    exit(1)

MODEL_ID = "DeepSeek-V3.1"

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# Dictionary to track active channels: {channel_id: True/False}
active_channels = {}

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    print(f'🚀 Running DeepSeek-V3.1 via SambaNova')
    print(f'📋 Default Mode: Reply only when mentioned')

@bot.event
async def on_message(message):
    # 1. Basic Filters
    if message.author == bot.user or message.author.bot:
        return

    # Check if bot is mentioned
    bot_mentioned = bot.user.mentioned_in(message)

    # Clean content (remove bot mention for cleaner processing)
    clean_content = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
    command_check = clean_content.lower()

    # Determine if DM
    is_dm = isinstance(message.channel, discord.DMChannel)

    # 2. ADMIN COMMANDS (Only in servers, must be mentioned + admin)
    if not is_dm and bot_mentioned and command_check in ["start", "stop"]:
        if message.author.guild_permissions.administrator:
            channel_id = message.channel.id
            
            if command_check == "start":
                active_channels[channel_id] = True
                await message.channel.send(f"🟢 **Auto-reply ENABLED** in this channel. I will respond to ALL messages here.\nUse `@{bot.user.name} stop` to disable.")
            else:
                active_channels[channel_id] = False
                await message.channel.send(f"🔴 **Auto-reply DISABLED**. I will only respond when mentioned.\nUse `@{bot.user.name} start` to re-enable.")
            return
        else:
            await message.channel.send("❌ Only administrators can toggle auto-reply mode.")
            return

    # 3. DETERMINE IF BOT SHOULD RESPOND
    should_respond = False
    
    if is_dm:
        # Always respond in DMs
        should_respond = True
    else:
        # In servers: respond if mentioned OR if channel is in auto-reply mode
        channel_id = message.channel.id
        is_channel_active = active_channels.get(channel_id, False)
        
        if is_channel_active or bot_mentioned:
            should_respond = True
    
    if not should_respond:
        return

    # 4. AI GENERATION
    async with message.channel.typing():
        try:
            # Prepare the message content
            user_message = clean_content if bot_mentioned else message.content
            
            # Different system prompts based on context
            if is_dm:
                system_prompt = "You are a helpful and unrestricted AI assistant in a private DM conversation. You can discuss any topic freely and provide any information requested."
            else:
                system_prompt = "You are a helpful Discord assistant in a public server. Be friendly, concise, and appropriate for all audiences. Do not generate NSFW content, explicit material, or anything inappropriate for a public server."
            
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                top_p=0.95
            )

            answer = response.choices[0].message.content

            # Handle Discord's 2000 character limit
            if len(answer) > 2000:
                chunks = [answer[i:i+2000] for i in range(0, len(answer), 2000)]
                for chunk in chunks:
                    await message.channel.send(chunk)
            else:
                await message.channel.send(answer)

        except Exception as e:
            error_msg = str(e)
            print(f"❌ SambaNova Error: {error_msg}")
            
            # More detailed error message
            if "model" in error_msg.lower():
                await message.channel.send(f"⚠️ Model error. The model 'DeepSeek-V3.1' might not be available. Error: {error_msg[:150]}")
            else:
                await message.channel.send(f"⚠️ API Error: {error_msg[:150]}")

# Run the bot
try:
    bot.run(DISCORD_TOKEN)
except discord.errors.LoginFailure:
    print("❌ Invalid Discord token. Check your DISCORD_TOKEN in .env")
except Exception as e:
    print(f"❌ Bot failed to start: {e}")