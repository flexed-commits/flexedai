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
    "link": "https://discord.com/users/1081876265683927080/"
    "friend": "https://discord.gg/XNNUR4Qn",
    "bio": """Add me as a friend to contact me. Must have a mutual friend to get it done.\n
Born <t:1265842320:R>\n
Created 👑 Shivam’s Discord:\n
https://discord.gg/bzePwKSDsp\n
E-mail: flexed@zohomail.in""",
    "gunslol": "https://guns.lol/flexedfr",
    "favserv": "https://discord.gg/bzePwKSDsp",
}

# Explicit instructions in the system prompt to use the link
SYSTEM_PROMPT = f"You are a helpful assistant. Owner: {OWNER['name']}. If asked for the owner's PFP or image, you MUST include this exact link: {OWNER['pfp']},. If asked for owner id then include this {OWNER['id']}. If asked for owner username then include this {OWNER['username']}. Be chill, explanatory, change your tone according to the recepient. If the user asks for owner's profile link then include {OWNER['link']}. If the user asks how can he add the owner, then say that you must have a mutual friend with him to get it done, also include this friend link {OWNER['friend']}. If the user asks for owner's bio then send this along with other request: {OWNER['bio']}. If user asks for owner's guns.lol profile then include: {OWNER['gunslol']}. If user wants to know owner's favorite Discord Server, then tell that it is 👑Shivam’s Discord, and send this invite link: {OWNER['favserv']}"

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

            # --- EMBED LOGIC FOR PFP ---
            # Check if the AI mentioned the PFP link in its response
            if OWNER['pfp'] in final_text:
                embed = discord.Embed(
                    title=f"Owner: {OWNER['name']}",
                    description=final_text.replace(OWNER['pfp'], ""), # Clean the link out of the text
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
            await message.channel.send(f"⚠️ Bot encountered an error: {e}")

discord_client.run(DISCORD_TOKEN)
