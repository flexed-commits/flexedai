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
    # Ignore bot messages
    if message.author.bot:
        return

    content = message.content.lower()
    guild_id = message.guild.id if message.guild else None
    channel_id = message.channel.id

    # --- DYNAMIC PROMPT LOGIC ---
    
    # 1. Check for specific server to allow Owner Bio/Fav Server
    allow_owner_info = (guild_id == 1349281907765936188)

    # 2. Strict Language Rules
    lang_instruction = "Always reply in Hinglish (Hindi written in Roman script)." # Default
    
    if guild_id == 1392347019917660161:
        if channel_id == 1418064211640193127:
            lang_instruction = "STRICT RULE: You MUST reply ONLY in English."
        elif channel_id == 1418064267374231766:
            # Updated: Ab is channel mein bot Hinglish bolega
            lang_instruction = "STRICT RULE: You MUST reply ONLY in Hinglish (Hindi in Roman script)."

    # 3. Respect Logic for Owner
    respect_instruction = ""
    if str(message.author.id) == OWNER['id']:
        respect_instruction = (
            f"CRITICAL: The user you are talking to is your Owner, {OWNER['name']}. "
            "Address him with supreme respect, use words like 'Sir', 'Boss', or 'Master'. "
            "Be extremely polite and helpful to him."
        )

    owner_info_text = ""
    if allow_owner_info:
        owner_info_text = (
            f"OWNER DETAILS:\n- PFP: {OWNER['pfp']}\n- ID: {OWNER['id']}\n- Username: {OWNER['username']}\n"
            f"- Profile Link: {OWNER['link']}\n- Contact: {OWNER['friend']}\n- Guns.lol: {OWNER['gunslol']}\n"
            f"- Favorite Server: 👑 Shivam’s Discord ({OWNER['favserv']})\n"
            f"CRITICAL: If asked for bio, provide this: {OWNER['bio']}"
        )

    system_prompt = (
        f"You are a helpful assistant. Your Owner is {OWNER['name']}.\n"
        f"{lang_instruction}\n"
        f"{respect_instruction}\n"
        f"{owner_info_text}\n"
        f"Tone: Chill and explanatory. Listen to orders carefully."
    )

    # --- COMMANDS ---
    if content == "!ping":
        latency = round(discord_client.latency * 1000)
        await message.reply(f"🏓 Pong! Latency: **{latency}ms**")
        return

    # --- AI CHAT LOGIC ---
    async with message.channel.typing():
        try:
            chat_completion = client_ai.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message.content}
                ],
                model="openai/gpt-oss-20b", 
            )

            final_text = chat_completion.choices[0].message.content

            # Handle Long Messages and Embeds
            if len(final_text) > 2000:
                parts = [final_text[i:i+2000] for i in range(0, len(final_text), 2000)]
                for index, part in enumerate(parts):
                    if index == 0:
                        await message.reply(part, mention_author=True)
                    else:
                        await message.channel.send(part)
            else:
                # Owner PFP Embed logic
                if OWNER['pfp'] in final_text and allow_owner_info:
                    embed = discord.Embed(
                        title=f"Owner: {OWNER['name']}", 
                        description=final_text.replace(OWNER['pfp'], "").strip(), 
                        color=discord.Color.blue()
                    )
                    embed.set_image(url=OWNER['pfp'])
                    await message.reply(embed=embed, mention_author=True)
                else:
                    await message.reply(final_text, mention_author=True)

        except Exception as e:
            print(f"CRASH ERROR: {e}")
            await message.reply("⚠️ Bot encountered an error.")

if DISCORD_TOKEN:
    discord_client.run(DISCORD_TOKEN)
