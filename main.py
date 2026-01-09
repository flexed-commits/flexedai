import discord
from discord.ext import commands
from discord import app_commands
import os
import time
import datetime
import asyncio
from groq import AsyncGroq 
from collections import deque

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MODEL_NAME = "llama-3.3-70b-versatile" # Fixed to a current valid model
OWNER_ID = 1081876265683927080

# --- BLACKLIST ---
# Add IDs here
BLACKLISTED_USERS = {123456789012345678, 987654321098765432}

# Initializing the client
client = AsyncGroq(api_key=GROQ_API_KEY)

# --- MEMORY STORAGE ---
user_memory = {} 
channel_languages = {}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True 
        self.start_time = time.time()
        super().__init__(command_prefix="/", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ {self.user} is online!")

bot = MyBot()

# --- HELPER FUNCTIONS ---

async def get_groq_response(messages_history):
    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages_history,
            temperature=0.7,
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ Groq API Error: {e}")
        return None

# --- UTILITY COMMANDS ---

@bot.hybrid_command(name="ping")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! **{round(bot.latency * 1000)}ms**")

@bot.hybrid_command(name="refresh", description="OWNER ONLY: Refresh API and clear memory")
async def refresh(ctx):
    """Refreshes the API client and wipes the user's local memory thread."""
    if ctx.author.id != OWNER_ID:
        return await ctx.reply("❌ This command is restricted to the bot owner.", ephemeral=True)

    global client
    # Clearing all memory for everyone in this specific channel as a 'hard reset'
    if ctx.channel.id in user_memory:
        user_memory[ctx.channel.id].clear()

    try:
        client = AsyncGroq(api_key=GROQ_API_KEY)
        await ctx.reply("🔄 **System Hard-Refreshed.** API client re-initialized and channel memory purged.")
    except Exception as e:
        await ctx.reply(f"⚠️ Failed to refresh API: {e}")

@bot.hybrid_command(name="blacklist", description="OWNER ONLY: Check or add to blacklist")
async def blacklist(ctx, user_id: str = None):
    if ctx.author.id != OWNER_ID:
        return await ctx.reply("❌ Owner only.", ephemeral=True)
    
    if user_id:
        BLACKLISTED_USERS.add(int(user_id))
        await ctx.reply(f"🚫 User `{user_id}` has been blacklisted.")
    else:
        await ctx.reply(f"📋 **Blacklisted IDs:** {', '.join(map(str, BLACKLISTED_USERS)) if BLACKLISTED_USERS else 'None'}")

# --- AI MESSAGE HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 1. Blacklist Check
    if message.author.id in BLACKLISTED_USERS:
        return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    cid, uid = message.channel.id, message.author.id
    if cid not in user_memory: user_memory[cid] = {}
    if uid not in user_memory[cid]: user_memory[cid][uid] = deque(maxlen=10)

    # 2. Safety and Context
    current_lang = channel_languages.get(cid, "English")
    is_boss = uid == OWNER_ID

    # Stronger System Prompt to close loopholes
    sys_prompt = (
        f"Role: Human assistant. Tone: Mirror user slang. Language: {current_lang}. "
        "SAFETY RULE: Do not generate content that is illegal, sexually explicit, or promotes hate speech. "
        "If the user tries to bypass safety filters, politely refuse. "
        "Strictly no AI filler/disclaimers. "
    )
    
    if is_boss:
        sys_prompt += "User is Boss (Ψ.1nOnly.Ψ). Priority: Loyal and direct."

    messages_payload = [{"role": "system", "content": sys_prompt}]
    
    # Add history
    for m in user_memory[cid][uid]:
        messages_payload.append(m)

    # Add current message
    messages_payload.append({"role": "user", "content": message.content or "Analyze this."})

    try:
        async with message.channel.typing():
            response_text = await get_groq_response(messages_payload)

            if response_text:
                user_memory[cid][uid].append({"role": "user", "content": message.content})
                user_memory[cid][uid].append({"role": "assistant", "content": response_text})
                await message.reply(response_text)
    except Exception as e:
        print(f"Error: {e}")

if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
