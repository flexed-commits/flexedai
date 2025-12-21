import discord
import os
from dotenv import load_dotenv
# Ensure you have installed the sambanova package: pip install sambanova
from sambanova import SambaNova

# --- CONFIG ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SAMBANOVA_API_KEY = os.getenv('SAMBANOVA_API_KEY')

# Initialize SambaNova Client
client = SambaNova(
    api_key=SAMBANOVA_API_KEY,
    base_url="https://api.sambanova.ai/v1",
)

MODEL_ID = "DeepSeek-V3" # Ensure this matches SambaNova's exact model string

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# Global toggle: Bot starts "OFF" by default
is_active = False

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    print(f'🚀 Running DeepSeek-V3 via SambaNova')

@bot.event
async def on_message(message):
    global is_active

    # 1. Basic Filters
    if message.author == bot.user or message.author.bot:
        return

    # Check for pings/mentions
    bot_mentioned = bot.user.mentioned_in(message)
    
    # Clean content for command checking
    clean_content = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
    command_check = clean_content.lower()

    # 2. ADMIN COMMANDS (Must be pinged + Administrator)
    if bot_mentioned and command_check in ["start", "stop"]:
        if message.author.guild_permissions.administrator:
            if command_check == "start":
                is_active = True
                await message.channel.send(f"🟢 **DeepSeek-V3 is now ACTIVE.** I will now reply to ALL messages in this channel.")
            else:
                is_active = False
                await message.channel.send(f"🔴 **DeepSeek-V3 is now SILENT.** Use @ping start to re-enable.")
            return
        else:
            await message.channel.send("❌ Error: Administrator permissions required to toggle the bot.")
            return

    # 3. GLOBAL RESPONSE LOGIC
    # If it's a DM, always respond. 
    # If it's a channel, only respond if is_active is True.
    is_dm = isinstance(message.channel, discord.DMChannel)
    
    if not is_dm and not is_active:
        return

    # 4. AI GENERATION (SambaNova / DeepSeek)
    async with message.channel.typing():
        try:
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": message.content} # Uses full message content
                ],
                temperature=0.1,
                top_p=0.1
            )
            
            answer = response.choices[0].message.content
            
            # Discord 2000 character limit split
            if len(answer) > 2000:
                for i in range(0, len(answer), 2000):
                    await message.channel.send(answer[i:i+2000])
            else:
                await message.channel.send(answer)
        
        except Exception as e:
            print(f"SambaNova Error: {e}")
            await message.channel.send("⚠️ I encountered an error communicating with the AI.")

bot.run(DISCORD_TOKEN)
