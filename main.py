import discord
from discord.ext import commands
from discord import app_commands
import os
import time
import requests
from datetime import timedelta

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
MIMO_API_KEY = os.getenv("MIMO_OPENAI_API_KEY")
MIMO_URL = "https://ai.mimo.org/v1/openai/message"

bot_start_time = time.time()

OWNER = {
    "name": "Ψ.1nOnly.Ψ",
    "username": ".flexed.",
    "pfp": "https://cdn.discordapp.com/avatars/1081876265683927080/a2671291fa7a3f13e03022eeeac15ef2.webp?size=2048",
    "id": "1081876265683927080",
    "link": "https://discord.com/users/1081876265683927080/",
    "friend": "https://discord.gg/XNNUR4Qn",
    "bio": "Add me as a friend to contact me. Must have a mutual friend to get it done.\nBorn <t:1265842320:R>\nCreated 👑 Shivam’s Discord:\nhttps://discord.gg/bzePwKSDsp\nE-mail: flexed@zohomail.in",
    "gunslol": "https://guns.lol/flexedfr",
    "favserv": "https://discord.gg/bzePwKSDsp",
}

# --- BOT CLASS FOR SLASH SYNCING ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Ye line slash commands ko Discord server pe register karti hai
        await self.tree.sync()
        print(f"✅ Slash commands synced for {self.user}")

bot = MyBot()
channel_threads = {}
channel_languages = {}

def get_mimo_response(user_message, thread_id, system_prompt):
    headers = {"api-key": MIMO_API_KEY}
    # Mimo works best when system instructions are part of the prompt
    full_message = f"System Instruction: {system_prompt}\nUser: {user_message}"
    body = {"message": full_message}
    if thread_id:
        body["threadId"] = thread_id
    
    try:
        response = requests.post(MIMO_URL, headers=headers, json=body, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Mimo Error: {e}")
        return None

# --- COMMANDS ---

@bot.hybrid_command(name="lang", description="Change AI language (e.g. Hindi, English, Marathi)")
@app_commands.describe(language="The language you want the AI to speak in")
async def lang(ctx, language: str):
    channel_languages[ctx.channel.id] = language
    await ctx.reply(f"🌐 Language updated to **{language}** for this channel.")

@bot.command()
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

@bot.command()
async def info(ctx):
    embed = discord.Embed(title="Bot Status", color=discord.Color.blue())
    embed.add_field(name="Owner", value=OWNER['name'], inline=True)
    embed.add_field(name="Bio", value=OWNER['bio'], inline=False)
    embed.set_thumbnail(url=OWNER['pfp'])
    await ctx.reply(embed=embed)

# --- AI MESSAGE HANDLER ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Execute commands first
    await bot.process_commands(message)
    
    # If message starts with prefix, don't trigger AI chat
    if message.content.startswith(bot.command_prefix):
        return

    # Language Logic
    current_lang = channel_languages.get(message.channel.id, "English")
    
    # Custom Server Logic (from your original code)
    if not channel_languages.get(message.channel.id):
        if message.guild and message.guild.id == 1349281907765936188:
            current_lang = "Hinglish"

    respect = ""
    if str(message.author.id) == OWNER['id']:
        respect = f"User is your Boss {OWNER['name']}. Be polite."

    sys_prompt = f"Reply ONLY in {current_lang}. {respect} Keep it very short."

    async with message.channel.typing():
        t_id = channel_threads.get(message.channel.id)
        data = get_mimo_response(message.content, t_id, sys_prompt)

        if data and "response" in data:
            channel_threads[message.channel.id] = data.get("threadId")
            await message.reply(data["response"])
        else:
            # Silent fail or error message
            pass

if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
