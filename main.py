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

# Initializing the client
client = AsyncGroq(api_key=GROQ_API_KEY)

MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct"
OWNER_ID = 1081876265683927080

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
        # Use the global client variable
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

@bot.hybrid_command(name="ping", description="Check latency")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! **{round(bot.latency * 1000)}ms**")

@bot.hybrid_command(name="uptime", description="Check bot uptime")
async def uptime(ctx):
    uptime_sec = int(round(time.time() - bot.start_time))
    text = str(datetime.timedelta(seconds=uptime_sec))
    await ctx.reply(f"🚀 Uptime: **{text}**")

@bot.hybrid_command(name="refresh", description="Fully refreshes the AI API and clears your current memory")
async def refresh(ctx):
    """Refreshes the API client and wipes the user's local memory thread."""
    global client
    cid, uid = ctx.channel.id, ctx.author.id
    
    # 1. Clear conversation memory for this specific user in this channel
    if cid in user_memory and uid in user_memory[cid]:
        user_memory[cid][uid].clear()
    
    # 2. Re-initialize the API client
    try:
        client = AsyncGroq(api_key=GROQ_API_KEY)
        await ctx.reply("🔄 **AI Refreshed.** API connection reset and local memory wiped.")
    except Exception as e:
        await ctx.reply(f"⚠️ Failed to refresh API: {e}")

@bot.hybrid_command(name="forget", description="Clear your personal AI memory thread")
async def forget(ctx):
    cid, uid = ctx.channel.id, ctx.author.id
    if cid in user_memory and uid in user_memory[cid]:
        user_memory[cid][uid].clear()
        await ctx.reply("🧠 Memory wiped. I've forgotten our conversation in this channel.")
    else:
        await ctx.reply("🤷 I don't have any active memory of you here.")

@bot.hybrid_command(name="lang", description="Change AI Language")
async def lang(ctx, language: str):
    is_admin = ctx.author.guild_permissions.administrator if ctx.guild else False
    if not (is_admin or ctx.author.id == OWNER_ID):
        await ctx.reply("❌ Administrator permissions required.", ephemeral=True)
        return
    channel_languages[ctx.channel.id] = language
    if ctx.channel.id in user_memory: user_memory[ctx.channel.id].clear()
    await ctx.reply(f"🌐 Language updated to **{language}**.")

# --- AI MESSAGE HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    cid, uid = message.channel.id, message.author.id
    if cid not in user_memory: user_memory[cid] = {}
    if uid not in user_memory[cid]: user_memory[cid][uid] = deque(maxlen=10)

    user = message.author
    guild = message.guild

    context_info = (
        f"[USER INFO] Name: {user.display_name}, Username: {user.name}, ID: {user.id}, "
        f"Avatar: {user.display_avatar.url}. "
    )
    if guild:
        context_info += (
            f"[SERVER INFO] Name: {guild.name}, ID: {guild.id}, "
            f"Icon: {guild.icon.url if guild.icon else 'No Icon'}, "
            f"Member Count: {guild.member_count}. "
        )

    current_lang = channel_languages.get(cid, "English")
    is_boss = uid == OWNER_ID

    sys_prompt = (
        f"Role: Human. Mirror user tone/slang. Language: {current_lang}. "
        f"Real-time: 2026. {context_info} "
        f"Strictly no AI filler/disclaimers."
    )
    if is_boss:
        sys_prompt += " Priority: User is Boss (Ψ.1nOnly.Ψ). Be loyal and direct."

    messages_payload = [{"role": "system", "content": sys_prompt}]
    for m in user_memory[cid][uid]:
        messages_payload.append(m)

    content_list = [{"type": "text", "text": message.content or "Analyze this."}]
    if message.attachments:
        for attachment in message.attachments:
            if any(attachment.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg', 'webp']):
                content_list.append({"type": "image_url", "image_url": {"url": attachment.url}})

    messages_payload.append({"role": "user", "content": content_list})

    try:
        async with message.channel.typing():
            response_text = await get_groq_response(messages_payload)

            if response_text:
                user_memory[cid][uid].append({"role": "user", "content": message.content or "[Image]"})
                user_memory[cid][uid].append({"role": "assistant", "content": response_text})
                await message.reply(response_text)
    except Exception as e:
        print(f"Error: {e}")

if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
