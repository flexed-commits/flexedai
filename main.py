import discord
from discord.ext import commands
from discord import app_commands
import os
import time
import datetime
from groq import Groq
from collections import deque

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

client = Groq(api_key=GROQ_API_KEY)

MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct"
OWNER_ID = 1081876265683927080

# --- MEMORY STORAGE ---
user_memory = {} 
channel_languages = {}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        self.start_time = time.time()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ {self.user} is online!")

bot = MyBot()

# --- HELPER FUNCTIONS ---

def get_groq_response(messages_history):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages_history,
            temperature=0.8,
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

@bot.hybrid_command(name="shard", description="Check shard info")
async def shard(ctx):
    shard_id = ctx.guild.shard_id if ctx.guild else 0
    await ctx.reply(f"💎 Shard ID: **{shard_id}**")

# --- LANGUAGE COMMAND (Hybrid: Works as Slash and !lang) ---

@bot.hybrid_command(name="lang", description="Change AI Language (Admin/Owner Only)")
@app_commands.describe(language="Example: Hindi, English, Spanish")
async def lang(ctx, language: str):
    # Auto-Admin: Check if User is Owner OR has Admin perms
    is_admin = ctx.author.guild_permissions.administrator if ctx.guild else False
    is_owner = ctx.author.id == OWNER_ID

    if not (is_admin or is_owner):
        await ctx.reply("❌ Administrator permissions required.", ephemeral=True)
        return

    channel_languages[ctx.channel.id] = language
    # Clear memory for everyone in this channel to reset context
    if ctx.channel.id in user_memory:
        user_memory[ctx.channel.id].clear()
    
    status = "Boss" if is_owner else "Admin"
    await ctx.reply(f"🌐 Language updated to **{language}** by {status}. Memory cleared.")

# --- AI MESSAGE HANDLER ---

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 1. Permission Safety (Fixes 403 Errors)
    if message.guild:
        perms = message.channel.permissions_for(message.guild.me)
        if not perms.send_messages or not perms.view_channel:
            return

    # 2. Process Commands (!ping, !lang, etc.)
    # This allows !lang to work even if Slash commands are blocked
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # 3. User-Specific Memory (Threads)
    cid, uid = message.channel.id, message.author.id
    if cid not in user_memory: user_memory[cid] = {}
    if uid not in user_memory[cid]: user_memory[cid][uid] = deque(maxlen=10)

    # 4. Identity & Tone Setup
    current_lang = channel_languages.get(cid, "English")
    is_boss = uid == OWNER_ID
    
    sys_prompt = (
        f"Role: Act like a human. Mirror the user's tone. Be conversational. "
        f"You know real-time info for 2026. Be descriptive with images. "
        f"Reply ONLY in {current_lang}."
    )
    if is_boss:
        sys_prompt += " User is your Boss (Ψ.1nOnly.Ψ). Be extremely loyal."

    # 5. Build Content (Text + Vision)
    content_list = [{"type": "text", "text": message.content or "Analyze this image."}]
    if message.attachments:
        for attachment in message.attachments:
            if any(attachment.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg', 'webp']):
                content_list.append({"type": "image_url", "image_url": {"url": attachment.url}})

    messages_payload = [{"role": "system", "content": sys_prompt}]
    
    # Add history for this specific user
    for m in user_memory[cid][uid]:
        messages_payload.append(m)
    messages_payload.append({"role": "user", "content": content_list})

    # 6. Response Logic
    try:
        async with message.channel.typing():
            response_text = get_groq_response(messages_payload)

            if response_text:
                # Update memory for this user's thread
                user_memory[cid][uid].append({"role": "user", "content": message.content or "[Sent an image]"})
                user_memory[cid][uid].append({"role": "assistant", "content": response_text})
                
                await message.reply(response_text)
    except Exception as e:
        print(f"Error: {e}")

if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
