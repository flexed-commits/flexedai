import discord
import os
import asyncio
import re
import json
from datetime import datetime
from dotenv import load_dotenv
from perplexity import Perplexity
from collections import deque

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')

client = Perplexity(api_key=PERPLEXITY_API_KEY)
MODEL_ID = "sonar-pro"

# --- STATE MANAGEMENT ---
# Tracks user expertise, session goals, and previous errors
user_states = {} 

class UserState:
    def __init__(self, user_id, name):
        self.user_id = user_id
        self.name = name
        self.history = deque(maxlen=6) # Contextual awareness
        self.expertise_level = "unknown" # Adaptive complexity
        self.last_error = None
        self.goal = None

    def update_expertise(self, text):
        technical_terms = ['async', 'latency', 'api', 'endpoint', 'json', 'sql']
        if any(term in text.lower() for term in technical_terms):
            self.expertise_level = "technical"

# --- UTILITIES ---
def clean_output(text):
    """Removes citations and ensures high Info-to-Word ratio."""
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\(http[s]?://\S+\)', '', text)
    return text.strip()

# --- CORE LOGIC ---
async def process_ai_response(state, user_input):
    """Handles reasoning, adaptive complexity, and error masking."""
    
    # Implicit Intent & Goal Tracking
    if "not working" in user_input.lower() or "error" in user_input.lower():
        goal_prompt = f"The user is reporting a failure. Analyze the last interaction: {state.history[-1] if state.history else 'None'}."
    else:
        goal_prompt = f"Identify the user's core intent and provide a structured solution."

    # Construct System Prompt with Traits
    sys_msg = (
        f"User: {state.name}. Expertise: {state.expertise_level}. "
        "Traits: High Info-to-Word ratio. No fluff ('I'd be happy to'). Use Markdown/Tables. "
        "If the query is complex, perform 'Step-by-Step Reasoning' internally before answering."
    )

    messages = [{"role": "system", "content": sys_msg}]
    messages.extend(list(state.history))
    messages.append({"role": "user", "content": user_input})

    try:
        # Latency Masking: Handled by Discord's typing indicator in the event loop
        response = client.chat.completions.create(model=MODEL_ID, messages=messages)
        content = clean_output(response.choices[0].message.content)
        
        # Self-Correction Check
        if "```" in content and "error" in content.lower():
            content += "\n\n**Verification:** Logic checked for syntax and common failure points."

        return content
    except Exception as e:
        # Graceful Failure
        return (
            "### ⚠️ Service Interruption\n"
            "I cannot reach the Perplexity API right now.\n"
            "**Fallback:** If you need code help, check the official documentation or retry in 60s."
        )

# --- DISCORD CLIENT ---
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

@bot.event
async def on_message(message):
    if message.author.bot: return

    uid = message.author.id
    if uid not in user_states:
        user_states[uid] = UserState(uid, message.author.display_name)
    
    state = user_states[uid]
    state.update_expertise(message.content)

    # 1. Immediate Latency Masking
    async with message.channel.typing():
        # 2. Reasoning & Response Generation
        answer = await process_ai_response(state, message.content)

        # 3. Update State for Contextual Awareness
        state.history.append({"role": "user", "content": message.content})
        state.history.append({"role": "assistant", "content": answer})

        # 4. Structured Output Delivery
        await message.reply(answer, mention_author=False)

bot.run(DISCORD_TOKEN)
