import discord
import os
import time
from datetime import datetime, timedelta
from openai import OpenAI

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY') or "gsk_your_key_here"
bot_start_time = time.time() 

client_ai = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

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

intents = discord.Intents.default()
intents.message_content = True 
discord_client = discord.Client(intents=intents)

@discord_client.event
async def on_ready():
    print(f'✅ Bot is online as {discord_client.user}')

@discord_client.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.lower()
    guild_id = message.guild.id if message.guild else None
    channel_id = message.channel.id

    # --- DYNAMIC LANGUAGE LOGIC ---
    # Default: Global English
    lang_instruction = "STRICT RULE: Reply ONLY in English."

    # Server-specific Logic
    if guild_id == 1392347019917660161:
        if channel_id == 1418064211640193127:
            lang_instruction = "STRICT RULE: Reply ONLY in English."
        elif channel_id == 1418064267374231766:
            lang_instruction = "STRICT RULE: Reply ONLY in Hinglish (Hindi in Roman script)."
    elif guild_id == 1349281907765936188:
        lang_instruction = "Reply in Hinglish (Hindi written in Roman script)."

    # --- COMMANDS ---
    
    if content == "!ping":
        latency = round(discord_client.latency * 1000)
        await message.reply(f"🏓 Pong! `{latency}ms`")
        return

    if content == "!uptime":
        uptime_diff = int(time.time() - bot_start_time)
        uptime_str = str(timedelta(seconds=uptime_diff))
        await message.reply(f"⏱️ **Uptime:** `{uptime_str}`")
        return

    if content == "!info":
        embed = discord.Embed(title="Bot Status", color=discord.Color.blue())
        embed.add_field(name="Owner", value=OWNER['name'], inline=True)
        embed.add_field(name="Servers", value=len(discord_client.guilds), inline=True)
        embed.add_field(name="Ping", value=f"{round(discord_client.latency * 1000)}ms", inline=True)
        embed.set_footer(text="Short & Fast AI Bot")
        await message.reply(embed=embed)
        return

    # --- AI CHAT LOGIC ---
    allow_owner_info = (guild_id == 1349281907765936188)
    respect_instruction = ""
    if str(message.author.id) == OWNER['id']:
        respect_instruction = f"The user is your Owner, {OWNER['name']}. Be respectful (Sir/Boss)."

    system_prompt = (
        f"You are a helpful assistant. {lang_instruction}\n"
        f"{respect_instruction}\n"
        "CRITICAL: Keep your replies very short, direct, and concise. No long paragraphs."
    )

    async with message.channel.typing():
        try:
            chat_completion = client_ai.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message.content}
                ],
                model="openai/gpt-oss-20b",
                max_tokens=150 # Limiting tokens for shorter responses
            )
            final_text = chat_completion.choices[0].message.content

            if allow_owner_info and OWNER['pfp'] in final_text:
                embed = discord.Embed(description=final_text.replace(OWNER['pfp'], ""), color=discord.Color.blue())
                embed.set_image(url=OWNER['pfp'])
                await message.reply(embed=embed)
            else:
                await message.reply(final_text)
        except Exception as e:
            await message.reply("⚠️ AI Error.")

if DISCORD_TOKEN:
    discord_client.run(DISCORD_TOKEN)
