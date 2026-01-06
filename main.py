import discord
from discord.ext import commands
from discord import app_commands
import os
from groq import Groq
from collections import deque

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

# Initializing Groq Client
client = Groq(api_key=GROQ_API_KEY)

# Using your specific Llama 4 Maverick model
MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct"
OWNER_ID = 1081876265683927080

# --- MEMORY STORAGE ---
channel_memory = {} 
channel_languages = {}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Bot is online and Slash commands are synced!")

bot = MyBot()

def get_groq_response(messages_history):
    """Sends the conversation history (including images) to Groq."""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages_history,
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ Groq API Error: {e}")
        return "Sorry, I encountered an error while thinking."

# --- COMMANDS ---

@bot.hybrid_command(name="lang", description="Change AI Language for this channel")
@app_commands.describe(language="Example: Hindi, English, Spanish")
async def lang(ctx, language: str):
    channel_languages[ctx.channel.id] = language
    if ctx.channel.id in channel_memory:
        channel_memory[ctx.channel.id].clear()
    await ctx.reply(f"🌐 Language updated to **{language}**. Memory cleared for fresh context.")

# --- AI MESSAGE HANDLER ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 1. Process Prefix Commands (!lang, etc.)
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # 2. Language & Identity Logic
    current_lang = channel_languages.get(message.channel.id, "English")
    is_boss = message.author.id == OWNER_ID
    respect = "User is your Boss (Ψ.1nOnly.Ψ). Be polite and helpful." if is_boss else ""

    # 3. Memory Management (Keep last 10 messages)
    if message.channel.id not in channel_memory:
        channel_memory[message.channel.id] = deque(maxlen=10)

    # 4. Handle Attachments (Vision)
    content_list = [{"type": "text", "text": message.content or "Analyze this image."}]
    
    if message.attachments:
        for attachment in message.attachments:
            if any(attachment.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg', 'webp']):
                content_list.append({
                    "type": "image_url",
                    "image_url": {"url": attachment.url}
                })

    # 5. Build Payload
    sys_prompt = f"Role: Helpful Assistant. Reply ONLY in {current_lang}. {respect} Keep it concise."
    messages_payload = [{"role": "system", "content": sys_prompt}]
    
    # Add historical context (Text only for history to save tokens)
    for m in channel_memory[message.channel.id]:
        messages_payload.append(m)
    
    # Add current message (which might contain images)
    messages_payload.append({"role": "user", "content": content_list})

    # 6. Get Response & Reply
    async with message.channel.typing():
        response_text = get_groq_response(messages_payload)

        if response_text:
            # Update Memory (We only store text in history to avoid re-sending old images)
            channel_memory[message.channel.id].append({"role": "user", "content": message.content})
            channel_memory[message.channel.id].append({"role": "assistant", "content": response_text})

            await message.reply(response_text)

if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
