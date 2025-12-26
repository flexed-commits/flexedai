import discord
from discord.ext import commands
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

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

# Global storage for thread IDs and language preferences
channel_threads = {}
channel_languages = {}

def get_mimo_response(user_message, thread_id, system_prompt):
    # Combining system prompt with user message as Mimo uses a simple endpoint
    full_prompt = f"{system_prompt}\n\nUser: {user_message}"
    headers = {"api-key": MIMO_API_KEY}
    body = {"message": full_prompt}
    if thread_id:
        body["threadId"] = thread_id
    
    try:
        response = requests.post(MIMO_URL, headers=headers, json=body)
        return response.json()
    except Exception as e:
        print(f"API Error: {e}")
        return None

@bot.event
async def on_ready():
    print(f'✅ Bot is online as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

# --- SLASH COMMANDS ---

@bot.tree.command(name="lang", description="Change the AI response language")
async def lang(interaction: discord.Interaction, language: str):
    channel_languages[interaction.channel_id] = language
    await interaction.response.send_message(f"✅ Language set to: **{language}** for this channel.")

@bot.command(name="ping")
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.reply(f"🏓 Pong! `{latency}ms`")

@bot.command(name="uptime")
async def uptime(ctx):
    uptime_diff = int(time.time() - bot_start_time)
    uptime_str = str(timedelta(seconds=uptime_diff))
    await ctx.reply(f"⏱️ **Uptime:** `{uptime_str}`")

@bot.command(name="info")
async def info(ctx):
    embed = discord.Embed(title="Bot Status", color=discord.Color.blue())
    embed.add_field(name="Owner", value=OWNER['name'], inline=True)
    embed.add_field(name="Servers", value=len(bot.guilds), inline=True)
    embed.add_field(name="Ping", value=f"{round(bot.latency * 1000)}ms", inline=True)
    embed.set_footer(text="Powered by Mimo AI")
    await ctx.reply(embed=embed)

# --- MESSAGE HANDLER (AI) ---

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Don't trigger AI if it's a prefix command
    if message.content.startswith('!'):
        await bot.process_commands(message)
        return

    guild_id = message.guild.id if message.guild else None
    channel_id = message.channel.id

    # 1. Determine Language
    custom_lang = channel_languages.get(channel_id)
    if custom_lang:
        lang_instruction = f"STRICT RULE: Reply ONLY in {custom_lang}."
    elif guild_id == 1392347019917660161 and channel_id == 1418064267374231766:
        lang_instruction = "STRICT RULE: Reply ONLY in Hinglish."
    elif guild_id == 1349281907765936188:
        lang_instruction = "Reply in Hinglish."
    else:
        lang_instruction = "Reply ONLY in English."

    # 2. Owner Respect Logic
    respect_instruction = ""
    if str(message.author.id) == OWNER['id']:
        respect_instruction = f"The user is your Owner, {OWNER['name']}. Be respectful (Sir/Boss)."

    system_prompt = (
        f"You are a helpful assistant. {lang_instruction}\n"
        f"{respect_instruction}\n"
        "Keep replies very short and direct."
    )

    # 3. Get AI Response
    async with message.channel.typing():
        thread_id = channel_threads.get(channel_id)
        response_data = get_mimo_response(message.content, thread_id, system_prompt)

        if response_data and "response" in response_data:
            final_text = response_data["response"]
            channel_threads[channel_id] = response_data.get("threadId")

            # Owner PFP Logic (As per your original code)
            allow_owner_info = (guild_id == 1349281907765936188)
            if allow_owner_info and OWNER['pfp'] in final_text:
                embed = discord.Embed(description=final_text.replace(OWNER['pfp'], ""), color=discord.Color.blue())
                embed.set_image(url=OWNER['pfp'])
                await message.reply(embed=embed)
            else:
                await message.reply(final_text)
        else:
            await message.reply("⚠️ AI Error (Mimo API).")

if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
