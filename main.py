import discord
import os
from openai import OpenAI

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY') or "gsk_your_key_here"

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

# Improved System Prompt for better bio retention
SYSTEM_PROMPT = (
    f"You are a helpful assistant. Your Owner is {OWNER['name']}.\n\n"
    f"OWNER DETAILS:\n"
    f"- PFP: {OWNER['pfp']}\n"
    f"- ID: {OWNER['id']}\n"
    f"- Username: {OWNER['username']}\n"
    f"- Profile Link: {OWNER['link']}\n"
    f"- Contact: {OWNER['friend']} (Requires mutual friend)\n"
    f"- Guns.lol: {OWNER['gunslol']}\n"
    f"- Favorite Server: 👑 Shivam’s Discord ({OWNER['favserv']})\n\n"
    f"CRITICAL: If asked for the owner's bio, you MUST provide this exact text in full:\n"
    f"{OWNER['bio']}\n\n"
    f"Tone: Chill, explanatory, and adapts to the user."
)

intents = discord.Intents.default()
intents.message_content = True 
discord_client = discord.Client(intents=intents)

@discord_client.event
async def on_ready():
    print(f'✅ Bot is online as {discord_client.user}')

@discord_client.event
async def on_message(message):
    if message.author == discord_client.user:
        return

    async with message.channel.typing():
        try:
            chat_completion = client_ai.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": message.content}
                ],
                model="openai/gpt-oss-20b", 
            )

            final_text = chat_completion.choices[0].message.content

            # --- SENDING LOGIC (Using message.reply) ---
            if OWNER['pfp'] in final_text:
                embed = discord.Embed(
                    title=f"Owner: {OWNER['name']}",
                    description=final_text.replace(OWNER['pfp'], "").strip(),
                    color=discord.Color.blue()
                )
                embed.set_image(url=OWNER['pfp'])
                # .reply() creates the mention/connection to the original message
                await message.reply(embed=embed)

            elif len(final_text) > 2000:
                for i in range(0, len(final_text), 2000):
                    await message.reply(final_text[i:i+2000])
            else:
                await message.reply(final_text)

        except Exception as e:
            print(f"CRASH ERROR: {e}")
            await message.reply("⚠️ Bot encountered an error processing that request.")

if DISCORD_TOKEN:
    discord_client.run(DISCORD_TOKEN)
else:
    print("Error: DISCORD_TOKEN environment variable not set.")
