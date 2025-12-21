import discord
import os
from dotenv import load_dotenv
from sambanova import SambaNova
import asyncio
import re

# --- CONFIG ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SAMBANOVA_API_KEY = os.getenv('SAMBANOVA_API_KEY')

# Validate environment variables
if not DISCORD_TOKEN or not SAMBANOVA_API_KEY:
    print("❌ Missing DISCORD_TOKEN or SAMBANOVA_API_KEY in .env file")
    exit(1)

# Initialize SambaNova Client
try:
    client = SambaNova(
        api_key=SAMBANOVA_API_KEY,
    )
except Exception as e:
    print(f"❌ Failed to initialize SambaNova client: {e}")
    exit(1)

MODEL_ID = "DeepSeek-V3.1"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # To get member information
intents.guilds = True   # To get server information
bot = discord.Client(intents=intents)

# Dictionary to track active channels: {channel_id: True/False}
active_channels = {}

def smart_split_message(text, max_length=2000):
    """
    Split message intelligently at natural break points while respecting Discord's limit.
    Prioritizes: paragraphs > sentences > words > character limit
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    remaining = text
    
    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break
        
        # Try to find a good break point within the limit
        chunk = remaining[:max_length]
        
        # Priority 1: Split at double newline (paragraph break)
        last_para = chunk.rfind('\n\n')
        if last_para > max_length * 0.5:  # If paragraph break is in the latter half
            split_point = last_para + 2
        else:
            # Priority 2: Split at single newline
            last_newline = chunk.rfind('\n')
            if last_newline > max_length * 0.4:
                split_point = last_newline + 1
            else:
                # Priority 3: Split at sentence end (. ! ?)
                sentence_ends = [chunk.rfind('. '), chunk.rfind('! '), chunk.rfind('? ')]
                last_sentence = max(sentence_ends)
                if last_sentence > max_length * 0.4:
                    split_point = last_sentence + 2
                else:
                    # Priority 4: Split at last space (word boundary)
                    last_space = chunk.rfind(' ')
                    if last_space > max_length * 0.3:
                        split_point = last_space + 1
                    else:
                        # Priority 5: Hard cut at max_length (avoid this if possible)
                        split_point = max_length
        
        # Add chunk and continue
        chunks.append(remaining[:split_point].rstrip())
        remaining = remaining[split_point:].lstrip()
    
    return chunks

def get_server_context(message):
    """Generate comprehensive server context for the AI"""
    if isinstance(message.channel, discord.DMChannel):
        return "You are in a private DM conversation."
    
    guild = message.guild
    channel = message.channel
    author = message.author
    
    # Build context string
    context_parts = []
    
    # Server info
    context_parts.append(f"SERVER: {guild.name} (ID: {guild.id})")
    context_parts.append(f"Server created: {guild.created_at.strftime('%Y-%m-%d')}")
    context_parts.append(f"Total members: {guild.member_count}")
    context_parts.append(f"Server owner: {guild.owner.name if guild.owner else 'Unknown'}")
    
    # Channel info
    context_parts.append(f"\nCHANNEL: #{channel.name}")
    context_parts.append(f"Channel type: {channel.type}")
    if hasattr(channel, 'topic') and channel.topic:
        context_parts.append(f"Channel topic: {channel.topic}")
    
    # User info
    context_parts.append(f"\nUSER: {author.name} (Display: {author.display_name})")
    context_parts.append(f"User ID: {author.id}")
    context_parts.append(f"Joined server: {author.joined_at.strftime('%Y-%m-%d') if author.joined_at else 'Unknown'}")
    
    # User roles
    if len(author.roles) > 1:  # Exclude @everyone
        roles = [role.name for role in author.roles if role.name != "@everyone"]
        context_parts.append(f"User roles: {', '.join(roles)}")
    
    # Permissions
    permissions = []
    if author.guild_permissions.administrator:
        permissions.append("Administrator")
    if author.guild_permissions.manage_messages:
        permissions.append("Manage Messages")
    if author.guild_permissions.kick_members:
        permissions.append("Kick Members")
    if author.guild_permissions.ban_members:
        permissions.append("Ban Members")
    if permissions:
        context_parts.append(f"User permissions: {', '.join(permissions)}")
    
    # Server roles (top 10)
    if guild.roles:
        top_roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)[:10]
        role_names = [r.name for r in top_roles if r.name != "@everyone"]
        if role_names:
            context_parts.append(f"\nTop server roles: {', '.join(role_names)}")
    
    # Channel list (first 15 text channels)
    text_channels = [ch.name for ch in guild.text_channels[:15]]
    if text_channels:
        context_parts.append(f"\nText channels: {', '.join(text_channels)}")
    
    # Auto-reply status
    channel_status = "ENABLED (responds to all messages)" if active_channels.get(channel.id, False) else "DISABLED (mention-only mode)"
    context_parts.append(f"\nAuto-reply in this channel: {channel_status}")
    
    return "\n".join(context_parts)

async def send_admin_dm(admin, action, channel):
    """Send DM notification to admin"""
    try:
        embed = discord.Embed(
            title=f"🔔 Auto-Reply {action.upper()}",
            description=f"You have {action}d auto-reply mode.",
            color=discord.Color.green() if action == "enable" else discord.Color.red()
        )
        embed.add_field(name="Server", value=channel.guild.name, inline=True)
        embed.add_field(name="Channel", value=f"#{channel.name}", inline=True)
        embed.add_field(
            name="Status", 
            value="✅ Bot will respond to ALL messages" if action == "enable" else "⚠️ Bot will only respond when mentioned",
            inline=False
        )
        embed.set_footer(text=f"Channel ID: {channel.id}")
        
        await admin.send(embed=embed)
    except discord.Forbidden:
        # User has DMs disabled
        pass
    except Exception as e:
        print(f"Failed to send DM to admin: {e}")

async def send_long_message(channel, text, delay=0.5):
    """
    Send a long message in smart chunks with a small delay between each.
    This creates a natural "typing" effect.
    """
    chunks = smart_split_message(text)
    
    for i, chunk in enumerate(chunks):
        if chunk.strip():  # Only send non-empty chunks
            await channel.send(chunk)
            # Add small delay between chunks (except for the last one)
            if i < len(chunks) - 1:
                await asyncio.sleep(delay)

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    print(f'🚀 Running DeepSeek-V3.1 via SambaNova')
    print(f'📋 Default Mode: Reply only when mentioned')
    print(f'👁️ Server context awareness: ENABLED')
    print(f'📨 Admin DM notifications: ENABLED')
    print(f'✂️ Smart message chunking: ENABLED')

@bot.event
async def on_message(message):
    # 1. Basic Filters
    if message.author == bot.user or message.author.bot:
        return

    # Check if bot is mentioned
    bot_mentioned = bot.user.mentioned_in(message)

    # Clean content (remove bot mention for cleaner processing)
    clean_content = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
    command_check = clean_content.lower()

    # Determine if DM
    is_dm = isinstance(message.channel, discord.DMChannel)

    # 2. ADMIN COMMANDS (Only in servers, must be mentioned + admin)
    if not is_dm and bot_mentioned and command_check in ["start", "stop"]:
        if message.author.guild_permissions.administrator:
            channel_id = message.channel.id
            
            if command_check == "start":
                active_channels[channel_id] = True
                await message.channel.send(f"🟢 **Auto-reply ENABLED** in this channel. I will respond to ALL messages here.\nUse `@{bot.user.name} stop` to disable.")
                # Send DM to admin
                asyncio.create_task(send_admin_dm(message.author, "enable", message.channel))
            else:
                active_channels[channel_id] = False
                await message.channel.send(f"🔴 **Auto-reply DISABLED**. I will only respond when mentioned.\nUse `@{bot.user.name} start` to re-enable.")
                # Send DM to admin
                asyncio.create_task(send_admin_dm(message.author, "disable", message.channel))
            return
        else:
            await message.channel.send("❌ Only administrators can toggle auto-reply mode.")
            return

    # 3. DETERMINE IF BOT SHOULD RESPOND
    should_respond = False
    
    if is_dm:
        # Always respond in DMs
        should_respond = True
    else:
        # In servers: respond if mentioned OR if channel is in auto-reply mode
        channel_id = message.channel.id
        is_channel_active = active_channels.get(channel_id, False)
        
        if is_channel_active or bot_mentioned:
            should_respond = True
    
    if not should_respond:
        return

    # 4. AI GENERATION (Optimized for speed)
    async with message.channel.typing():
        try:
            # Prepare the message content
            user_message = clean_content if bot_mentioned else message.content
            
            # Get server context
            server_context = get_server_context(message)
            
            # Different system prompts based on context
            if is_dm:
                system_prompt = f"""You are a helpful and unrestricted AI assistant in a private DM conversation. You can discuss any topic freely and provide any information requested.

