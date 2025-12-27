import discord
from discord.ext import commands
from discord import app_commands
import os
from groq import Groq
from collections import deque # Memory store karne ke liye

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_NAME = "openai/gpt-oss-20b"

OWNER = {"name": "Ψ.1nOnly.Ψ", "id": "1081876265683927080"}

client = Groq(api_key=GROQ_API_KEY)

# --- MEMORY STORAGE ---
# Har channel ke liye alag memory (max 5 messages)
channel_memory = {} 
channel_languages = {}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Slash commands synced")

bot = MyBot()

def get_groq_response(messages):
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages, # Pura memory context bhej rahe hain
            temperature=0.7,
            max_tokens=200,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Groq Error: {e}")
        return None

@bot.hybrid_command(name="lang", description="Change AI language")
async def lang(ctx, language: str):
    channel_languages[ctx.channel.id] = language
    # Language change hone par memory clear karna better hota hai context ke liye
    if ctx.channel.id in channel_memory:
        channel_memory[ctx.channel.id].clear()
    await ctx.reply(f"🌐 Language updated to **{language}** and memory reset.")

@bot.event
async def on_message(message):
    if message.author.bot: return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # Language Setup
    current_lang = channel_languages.get(message.channel.id)
    if not current_lang:
        current_lang = "Hinglish" if message.guild and message.guild.id == 1349281907765936188 else "English"

    # Memory Initialize (agar channel naya hai)
    if message.channel.id not in channel_memory:
        channel_memory[message.channel.id] = deque(maxlen=10) # 5 user + 5 assistant messages

    respect = f"User is your Boss {OWNER['name']}. Be polite." if str(message.author.id) == OWNER['id'] else ""
    sys_prompt = f"Reply ONLY in {current_lang}. {respect} Keep it short."

    # Build Message History
    messages_for_api = [{"role": "system", "content": sys_prompt}]
    
    # Purani baatein add karo
    for msg in channel_memory[message.channel.id]:
        messages_for_api.append(msg)
    
    # Current message add karo
    messages_for_api.append({"role": "user", "content": message.content})

    async with message.channel.typing():
        response_text = get_groq_response(messages_for_api)

        if response_text:
            # Memory mein save karo (Context maintain karne ke liye)
            channel_memory[message.channel.id].append({"role": "user", "content": message.content})
            channel_memory[message.channel.id].append({"role": "assistant", "content": response_text})
            
            await message.reply(response_text)

if DISCORD_TOKEN and GROQ_API_KEY:
    bot.run(DISCORD_TOKEN)
