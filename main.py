import discord
import os
import time
from datetime import datetime, timedelta
from openai import OpenAI

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY') or "gsk_your_key_here"
bot_start_time = time.time()  # To calculate uptime

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
    # Default: English for all other servers
    lang_instruction = "STRICT RULE: You MUST reply ONLY in English."

    # Specific server logic
    if guild_id == 1392347019917660161:
        if channel_id == 1418064211640193127:
            lang_instruction = "STRICT RULE: You MUST reply ONLY in English."
        elif channel_id == 1418064267374231766:
            lang_instruction = "STRICT RULE: You MUST reply ONLY in Hinglish (Hindi in Roman script)."
    
    # Optional: If you want Hinglish in the second server too
    elif guild_id == 1349281907765936188:
        lang_instruction = "Always reply in Hinglish (Hindi written in Roman script)."

    # --- COMMANDS ---
    
    # 1. Ping Command
    if content == "!ping":
        latency = round(discord_client.latency * 1000)
        await message.reply(f"🏓 Pong! Latency: **{latency}ms**")
        return

    # 2. Uptime Command
    if content == "!uptime":
        current_time = time.time()
        difference = int(round(current_time - bot_start_time))
        uptime_str = str(timedelta(seconds=difference))
        await message.reply(f"⏱️ **Uptime:** `{uptime_str}`")
        return

    # 3. Bot Info Command
    if content == "!info":
        embed = discord.Embed(title="Bot Information", color=discord.Color.gold())
        embed.set_thumbnail(url=discord_client.user.avatar.url if discord_client.user.avatar else None)
        embed.add_field(name="Name", value=discord_client.user.name, inline=True)
        embed.add_field(name="Owner", value=OWNER['name'], inline=True)
        embed.add_field(name="Servers", value=len(discord_client.guilds), inline=True)
        embed.add_field(name="Library", value="Discord.py", inline=True)
        embed.set_footer(text=f"Requested by {message.author}", icon_url=message.author.display_avatar.url)
        await message.reply(embed=embed)
        return

    # --- AI CHAT LOGIC ---
    allow_owner_info = (guild_id == 1349281907765936188)
    
    respect_instruction = ""
    if str(message.author.id) == OWNER['id']:
        respect_instruction = (
            f"CRITICAL: The user is your Owner, {OWNER['name']}. Address him with supreme respect ('Sir'/'Boss')."
        )

    owner_info_text = ""
    if allow_owner_info:
        owner_info_text = f"OWNER DETAILS: {OWNER['bio']}. Use PFP: {OWNER['pfp']} if bio requested."

    system_prompt = (
        f"You are a helpful assistant. {lang_instruction}\n"
        f"{respect_instruction}\n{owner_info_text}\n"
        "Tone: Chill and explanatory."
    )

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

            if len(final_text) > 2000:
                for i in range(0, len(final_text), 2000):
                    await message.channel.send(final_text[i:i+2000])
            else:
                if allow_owner_info and OWNER['pfp'] in final_text:
                    embed = discord.Embed(description=final_text.replace(OWNER['pfp'], ""), color=discord.Color.blue())
                    embed.set_image(url=OWNER['pfp'])
                    await message.reply(embed=embed)
                else:
                    await message.reply(final_text)
        except Exception as e:
            print(f"Error: {e}")
            await message.reply("⚠️ Error connecting to AI.")

if DISCORD_TOKEN:
    discord_client.run(DISCORD_TOKEN)