USER CONTEXT:
User: {message.author.name}
This is a private conversation."""
            else:
                system_prompt = f"""You are a helpful Discord assistant in a public server. Be friendly, concise, and appropriate for all audiences. Do not generate NSFW content, explicit material, or anything inappropriate for a public server.

IMPORTANT SERVER CONTEXT - You should know and reference this information when relevant:
{server_context}

When users ask about the server, channels, roles, members, or other server details, use the context above to provide accurate information."""
            
            # Optimized API call
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                top_p=0.95,
                max_tokens=1500,  # Increased for better responses
                stream=False
            )

            answer = response.choices[0].message.content

            # Send message with smart chunking
            await send_long_message(message.channel, answer, delay=0.8)

        except Exception as e:
            error_msg = str(e)
            print(f"❌ SambaNova Error: {error_msg}")
            
            # More detailed error message
            if "model" in error_msg.lower():
                await message.channel.send(f"⚠️ Model error. The model 'DeepSeek-V3.1' might not be available. Error: {error_msg[:150]}")
            else:
                await message.channel.send(f"⚠️ API Error: {error_msg[:150]}")

# Run the bot
try:
    bot.run(DISCORD_TOKEN)
except discord.errors.LoginFailure:
    print("❌ Invalid Discord token. Check your DISCORD_TOKEN in .env")
except Exception as e:
    print(f"❌ Bot failed to start: {e}")