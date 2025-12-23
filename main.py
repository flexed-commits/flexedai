import discord
import os
from openai import OpenAI

# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_API_KEY = os.getenv('GROQ_API_KEY') or "gsk_your_key_here"

# Initialize Groq client using OpenAI compatibility
client_ai = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

OWNER = {
    "name": "Ψ.1nOnly.Ψ",
    "username": ".flexed.",
    "pfp": "https://cdn.discordapp.com/avatars/1081876265683927080/a2671291fa7a3f13e03022eeeac15ef2.webp?size=2048",
    "id": "1081876265683927080",
    "link": "https://discord.com/users/1081876265683927080/", # Fixed missing comma here
    "friend": "https://discord.gg/XNNUR4Qn",
    "bio": "Add me as a friend to contact me. Must have a mutual friend to get it done.\nBorn <t:1265842320:R>\nCreated 👑 Shivam’s Discord:\nhttps://discord.gg/bzePwKSDsp\nE-mail: flexed@zohomail.in",
    "gunslol": "https://guns.lol/flexedfr",
    "favserv": "https://discord.gg/bzePwKSDsp",
}

SYSTEM_PROMPT = (
    f"You are a helpful assistant. Owner: {OWNER['name']}. "
    f"If asked for the owner's PFP or image, you MUST include this exact link: {OWNER['pfp']}. "
    f"If asked for owner id, include {OWNER['id']}. "
    f"If asked for owner username, include {OWNER['username']}. "
    f"Be chill and change your tone according to the recipient. "
    f"If asked for the profile link, include {OWNER['link']}. "
    f"If asked how to add the owner, say they must have a mutual friend and include {OWNER['friend']}. "
    f"If asked for bio, include: {OWNER['bio']}. "
    f"If asked for owner's guns.lol, include: {OWNER['gunslol']}. "
    f"If asked for favorite server, mention '👑 Shivam’s Discord' and link {OWNER['favserv']}."
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
                model="openai/gpt-oss-20b", # Changed to a valid Groq model
            )

            final_text = chat_completion.choices[0].message.content

            # --- EMBED LOGIC FOR PFP ---
            if OWNER['pfp'] in final_text:
                # Remove the raw URL from the text so it looks cleaner in the embed
                clean_text = final_text.replace(OWNER['pfp'], "").strip()
                
                embed = discord.Embed(
                    title=f"Owner Profile: {OWNER['name']}",
                    description=clean_text or "Here is the owner's profile picture:",
                    color=discord.Color.blue()
                )
                embed.set_image(url=OWNER['pfp'])
                await message.channel.send(embed=embed)

            # Standard message handling
            elif len(final_text) > 2000:
                for i in range(0, len(final_text), 2000):
                    await message.channel.send(final_text[i:i+2000])
            else:
                await message.channel.send(final_text)

        except Exception as e:
            print(f"CRASH ERROR: {e}")
            await message.channel.send(f"⚠️ Bot encountered an error.")

if DISCORD_TOKEN:
    discord_client.run(DISCORD_TOKEN)
else:
    print("❌ ERROR: No DISCORD_TOKEN found in environment variables.")
