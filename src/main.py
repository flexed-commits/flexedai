# Feel free to use my code; Just make sure to edit the hardcoded ids.

import discord
import hashlib, string
from discord.ext import commands, tasks
import os, time, datetime, json, sqlite3, asyncio
from groq import AsyncGroq
from collections import deque
import random
from patreon import PatreonPromoter
from topgg import init_vote_db, start_webhook_server, vote_reminder_loop, role_expiration_loop, check_and_assign_voter_role_on_join
import hashlib
import chess
import aiohttp
from io import BytesIO
from dotenv import load_dotenv
load_dotenv()
user_cooldowns = {}
# --- CONFIGURATION ---
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') 
GROQ_KEYS = [
    os.getenv('GROQ_API_KEY_1'),
    os.getenv('GROQ_API_KEY_2'),
    os.getenv('GROQ_API_KEY_3'),
    os.getenv('GROQ_API_KEY_4'),
    os.getenv('GROQ_API_KEY_5'),
    os.getenv('GROQ_API_KEY_6'),
    os.getenv('GROQ_API_KEY_7')
]
GROQ_KEYS = [key for key in GROQ_KEYS if key] 
MODEL_NAME = "groq/compound" 
OWNER_ID = int(os.getenv('OWNER_ID'))
OWNER_NAME = os.getenv('OWNER_NAME')
DB_FILE = "bot_data.db"
JSON_FILE = "bot_data.json"
INTERACTION_JSON = "interaction_logs.json"
BOT_NAME= os.getenv('BOT_NAME')
ENCODING_FILE="encoding_map.json"
# Logging Channels
LOG_CHANNELS = {
    'server_join_leave': int(os.getenv('LOG_CHANNEL_SERVER_JOIN_LEAVE')),
    'strikes': int(os.getenv('LOG_CHANNEL_STRIKES')),
    'blacklist': int(os.getenv('LOG_CHANNEL_BLACKLIST')),
    'banned_words': int(os.getenv('LOG_CHANNEL_BANNED_WORDS')),
    'admin_logs': int(os.getenv('LOG_CHANNEL_ADMIN_LOGS')),
    'reports': int(os.getenv('LOG_CHANNEL_REPORTS'))
}
SUGGESTION_FORUM_CHANNEL = int(os.getenv('SUGGESTION_FORUM_CHANNEL'))
SUGGESTION_LOG_CHANNEL = int(os.getenv('SUGGESTION_LOG_CHANNEL'))
# Discord message limits
MAX_MESSAGE_LENGTH = 2000
MAX_INPUT_TOKENS = 8000

# Available languages constant
AVAILABLE_LANGUAGES = [
    "English", "Hindi", "Hinglish", "Spanish", "French", 
    "German", "Portuguese", "Italian", "Japanese", "Korean",
    "Chinese", "Russian", "Arabic", "Turkish", "Dutch", "Marathi"
]

# Owner information for bot knowledge
OWNER_INFO = {
    'name': os.getenv('OWNER_NAME'),
    'id': int(os.getenv('OWNER_ID')),
    'bio': os.getenv('OWNER_BIO', f'Creator and core maintainer of {BOT_NAME} Discord Bot')
}

# --- Timezone Adjustments ---
def get_discord_timestamp(dt, style='f'):
    """
    Convert datetime to Discord timestamp format
    Styles: t=time, T=time+sec, d=date, D=date+full, f=datetime, F=datetime+full, R=relative
    """
    if not dt:
        return "Unknown"
    
    # Ensure datetime is timezone-aware (UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    
    timestamp = int(dt.timestamp())
    return f"<t:{timestamp}:{style}>"
    
# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, 
        strikes INTEGER DEFAULT 0, 
        blacklisted INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS banned_words (
        word TEXT PRIMARY KEY
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        id TEXT PRIMARY KEY, 
        prefix TEXT DEFAULT "/", 
        language TEXT DEFAULT "English", 
        mode TEXT DEFAULT "stop"
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        log TEXT, 
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS interaction_logs (
        timestamp REAL, 
        guild_id TEXT, 
        channel_id TEXT, 
        user_name TEXT, 
        user_id TEXT, 
        prompt TEXT, 
        response TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS bot_admins (
        user_id TEXT PRIMARY KEY,
        added_by TEXT,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS word_filter_bypass (
        user_id TEXT PRIMARY KEY,
        added_by TEXT,
        reason TEXT,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS reports (
        report_id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id TEXT,
        reporter_name TEXT,
        reported_user_id TEXT,
        reported_user_name TEXT,
        guild_id TEXT,
        guild_name TEXT,
        reason TEXT,
        proof TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'pending',
        deleted INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS blacklisted_guilds (
        guild_id TEXT PRIMARY KEY,
        guild_name TEXT,
        blacklisted_by TEXT,  -- Ensure this is here
        reason TEXT,
        blacklisted_at DATETIME DEFAULT CURRENT_TIMESTAMP
)''')
    c.execute('''CREATE TABLE IF NOT EXISTS updates_channels (
        guild_id TEXT PRIMARY KEY,
        channel_id TEXT NOT NULL,
        setup_by TEXT,
        setup_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS reaction_responses (
        message_id TEXT PRIMARY KEY,
        channel_id TEXT,
        guild_id TEXT,
        original_author_id TEXT,
        reactor_id TEXT,
        reaction_emoji TEXT,
        bot_response TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS suggestions (
        suggestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        user_name TEXT,
        guild_id TEXT,
        guild_name TEXT,
        guild_icon TEXT,
        title TEXT,
        suggestion TEXT,
        status TEXT DEFAULT 'pending',
        thread_id TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS chess_games (
        game_id INTEGER PRIMARY KEY AUTOINCREMENT,
        player1_id TEXT,
        player2_id TEXT,
        current_turn TEXT,
        board_fen TEXT,
        last_move TEXT,
        message_id TEXT,
        channel_id TEXT,
        status TEXT DEFAULT 'active',
        winner_id TEXT,
        started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        ended_at DATETIME
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS suggestion_cooldowns (
        user_id TEXT PRIMARY KEY,
        last_suggestion_time DATETIME
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS report_cooldowns (
        user_id TEXT PRIMARY KEY,
        last_report_time DATETIME
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS tictactoe_games (
        game_id INTEGER PRIMARY KEY AUTOINCREMENT,
        player1_id TEXT,
        player2_id TEXT,
        current_turn TEXT,
        board TEXT DEFAULT '         ',
        message_id TEXT,
        channel_id TEXT,
        difficulty TEXT,
        is_ai_game INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        winner_id TEXT,
        started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        ended_at DATETIME
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS leaderboard_ai_chat (
        user_id TEXT,
        guild_id TEXT,
        message_count INTEGER DEFAULT 0,
        first_message_date DATE DEFAULT CURRENT_DATE,
        PRIMARY KEY (user_id, guild_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS leaderboard_chess (
        user_id TEXT,
        guild_id TEXT,
        wins INTEGER DEFAULT 0,
        first_win_date DATE DEFAULT CURRENT_DATE,
        PRIMARY KEY (user_id, guild_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS leaderboard_tictactoe (
        user_id TEXT,
        guild_id TEXT,
        difficulty TEXT,
        wins INTEGER DEFAULT 0,
        first_win_date DATE DEFAULT CURRENT_DATE,
        PRIMARY KEY (user_id, guild_id, difficulty)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS server_banned_words (
        guild_id TEXT,
        word TEXT,
        added_by TEXT,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (guild_id, word)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS server_censor_bypass (
        guild_id TEXT,
        user_id TEXT,
        added_by TEXT,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (guild_id, user_id)
    )''')
    conn.commit()
    conn.close()

init_vote_db()

def migrate_json_to_db():
    if not os.path.exists(JSON_FILE):
        print("⚠️ No bot_data.json found. Skipping migration.")
        return

    with open(JSON_FILE, 'r') as f:
        data = json.load(f)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    for user_id in data.get('blacklist', []):
        c.execute("INSERT OR IGNORE INTO users (user_id, blacklisted) VALUES (?, 1)", (str(user_id),))

    for word in data.get('banned_words', []):
        c.execute("INSERT OR IGNORE INTO banned_words (word) VALUES (?)", (word.lower(),))

    for user_id, strikes in data.get('violations', {}).items():
        clean_id = user_id.replace('<@', '').replace('>', '')
        blacklisted = 1 if strikes >= 3 else 0
        c.execute("INSERT OR REPLACE INTO users (user_id, strikes, blacklisted) VALUES (?, ?, ?)", (clean_id, strikes, blacklisted))

    for channel_id, lang in data.get('languages', {}).items():
        c.execute("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", (str(channel_id), lang))

    for guild_id, prefix in data.get('prefixes', {}).items():
        c.execute("INSERT OR REPLACE INTO settings (id, prefix) VALUES (?, ?)", (str(guild_id), prefix))

    for channel_id, mode in data.get('response_mode', {}).items():
        c.execute("INSERT OR REPLACE INTO settings (id, mode) VALUES (?, ?)", (str(channel_id), mode))

    for log in data.get('admin_logs', []):
        c.execute("INSERT INTO admin_logs (log) VALUES (?)", (log,))

    conn.commit()
    conn.close()

    os.rename(JSON_FILE, f"{JSON_FILE}.backup")
    print(f"✅ Migrated bot_data.json → {DB_FILE}")

def migrate_interaction_logs():
    if not os.path.exists(INTERACTION_JSON):
        print("⚠️ No interaction_logs.json found. Skipping migration.")
        return

    with open(INTERACTION_JSON, 'r') as f:
        logs = json.load(f)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    for log in logs:
        c.execute("""INSERT INTO interaction_logs (timestamp, guild_id, channel_id, user_name, user_id, prompt, response) VALUES (?, ?, ?, ?, ?, ?, ?)""", (log['timestamp'], str(log.get('guild_id', 'DM')), str(log['channel_id']), log['user_name'], str(log['user_id']), log['prompt'], log['response']))

    conn.commit()
    conn.close()

    os.rename(INTERACTION_JSON, f"{INTERACTION_JSON}.backup")
    print(f"✅ Migrated interaction_logs.json → {DB_FILE}")

def db_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(query, params)
        conn.commit()
        return c.fetchall() if fetch else None

def is_bot_admin(user_id):
    """Check if user is owner or bot admin"""
    if user_id == OWNER_ID:
        return True
    res = db_query("SELECT user_id FROM bot_admins WHERE user_id = ?", (str(user_id),), fetch=True)
    return bool(res)

def get_channel_language(channel_id):
    """Get the configured language for a channel"""
    res = db_query("SELECT language FROM settings WHERE id = ?", (str(channel_id),), fetch=True)
    return res[0][0] if res and res[0][0] else "English"

def is_bypass_user(user_id):
    """Check if user has word filter bypass"""
    if user_id == OWNER_ID:
        return True
    res = db_query("SELECT user_id FROM word_filter_bypass WHERE user_id = ?", (str(user_id),), fetch=True)
    return bool(res)

def is_guild_blacklisted(guild_id):
    """Check if a guild is blacklisted"""
    res = db_query("SELECT guild_id FROM blacklisted_guilds WHERE guild_id = ?", (str(guild_id),), fetch=True)
    return bool(res)

def has_updates_channel(guild_id):
    """Check if a guild has setup an updates channel"""
    res = db_query("SELECT channel_id FROM updates_channels WHERE guild_id = ?", (str(guild_id),), fetch=True)
    return bool(res)

def get_updates_channel(guild_id):
    """Get the updates channel ID for a guild"""
    res = db_query("SELECT channel_id FROM updates_channels WHERE guild_id = ?", (str(guild_id),), fetch=True)
    return res[0][0] if res else None

def check_suggestion_cooldown(user_id):
    """Check if user can submit a suggestion (1 hour cooldown)"""
    result = db_query(
        "SELECT last_suggestion_time FROM suggestion_cooldowns WHERE user_id = ?",
        (str(user_id),),
        fetch=True
    )
    
    if not result:
        return True, None  # No cooldown record, user can submit
    
    last_time = datetime.datetime.fromisoformat(result[0][0])
    now = datetime.datetime.now(datetime.timezone.utc)
    time_diff = now - last_time
    
    if time_diff.total_seconds() >= 3600:  # 1 hour = 3600 seconds
        return True, None
    
    remaining = 3600 - time_diff.total_seconds()
    return False, remaining


def check_report_cooldown(user_id):
    """Check if user can submit a report (1 hour cooldown)"""
    result = db_query(
        "SELECT last_report_time FROM report_cooldowns WHERE user_id = ?",
        (str(user_id),),
        fetch=True
    )
    
    if not result:
        return True, None  # No cooldown record, user can submit
    
    last_time = datetime.datetime.fromisoformat(result[0][0])
    now = datetime.datetime.now(datetime.timezone.utc)
    time_diff = now - last_time
    
    if time_diff.total_seconds() >= 3600:  # 1 hour = 3600 seconds
        return True, None
    
    remaining = 3600 - time_diff.total_seconds()
    return False, remaining


def update_suggestion_cooldown(user_id):
    """Update the last suggestion time for a user"""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db_query(
        "INSERT OR REPLACE INTO suggestion_cooldowns (user_id, last_suggestion_time) VALUES (?, ?)",
        (str(user_id), now)
    )


def update_report_cooldown(user_id):
    """Update the last report time for a user"""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db_query(
        "INSERT OR REPLACE INTO report_cooldowns (user_id, last_report_time) VALUES (?, ?)",
        (str(user_id), now)
    )

def check_user_cooldown(channel_id: str, user_id: str, cooldown_seconds: float = 1.0):
    """
    Check if user can send message in this channel.
    Returns (can_send, remaining_time)
    """
    import time
    current_time = time.time()
    
    # Initialize channel if not exists
    if channel_id not in user_cooldowns:
        user_cooldowns[channel_id] = {}
    
    # Check if user has cooldown in this channel
    if user_id in user_cooldowns[channel_id]:
        last_time = user_cooldowns[channel_id][user_id]
        time_diff = current_time - last_time
        
        if time_diff < cooldown_seconds:
            remaining = cooldown_seconds - time_diff
            return False, remaining
    
    return True, 0.0


def update_user_cooldown(channel_id: str, user_id: str):
    """Update the last message time for a user in a channel"""
    import time
    
    if channel_id not in user_cooldowns:
        user_cooldowns[channel_id] = {}
    
    user_cooldowns[channel_id][user_id] = time.time()


def check_channel_cooldown(channel_id: str, cooldown_seconds: float = 1.0):
    """
    Check if ANY user can send in this channel (global channel cooldown).
    Returns (can_send, remaining_time, last_user_id)
    """
    import time
    current_time = time.time()
    
    if channel_id not in user_cooldowns or not user_cooldowns[channel_id]:
        return True, 0.0, None
    
    # Find the most recent message in this channel from ANY user
    last_user = max(user_cooldowns[channel_id].items(), key=lambda x: x[1])
    last_user_id, last_time = last_user
    time_diff = current_time - last_time
    
    if time_diff < cooldown_seconds:
        remaining = cooldown_seconds - time_diff
        return False, remaining, last_user_id
    
    return True, 0.0, None
def export_db_to_json():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    data = {}

    c.execute("SELECT * FROM users")
    users = c.fetchall()
    data['users'] = [{"user_id": u[0], "strikes": u[1], "blacklisted": bool(u[2])} for u in users]

    c.execute("SELECT word FROM banned_words")
    data['banned_words'] = [w[0] for w in c.fetchall()]

    c.execute("SELECT * FROM settings")
    settings = c.fetchall()
    data['settings'] = [{"id": s[0], "prefix": s[1], "language": s[2], "mode": s[3]} for s in settings]

    c.execute("SELECT * FROM admin_logs ORDER BY timestamp DESC LIMIT 100")
    logs = c.fetchall()
    data['admin_logs'] = [{"log": l[0], "timestamp": l[1]} for l in logs]

    c.execute("SELECT * FROM bot_admins")
    admins = c.fetchall()
    data['bot_admins'] = [{"user_id": a[0], "added_by": a[1], "added_at": a[2]} for a in admins]

    c.execute("SELECT * FROM word_filter_bypass")
    bypass_users = c.fetchall()
    data['word_filter_bypass'] = [{"user_id": b[0], "added_by": b[1], "reason": b[2], "added_at": b[3]} for b in bypass_users]

    cutoff = time.time() - 86400
    c.execute("SELECT * FROM interaction_logs WHERE timestamp > ? ORDER BY timestamp DESC", (cutoff,))
    interactions = c.fetchall()
    data['interaction_logs'] = [{"timestamp": i[0], "guild_id": i[1], "channel_id": i[2], "user_name": i[3], "user_id": i[4], "prompt": i[5], "response": i[6]} for i in interactions]

    conn.close()
    return data

def is_bot_admin(user_id: int) -> bool:
    """Check if user is a bot admin"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM bot_admins WHERE user_id = ?", (str(user_id),))
    result = c.fetchone() is not None
    conn.close()
    return result or user_id == OWNER_ID

def get_next_suggestion_id():
    """Get the next suggestion ID"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT MAX(suggestion_id) FROM suggestions")
    result = c.fetchone()[0]
    conn.close()
    return (result or 0) + 1

async def log_suggestion_action(bot, suggestion_id, action, admin_name, reason=None):
    """Log suggestion actions to the log channel"""
    try:
        log_channel = bot.get_channel(SUGGESTION_LOG_CHANNEL)
        if not log_channel:
            return
        
        # Get suggestion details
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT * FROM suggestions WHERE suggestion_id = ?", (suggestion_id,))
        result = c.fetchone()
        conn.close()
        
        if not result:
            return
        
        _, user_id, user_name, guild_id, guild_name, _, title, suggestion, status, thread_id, timestamp = result
        
        color_map = {
            'accepted': discord.Color.green(),
            'considered': discord.Color.greyple(),
            'denied': discord.Color.red()
        }
        
        embed = discord.Embed(
            title=f"📋 Suggestion #{suggestion_id} - {action.title()}",
            description=f"**Title:** {title}\n**Suggestion:** {suggestion[:100]}{'...' if len(suggestion) > 100 else ''}",
            color=color_map.get(action.lower(), discord.Color.blue()),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        
        embed.add_field(name="Suggested By", value=f"{user_name} (`{user_id}`)", inline=True)
        embed.add_field(name="From Server", value=f"{guild_name} (`{guild_id}`)", inline=True)
        embed.add_field(name="Actioned By", value=admin_name, inline=True)
        
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        
        if thread_id:
            embed.add_field(name="Thread", value=f"<#{thread_id}>", inline=False)
        
        await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Error logging suggestion action: {e}")


class TicTacToeButton(discord.ui.Button):
    """Individual button for tic-tac-toe grid"""
    def __init__(self, x: int, y: int, player1: str, player2: str, is_ai: bool = False):
        super().__init__(style=discord.ButtonStyle.secondary, label='\u200b', row=y)
        self.x = x
        self.y = y
        self.player1 = player1
        self.player2 = player2
        self.is_ai = is_ai

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: TicTacToe = self.view
        
        # Check if it's the correct player's turn
        current_player = view.player1 if view.current_player == 'X' else view.player2
        if str(interaction.user.id) != current_player:
            await interaction.response.send_message(
                "❌ It's not your turn!", 
                ephemeral=True
            )
            return

        # Make the move
        if view.board[self.y][self.x] == ' ':
            view.board[self.y][self.x] = view.current_player
            self.label = 'X' if view.current_player == 'X' else 'O'
            self.style = discord.ButtonStyle.danger if view.current_player == 'X' else discord.ButtonStyle.success
            self.disabled = True

            # Check for winner
            winner = view.check_winner()
            
            if winner:
                await view.end_game(interaction, winner)
            elif view.is_board_full():
                await view.end_game(interaction, 'Tie')
            else:
                # Switch turns
                view.current_player = 'O' if view.current_player == 'X' else 'X'
                
                # Update database
                board_str = ''.join([''.join(row) for row in view.board])
                current_turn = view.player2 if view.current_player == 'O' else view.player1
                db_query(
                    "UPDATE tictactoe_games SET board = ?, current_turn = ? WHERE game_id = ?",
                    (board_str, current_turn, view.game_id)
                )
                
                await interaction.response.edit_message(
                    embed=view.get_game_embed(),
                    view=view
                )
                
                # If AI's turn, make AI move
                if view.is_ai and view.current_player == 'O':
                    await view.make_ai_move(interaction)


class TicTacToe(discord.ui.View):
    """Main tic-tac-toe game view"""
    children: list[TicTacToeButton]

    def __init__(self, player1: str, player2: str, is_ai: bool = False, difficulty: str = 'Hard', game_id: int = None):
        super().__init__(timeout=600)
        self.player1 = player1
        self.player2 = player2
        self.is_ai = is_ai
        self.difficulty = difficulty
        self.game_id = game_id
        self.current_player = 'X'
        self.board = [[' ' for _ in range(3)] for _ in range(3)]
        
        # Create 3x3 grid
        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y, player1, player2, is_ai))
        
        # Add forfeit button
        forfeit_btn = discord.ui.Button(
            label='🏳️ Forfeit',
            style=discord.ButtonStyle.danger,
            row=3
        )
        forfeit_btn.callback = self.forfeit
        self.add_item(forfeit_btn)

    def check_winner(self) -> str | None:
        """Check if there's a winner"""
        # Check rows
        for row in self.board:
            if row[0] == row[1] == row[2] != ' ':
                return row[0]
        
        # Check columns
        for col in range(3):
            if self.board[0][col] == self.board[1][col] == self.board[2][col] != ' ':
                return self.board[0][col]
        
        # Check diagonals
        if self.board[0][0] == self.board[1][1] == self.board[2][2] != ' ':
            return self.board[0][0]
        if self.board[0][2] == self.board[1][1] == self.board[2][0] != ' ':
            return self.board[0][2]
        
        return None

    def is_board_full(self) -> bool:
        """Check if board is full"""
        return all(cell != ' ' for row in self.board for cell in row)

    def get_game_embed(self) -> discord.Embed:
        """Create game state embed"""
        embed = discord.Embed(
            title="🎮 Tic-Tac-Toe",
            color=discord.Color.blue()
        )
        
        if self.is_ai:
            embed.description = (
                f"**Player X:** <@{self.player1}>\n"
                f"**Player O:** AI ({self.difficulty})\n\n"
                f"**Current Turn:** {'X' if self.current_player == 'X' else 'O'}"
            )
        else:
            current_user = self.player1 if self.current_player == 'X' else self.player2
            embed.description = (
                f"**Player X:** <@{self.player1}>\n"
                f"**Player O:** <@{self.player2}>\n\n"
                f"**Current Turn:** <@{current_user}>"
            )
        
        return embed

    async def end_game(self, interaction: discord.Interaction, winner: str):
        """Handle game end"""
        # Disable all game buttons
        for child in self.children:
            if not isinstance(child, discord.ui.Button) or child.label != '🏳️ Forfeit':
                child.disabled = True
            else:
                # Remove forfeit button
                self.remove_item(child)
        
        if winner == 'Tie':
            embed = discord.Embed(
                title="🎮 Tic-Tac-Toe - Draw!",
                description="🤝 It's a tie! Nobody wins.",
                color=discord.Color.gold()
            )
            db_query(
                "UPDATE tictactoe_games SET status = 'draw', ended_at = CURRENT_TIMESTAMP WHERE game_id = ?",
                (self.game_id,)
            )
        else:
            winner_id = self.player1 if winner == 'X' else self.player2
            winner_symbol = '❌' if winner == 'X' else '⭕'
            
            if self.is_ai and winner == 'O':
                winner_name = f"AI ({self.difficulty})"
            else:
                winner_name = f"<@{winner_id}>"
            
            embed = discord.Embed(
                title=f"🎮 Tic-Tac-Toe - {winner_symbol} Wins!",
                description=f"🎉 **Winner:** {winner_name}",
                color=discord.Color.green()
            )
            
            db_query(
                "UPDATE tictactoe_games SET status = 'finished', winner_id = ?, ended_at = CURRENT_TIMESTAMP WHERE game_id = ?",
                (winner_id, self.game_id)
            )
            if winner_id and winner_id != self.player2 or (not self.is_ai):
                try:
                    guild_id = interaction.guild.id if interaction.guild else None
                    if guild_id and winner_id != 'AI':
                        increment_tictactoe_wins(int(winner_id), guild_id, self.difficulty)
                except:
                    pass
        
        # Always add "New Game" button for all scenarios
        new_game_btn = discord.ui.Button(
            label='🎮 New Game',
            style=discord.ButtonStyle.success,
            custom_id=f'ttt_new_{self.game_id}'
        )
        new_game_btn.callback = self.create_new_game_callback(winner == 'Tie')
        self.add_item(new_game_btn)
        
        await interaction.response.edit_message(embed=embed, view=self)
        
    def create_restart_callback(self):
        """Create callback for restart button (draw games)"""
        async def restart_callback(interaction: discord.Interaction):
            # Check if user is in the game
            if str(interaction.user.id) not in [self.player1, self.player2]:
                await interaction.response.send_message(
                    "❌ Only players in this game can restart!",
                    ephemeral=True
                )
                return
            
            if self.is_ai:
                # Restart AI game with same difficulty
                new_game = TicTacToe(
                    player1=self.player1,
                    player2=self.player2,
                    is_ai=True,
                    difficulty=self.difficulty,
                    game_id=None
                )
                
                # Create new game in database
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute(
                    """INSERT INTO tictactoe_games 
                    (player1_id, player2_id, current_turn, channel_id, is_ai_game, ai_difficulty) 
                    VALUES (?, ?, ?, ?, 1, ?)""",
                    (self.player1, self.player2, self.player1, str(interaction.channel.id), self.difficulty)
                )
                new_game.game_id = c.lastrowid
                conn.commit()
                conn.close()
                
                await interaction.response.edit_message(
                    embed=new_game.get_game_embed(),
                    view=new_game
                )
                
                # Update message_id
                msg = await interaction.original_response()
                db_query(
                    "UPDATE tictactoe_games SET message_id = ? WHERE game_id = ?",
                    (str(msg.id), new_game.game_id)
                )
            else:
                # PvP restart - send new invitation
                invite_embed = discord.Embed(
                    title="🎮 Tic-Tac-Toe Rematch",
                    description=f"**{interaction.user.mention}** wants a rematch!\n\n**Player X:** <@{self.player1}>\n**Player O:** <@{self.player2}>",
                    color=discord.Color.blue()
                )
                
                invite_view = TicTacToeInvite(
                    challenger_id=self.player1,
                    opponent_id=self.player2,
                    channel_id=str(interaction.channel.id)
                )
                
                await interaction.response.edit_message(embed=invite_embed, view=invite_view)
        
        return restart_callback
    
    def create_new_game_callback(self, is_draw: bool):
        """Create callback for new game button"""
        async def new_game_callback(interaction: discord.Interaction):
            # Check if user is in the game
            if str(interaction.user.id) not in [self.player1, self.player2]:
                await interaction.response.send_message(
                    "❌ Only players in this game can start a new game!",
                    ephemeral=True
                )
                return
            
            if self.is_ai:
                # AI GAME
                if is_draw:
                    # DRAW: Start new game with same difficulty immediately
                    new_game = TicTacToe(
                        player1=self.player1,
                        player2=self.player2,
                        is_ai=True,
                        difficulty=self.difficulty,
                        game_id=None
                    )
                    
                    # Create new game in database
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute(
                        """INSERT INTO tictactoe_games 
                        (player1_id, player2_id, current_turn, channel_id, is_ai_game, ai_difficulty) 
                        VALUES (?, ?, ?, ?, 1, ?)""",
                        (self.player1, self.player2, self.player1, str(interaction.channel.id), self.difficulty)
                    )
                    new_game.game_id = c.lastrowid
                    conn.commit()
                    conn.close()
                    
                    await interaction.response.edit_message(
                        embed=new_game.get_game_embed(),
                        view=new_game
                    )
                    
                    # Update message_id
                    msg = await interaction.original_response()
                    db_query(
                        "UPDATE tictactoe_games SET message_id = ? WHERE game_id = ?",
                        (str(msg.id), new_game.game_id)
                    )
                else:
                    # WIN/LOSE: Show difficulty selector first
                    difficulty_select = discord.ui.Select(
                        placeholder="Select AI Difficulty",
                        options=[
                            discord.SelectOption(label="Easy", value="Easy", emoji="😴"),
                            discord.SelectOption(label="Middle", value="Middle", emoji="🤔"),
                            discord.SelectOption(label="Hard", value="Hard", emoji="😤"),
                            discord.SelectOption(label="Insane", value="Insane", emoji="😈")
                        ]
                    )
                    
                    async def difficulty_callback(select_interaction: discord.Interaction):
                        selected_difficulty = difficulty_select.values[0]
                        
                        # Create new AI game with selected difficulty
                        new_game = TicTacToe(
                            player1=self.player1,
                            player2=self.player2,
                            is_ai=True,
                            difficulty=selected_difficulty,
                            game_id=None
                        )
                        
                        # Create new game in database
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute(
                            """INSERT INTO tictactoe_games 
                            (player1_id, player2_id, current_turn, channel_id, is_ai_game, ai_difficulty) 
                            VALUES (?, ?, ?, ?, 1, ?)""",
                            (self.player1, self.player2, self.player1, str(select_interaction.channel.id), selected_difficulty)
                        )
                        new_game.game_id = c.lastrowid
                        conn.commit()
                        conn.close()
                        
                        await select_interaction.response.edit_message(
                            embed=new_game.get_game_embed(),
                            view=new_game
                        )
                        
                        # Update message_id
                        msg = await select_interaction.original_response()
                        db_query(
                            "UPDATE tictactoe_games SET message_id = ? WHERE game_id = ?",
                            (str(msg.id), new_game.game_id)
                        )
                    
                    difficulty_select.callback = difficulty_callback
                    
                    select_view = discord.ui.View()
                    select_view.add_item(difficulty_select)
                    
                    select_embed = discord.Embed(
                        title="🎮 New Tic-Tac-Toe Game",
                        description="Select AI difficulty to start a new game:",
                        color=discord.Color.blue()
                    )
                    
                    await interaction.response.edit_message(embed=select_embed, view=select_view)
            else:
                # PvP GAME: Send invitation for all scenarios (draw/win/lose)
                invite_embed = discord.Embed(
                    title="🎮 Tic-Tac-Toe Invitation",
                    description=f"**{interaction.user.mention}** wants to play again!\n\n**Player X:** <@{self.player1}>\n**Player O:** <@{self.player2}>",
                    color=discord.Color.blue()
                )
                
                invite_view = TicTacToeInvite(
                    challenger_id=self.player1,
                    opponent_id=self.player2,
                    channel_id=str(interaction.channel.id)
                )
                
                await interaction.response.edit_message(embed=invite_embed, view=invite_view)
        
        return new_game_callback

    async def forfeit(self, interaction: discord.Interaction):
        """Handle forfeit button"""
        # Check if user is in the game
        if str(interaction.user.id) not in [self.player1, self.player2]:
            await interaction.response.send_message(
                "❌ You're not in this game!",
                ephemeral=True
            )
            return
        
        # Determine winner (the other player)
        winner_id = self.player2 if str(interaction.user.id) == self.player1 else self.player1
        winner_symbol = 'O' if str(interaction.user.id) == self.player1 else 'X'
        
        # Disable all buttons
        for child in self.children:
            child.disabled = True
        
        if self.is_ai and winner_id == self.player2:
            winner_name = f"AI ({self.difficulty})"
        else:
            winner_name = f"<@{winner_id}>"
        
        embed = discord.Embed(
            title="🎮 Tic-Tac-Toe - Forfeit",
            description=f"<@{interaction.user.id}> forfeited!\n🎉 **Winner:** {winner_name}",
            color=discord.Color.orange()
        )
        
        db_query(
            "UPDATE tictactoe_games SET status = 'forfeit', winner_id = ?, ended_at = CURRENT_TIMESTAMP WHERE game_id = ?",
            (winner_id, self.game_id)
        )
        
        await interaction.response.edit_message(embed=embed, view=self)

    def minimax(self, board: list, depth: int, is_maximizing: bool) -> int:
        """Minimax algorithm for optimal AI moves"""
        # Check terminal states
        winner = self.check_winner_state(board)
        if winner == 'O':
            return 10 - depth
        elif winner == 'X':
            return depth - 10
        elif self.is_board_full_state(board):
            return 0
        
        if is_maximizing:
            best_score = -float('inf')
            for y in range(3):
                for x in range(3):
                    if board[y][x] == ' ':
                        board[y][x] = 'O'
                        score = self.minimax(board, depth + 1, False)
                        board[y][x] = ' '
                        best_score = max(score, best_score)
            return best_score
        else:
            best_score = float('inf')
            for y in range(3):
                for x in range(3):
                    if board[y][x] == ' ':
                        board[y][x] = 'X'
                        score = self.minimax(board, depth + 1, True)
                        board[y][x] = ' '
                        best_score = min(score, best_score)
            return best_score

    def check_winner_state(self, board: list) -> str | None:
        """Check winner for a given board state"""
        # Check rows
        for row in board:
            if row[0] == row[1] == row[2] != ' ':
                return row[0]
        
        # Check columns
        for col in range(3):
            if board[0][col] == board[1][col] == board[2][col] != ' ':
                return board[0][col]
        
        # Check diagonals
        if board[0][0] == board[1][1] == board[2][2] != ' ':
            return board[0][0]
        if board[0][2] == board[1][1] == board[2][0] != ' ':
            return board[0][2]
        
        return None

    def is_board_full_state(self, board: list) -> bool:
        """Check if board state is full"""
        return all(cell != ' ' for row in board for cell in row)

    def get_best_move(self) -> tuple[int, int] | None:
        """Get best move using minimax"""
        best_score = -float('inf')
        best_move = None
        
        for y in range(3):
            for x in range(3):
                if self.board[y][x] == ' ':
                    self.board[y][x] = 'O'
                    score = self.minimax(self.board, 0, False)
                    self.board[y][x] = ' '
                    
                    if score > best_score:
                        best_score = score
                        best_move = (x, y)
        
        return best_move

    def get_random_move(self) -> tuple[int, int] | None:
        """Get random available move"""
        available = []
        for y in range(3):
            for x in range(3):
                if self.board[y][x] == ' ':
                    available.append((x, y))
        
        return random.choice(available) if available else None

    def get_ai_move_by_difficulty(self) -> tuple[int, int] | None:
        """Get AI move based on difficulty"""
        difficulty_chances = {
            'Easy': 0.30,
            'Middle': 0.50,
            'Hard': 0.70,
            'Insane': 0.85
        }
        
        optimal_chance = difficulty_chances.get(self.difficulty, 0.70)
        
        # Decide whether to play optimally or randomly
        if random.random() < optimal_chance:
            return self.get_best_move()
        else:
            return self.get_random_move()

    async def make_ai_move(self, interaction: discord.Interaction):
        """Make AI move"""
        await asyncio.sleep(1)  # Small delay for realism
        
        move = self.get_ai_move_by_difficulty()
        if not move:
            return
        
        x, y = move
        self.board[y][x] = 'O'
        
        # Update button
        for child in self.children:
            if isinstance(child, TicTacToeButton) and child.x == x and child.y == y:
                child.label = 'O'
                child.style = discord.ButtonStyle.success
                child.disabled = True
                break
        
        # Check winner
        winner = self.check_winner()
        
        if winner:
            await self.end_game(interaction, winner)
        elif self.is_board_full():
            await self.end_game(interaction, 'Tie')
        else:
            # Switch back to player
            self.current_player = 'X'
            
            # Update database
            board_str = ''.join([''.join(row) for row in self.board])
            db_query(
                "UPDATE tictactoe_games SET board = ?, current_turn = ? WHERE game_id = ?",
                (board_str, self.player1, self.game_id)
            )
            
            await interaction.edit_original_response(
                embed=self.get_game_embed(),
                view=self
            )


class DifficultySelect(discord.ui.Select):
    """Difficulty selection dropdown"""
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Easy",
                description="AI has 30% win chance",
                emoji="🟢"
            ),
            discord.SelectOption(
                label="Middle",
                description="AI has 50% win chance",
                emoji="🟡"
            ),
            discord.SelectOption(
                label="Hard",
                description="AI has 70% win chance",
                emoji="🟠"
            ),
            discord.SelectOption(
                label="Insane",
                description="AI has 85% win chance",
                emoji="🔴"
            )
        ]
        super().__init__(
            placeholder="Select difficulty...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        difficulty = self.values[0]
        player1_id = str(interaction.user.id)
        player2_id = "AI"
        
        # Create game in database
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            """INSERT INTO tictactoe_games 
            (player1_id, player2_id, current_turn, channel_id, difficulty, is_ai_game) 
            VALUES (?, ?, ?, ?, ?, 1)""",
            (player1_id, player2_id, player1_id, str(interaction.channel.id), difficulty)
        )
        game_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Create game view
        game_view = TicTacToe(
            player1=player1_id,
            player2=player2_id,
            is_ai=True,
            difficulty=difficulty,
            game_id=game_id
        )
        
        await interaction.response.edit_message(
            embed=game_view.get_game_embed(),
            view=game_view
        )
        
        # Update message_id
        msg = await interaction.original_response()
        db_query(
            "UPDATE tictactoe_games SET message_id = ? WHERE game_id = ?",
            (str(msg.id), game_id)
        )


class DifficultyView(discord.ui.View):
    """View containing difficulty selector"""
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(DifficultySelect())


class TicTacToeInvite(discord.ui.View):
    """Invite view for PvP games"""
    def __init__(self, challenger_id: str, opponent_id: str, channel_id: str):
        super().__init__(timeout=600)
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.channel_id = channel_id

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.opponent_id:
            await interaction.response.send_message(
                "❌ This invite is not for you!",
                ephemeral=True
            )
            return
        
        # Create game
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            """INSERT INTO tictactoe_games 
            (player1_id, player2_id, current_turn, channel_id, is_ai_game) 
            VALUES (?, ?, ?, ?, 0)""",
            (self.challenger_id, self.opponent_id, self.challenger_id, self.channel_id)
        )
        game_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Create game view
        game_view = TicTacToe(
            player1=self.challenger_id,
            player2=self.opponent_id,
            is_ai=False,
            game_id=game_id
        )
        
        await interaction.response.edit_message(
            embed=game_view.get_game_embed(),
            view=game_view
        )
        
        # Update message_id
        msg = await interaction.original_response()
        db_query(
            "UPDATE tictactoe_games SET message_id = ? WHERE game_id = ?",
            (str(msg.id), game_id)
        )

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.opponent_id:
            await interaction.response.send_message(
                "❌ This invite is not for you!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🎮 Invite Declined",
            description=f"<@{self.opponent_id}> declined the game.",
            color=discord.Color.red()
        )
        
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        """Called when the invitation expires after 300 seconds"""
        expired_embed = discord.Embed(
            title="⏱️ Invitation Expired",
            description=f"~~**{self.challenger_mention}** has challenged **{self.opponent_mention}** to a game!~~\n\n"
                        f"**This invitation has expired.**\n"
                        f"Challenge them again to start a new game!",
            color=discord.Color.red()
        )
        expired_embed.set_footer(text="Invitation expired after 5 minutes")
        
        try:
            await self.message.edit(content=None, embed=expired_embed, view=None)
        except:
            pass
class SuggestionActionModal(discord.ui.Modal):
    def __init__(self, action: str, suggestion_id: int, thread, original_embed, user_id: str):
        self.action = action
        self.suggestion_id = suggestion_id
        self.thread = thread
        self.original_embed = original_embed
        self.user_id = user_id
        
        title_map = {
            'accepted': 'Accept Suggestion',
            'considered': 'Consider Suggestion',
            'denied': 'Deny Suggestion'
        }
        super().__init__(title=title_map.get(action, 'Action'))
        
        # Reason is optional for accepted, required for others
        required = action != 'accepted'
        self.reason_input = discord.ui.TextInput(
            label='Reason',
            placeholder='Provide a reason...' if required else 'Provide a reason (optional)...',
            required=required,
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.add_item(self.reason_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason_input.value.strip() if self.reason_input.value else None
        
        # Update database
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE suggestions SET status = ? WHERE suggestion_id = ?", 
                 (self.action, self.suggestion_id))
        conn.commit()
        conn.close()
        
        # Update embed
        color_map = {
            'accepted': discord.Color.green(),
            'considered': discord.Color.greyple(),
            'denied': discord.Color.red()
        }
        
        status_emoji = {
            'accepted': '✅',
            'considered': '⏳',
            'denied': '❌'
        }
        
        new_embed = discord.Embed(
            title=self.original_embed.title,
            description=self.original_embed.description,
            color=color_map.get(self.action, discord.Color.blue()),
            timestamp=self.original_embed.timestamp
        )
        
        if self.original_embed.author:
            new_embed.set_author(
                name=self.original_embed.author.name,
                icon_url=self.original_embed.author.icon_url
            )
        
        if self.original_embed.thumbnail:
            new_embed.set_thumbnail(url=self.original_embed.thumbnail.url)
        
        if self.original_embed.footer:
            new_embed.set_footer(text=self.original_embed.footer.text)
        
        new_embed.add_field(
            name=f"Status: {status_emoji.get(self.action, '📋')} {self.action.title()}",
            value=f"Actioned by {interaction.user.mention}",
            inline=False
        )
        
        if reason:
            new_embed.add_field(name="Reason", value=reason, inline=False)
        
        # Edit thread starter message
        starter_message = None
        async for message in self.thread.history(limit=1, oldest_first=True):
            starter_message = message
            break
        
        if starter_message:
            await starter_message.edit(embed=new_embed, view=None)
        
        # DM the user
        try:
            user = await interaction.client.fetch_user(int(self.user_id))
            
            dm_embed = discord.Embed(
                title=f"{status_emoji.get(self.action, '📋')} Your Suggestion has been {self.action.title()}",
                description=f"**Suggestion ID:** #{self.suggestion_id}\n**Title:** {self.original_embed.title.replace('New suggestion #' + str(self.suggestion_id), '').strip()}",
                color=color_map.get(self.action, discord.Color.blue()),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            
            if reason:
                dm_embed.add_field(name="Reason", value=reason, inline=False)
            
            if self.action == 'accepted':
                dm_embed.add_field(
                    name="What's Next?",
                    value="Your suggestion has been accepted and will be implemented soon!",
                    inline=False
                )
            elif self.action == 'considered':
                dm_embed.add_field(
                    name="What's Next?",
                    value="Your suggestion is being considered and may be added in the future.",
                    inline=False
                )
            elif self.action == 'denied':
                dm_embed.add_field(
                    name="What's Next?",
                    value="Your suggestion has been reviewed but won't be implemented at this time.",
                    inline=False
                )
            
            dm_embed.set_footer(text=f"Suggestion Thread: {self.thread.name}")
            
            await user.send(embed=dm_embed)
        except Exception as e:
            print(f"Could not DM user: {e}")
        
        # Log the action
        await log_suggestion_action(
            interaction.client,
            self.suggestion_id,
            self.action,
            interaction.user.name,
            reason
        )
        
        await interaction.response.send_message(
            f"✅ Suggestion #{self.suggestion_id} marked as **{self.action}**!",
            ephemeral=True
        )

class SuggestionButtonView(discord.ui.View):
    def __init__(self, suggestion_id: int, user_id: str, original_embed):
        super().__init__(timeout=None)
        self.suggestion_id = suggestion_id
        self.user_id = user_id
        self.original_embed = original_embed
    
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, custom_id="accept_suggestion")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bot_admin(interaction.user.id):
            await interaction.response.send_message("❌ Only bot admins can use this button!", ephemeral=True)
            return
        
        modal = SuggestionActionModal('accepted', self.suggestion_id, interaction.channel, self.original_embed, self.user_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Consider", style=discord.ButtonStyle.secondary, custom_id="consider_suggestion")
    async def consider_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bot_admin(interaction.user.id):
            await interaction.response.send_message("❌ Only bot admins can use this button!", ephemeral=True)
            return
        
        modal = SuggestionActionModal('considered', self.suggestion_id, interaction.channel, self.original_embed, self.user_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="deny_suggestion")
    async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bot_admin(interaction.user.id):
            await interaction.response.send_message("❌ Only bot admins can use this button!", ephemeral=True)
            return
        
        modal = SuggestionActionModal('denied', self.suggestion_id, interaction.channel, self.original_embed, self.user_id)
        await interaction.response.send_modal(modal)

async def board_to_image(board: chess.Board, last_move: chess.Move = None) -> BytesIO:
    """Convert chess board to image using backscattering.de API"""
    try:
        # Get FEN from board
        fen = board.fen()
        
        # Build URL
        url = f"https://backscattering.de/web-boardimage/board.png?coordinates=true&fen={fen}"
        
        # Add last move if available
        if last_move:
            lastmove_str = last_move.uci()
            url += f"&lastmove={lastmove_str}"
        
        # Fetch the image
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    image_io = BytesIO(image_data)
                    image_io.seek(0)
                    return image_io
                else:
                    raise Exception(f"Failed to fetch board image: HTTP {response.status}")
    except Exception as e:
        print(f"Error fetching board image: {e}")
        raise

def get_active_game(user_id: str):
    """Get active game for a user"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT * FROM chess_games 
                 WHERE (player1_id = ? OR player2_id = ?) 
                 AND status = 'active' 
                 ORDER BY started_at DESC LIMIT 1''', 
             (user_id, user_id))
    result = c.fetchone()
    conn.close()
    return result

def update_game_board(game_id: int, board_fen: str, current_turn: str, last_move: str = None):
    """Update game board state"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if last_move:
        c.execute("UPDATE chess_games SET board_fen = ?, current_turn = ?, last_move = ? WHERE game_id = ?",
                 (board_fen, current_turn, last_move, game_id))
    else:
        c.execute("UPDATE chess_games SET board_fen = ?, current_turn = ? WHERE game_id = ?",
                 (board_fen, current_turn, game_id))
    conn.commit()
    conn.close()

def end_game(game_id: int, winner_id: str = None):
    """End a chess game"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''UPDATE chess_games 
                 SET status = 'completed', winner_id = ?, ended_at = CURRENT_TIMESTAMP 
                 WHERE game_id = ?''',
             (winner_id, game_id))
    conn.commit()
    conn.close()

class ChessMoveModal(discord.ui.Modal):
    def __init__(self, game_id: int, board: chess.Board, player_id: str, message, is_vs_ai: bool = False):
        super().__init__(title="Make a Chess Move")
        self.game_id = game_id
        self.board = board
        self.player_id = player_id
        self.message = message
        self.is_vs_ai = is_vs_ai
        
        self.move_input = discord.ui.TextInput(
            label='Move',
            placeholder='e.g., e2e4, Nf3, O-O',
            required=True,
            max_length=10,
            style=discord.TextStyle.short
        )
        self.add_item(self.move_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        move_str = self.move_input.value.strip()
        
        try:
            # Parse and make the move
            move = self.board.parse_san(move_str)
            self.board.push(move)
            
            # Store the last move
            last_move = move
            
            # Check game status
            game_over = False
            result_text = ""
            winner_id = None
            
            if self.board.is_checkmate():
                game_over = True
                winner_id = self.player_id
                result_text = f"🏆 Checkmate! <@{self.player_id}> wins!"
            elif self.board.is_stalemate():
                game_over = True
                result_text = "🤝 Stalemate! The game is a draw."
            elif self.board.is_insufficient_material():
                game_over = True
                result_text = "🤝 Draw by insufficient material."
            elif self.board.is_fifty_moves():
                game_over = True
                result_text = "🤝 Draw by fifty-move rule."
            elif self.board.is_repetition():
                game_over = True
                result_text = "🤝 Draw by threefold repetition."
            
# If playing against AI and game is not over, make AI move
            ai_move_text = ""
            if self.is_vs_ai and not game_over:
                # Simple AI: random legal move (you can integrate real Stockfish here)
                import random
                ai_move = random.choice(list(self.board.legal_moves))
                self.board.push(ai_move)
                last_move = ai_move  # Update last move to AI's move
                ai_move_text = f"\n🤖 Stockfish played: `{ai_move.uci()}`"
                
                # Check again after AI move
                if self.board.is_checkmate():
                    game_over = True
                    result_text = "🏆 Checkmate! Stockfish wins!"
                    winner_id = "stockfish"
                elif self.board.is_stalemate():
                    game_over = True
                    result_text = "🤝 Stalemate! The game is a draw."
            
            # Update database
            if game_over:
                end_game(self.game_id, winner_id)
                # Increment chess leaderboard if player won against AI
                if winner_id and winner_id != "stockfish" and self.is_vs_ai:
                    try:
                        guild_id = interaction.guild.id if interaction.guild else None
                        if guild_id:
                            increment_chess_wins(int(winner_id), guild_id)
                    except Exception as e:
                        print(f"Failed to increment chess leaderboard: {e}")
            else:
                # Switch turn
                if self.is_vs_ai:
                    current_turn = self.player_id
                else:
                    # Get opponent ID from database
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("SELECT player1_id, player2_id FROM chess_games WHERE game_id = ?", (self.game_id,))
                    p1, p2 = c.fetchone()
                    conn.close()
                    current_turn = p2 if p1 == self.player_id else p1
                
                update_game_board(self.game_id, self.board.fen(), current_turn, last_move.uci())
            
            # Update board image (with last move highlighted)
            board_image = await board_to_image(self.board, last_move)
            file = discord.File(board_image, filename="chess_board.png")
            
            # Create updated embed
            embed = discord.Embed(
                title="♟️ Chess Game",
                description=f"**Move:** `{move_str}`{ai_move_text}\n\n" + 
                           (result_text if game_over else f"**Current turn:** <@{current_turn}>"),
                color=discord.Color.green() if game_over else discord.Color.blue()
            )
            
            embed.set_image(url="attachment://chess_board.png")
            
            if self.board.is_check() and not game_over:
                embed.add_field(name="⚠️ Check!", value="The king is in check!", inline=False)
            
            # Update view
            if game_over:
                # Create "New Game" button view
                new_game_view = discord.ui.View(timeout=None)
                
                if self.is_vs_ai:
                    # AI Game: Start new game vs AI button
                    new_game_btn = discord.ui.Button(
                        label='♟️ New Game vs AI',
                        style=discord.ButtonStyle.success,
                        custom_id=f'chess_new_ai_{self.game_id}_{self.player_id}'
                    )
                    
                    async def new_ai_game_callback(btn_interaction: discord.Interaction):
                        if str(btn_interaction.user.id) != self.player_id:
                            await btn_interaction.response.send_message(
                                "❌ Only the original player can start a new game!",
                                ephemeral=True
                            )
                            return
                        
                        # Start new AI chess game
                        await btn_interaction.response.defer()
                        ctx = await bot.get_context(btn_interaction.message)
                        await bot.get_command('chess').callback(ctx, opponent=None)
                        await btn_interaction.followup.send("🎮 New chess game started!", ephemeral=True)
                    
                    new_game_btn.callback = new_ai_game_callback
                else:
                    # PvP Game: Send invitation button
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("SELECT player1_id, player2_id FROM chess_games WHERE game_id = ?", (self.game_id,))
                    p1, p2 = c.fetchone()
                    conn.close()
                    
                    opponent_id = p2 if p1 == self.player_id else p1
                    
                    new_game_btn = discord.ui.Button(
                        label='♟️ New Game (Send Invitation)',
                        style=discord.ButtonStyle.success,
                        custom_id=f'chess_new_pvp_{self.game_id}_{self.player_id}_{opponent_id}'
                    )
                    
                    async def new_pvp_game_callback(btn_interaction: discord.Interaction):
                        if str(btn_interaction.user.id) not in [p1, p2]:
                            await btn_interaction.response.send_message(
                                "❌ Only players from the original game can start a new game!",
                                ephemeral=True
                            )
                            return
                        
                        # Determine opponent
                        if str(btn_interaction.user.id) == p1:
                            opp_id = p2
                        else:
                            opp_id = p1
                        
                        # Send invitation
                        invite_embed = discord.Embed(
                            title="♟️ Chess Rematch!",
                            description=f"{btn_interaction.user.mention} challenges <@{opp_id}> to a rematch!",
                            color=discord.Color.blue()
                        )
                        
                        invite_view = ChessInviteView(
                            challenger_id=str(btn_interaction.user.id),
                            opponent_id=opp_id
                        )
                        
                        await btn_interaction.response.send_message(embed=invite_embed, view=invite_view)
                    
                    new_game_btn.callback = new_pvp_game_callback
                
                new_game_view.add_item(new_game_btn)
                await self.message.edit(embed=embed, view=new_game_view, attachments=[file])
            else:
                view = ChessGameView(self.game_id, self.board, current_turn, self.is_vs_ai)
                await self.message.edit(embed=embed, view=view, attachments=[file])
            
            await interaction.response.send_message(f"✅ Move played: `{move_str}`", ephemeral=True)
            
        except ValueError as e:
            await interaction.response.send_message(f"❌ `{move_str}` is an invalid move. Please use standard chess notation (e.g., e4, Nf3, O-O).", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
            import traceback
            traceback.print_exc()

# --- Add Button View Classes ---

class ChessGameView(discord.ui.View):
    def __init__(self, game_id: int, board: chess.Board, current_player_id: str, is_vs_ai: bool = False):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.board = board
        self.current_player_id = current_player_id
        self.is_vs_ai = is_vs_ai
    
    @discord.ui.button(label="Move", style=discord.ButtonStyle.primary, emoji="♟️")
    async def move_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if it's the player's turn
        if str(interaction.user.id) != self.current_player_id:
            await interaction.response.send_message("❌ It's not your turn!", ephemeral=True)
            return
        
        modal = ChessMoveModal(self.game_id, self.board, str(interaction.user.id), interaction.message, self.is_vs_ai)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Resign", style=discord.ButtonStyle.danger, emoji="🏳️")
    async def resign_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user is a player in the game
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT player1_id, player2_id FROM chess_games WHERE game_id = ?", (self.game_id,))
        result = c.fetchone()
        conn.close()
        
        if not result:
            await interaction.response.send_message("❌ Game not found!", ephemeral=True)
            return
        
        player1_id, player2_id = result
        
        if str(interaction.user.id) not in [player1_id, player2_id]:
            await interaction.response.send_message("❌ You are not a player in this game!", ephemeral=True)
            return
        
        # Determine winner
        winner_id = player2_id if str(interaction.user.id) == player1_id else player1_id
        resigner_id = str(interaction.user.id)
        
        # End game
        end_game(self.game_id, winner_id if not self.is_vs_ai else "stockfish")
        
        # Update embed (no last move for resignation)
        board_image = await board_to_image(self.board)
        file = discord.File(board_image, filename="chess_board.png")
        
        embed = discord.Embed(
            title="♟️ Chess Game - Game Over",
            description=f"<@{interaction.user.id}> resigned!\n\n🏆 Winner: {'Stockfish' if self.is_vs_ai else f'<@{winner_id}>'}",
            color=discord.Color.red()
        )
        
        embed.set_image(url="attachment://chess_board.png")
        
        # Create "New Game" button view
        new_game_view = discord.ui.View(timeout=None)
        
        if self.is_vs_ai:
            # AI Game: Start new game vs AI button
            new_game_btn = discord.ui.Button(
                label='♟️ New Game vs AI',
                style=discord.ButtonStyle.success,
                custom_id=f'chess_resign_new_ai_{self.game_id}_{resigner_id}'
            )
            
            async def new_ai_game_callback(btn_interaction: discord.Interaction):
                if str(btn_interaction.user.id) not in [player1_id, player2_id]:
                    await btn_interaction.response.send_message(
                        "❌ Only players from the original game can start a new game!",
                        ephemeral=True
                    )
                    return
                
                # Start new AI chess game
                await btn_interaction.response.defer()
                ctx = await bot.get_context(btn_interaction.message)
                await bot.get_command('chess').callback(ctx, opponent=None)
                await btn_interaction.followup.send("🎮 New chess game started!", ephemeral=True)
            
            new_game_btn.callback = new_ai_game_callback
        else:
            # PvP Game: Send invitation button
            new_game_btn = discord.ui.Button(
                label='♟️ New Game (Send Invitation)',
                style=discord.ButtonStyle.success,
                custom_id=f'chess_resign_new_pvp_{self.game_id}_{player1_id}_{player2_id}'
            )
            
            async def new_pvp_game_callback(btn_interaction: discord.Interaction):
                if str(btn_interaction.user.id) not in [player1_id, player2_id]:
                    await btn_interaction.response.send_message(
                        "❌ Only players from the original game can start a new game!",
                        ephemeral=True
                    )
                    return
                
                # Determine opponent
                if str(btn_interaction.user.id) == player1_id:
                    opp_id = player2_id
                else:
                    opp_id = player1_id
                
                # Send invitation
                invite_embed = discord.Embed(
                    title="♟️ Chess Rematch!",
                    description=f"{btn_interaction.user.mention} challenges <@{opp_id}> to a rematch!",
                    color=discord.Color.blue()
                )
                
                invite_view = ChessInviteView(
                    challenger_id=str(btn_interaction.user.id),
                    opponent_id=opp_id
                )
                
                await btn_interaction.response.send_message(embed=invite_embed, view=invite_view)
            
            new_game_btn.callback = new_pvp_game_callback
        
        new_game_view.add_item(new_game_btn)
        
        await interaction.message.edit(embed=embed, view=new_game_view, attachments=[file])
        await interaction.response.send_message("You have resigned from the game.", ephemeral=True)


class ChessInviteView(discord.ui.View):
    def __init__(self, challenger_id: str, opponent_id: str):
        super().__init__(timeout=300)  # 5 minute timeout
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.value = None
    
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.opponent_id:
            await interaction.response.send_message("❌ This invite is not for you!", ephemeral=True)
            return
        
        # DEFER IMMEDIATELY - THIS IS THE FIX
        await interaction.response.defer()
        
        self.value = True
        self.stop()
        
        # Create the game
        board = chess.Board()
        
        # Store in database
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT INTO chess_games 
                     (player1_id, player2_id, current_turn, board_fen, channel_id)
                     VALUES (?, ?, ?, ?, ?)''',
                 (self.challenger_id, self.opponent_id, self.challenger_id, board.fen(), str(interaction.channel.id)))
        game_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Create board image (no last move for starting position)
        board_image = await board_to_image(board)
        file = discord.File(board_image, filename="chess_board.png")
        
        # Create game embed
        game_embed = discord.Embed(
            title="♟️ Chess Game Started!",
            description=f"**White:** <@{self.challenger_id}>\n**Black:** <@{self.opponent_id}>\n\n**Current turn:** <@{self.challenger_id}>",
            color=discord.Color.blue()
        )
        
        game_embed.set_image(url="attachment://chess_board.png")
        game_embed.set_footer(text=f"Game ID: {game_id}")
        
        # Create game view
        view = ChessGameView(game_id, board, self.challenger_id, False)
        
        # Edit original message
        accept_embed = discord.Embed(
            title="✅ Chess Invite Accepted",
            description=f"<@{self.opponent_id}> accepted the chess match!",
            color=discord.Color.green()
        )
        
        await interaction.message.edit(embed=accept_embed, view=None)
        
        # Send game message
        await interaction.channel.send(
            content=f"<@{self.challenger_id}> vs <@{self.opponent_id}>",
            embed=game_embed,
            view=view,
            file=file
        )
        
        # USE FOLLOWUP INSTEAD - THIS IS THE FIX
        await interaction.followup.send("Game started! Good luck! ♟️", ephemeral=True)
    
    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.opponent_id:
            await interaction.response.send_message("❌ This invite is not for you!", ephemeral=True)
            return
        
        # DEFER IMMEDIATELY - THIS IS THE FIX
        await interaction.response.defer()
        
        self.value = False
        self.stop()
        
        decline_embed = discord.Embed(
            title="❌ Chess Invite Declined",
            description=f"<@{self.opponent_id}> declined the chess match.",
            color=discord.Color.red()
        )
        
        await interaction.message.edit(embed=decline_embed, view=None)
        
        # USE FOLLOWUP INSTEAD - THIS IS THE FIX
        await interaction.followup.send("You declined the chess invite.", ephemeral=True)


def increment_ai_chat_count(user_id, guild_id):
    """Increment AI chat message count for leaderboard"""
    today = datetime.date.today()
    db_query('''
        INSERT INTO leaderboard_ai_chat (user_id, guild_id, message_count, first_message_date)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(user_id, guild_id) DO UPDATE SET
        message_count = message_count + 1
    ''', (str(user_id), str(guild_id), today))

def increment_chess_wins(user_id, guild_id):
    ""Increment chess wins for leaderboard"""
    today = datetime.date.today()
    db_query('''
        INSERT INTO leaderboard_chess (user_id, guild_id, wins, first_win_date)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(user_id, guild_id) DO UPDATE SET
        wins = wins + 1
    ''', (str(user_id), str(guild_id), today))

def increment_tictactoe_wins(user_id, guild_id, difficulty):
    """Increment tic-tac-toe wins for leaderboard"""
    today = datetime.date.today()
    db_query('''
        INSERT INTO leaderboard_tictactoe (user_id, guild_id, difficulty, wins, first_win_date)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(user_id, guild_id, difficulty) DO UPDATE SET
        wins = wins + 1
    ''', (str(user_id), str(guild_id), difficulty, today))

def is_server_censor_bypass(guild_id, user_id):
    """Check if user has server-specific censor bypass"""
    result = db_query(
        "SELECT user_id FROM server_censor_bypass WHERE guild_id = ? AND user_id = ?",
        (str(guild_id), str(user_id)),
        fetch=True
    )
    return bool(result)

def get_server_banned_words(guild_id):
    """Get banned words for a specific server"""
    result = db_query(
        "SELECT word FROM server_banned_words WHERE guild_id = ?",
        (str(guild_id),),
        fetch=True
    )
    return [r[0] for r in result] if result else []

def has_server_banned_words(guild_id):
    """Check if server has custom banned words configured"""
    result = db_query(
        "SELECT COUNT(*) FROM server_banned_words WHERE guild_id = ?",
        (str(guild_id),),
        fetch=True
    )
    return result[0][0] > 0 if result else False


# --- UTILITY FUNCTIONS ---
async def log_to_channel(bot, channel_key, embed, **kwargs):
    """Send log embed and optional components to specified channel"""
    try:
        channel_id = LOG_CHANNELS.get(channel_key)
        if not channel_id:
            return False
        
        channel = bot.get_channel(channel_id)
        if not channel:
            return False
        
        # Passing kwargs allows 'view' to be processed
        await channel.send(embed=embed, **kwargs)
        return True
    except Exception as e:
        print(f"❌ Failed to log to {channel_key}: {e}")
        return False


def truncate_message(content, max_length=MAX_INPUT_TOKENS):
    """Truncate message if its too long, keeping the most recent content"""
    if len(content) <= max_length:
        return content, False
    
    truncated = content[-max_length:]
    return f"[Message truncated due to length]\n{truncated}", True

async def split_and_send(message, content):
    """Split long responses and send them in multiple messages"""
    if len(content) <= MAX_MESSAGE_LENGTH:
        try:
            await message.reply(content)
        except discord.errors.HTTPException:
            # Message was deleted, send to channel instead
            await message.channel.send(content)
        return
    
    paragraphs = content.split('\n\n')
    current_chunk = ""
    chunks = []
    
    for para in paragraphs:
        if len(para) > MAX_MESSAGE_LENGTH:
            sentences = para.split('. ')
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 2 > MAX_MESSAGE_LENGTH:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = sentence + ". "
                else:
                    current_chunk += sentence + ". "
        else:
            if len(current_chunk) + len(para) + 2 > MAX_MESSAGE_LENGTH:
                chunks.append(current_chunk)
                current_chunk = para + "\n\n"
            else:
                current_chunk += para + "\n\n"
    
    if current_chunk:
        chunks.append(current_chunk)
    
    try:
        await message.reply(chunks[0])
    except discord.errors.HTTPException:
        # Message was deleted, send to channel instead
        await message.channel.send(chunks[0])
    
    for chunk in chunks[1:]:
        await message.channel.send(chunk)
        await asyncio.sleep(0.5)
async def send_user_dm(user_id, message):
    """Send DM to user, handle errors silently"""
    try:
        user = await bot.fetch_user(int(user_id))
        await user.send(message)
        return True
    except:
        return False

init_db()
migrate_json_to_db()
migrate_interaction_logs()
async def get_prefix(bot, message):
    guild_or_user_id = str(message.guild.id if message.guild else message.author.id)
    res = db_query("SELECT prefix FROM settings WHERE id = ?", (guild_or_user_id,), fetch=True)
    return res[0][0] if res and res[0][0] else "/"


class GroqAPIManager:
    def __init__(self, groq_keys):
        self.groq_keys = groq_keys
        self.current_index = 0
        self.clients = [AsyncGroq(api_key=key) for key in groq_keys]
        print(f"✅ Loaded {len(self.clients)} Groq API keys")
    
    def rotate(self):
        """Switch to next API key"""
        self.current_index = (self.current_index + 1) % len(self.clients)
        print(f"🔄 Rotated to Groq key #{self.current_index + 1}")
    
    async def generate(self, messages, max_tokens=800, temp=0.7):
        """Generate response with automatic rotation on rate limit"""
        
        # Try all keys
        for attempt in range(len(self.clients)):
            try:
                client = self.clients[self.current_index]
                
                response = await client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temp
                )
                
                return response.choices[0].message.content
                
            except Exception as e:
                error = str(e).lower()
                
                # Check if rate limit
                if "rate" in error or "429" in error or "limit" in error:
                    print(f"⚠️ Groq key #{self.current_index + 1} rate limited")
                    
                    if attempt < len(self.clients) - 1:
                        self.rotate()
                        continue
                    else:
                        raise Exception("All Groq API keys exhausted")
                else:
                    raise e
        
        raise Exception("All API keys failed")
    
class AIBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=get_prefix, intents=discord.Intents.all(), help_command=None)
        self.api_manager = GroqAPIManager(GROQ_KEYS)
        self.memory = {}
        self.reaction_chance = 0.10
        self.last_response_time = 0
        
    async def setup_hook(self):
        self.daily_backup.start()
        # Start webhook server
        asyncio.create_task(start_webhook_server(self, port=8080))
        # Start vote reminder loop
        asyncio.create_task(vote_reminder_loop(self))
        asyncio.create_task(role_expiration_loop(self))
        print(f"⏰ Role expiration loop started")
        print(f"✅ {self.user} Online | All Commands Locked & Loaded")
        print(f"🔄 Daily backup task started")
        print(f"🗳️ Top.gg webhook server starting...")
        print(f"🔔 Vote reminder loop started")

# Initialize Patreon promoter (OUTSIDE the class, at module level)
patreon_promoter = PatreonPromoter(
    patreon_url="https://patreon.com/flexedAI/membership",
    min_messages=15,
    max_messages=20
)

bot = AIBot()

# --- EVENT HANDLERS FOR LOGGING ---
@bot.event
async def on_guild_join(guild):
    """Log when bot joins a server and auto-leave if blacklisted"""
    
    # Check if guild is blacklisted
    if is_guild_blacklisted(guild.id):
        blacklist_info = db_query(
            "SELECT reason, blacklisted_by FROM blacklisted_guilds WHERE guild_id = ?", 
            (str(guild.id),), 
            fetch=True
        )
        
        if blacklist_info:
            reason, blacklisted_by = blacklist_info[0]
            
            # Try to notify owner
            try:
                await guild.owner.send(
                    f"""\U0001F6AB **{BOT_NAME} Bot - Blacklisted Server**

Hello {guild.owner.name},

Your server **{guild.name}** is blacklisted from using {BOT_NAME} Bot.

**Reason:** {reason}

The bot has automatically left your server. You cannot re-add this bot while blacklisted.

**Appeal:** Contact <@{OWNER_ID}>
**Join the Support Server:** {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}

*Timestamp: {get_discord_timestamp(style='F')}*
"""
                )
            except:
                pass
            
            # Log the attempted join
            log_embed = discord.Embed(
                title="🚫 Blacklisted Guild Attempted Join",
                description=f"Bot was added to a blacklisted server and auto-left.",
                color=discord.Color.dark_red(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            log_embed.add_field(name="🏰 Server Name", value=guild.name, inline=True)
            log_embed.add_field(name="🆔 Server ID", value=f"`{guild.id}`", inline=True)
            log_embed.add_field(name="👑 Server Owner", value=f"{guild.owner.mention} (`{guild.owner.id}`)", inline=False)
            log_embed.add_field(name="📝 Blacklist Reason", value=reason, inline=False)
            log_embed.add_field(name="⚖️ Originally Blacklisted By", value=f"<@{blacklisted_by}>", inline=True)
            
            await log_to_channel(bot, 'blacklist', log_embed)
            
            # Leave the guild
            await guild.leave()
            return
    
    # Get the user who added the bot (inviter)
    inviter = None
    try:
        # Fetch audit logs to find who added the bot
        async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.bot_add):
            if entry.target.id == bot.user.id:
                inviter = entry.user
                break
    except:
        pass
    
    # Original join logic continues below...
    embed = discord.Embed(
        title="🟢 Bot Joined Server",
        description=f"{BOT_NAME} has been added to a new server!",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="📋 Server Name", value=guild.name, inline=True)
    embed.add_field(name="🆔 Server ID", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="👑 Server Owner", value=f"{guild.owner.mention} (`{guild.owner.id}`)", inline=False)
    
    if inviter:
        embed.add_field(name="➕ Added By", value=f"{inviter.mention} (`{inviter.id}`)", inline=False)
    
    embed.add_field(name="👥 Member Count", value=guild.member_count, inline=True)
    embed.add_field(name="📅 Server Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="📊 Total Servers", value=len(bot.guilds), inline=True)
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.set_footer(text=f"Server Owner ID: {guild.owner.id}")
    
    await log_to_channel(bot, 'server_join_leave', embed)
    
    # Log to database
    db_query("INSERT INTO admin_logs (log) VALUES (?)", 
             (f"Bot joined server: {guild.name} (ID: {guild.id}, Owner: {guild.owner.name} - {guild.owner.id})",))
    
    # Welcome message content
    welcome_msg = f"""👋 **Hello!**

Thank you for adding **{BOT_NAME} Bot** to **{guild.name}**!

🚀 **Quick Start Guide:**
• Use `/help` to see all available commands
• Use `/start` in a channel to enable automatic responses
• Use `/stop` to make the bot respond only when mentioned
• Use `/lang` to set the bot's language for a channel
• Server administrators can configure bot settings

📚 **Key Features:**
• AI-powered conversations with context memory
• Multi-language support (15+ languages)
• Moderation tools (strikes, blacklist, word filter)
• Customizable command prefix
• Channel-specific response modes

⏱️ **Response Cooldown:**
To maintain optimal performance with our AI API, the bot has a 0.6-second cooldown between responses. This means:
• The bot responds immediately to any user's message
• If another user sends a message within 0.6 seconds of the last response, the bot remains silent
• This prevents API rate limiting and ensures stable service for everyone

💡 **Need Help?**
Contact the bot owner: <@{OWNER_ID}>
Join the Support Server: {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}

Enjoy using {BOT_NAME}! 🎉
"""
    
    # Try to send welcome message to server owner
    owner_dm_sent = False
    try:
        await guild.owner.send(welcome_msg)
        owner_dm_sent = True
    except:
        pass  # Owner has DMs disabled
    
    # Try to send welcome message to inviter (if different from owner)
    inviter_dm_sent = False
    if inviter and inviter.id != guild.owner.id:
        try:
            inviter_welcome = f"""👋 **Hello {inviter.name}!**

Thank you for adding **{BOT_NAME} Bot** to **{guild.name}**!

🚀 **Quick Start Guide:**
• Use `/help` to see all available commands
• Use `/start` in a channel to enable automatic responses
• Use `/stop` to make the bot respond only when mentioned
• Use `/lang` to set the bot's language for a channel

📚 **Key Features:**
• AI-powered conversations with context memory
• Multi-language support (15+ languages)
• Moderation tools (strikes, blacklist, word filter)
• Customizable command prefix
• Channel-specific response modes

⏱️ **Response Cooldown:**
The bot has a 0.6-second cooldown between responses to prevent API rate limiting and ensure stable service.

💡 **Need Help?**
Contact the bot owner: <@{OWNER_ID}>
Join the Support Server: {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}

Enjoy using {BOT_NAME}! 🎉
"""
            await inviter.send(inviter_welcome)
            inviter_dm_sent = True
        except:
            pass  # Inviter has DMs disabled
    
    # Try to find a general/system channel to send welcome message
    try:
        # Try to find the system channel or first text channel
        target_channel = guild.system_channel
        
        if not target_channel:
            # Find first text channel bot can send messages to
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    target_channel = channel
                    break
        
        if target_channel:
            welcome_embed = discord.Embed(
                title=f"👋 Thanks for adding {BOT_NAME}!",
                description="**⚠️ IMPORTANT: Setup Required**\n\nBefore you can use this bot, you need to set up an updates channel!",
                color=discord.Color.orange()
            )
            
            welcome_embed.add_field(
                name="🔧 Required Setup",
                value=f"Use `/setupupdates` to set a channel for important bot announcements and updates.\n\n**Without this setup, the bot will not function!**",
                inline=False
            )
            
            welcome_embed.add_field(
                name="🚀 Getting Started",
                value="• Use `/setupupdates #channel` to set updates channel\n• Use `/help` to see all commands\n• Use `/start` to enable auto-responses in channels\n• Use `/lang` to set your preferred language",
                inline=False
            )
            
            welcome_embed.add_field(
                name="⏱️ Response Cooldown (Important!)",
                value="**The bot has a 0.6-second cooldown between responses.**\n\n"
                      "**How it works:**\n"
                      "• Bot responds immediately to any message\n"
                      "• If another user messages within 0.6s of last response, bot stays silent\n"
                      "• After 0.6s, bot will respond to new messages normally\n\n"
                      "**Why?** We use a cost-effective API with rate limits. This cooldown ensures stable, reliable service for everyone! 🎯",
                inline=False
            )
            
            welcome_embed.add_field(
                name="💡 Need Help?",
                value=f"Contact: <@{OWNER_ID}>\n[Join Support Server]({os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')})",
                inline=False
            )
            
            # Add notification about DMs
            dm_status = []
            if owner_dm_sent:
                dm_status.append(f"✅ Server owner {guild.owner.mention} has been notified via DM")
            else:
                dm_status.append(f"⚠️ Server owner {guild.owner.mention} - DM failed (DMs disabled)")
            
            if inviter and inviter.id != guild.owner.id:
                if inviter_dm_sent:
                    dm_status.append(f"✅ Bot inviter {inviter.mention} has been notified via DM")
                else:
                    dm_status.append(f"⚠️ Bot inviter {inviter.mention} - DM failed (DMs disabled)")
            
            welcome_embed.add_field(
                name="📬 Notifications Sent",
                value="\n".join(dm_status),
                inline=False
            )
            
            welcome_embed.set_footer(text="⚠️ Setup updates channel first using /setupupdates")
            
            await target_channel.send(embed=welcome_embed)
    except Exception as e:
        print(f"⚠️ Could not send welcome message to server {guild.name}: {e}")



@bot.event
async def on_member_join(member):
    """
    Handle new member joins to support server
    - Check if they voted within last 12 hours
    - Assign voter role for remaining time if applicable
    - Send DM notification about role
    """
    
    # Only process joins in support server
    support_server_id = int(os.getenv('SUPPORT_SERVER_ID', 0))
    
    if not support_server_id:
        print("⚠️ SUPPORT_SERVER_ID not configured in .env")
        return
    
    if member.guild.id != support_server_id:
        # Not support server, ignore
        return
    
    print(f"👤 New member joined support server: {member.name} ({member.id})")
    
    # Check if user voted recently and assign role with remaining time
    await check_and_assign_voter_role_on_join(bot, member)
@bot.event
async def on_guild_remove(guild):
    """Log when bot leaves a server"""
    embed = discord.Embed(
        title="🔴 Bot Left Server",
        description=f"{BOT_NAME} has been removed from a server.",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="📋 Server Name", value=guild.name, inline=True)
    embed.add_field(name="🆔 Server ID", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="👑 Server Owner", value=f"{guild.owner.mention} (`{guild.owner.id}`)", inline=False)
    embed.add_field(name="👥 Member Count", value=guild.member_count, inline=True)
    embed.add_field(name="📊 Remaining Servers", value=len(bot.guilds), inline=True)
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.set_footer(text=f"Server Owner ID: {guild.owner.id}")
    
    await log_to_channel(bot, 'server_join_leave', embed)
    
    # Log to database
    db_query("INSERT INTO admin_logs (log) VALUES (?)", 
             (f"Bot left server: {guild.name} (ID: {guild.id}, Owner: {guild.owner.name} - {guild.owner.id})",))

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user.name}")
    print(f"📊 Connected to {len(bot.guilds)} servers")
    print(f"👤 Owner: {OWNER_INFO['name']} (ID: {OWNER_INFO['id']})")

@tasks.loop(hours=24)
async def daily_backup_task():
    try:
        owner = await bot.fetch_user(OWNER_ID)
        db_data = export_db_to_json()
        timestamp = int(time.time())
        filename = f"backup_{timestamp}.json"

        with open(filename, "w") as f:
            json.dump(db_data, f, indent=2)

        embed = discord.Embed(
            title="📦 24-Hour Database Backup", 
            description=f"**Timestamp:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
            color=discord.Color.green()
        )
        embed.add_field(name="Users", value=len(db_data['users']), inline=True)
        embed.add_field(name="Banned Words", value=len(db_data['banned_words']), inline=True)
        embed.add_field(name="Interactions (24h)", value=len(db_data['interaction_logs']), inline=True)

        await owner.send(embed=embed, file=discord.File(filename))
        os.remove(filename)
        print(f"✅ Backup sent to owner at {datetime.datetime.now()}")
    except Exception as e:
        print(f"❌ Backup failed: {e}")

@daily_backup_task.before_loop
async def before_backup():
    await bot.wait_until_ready()

bot.daily_backup = daily_backup_task

# Language Select View (Dropdown for slash command)
class LanguageSelectView(discord.ui.View):
    def __init__(self, channel_id, author_id):
        super().__init__(timeout=60)
        self.channel_id = channel_id
        self.author_id = author_id
        self.add_item(LanguageSelect(channel_id, author_id))

class LanguageSelect(discord.ui.Select):
    def __init__(self, channel_id, author_id):
        self.channel_id = channel_id
        self.author_id = author_id
        
        options = [
            discord.SelectOption(label=lang, value=lang, emoji="🌐")
            for lang in AVAILABLE_LANGUAGES
        ]
        
        super().__init__(
            placeholder="Choose a language...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Only the command user can select a language.", ephemeral=True)
            return
        
        selected_lang = self.values[0]
        db_query("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", (str(self.channel_id), selected_lang))
        
        await interaction.response.send_message(f"🌐 Language set to **{selected_lang}** for this channel.", ephemeral=True)
        self.view.stop()

# Language Button View (for prefix command)
class LanguageButtonView(discord.ui.View):
    def __init__(self, channel_id, author_id, owner_id):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.author_id = author_id
        self.owner_id = owner_id
        self.message = None
        
        for i, lang in enumerate(AVAILABLE_LANGUAGES):
            button = discord.ui.Button(
                label=lang,
                style=discord.ButtonStyle.primary,
                custom_id=f"lang_{lang}",
                row=i // 5
            )
            button.callback = self.create_callback(lang)
            self.add_item(button)
    
    def create_callback(self, lang):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                if not interaction.guild or not interaction.user.guild_permissions.administrator:
                    await interaction.response.send_message("❌ Only administrators and the bot owner can change language settings.", ephemeral=True)
                    return
            
            db_query("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", (str(self.channel_id), lang))
            
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(
                content=f"🌐 Language set to **{lang}** by {interaction.user.mention}. {BOT_NAME} will now respond in {lang}",
                view=self
            )
            
            await interaction.followup.send(f"✅ Language successfully changed to **{lang}** for this channel.", ephemeral=True)
            
            self.stop()
        
        return callback

# Permission checker decorator
def owner_or_bot_admin():
    async def predicate(ctx):
        if ctx.author.id == OWNER_ID:
            return True
        if is_bot_admin(ctx.author.id):
            return True
        await ctx.send("❌ **Permission Denied**\n**Required:** Bot Owner or Bot Admin privileges\n\nThis command is restricted to authorized personnel only.")
        return False
    return commands.check(predicate)
# Moderation Commands with Enhanced Logging

@bot.hybrid_command(name="sync", description="Owner/Admin: Sync slash commands.")
@owner_or_bot_admin()
async def sync(ctx):
    await bot.tree.sync()
    await ctx.send("🚀 **Slash commands synced globally!**\nAll commands are now up to date across Discord.")

@bot.hybrid_command(name="allinteractions", description="Owner/Admin: Export ALL interaction logs.")
@owner_or_bot_admin()
@commands.dm_only()
async def all_interactions(ctx):
    rows = db_query("SELECT * FROM interaction_logs ORDER BY timestamp DESC", fetch=True)

    if not rows:
        await ctx.send("❌ **No interaction logs found.**\nThe database is currently empty.")
        return

    data = [{"timestamp": r[0], "guild_id": r[1], "channel_id": r[2], "user_name": r[3], "user_id": r[4], "prompt": r[5], "response": r[6]} for r in rows]
    fname = f"all_logs_{int(time.time())}.json"

    with open(fname, "w") as f: 
        json.dump(data, f, indent=2)

    await ctx.send(f"📊 **Export Complete**\n**Total Interactions:** {len(data)}\n\nAll interaction logs have been exported successfully.", file=discord.File(fname))
    os.remove(fname)

@bot.hybrid_command(name="messages", description="Owner/Admin: Export interaction logs (last 24h).")
@owner_or_bot_admin()
@commands.dm_only()
async def messages(ctx):
    cutoff = time.time() - 86400
    rows = db_query("SELECT * FROM interaction_logs WHERE timestamp > ? ORDER BY timestamp DESC", (cutoff,), fetch=True)
    
    if not rows:
        await ctx.send("❌ **No interactions in the last 24 hours.**")
        return
    
    data = [{"timestamp": r[0], "guild_id": r[1], "channel_id": r[2], "user_name": r[3], "user_id": r[4], "prompt": r[5], "response": r[6]} for r in rows]
    fname = f"logs_{int(time.time())}.json"

    with open(fname, "w") as f: 
        json.dump(data, f, indent=2)

    await ctx.send(f"📊 **24-Hour Export Complete**\n**Interactions:** {len(data)}", file=discord.File(fname))
    os.remove(fname)

@bot.hybrid_command(name="clearlogs", description="Owner/Admin: Wipe interaction logs.")
@owner_or_bot_admin()
@commands.dm_only()
async def clear_logs(ctx):
    count = db_query("SELECT COUNT(*) FROM interaction_logs", fetch=True)[0][0]
    db_query("DELETE FROM interaction_logs")
    await ctx.send(f"🗑️ **Interaction logs cleared!**\n**Removed:** {count} interaction records")

@bot.command(name="server-list", description="Owner/Admin: Export server list.")
@owner_or_bot_admin()
@commands.dm_only()
async def server_list(ctx):
    guilds = [{"id": str(g.id), "name": g.name, "member_count": g.member_count, "owner_id": str(g.owner.id), "owner_name": g.owner.name} for g in bot.guilds]
    fname = f"servers_{int(time.time())}.json"

    with open(fname, "w") as f:
        json.dump(guilds, f, indent=2)

    await ctx.send(f"📊 **Server List Export**\n**Total Servers:** {len(guilds)}", file=discord.File(fname))
    os.remove(fname)

@bot.command(name="data", description="Owner/Admin: Complete bot configuration data.")
@owner_or_bot_admin()
@commands.dm_only()
async def bot_data(ctx):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    data = {
        "export_timestamp": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "bot_info": {
            "total_servers": len(bot.guilds),
            "total_users_tracked": 0,
            "total_interactions_logged": 0
        },
        "users": {
            "blacklisted": [],
            "strikes": [],
            "all_tracked": []
        },
        "banned_words": [],
        "bot_admins": [],
        "word_filter_bypass": [],
        "blacklisted_guilds": [],
        "server_configurations": {},
        "channel_configurations": {},
        "statistics": {
            "total_strikes_issued": 0,
            "total_blacklists": 0,
            "total_banned_words": 0,
            "total_blacklisted_guilds": 0,
            "channels_in_start_mode": 0,
            "channels_in_stop_mode": 0
        }
    }

    # Users data
    c.execute("SELECT user_id, strikes, blacklisted FROM users")
    users = c.fetchall()
    data['bot_info']['total_users_tracked'] = len(users)

    for user in users:
        user_data = {
            "user_id": user[0],
            "strikes": user[1],
            "blacklisted": bool(user[2])
        }
        data['users']['all_tracked'].append(user_data)

        if user[2] == 1:
            data['users']['blacklisted'].append(user[0])
            data['statistics']['total_blacklists'] += 1

        if user[1] > 0:
            data['users']['strikes'].append({
                "user_id": user[0],
                "strike_count": user[1]
            })
            data['statistics']['total_strikes_issued'] += user[1]

    # Banned words
    c.execute("SELECT word FROM banned_words")
    banned = c.fetchall()
    data['banned_words'] = [w[0] for w in banned]
    data['statistics']['total_banned_words'] = len(data['banned_words'])

    # Bot admins
    c.execute("SELECT user_id, added_by, added_at FROM bot_admins")
    admins = c.fetchall()
    data['bot_admins'] = [{"user_id": a[0], "added_by": a[1], "added_at": a[2]} for a in admins]

    # Word filter bypass users
    c.execute("SELECT user_id, added_by, reason, added_at FROM word_filter_bypass")
    bypass_users = c.fetchall()
    data['word_filter_bypass'] = [
        {
            "user_id": b[0],
            "added_by": b[1],
            "reason": b[2],
            "added_at": b[3]
        } for b in bypass_users
    ]

    # Blacklisted guilds
    c.execute("SELECT guild_id, guild_name, blacklisted_by, reason, blacklisted_at FROM blacklisted_guilds")
    guild_blacklist = c.fetchall()
    data['blacklisted_guilds'] = [
        {
            "guild_id": g[0],
            "guild_name": g[1],
            "blacklisted_by": g[2],
            "reason": g[3],
            "blacklisted_at": g[4]
        } for g in guild_blacklist
    ]
    data['statistics']['total_blacklisted_guilds'] = len(data['blacklisted_guilds'])
    # Updates channels configuration
    c.execute("SELECT guild_id, channel_id, setup_by, setup_at FROM updates_channels")
    updates_channels_data = c.fetchall()
    data['updates_channels'] = [
        {
            "guild_id": u[0],
            "guild_name": bot.get_guild(int(u[0])).name if bot.get_guild(int(u[0])) else "Unknown",
            "channel_id": u[1],
            "setup_by": u[2],
            "setup_at": u[3]
        } for u in updates_channels_data
    ]
    data['statistics']['total_configured_updates_channels'] = len(data['updates_channels'])

    # Server and channel configurations
    c.execute("SELECT id, prefix, language, mode FROM settings")
    settings = c.fetchall()

    for setting in settings:
        setting_id = setting[0]
        prefix = setting[1] if setting[1] else "!"
        language = setting[2] if setting[2] else "English"
        mode = setting[3] if setting[3] else "stop"

        try:
            guild = bot.get_guild(int(setting_id))
            if guild:
                data['server_configurations'][guild.name] = {
                    "guild_id": setting_id,
                    "prefix": prefix,
                    "member_count": guild.member_count
                }
            else:
                channel = bot.get_channel(int(setting_id))
                if channel:
                    guild_name = channel.guild.name if channel.guild else "DM"
                    data['channel_configurations'][f"{guild_name} > {channel.name}"] = {
                        "channel_id": setting_id,
                        "guild_id": str(channel.guild.id) if channel.guild else "DM",
                        "language": language,
                        "mode": mode
                    }

                    if mode == "start":
                        data['statistics']['channels_in_start_mode'] += 1
                    else:
                        data['statistics']['channels_in_stop_mode'] += 1
                else:
                    data['channel_configurations'][f"Unknown Channel {setting_id}"] = {
                        "channel_id": setting_id,
                        "language": language,
                        "mode": mode,
                        "note": "Channel/Guild not found - may have been deleted"
                    }
        except:
            pass

    # Interaction logs count
    c.execute("SELECT COUNT(*) FROM interaction_logs")
    interaction_count = c.fetchone()[0]
    data['bot_info']['total_interactions_logged'] = interaction_count

    # Recent admin logs
    c.execute("SELECT log, timestamp FROM admin_logs ORDER BY timestamp DESC LIMIT 100")
    logs = c.fetchall()
    data['admin_logs_recent'] = [{"log": l[0], "timestamp": l[1]} for l in logs]

    # Recent reports
    c.execute("SELECT report_id, reporter_id, reported_user_id, reason, status, timestamp FROM reports ORDER BY timestamp DESC LIMIT 50")
    reports = c.fetchall()
    data['recent_reports'] = [
        {
            "report_id": r[0],
            "reporter_id": r[1],
            "reported_user_id": r[2],
            "reason": r[3],
            "status": r[4],
            "timestamp": r[5]
        } for r in reports
    ]

    conn.close()

    timestamp = int(time.time())
    filename = f"bot_data_complete_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

    embed = discord.Embed(
        title="🗄️ Complete Bot Configuration Data",
        description=f"**Export Time:** {data['export_timestamp']}",
        color=discord.Color.purple()
    )

    # Bot statistics
    embed.add_field(name="📊 Servers", value=data['bot_info']['total_servers'], inline=True)
    embed.add_field(name="👥 Users Tracked", value=data['bot_info']['total_users_tracked'], inline=True)
    embed.add_field(name="💬 Total Interactions", value=data['bot_info']['total_interactions_logged'], inline=True)

    # Moderation statistics
    embed.add_field(name="🚫 Blacklisted Users", value=data['statistics']['total_blacklists'], inline=True)
    embed.add_field(name="⚡ Total Strikes", value=data['statistics']['total_strikes_issued'], inline=True)
    embed.add_field(name="🔇 Banned Words", value=data['statistics']['total_banned_words'], inline=True)

    # Guild blacklist statistic
    embed.add_field(name="🏰 Blacklisted Guilds", value=data['statistics']['total_blacklisted_guilds'], inline=True)
    embed.add_field(name="🔓 Filter Bypass Users", value=len(data['word_filter_bypass']), inline=True)
    embed.add_field(name="✨ Bot Admins", value=len(data['bot_admins']), inline=True)
    embed.add_field(name="📢 Updates Channels", value=len(data['updates_channels']), inline=True)

    # Channel statistics
    embed.add_field(name="🟢 Channels (Start Mode)", value=data['statistics']['channels_in_start_mode'], inline=True)
    embed.add_field(name="🔴 Channels (Stop Mode)", value=data['statistics']['channels_in_stop_mode'], inline=True)
    embed.add_field(name="⚙️ Server Configs", value=len(data['server_configurations']), inline=True)

    # Additional info
    embed.add_field(name="📋 Recent Reports", value=len(data['recent_reports']), inline=True)
    embed.add_field(name="📝 Recent Logs", value=len(data['admin_logs_recent']), inline=True)
    embed.add_field(name="📦 Export Size", value=f"{os.path.getsize(filename) / 1024:.2f} KB", inline=True)

    embed.set_footer(text=f"Complete data export • File: {filename}")

    await ctx.send(embed=embed, file=discord.File(filename))
    os.remove(filename)

    print(f"✅ Complete data export sent to owner at {datetime.datetime.now()}")
@bot.hybrid_command(name="backup", description="Owner/Admin: Trigger immediate backup.")
@owner_or_bot_admin()
@commands.dm_only()
async def manual_backup(ctx):
    db_data = export_db_to_json()
    timestamp = int(time.time())
    filename = f"manual_backup_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(db_data, f, indent=2)

    embed = discord.Embed(
        title="📦 Manual Database Backup", 
        description=f"**Timestamp:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
        color=discord.Color.blue()
    )
    embed.add_field(name="Users", value=len(db_data['users']), inline=True)
    embed.add_field(name="Banned Words", value=len(db_data['banned_words']), inline=True)
    embed.add_field(name="Interactions (24h)", value=len(db_data['interaction_logs']), inline=True)

    await ctx.send(embed=embed, file=discord.File(filename))
    os.remove(filename)

@bot.hybrid_group(name="blacklist", description="Owner/Admin: Manage user access.", invoke_without_command=True)
@owner_or_bot_admin()
async def blacklist_group(ctx):
    res = db_query("SELECT user_id FROM users WHERE blacklisted = 1", fetch=True)
    if res:
        user_list = "\n".join([f"• <@{r[0]}> (`{r[0]}`)" for r in res])
        embed = discord.Embed(
            title="🚫 Blacklisted Users",
            description=user_list,
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Total: {len(res)} user(s)")
        await ctx.send(embed=embed)
    else:
        await ctx.send("✅ **No blacklisted users**\nThe blacklist is currently empty.")

@blacklist_group.command(name="add")
@owner_or_bot_admin()
async def bl_add(ctx, user_id: str, *, reason: str = "No reason provided"):
    # DEFER RESPONSE IMMEDIATELY to prevent interaction timeout
    await ctx.defer()
    
    db_query("INSERT OR REPLACE INTO users (user_id, blacklisted) VALUES (?, 1)", (user_id,))
    log_msg = f"User {user_id} BLACKLISTED by {ctx.author.name} ({ctx.author.id}). Reason: {reason}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Get current time
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # Send DM to user
    dm_sent = await send_user_dm(
        user_id, 
        f"🚫 **You have been blacklisted from {BOT_NAME} Bot**\n\n**Reason:** {reason}\n\n**What this means:**\n• You can no longer use any bot commands\n• The bot will not respond to your messages\n• This action has been logged by bot administrators\n\n**Believe this is a mistake?**\nContact the bot owner: <@{OWNER_ID}>\n**Join the Support Server:** {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}\n\n*Timestamp: {get_discord_timestamp(now, style='F')}*"
    )
    
    # Log to dedicated blacklist channel
    log_embed = discord.Embed(
        title="🚫 User Blacklisted",
        description=f"A user has been added to the blacklist.",
        color=discord.Color.dark_red(),
        timestamp=now
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="⚖️ Actioned By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    log_embed.add_field(name="📬 DM Notification", value="✅ Delivered" if dm_sent else "❌ Failed (DMs closed)", inline=True)
    log_embed.add_field(name="🕐 Timestamp", value=get_discord_timestamp(now, style='F'), inline=True)
    
    await log_to_channel(bot, 'blacklist', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="🚫 User Blacklisted",
        description=f"User `{user_id}` has been successfully added to the blacklist.",
        color=discord.Color.red()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Actioned By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="DM Notification", value="✅ Sent" if dm_sent else "❌ Failed (DMs disabled)", inline=True)
    
    await ctx.followup.send(embed=embed)


# ─────────────────────────────────────────────────────────────
# FIX: blacklist remove command
# ─────────────────────────────────────────────────────────────

@blacklist_group.command(name="remove")
@owner_or_bot_admin()
async def bl_rem(ctx, user_id: str, *, reason: str = "No reason provided"):
    # DEFER RESPONSE IMMEDIATELY to prevent interaction timeout
    await ctx.defer()
    
    db_query("UPDATE users SET blacklisted = 0 WHERE user_id = ?", (user_id,))
    log_msg = f"User {user_id} removed from blacklist by {ctx.author.name} ({ctx.author.id}). Reason: {reason}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Get current time
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # Send DM to user
    dm_sent = await send_user_dm(
        user_id, 
        f"✅ **Your blacklist has been removed**\n\n**Reason:** {reason}\n\n**What this means:**\n• You can now use the bot again\n• All bot features are now accessible to you\n• Your previous violations have been reviewed\n\n**Welcome back!** Please follow the community guidelines to maintain your access.\n\n*Timestamp: {get_discord_timestamp(now, style='F')}*"
    )
    
    # Log to dedicated blacklist channel
    log_embed = discord.Embed(
        title="✅ User Unblacklisted",
        description=f"A user has been removed from the blacklist.",
        color=discord.Color.green(),
        timestamp=now
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="⚖️ Actioned By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    log_embed.add_field(name="📬 DM Notification", value="✅ Delivered" if dm_sent else "❌ Failed (DMs closed)", inline=True)
    log_embed.add_field(name="🕐 Timestamp", value=get_discord_timestamp(now, style='F'), inline=True)
    
    await log_to_channel(bot, 'blacklist', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="✅ User Unblacklisted",
        description=f"User `{user_id}` has been successfully removed from the blacklist.",
        color=discord.Color.green()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Actioned By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="DM Notification", value="✅ Sent" if dm_sent else "❌ Failed (DMs disabled)", inline=True)
    
    await ctx.followup.send(embed=embed)

@bot.hybrid_group(name="censor", description="Server Admins: Manage server-specific banned words")
async def censor_group(ctx):
    """Server-specific word filter management"""
    if ctx.invoked_subcommand is None:
        await ctx.send("Use `/censor add`, `/censor remove`, or `/censor list`")

@censor_group.command(name="add", description="Add a banned word for this server")
async def censor_add(ctx, word: str):
    """Add a word to server-specific ban list"""
    if not ctx.guild:
        await ctx.send("❌ This command can only be used in servers.")
        return
    
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ **Permission Denied**\nOnly server administrators can manage the censor filter.")
        return
    
    word = word.lower().strip()
    
    if not word:
        await ctx.send("❌ Please provide a valid word to ban.")
        return
    
    # Check if word already exists
    existing = db_query(
        "SELECT word FROM server_banned_words WHERE guild_id = ? AND word = ?",
        (str(ctx.guild.id), word),
        fetch=True
    )
    
    if existing:
        await ctx.send(f"⚠️ The word `{word}` is already banned in this server.")
        return
    
    # Add word
    db_query(
        "INSERT INTO server_banned_words (guild_id, word, added_by) VALUES (?, ?, ?)",
        (str(ctx.guild.id), word, str(ctx.author.id))
    )
    
    embed = discord.Embed(
        title="🚫 Word Banned (Server Filter)",
        description=f"Successfully added `{word}` to server's banned words list.",
        color=discord.Color.red()
    )
    embed.add_field(name="Server", value=ctx.guild.name, inline=True)
    embed.add_field(name="Added By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Note", value="Global banned words are now DISABLED for this server. Only your custom list applies.", inline=False)
    
    await ctx.send(embed=embed)

@censor_group.command(name="remove", description="Remove a banned word from this server")
async def censor_remove(ctx, word: str):
    """Remove a word from server-specific ban list"""
    if not ctx.guild:
        await ctx.send("❌ This command can only be used in servers.")
        return
    
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ **Permission Denied**\nOnly server administrators can manage the censor filter.")
        return
    
    word = word.lower().strip()
    
    # Check if word exists
    existing = db_query(
        "SELECT word FROM server_banned_words WHERE guild_id = ? AND word = ?",
        (str(ctx.guild.id), word),
        fetch=True
    )
    
    if not existing:
        await ctx.send(f"⚠️ The word `{word}` is not in this server's banned list.")
        return
    
    # Remove word
    db_query(
        "DELETE FROM server_banned_words WHERE guild_id = ? AND word = ?",
        (str(ctx.guild.id), word)
    )
    
    embed = discord.Embed(
        title="✅ Word Unbanned (Server Filter)",
        description=f"Successfully removed `{word}` from server's banned words list.",
        color=discord.Color.green()
    )
    embed.add_field(name="Server", value=ctx.guild.name, inline=True)
    embed.add_field(name="Removed By", value=ctx.author.mention, inline=True)
    
    await ctx.send(embed=embed)

@censor_group.command(name="list", description="List all banned words for this server")
async def censor_list(ctx):
    """List server-specific banned words"""
    if not ctx.guild:
        await ctx.send("❌ This command can only be used in servers.")
        return
    
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ **Permission Denied**\nOnly server administrators can view the censor filter.")
        return
    
    words = get_server_banned_words(ctx.guild.id)
    
    if not words:
        embed = discord.Embed(
            title="📋 Server Banned Words",
            description="No custom banned words configured.\n\n**Note:** Global banned words are currently active for this server.\nUse `/censor add <word>` to create a custom filter (this will disable global filter).",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        return
    
    # Split into chunks if too many words
    word_list = ", ".join([f"`{w}`" for w in sorted(words)])
    
    embed = discord.Embed(
        title="🚫 Server Banned Words",
        description=word_list,
        color=discord.Color.red()
    )
    embed.add_field(name="Total Words", value=str(len(words)), inline=True)
    embed.add_field(name="Filter Type", value="Server Custom (Global Disabled)", inline=True)
    embed.set_footer(text=f"Server: {ctx.guild.name}")
    
    await ctx.send(embed=embed)


@bot.hybrid_group(name="censor-bypass", description="Server Admins: Manage server-specific censor bypass")
async def censor_bypass_group(ctx):
    """Server-specific censor bypass management"""
    if ctx.invoked_subcommand is None:
        await ctx.send("Use `/censor-bypass add`, `/censor-bypass remove`, or `/censor-bypass users`")

@censor_bypass_group.command(name="add", description="Add user to server censor bypass")
async def censor_bypass_add(ctx, user_id: str):
    """Add user to server-specific censor bypass"""
    if not ctx.guild:
        await ctx.send("❌ This command can only be used in servers.")
        return
    
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ **Permission Denied**\nOnly server administrators can manage censor bypass.")
        return
    
    # Check if already bypassed
    if is_server_censor_bypass(ctx.guild.id, user_id):
        await ctx.send(f"⚠️ User `{user_id}` already has censor bypass in this server.")
        return
    
    # Add bypass
    db_query(
        "INSERT INTO server_censor_bypass (guild_id, user_id, added_by) VALUES (?, ?, ?)",
        (str(ctx.guild.id), user_id, str(ctx.author.id))
    )
    
    embed = discord.Embed(
        title="✅ Censor Bypass Added (Server)",
        description=f"User `{user_id}` can now bypass the server's word filter.",
        color=discord.Color.green()
    )
    embed.add_field(name="Server", value=ctx.guild.name, inline=True)
    embed.add_field(name="Added By", value=ctx.author.mention, inline=True)
    
    await ctx.send(embed=embed)

@censor_bypass_group.command(name="remove", description="Remove user from server censor bypass")
async def censor_bypass_remove(ctx, user_id: str):
    """Remove user from server-specific censor bypass"""
    if not ctx.guild:
        await ctx.send("❌ This command can only be used in servers.")
        return
    
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ **Permission Denied**\nOnly server administrators can manage censor bypass.")
        return
    
    # Check if user has bypass
    if not is_server_censor_bypass(ctx.guild.id, user_id):
        await ctx.send(f"⚠️ User `{user_id}` doesn't have censor bypass in this server.")
        return
    
    # Remove bypass
    db_query(
        "DELETE FROM server_censor_bypass WHERE guild_id = ? AND user_id = ?",
        (str(ctx.guild.id), user_id)
    )
    
    embed = discord.Embed(
        title="🚫 Censor Bypass Removed (Server)",
        description=f"User `{user_id}` no longer bypasses the server's word filter.",
        color=discord.Color.red()
    )
    embed.add_field(name="Server", value=ctx.guild.name, inline=True)
    embed.add_field(name="Removed By", value=ctx.author.mention, inline=True)
    
    await ctx.send(embed=embed)

@censor_bypass_group.command(name="users", description="List users with server censor bypass")
async def censor_bypass_users(ctx):
    """List users with server-specific censor bypass"""
    if not ctx.guild:
        await ctx.send("❌ This command can only be used in servers.")
        return
    
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ **Permission Denied**\nOnly server administrators can view censor bypass list.")
        return
    
    users = db_query(
        "SELECT user_id, added_by, added_at FROM server_censor_bypass WHERE guild_id = ?",
        (str(ctx.guild.id),),
        fetch=True
    )
    
    if not users:
        embed = discord.Embed(
            title="📋 Server Censor Bypass Users",
            description="No users have censor bypass in this server.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        return
    
    user_list = "\n".join([f"• <@{u[0]}> (`{u[0]}`) - Added by <@{u[1]}>" for u in users])
    
    embed = discord.Embed(
        title="✅ Server Censor Bypass Users",
        description=user_list,
        color=discord.Color.green()
    )
    embed.add_field(name="Total Users", value=str(len(users)), inline=True)
    embed.set_footer(text=f"Server: {ctx.guild.name}")
    
    await ctx.send(embed=embed)

@bot.hybrid_group(name="blacklist-guild", description="Owner/Admin: Manage guild blacklist.", invoke_without_command=True)
@owner_or_bot_admin()
async def blacklist_guild_group(ctx):
    """List all blacklisted guilds"""
    res = db_query("SELECT guild_id, guild_name, reason, blacklisted_by, blacklisted_at FROM blacklisted_guilds ORDER BY blacklisted_at DESC", fetch=True)
    
    if not res:
        await ctx.send("✅ **No blacklisted guilds**\nThe guild blacklist is currently empty.")
        return
    
    embed = discord.Embed(
        title="🚫 Blacklisted Guilds",
        description="Servers that are banned from using this bot:",
        color=discord.Color.dark_red()
    )
    
    for guild in res:
        guild_id, guild_name, reason, blacklisted_by, blacklisted_at = guild
        embed.add_field(
            name=f"🏰 {guild_name}",
            value=f"**ID:** `{guild_id}`\n**Reason:** {reason}\n**By:** <@{blacklisted_by}>\n**Date:** {blacklisted_at}",
            inline=False
        )
    
    embed.set_footer(text=f"Total: {len(res)} blacklisted guild(s)")
    await ctx.send(embed=embed)

@blacklist_guild_group.command(name="add")
@owner_or_bot_admin()
async def blacklist_guild_add(ctx, guild_id: str, *, reason: str = "No reason provided"):
    """Blacklist a guild and force bot to leave"""
    try:
        # DEFER RESPONSE IMMEDIATELY to prevent interaction timeout
        await ctx.defer()
        
        guild = bot.get_guild(int(guild_id))
        
        # Check if already blacklisted
        existing = db_query("SELECT guild_id FROM blacklisted_guilds WHERE guild_id = ?", (guild_id,), fetch=True)
        if existing:
            await ctx.followup.send(f"⚠️ **Guild `{guild_id}` is already blacklisted.**")
            return
        
        guild_name = guild.name if guild else "Unknown Server"
        
        # Add to blacklist database
        db_query(
            "INSERT INTO blacklisted_guilds (guild_id, guild_name, blacklisted_by, reason) VALUES (?, ?, ?, ?)",
            (guild_id, guild_name, str(ctx.author.id), reason)
        )
        
        # Log the action
        log_msg = f"Guild {guild_name} ({guild_id}) BLACKLISTED by {ctx.author.name} ({ctx.author.id}). Reason: {reason}"
        db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
        
        # Get current time
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Try to notify guild owner before leaving
        owner_notified = False
        if guild and guild.owner:
            try:
                dm_message = f"""🚫 **{BOT_NAME} Bot - Server Blacklisted**

Hello {guild.owner.name},

Your server **{guild_name}** has been blacklisted from using {BOT_NAME} Bot.

**Reason:** {reason}

**What this means:**
• The bot will leave your server immediately
• Your server cannot re-add the bot
• This is a permanent restriction

**Appeal Process:**
If you believe this is a mistake, contact: <@{OWNER_ID}>
**Join the Support Server:** {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}

*Timestamp: {get_discord_timestamp(now, style='F')}*
"""
                await guild.owner.send(dm_message)
                owner_notified = True
            except:
                pass
        
        # Leave the guild if bot is in it
        left_guild = False
        if guild:
            try:
                await guild.leave()
                left_guild = True
            except Exception as e:
                left_guild = False
        
        # Log to blacklist channel
        log_embed = discord.Embed(
            title="🚫 Guild Blacklisted",
            description=f"A server has been blacklisted.",
            color=discord.Color.dark_red(),
            timestamp=now
        )
        log_embed.add_field(name="🏰 Server Name", value=guild_name, inline=True)
        log_embed.add_field(name="🆔 Server ID", value=f"`{guild_id}`", inline=True)
        log_embed.add_field(name="⚖️ Blacklisted By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
        
        if guild:
            log_embed.add_field(name="👑 Server Owner", value=f"<@{guild.owner.id}> (`{guild.owner.id}`)", inline=True)
            log_embed.add_field(name="👥 Member Count", value=str(guild.member_count), inline=True)
        
        log_embed.add_field(name="📝 Reason", value=reason, inline=False)
        log_embed.add_field(name="📬 Owner Notified", value="✅ Yes" if owner_notified else "❌ No", inline=True)
        log_embed.add_field(name="🚪 Bot Left Server", value="✅ Yes" if left_guild else "❌ Not in server", inline=True)
        
        await log_to_channel(bot, 'blacklist', log_embed)
        
        # Confirm to command user
        embed = discord.Embed(
            title="🚫 Guild Blacklisted",
            description=f"Server has been blacklisted.",
            color=discord.Color.red()
        )
        embed.add_field(name="Server Name", value=guild_name, inline=True)
        embed.add_field(name="Server ID", value=guild_id, inline=True)
        embed.add_field(name="Blacklisted By", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Owner Notified", value="✅ Yes" if owner_notified else "❌ No", inline=True)
        embed.add_field(name="Bot Left", value="✅ Yes" if left_guild else "❌ Not in server", inline=True)
        
        await ctx.followup.send(embed=embed)
        
    except ValueError:
        await ctx.followup.send("❌ **Invalid guild ID**\nPlease provide a valid numeric guild ID.")
    except Exception as e:
        await ctx.followup.send(f"❌ **Error:** {str(e)}")

@blacklist_guild_group.command(name="remove")
@owner_or_bot_admin()
async def blacklist_guild_remove(ctx, guild_id: str, *, reason: str = "No reason provided"):
    """Remove a guild from the blacklist"""
    # DEFER RESPONSE IMMEDIATELY to prevent interaction timeout
    await ctx.defer()
    
    # Check if blacklisted
    existing = db_query("SELECT guild_name, blacklisted_by, blacklisted_at FROM blacklisted_guilds WHERE guild_id = ?", (guild_id,), fetch=True)
    
    if not existing:
        await ctx.followup.send(f"⚠️ **Guild `{guild_id}` is not blacklisted.**")
        return
    
    guild_name, blacklisted_by, blacklisted_at = existing[0]
    
    # Remove from blacklist
    db_query("DELETE FROM blacklisted_guilds WHERE guild_id = ?", (guild_id,))
    
    # Log the action
    log_msg = f"Guild {guild_name} ({guild_id}) removed from blacklist by {ctx.author.name} ({ctx.author.id}). Reason: {reason}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Get current time
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # Log to blacklist channel
    log_embed = discord.Embed(
        title="✅ Guild Unblacklisted",
        description=f"A server has been removed from the blacklist.",
        color=discord.Color.green(),
        timestamp=now
    )
    log_embed.add_field(name="🏰 Server Name", value=guild_name, inline=True)
    log_embed.add_field(name="🆔 Server ID", value=f"`{guild_id}`", inline=True)
    log_embed.add_field(name="⚖️ Removed By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📜 Originally Blacklisted", value=f"**By:** <@{blacklisted_by}>\n**Date:** {blacklisted_at}", inline=False)
    log_embed.add_field(name="📝 Removal Reason", value=reason, inline=False)
    
    await log_to_channel(bot, 'blacklist', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="✅ Guild Unblacklisted",
        description=f"Server has been removed from the blacklist and can now re-add the bot.",
        color=discord.Color.green()
    )
    embed.add_field(name="Server Name", value=guild_name, inline=True)
    embed.add_field(name="Server ID", value=guild_id, inline=True)
    embed.add_field(name="Removed By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    
    await ctx.followup.send(embed=embed)
@bot.hybrid_command(name="addstrike", description="Owner/Admin: Add strikes to a user.")
@owner_or_bot_admin()
async def add_strike(ctx, user_id: str, amount: int = 1, *, reason: str = "No reason provided"):
    res = db_query("SELECT strikes FROM users WHERE user_id = ?", (user_id,), fetch=True)
    current_strikes = res[0][0] if res else 0
    new_strikes = current_strikes + amount
    is_banned = 1 if new_strikes >= 3 else 0

    db_query("INSERT OR REPLACE INTO users (user_id, strikes, blacklisted) VALUES (?, ?, ?)", (user_id, new_strikes, is_banned))

    log_msg = f"Strike added to {user_id} by {ctx.author.name} ({ctx.author.id}). Amount: {amount}. Total: {new_strikes}/3. Reason: {reason}"
    if is_banned:
        log_msg += f" | User {user_id} AUTO-BLACKLISTED (3 strikes reached)."

    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_message = f"⚡ **Strike Issued**\n\n**You have received {amount} strike(s)**\n\n**Reason:** {reason}\n**Total Strikes:** {new_strikes}/3\n**Issued By:** Administrator\n\n"
    if is_banned:
        dm_message += f"🚫 **ACCOUNT SUSPENDED**\n\nYou have reached 3 strikes and have been automatically blacklisted from {BOT_NAME} Bot.\n\n**What this means:**\n• You can no longer use the bot\n• All access has been revoked\n• This is a permanent suspension unless appealed\n\n**Appeal Process:**\nContact the bot owner: <@!{OWNER_ID}>\n**Join the Support Server:** {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}"
    else:
        strikes_remaining = 3 - new_strikes
        dm_message += f"⚠️ **Warning:** You are {strikes_remaining} strike(s) away from being blacklisted.\n\n**How to avoid more strikes:**\n• Follow community guidelines\n• Avoid using banned words\n• Be respectful to others\n• Follow server and bot rules"
    
    dm_message += f"\n\n*Timestamp: {get_discord_timestamp(style='F')}*"
    
    dm_sent = await send_user_dm(user_id, dm_message)
    
    # Log to dedicated strikes channel
    log_embed = discord.Embed(
        title="⚡ Strike Issued" if not is_banned else "🚫 User Auto-Blacklisted (3 Strikes)",
        description=f"Strike(s) have been added to a user.",
        color=discord.Color.orange() if not is_banned else discord.Color.dark_red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="⚡ Strikes Added", value=str(amount), inline=True)
    log_embed.add_field(name="📊 Total Strikes", value=f"{new_strikes}/3", inline=True)
    log_embed.add_field(name="⚖️ Actioned By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📌 Status", value="🚫 **AUTO-BANNED**" if is_banned else f"⚠️ Active ({3-new_strikes} remaining)", inline=True)
    log_embed.add_field(name="📬 DM Sent", value="✅ Delivered" if dm_sent else "❌ Failed", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    
    await log_to_channel(bot, 'strikes', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="⚡ Strike Added" if not is_banned else "🚫 User Auto-Blacklisted",
        description=f"Strike(s) successfully added to user `{user_id}`",
        color=discord.Color.orange() if not is_banned else discord.Color.red()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Strikes Added", value=amount, inline=True)
    embed.add_field(name="Total Strikes", value=f"{new_strikes}/3", inline=True)
    embed.add_field(name="Actioned By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Status", value="🚫 AUTO-BANNED" if is_banned else "⚠️ Active", inline=True)
    embed.add_field(name="DM Sent", value="✅ Yes" if dm_sent else "❌ Failed", inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="removestrike", description="Owner/Admin: Remove strikes from a user.")
@owner_or_bot_admin()
async def remove_strike(ctx, user_id: str, amount: int = 1, *, reason: str = "No reason provided"):
    res = db_query("SELECT strikes FROM users WHERE user_id = ?", (user_id,), fetch=True)

    if not res or res[0][0] == 0:
        await ctx.send(f"⚠️ **User `{user_id}` has no strikes to remove.**")
        return

    current_strikes = res[0][0]
    new_strikes = max(0, current_strikes - amount)
    is_banned = 1 if new_strikes >= 3 else 0

    db_query("UPDATE users SET strikes = ?, blacklisted = ? WHERE user_id = ?", (new_strikes, is_banned, user_id))

    log_msg = f"Removed {amount} strike(s) from {user_id} by {ctx.author.name} ({ctx.author.id}). Total: {new_strikes}/3. Reason: {reason}"
    was_unbanned = current_strikes >= 3 and new_strikes < 3
    if was_unbanned:
        log_msg += f" | User {user_id} unbanned (below 3 strikes)."

    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_message = f"✅ **Strike(s) Removed**\n\n**{amount} strike(s) have been removed from your account**\n\n**Reason:** {reason}\n**Previous Strikes:** {current_strikes}/3\n**Current Strikes:** {new_strikes}/3\n**Reviewed By:** Administrator\n\n"
    if was_unbanned:
        dm_message += f"🎉 **ACCOUNT RESTORED**\n\nYour blacklist has been lifted! You can now use {BOT_NAME} Bot again.\n\n**Remember:**\n• Follow community guidelines\n• Avoid accumulating more strikes\n• Be respectful and follow the rules\n\nWelcome back!"
    else:
        dm_message += "**Status:** Your account is in good standing. Keep following the rules to avoid future strikes."
    
    dm_message += f"\n\n*Timestamp: {get_discord_timestamp(style='F')}*"
    
    dm_sent = await send_user_dm(user_id, dm_message)
    
    # Log to dedicated strikes channel
    log_embed = discord.Embed(
        title="✅ Strike(s) Removed" if not was_unbanned else "🎉 User Unbanned (Strike Removal)",
        description=f"Strike(s) have been removed from a user.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="⚡ Strikes Removed", value=str(amount), inline=True)
    log_embed.add_field(name="📊 Remaining Strikes", value=f"{new_strikes}/3", inline=True)
    log_embed.add_field(name="⚖️ Actioned By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📌 Status", value="🎉 **UNBANNED**" if was_unbanned else "✅ Active", inline=True)
    log_embed.add_field(name="📬 DM Sent", value="✅ Delivered" if dm_sent else "❌ Failed", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    
    await log_to_channel(bot, 'strikes', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="✅ Strike Removed" if not was_unbanned else "🎉 User Unbanned",
        description=f"Strike(s) successfully removed from user `{user_id}`",
        color=discord.Color.green()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Strikes Removed", value=amount, inline=True)
    embed.add_field(name="Remaining Strikes", value=f"{new_strikes}/3", inline=True)
    embed.add_field(name="Actioned By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Status", value="🎉 Unbanned" if was_unbanned else "✅ Active", inline=True)
    embed.add_field(name="DM Sent", value="✅ Yes" if dm_sent else "❌ Failed", inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="reactionstats", description="Owner/Admin: View reaction response statistics.")
@owner_or_bot_admin()
async def reaction_stats(ctx):
    """View statistics about reaction responses"""
    
    # Get total reaction responses
    total = db_query("SELECT COUNT(*) FROM reaction_responses", fetch=True)[0][0]
    
    # Get recent reactions (last 24 hours)
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)).isoformat()
    recent = db_query(
        "SELECT COUNT(*) FROM reaction_responses WHERE timestamp > ?",
        (cutoff,),
        fetch=True
    )[0][0]
    
    # Get most common reactions
    common_reactions = db_query(
        "SELECT reaction_emoji, COUNT(*) as count FROM reaction_responses GROUP BY reaction_emoji ORDER BY count DESC LIMIT 10",
        fetch=True
    )
    
    # Get top reactors
    top_reactors = db_query(
        "SELECT reactor_id, COUNT(*) as count FROM reaction_responses GROUP BY reactor_id ORDER BY count DESC LIMIT 5",
        fetch=True
    )
    
    embed = discord.Embed(
        title="📊 Reaction Response Statistics",
        description="Bot's reaction detection and response data",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="📈 Total Responses", value=str(total), inline=True)
    embed.add_field(name="🕐 Last 24h", value=str(recent), inline=True)
    embed.add_field(name="⏱️ Message Limit", value="14 days", inline=True)
    
    if common_reactions:
        reaction_list = "\n".join([f"{r[0]} - {r[1]} times" for r in common_reactions[:5]])
        embed.add_field(name="🔥 Most Common Reactions", value=reaction_list, inline=False)
    
    if top_reactors:
        reactor_list = "\n".join([f"<@{r[0]}> - {r[1]} reactions" for r in top_reactors])
        embed.add_field(name="👥 Top Reactors", value=reactor_list, inline=False)
    
    embed.set_footer(text="Reaction responses are AI-generated based on context")
    
    await ctx.send(embed=embed)


@bot.hybrid_command(name="togglereactions", description="Admin: Toggle reaction responses for this channel.")
async def toggle_reactions(ctx, enabled: bool = None):
    """Enable or disable reaction responses in the current channel"""
    
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\n**Required:** Administrator permissions")
            return
    
    # Add new column to settings if not exists (you may need to run this migration once)
    try:
        db_query("ALTER TABLE settings ADD COLUMN reactions_enabled INTEGER DEFAULT 1")
    except:
        pass  # Column already exists
    
    if enabled is None:
        # Check current status
        status = db_query(
            "SELECT reactions_enabled FROM settings WHERE id = ?",
            (str(ctx.channel.id),),
            fetch=True
        )
        current = status[0][0] if status else 1
        
        await ctx.send(
            f"🔔 **Reaction responses are currently {'ENABLED' if current else 'DISABLED'} in this channel.**\n\n"
            f"Use `/togglereactions true` to enable or `/togglereactions false` to disable."
        )
        return
    
    # Update setting
    db_query(
        "INSERT OR REPLACE INTO settings (id, reactions_enabled) VALUES (?, ?)",
        (str(ctx.channel.id), 1 if enabled else 0)
    )
    
    embed = discord.Embed(
        title=f"{'🔔 Enabled' if enabled else '🔕 Disabled'} Reaction Responses",
        description=f"Reaction responses are now **{'ENABLED' if enabled else 'DISABLED'}** in this channel.",
        color=discord.Color.green() if enabled else discord.Color.red()
    )
    
    await ctx.send(embed=embed)


@bot.hybrid_command(name="clearreactionlog", description="Owner/Admin: Clear reaction response logs.")
@owner_or_bot_admin()
async def clear_reaction_log(ctx, days: int = None):
    """Clear reaction response logs, optionally older than X days"""
    
    if days:
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
        count_before = db_query("SELECT COUNT(*) FROM reaction_responses WHERE timestamp < ?", (cutoff,), fetch=True)[0][0]
        db_query("DELETE FROM reaction_responses WHERE timestamp < ?", (cutoff,))
        await ctx.send(f"🗑️ **Cleared {count_before} reaction logs older than {days} days.**")
    else:
        count = db_query("SELECT COUNT(*) FROM reaction_responses", fetch=True)[0][0]
        db_query("DELETE FROM reaction_responses")
        await ctx.send(f"🗑️ **Cleared all {count} reaction response logs.**")
        
@bot.hybrid_command(name="strikelist", description="Owner/Admin: View all users with strikes.")
@owner_or_bot_admin()
async def strike_list(ctx):
    res = db_query("SELECT user_id, strikes FROM users WHERE strikes > 0 ORDER BY strikes DESC", fetch=True)
    
    if not res:
        await ctx.send("✅ **No active strikes**\nAll users are in good standing.")
        return
    
    strike_text = "\n".join([f"{'🚫' if r[1] >= 3 else '⚡'} <@{r[0]}> - **{r[1]}/3** strikes" for r in res])
    
    embed = discord.Embed(
        title="⚡ Strike Ledger", 
        description=strike_text, 
        color=discord.Color.orange()
    )
    embed.set_footer(text=f"Total users with strikes: {len(res)}")
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="clearstrike", description="Owner/Admin: Clear all strikes for a user.")
@owner_or_bot_admin()
async def clear_strike(ctx, user_id: str, *, reason: str = "Strikes cleared by administrator"):
    res = db_query("SELECT strikes FROM users WHERE user_id = ?", (user_id,), fetch=True)
    
    if not res or res[0][0] == 0:
        await ctx.send(f"⚠️ **User `{user_id}` has no strikes to clear.**")
        return
    
    previous_strikes = res[0][0]
    db_query("UPDATE users SET strikes = 0, blacklisted = 0 WHERE user_id = ?", (user_id,))
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (f"All strikes cleared for {user_id} by {ctx.author.name} ({ctx.author.id}). Previous strikes: {previous_strikes}. Reason: {reason}",))
    
    # Send DM to user
    dm_message = f"✅ **All Strikes Cleared**\n\n**Your account has been fully restored**\n\n**Previous Strikes:** {previous_strikes}/3\n**Current Strikes:** 0/3\n**Reason:** {reason}\n\n🎉 You now have a clean slate! Your account is in good standing.\n\n**Remember to:**\n• Follow all community guidelines\n• Respect other users\n• Avoid banned words and inappropriate behavior\n\nThank you for being part of the community!\n\n*Timestamp: {get_discord_timestamp(style='F')}*"
    
    dm_sent = await send_user_dm(user_id, dm_message)
    
    # Log to strikes channel
    log_embed = discord.Embed(
        title="🧹 All Strikes Cleared",
        description=f"All strikes have been cleared for a user.",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="📊 Previous Strikes", value=f"{previous_strikes}/3", inline=True)
    log_embed.add_field(name="📊 Current Strikes", value="0/3", inline=True)
    log_embed.add_field(name="⚖️ Actioned By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📬 DM Sent", value="✅ Delivered" if dm_sent else "❌ Failed", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    
    await log_to_channel(bot, 'strikes', log_embed)
    
    embed = discord.Embed(
        title="✅ Strikes Cleared",
        description=f"All strikes have been cleared for user `{user_id}`",
        color=discord.Color.green()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Previous Strikes", value=f"{previous_strikes}/3", inline=True)
    embed.add_field(name="Actioned By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    
    await ctx.send(embed=embed)

@bot.tree.command(name="chess", description="Play chess against Stockfish or another player")
async def chess_command(interaction: discord.Interaction, opponent: discord.Member = None):
    """Start a chess game"""
    await interaction.response.defer()
    
    # Check if user already has an active game
    existing_game = get_active_game(str(interaction.user.id))
    if existing_game:
        await interaction.followup.send("❌ You already have an active chess game! Finish or resign from it first.", ephemeral=True)
        return
    
    if opponent:
        # Check if opponent is a bot
        if opponent.bot:
            await interaction.followup.send("❌ You cannot play against bots!", ephemeral=True)
            return
        
        # Check if opponent is the same as user
        if opponent.id == interaction.user.id:
            await interaction.followup.send("❌ You cannot play against yourself!", ephemeral=True)
            return
        
        # Check if opponent has an active game
        opponent_game = get_active_game(str(opponent.id))
        if opponent_game:
            await interaction.followup.send(f"❌ {opponent.mention} already has an active chess game!", ephemeral=True)
            return
        
        # Send invite
        invite_embed = discord.Embed(
            title="♟️ Chess Match Invitation",
            description=f"<@{interaction.user.id}> has challenged you to a chess match!\n\nDo you accept?",
            color=discord.Color.blue()
        )
        
        invite_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        invite_embed.set_footer(text="You have 5 minutes to respond")
        
        view = ChessInviteView(str(interaction.user.id), str(opponent.id))
        
        await interaction.followup.send(
            content=opponent.mention,
            embed=invite_embed,
            view=view
        )
    else:
        # Play against AI (Stockfish simulation - random moves)
        board = chess.Board()
        
        # Store in database
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT INTO chess_games 
                     (player1_id, player2_id, current_turn, board_fen, channel_id)
                     VALUES (?, ?, ?, ?, ?)''',
                 (str(interaction.user.id), "stockfish", str(interaction.user.id), board.fen(), str(interaction.channel.id)))
        game_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Create board image (no last move for starting position)
        board_image = await board_to_image(board)
        file = discord.File(board_image, filename="chess_board.png")
        
        # Create game embed
        embed = discord.Embed(
            title="♟️ Chess vs Stockfish",
            description=f"**Player:** <@{interaction.user.id}>\n**Opponent:** 🤖 Stockfish\n\n**Your turn!**",
            color=discord.Color.blue()
        )
        
        embed.set_image(url="attachment://chess_board.png")
        embed.set_footer(text=f"Game ID: {game_id}")
        
        # Create game view
        view = ChessGameView(game_id, board, str(interaction.user.id), True)
        
        await interaction.followup.send(
            embed=embed,
            view=view,
            file=file
        )
        
@bot.hybrid_group(name="bannedword", invoke_without_command=True)
@owner_or_bot_admin()
async def bw_group(ctx):
    res = db_query("SELECT word FROM banned_words ORDER BY word", fetch=True)
    
    if not res:
        await ctx.send("✅ **No banned words**\nThe word filter is currently empty.")
        return
    
    words = ', '.join([f"`{r[0]}`" for r in res])
    embed = discord.Embed(
        title="🔇 Banned Words List",
        description=words,
        color=discord.Color.red()
    )
    embed.set_footer(text=f"Total: {len(res)} banned word(s)")
    
    await ctx.send(embed=embed)

@bw_group.command(name="add")
@owner_or_bot_admin()
async def bw_add(ctx, word: str):
    word_lower = word.lower()
    existing = db_query("SELECT word FROM banned_words WHERE word = ?", (word_lower,), fetch=True)
    
    if existing:
        await ctx.send(f"⚠️ **`{word}` is already in the banned words list.**")
        return
    
    db_query("INSERT INTO banned_words VALUES (?)", (word_lower,))
    log_msg = f"Banned word added: '{word}' by {ctx.author.name} ({ctx.author.id})"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Log to banned words channel
    log_embed = discord.Embed(
        title="🔇 Banned Word Added",
        description=f"A new word has been added to the filter.",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    log_embed.add_field(name="🔤 Word", value=f"`{word_lower}`", inline=True)
    log_embed.add_field(name="⚖️ Added By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📊 Total Banned Words", value=str(len(db_query("SELECT word FROM banned_words", fetch=True))), inline=True)
    
    await log_to_channel(bot, 'banned_words', log_embed)
    
    await ctx.send(f"🚫 **Word banned successfully**\n`{word}` has been added to the filter and will be automatically removed from messages.")

@bw_group.command(name="remove")
@owner_or_bot_admin()
async def bw_rem(ctx, word: str):
    word_lower = word.lower()
    existing = db_query("SELECT word FROM banned_words WHERE word = ?", (word_lower,), fetch=True)
    
    if not existing:
        await ctx.send(f"⚠️ **`{word}` is not in the banned words list.**")
        return
    
    db_query("DELETE FROM banned_words WHERE word = ?", (word_lower,))
    log_msg = f"Banned word removed: '{word}' by {ctx.author.name} ({ctx.author.id})"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Log to banned words channel
    log_embed = discord.Embed(
        title="✅ Banned Word Removed",
        description=f"A word has been removed from the filter.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    log_embed.add_field(name="🔤 Word", value=f"`{word_lower}`", inline=True)
    log_embed.add_field(name="⚖️ Removed By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📊 Total Banned Words", value=str(len(db_query("SELECT word FROM banned_words", fetch=True))), inline=True)
    
    await log_to_channel(bot, 'banned_words', log_embed)
    
    await ctx.send(f"✅ **Word unbanned successfully**\n`{word}` has been removed from the filter.")

@bot.hybrid_group(name="bypass", description="Owner/Admin: Manage word filter bypass.", invoke_without_command=True)
@owner_or_bot_admin()
async def bypass_group(ctx):
    """List all users with word filter bypass"""
    res = db_query("SELECT user_id, reason, added_by, added_at FROM word_filter_bypass ORDER BY added_at DESC", fetch=True)
    
    if not res:
        await ctx.send("✅ **No bypass users**\nNo users currently have word filter bypass privileges.")
        return
    
    embed = discord.Embed(
        title="🔓 Word Filter Bypass List",
        description="Users who can use banned words:",
        color=discord.Color.blue()
    )
    
    for user in res:
        user_id, reason, added_by, added_at = user
        embed.add_field(
            name=f"👤 <@{user_id}>",
            value=f"**ID:** `{user_id}`\n**Reason:** {reason}\n**Added By:** <@{added_by}>\n**Date:** {added_at}",
            inline=False
        )
    
    embed.set_footer(text=f"Total: {len(res)} user(s) with bypass")
    await ctx.send(embed=embed)

@bypass_group.command(name="add")
@owner_or_bot_admin()
async def bypass_add(ctx, user_id: str, *, reason: str = "No reason provided"):
    """Add a user to word filter bypass"""
    # Check if already has bypass
    existing = db_query("SELECT user_id FROM word_filter_bypass WHERE user_id = ?", (user_id,), fetch=True)
    if existing:
        await ctx.send(f"⚠️ **User `{user_id}` already has word filter bypass.**")
        return
    
    # Add to database
    db_query("INSERT INTO word_filter_bypass (user_id, added_by, reason) VALUES (?, ?, ?)", 
             (user_id, str(ctx.author.id), reason))
    
    # Log the action
    log_msg = f"Word filter bypass granted to {user_id} by {ctx.author.name} ({ctx.author.id}). Reason: {reason}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_message = f"""🔓 **Word Filter Bypass Granted**

You have been granted permission to bypass the word filter in {BOT_NAME} Bot.

**Reason:** {reason}
**Granted By:** {ctx.author.name}

**What this means:**
• You can use banned words without being filtered
• Your messages will not be automatically deleted
• This privilege can be revoked at any time

**Important:**
• Use this privilege responsibly
• Don't abuse this permission
• Follow all other server and bot rules

*Timestamp: {get_discord_timestamp(style='F')}*
"""
    dm_sent = await send_user_dm(user_id, dm_message)
    
    # Log to banned words channel (since it's filter-related)
    log_embed = discord.Embed(
        title="🔓 Word Filter Bypass Granted",
        description="A user has been granted word filter bypass privileges.",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="⚖️ Granted By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    log_embed.add_field(name="📬 DM Sent", value="✅ Delivered" if dm_sent else "❌ Failed", inline=True)
    log_embed.add_field(name="🕐 Timestamp", value=get_discord_timestamp(style='F'), inline=True)
    
    await log_to_channel(bot, 'banned_words', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="🔓 Word Filter Bypass Granted",
        description=f"User `{user_id}` can now bypass the word filter.",
        color=discord.Color.green()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Granted By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="DM Notification", value="✅ Sent" if dm_sent else "❌ Failed", inline=True)
    
    await ctx.send(embed=embed)

@bypass_group.command(name="remove")
@owner_or_bot_admin()
async def bypass_remove(ctx, user_id: str, *, reason: str = "No reason provided"):
    """Remove a user from word filter bypass"""
    # Check if has bypass
    existing = db_query("SELECT user_id FROM word_filter_bypass WHERE user_id = ?", (user_id,), fetch=True)
    if not existing:
        await ctx.send(f"⚠️ **User `{user_id}` does not have word filter bypass.**")
        return
    
    # Remove from database
    db_query("DELETE FROM word_filter_bypass WHERE user_id = ?", (user_id,))
    
    # Log the action
    log_msg = f"Word filter bypass revoked from {user_id} by {ctx.author.name} ({ctx.author.id}). Reason: {reason}"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to user
    dm_message = f"""🔒 **Word Filter Bypass Revoked**

Your word filter bypass privileges have been revoked.

**Reason:** {reason}
**Revoked By:** {ctx.author.name}

**What this means:**
• You can no longer use banned words
• Your messages will be filtered like normal users
• Using banned words will result in message deletion

**Remember:**
• Follow the word filter rules
• Avoid using banned words
• Repeated violations may result in strikes

*Timestamp: {get_discord_timestamp(style='F')}*
"""
    dm_sent = await send_user_dm(user_id, dm_message)
    
    # Log to banned words channel
    log_embed = discord.Embed(
        title="🔒 Word Filter Bypass Revoked",
        description="Word filter bypass has been removed from a user.",
        color=discord.Color.orange(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    log_embed.add_field(name="👤 User ID", value=f"`{user_id}`", inline=True)
    log_embed.add_field(name="⚖️ Revoked By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    log_embed.add_field(name="📬 DM Sent", value="✅ Delivered" if dm_sent else "❌ Failed", inline=True)
    log_embed.add_field(name="🕐 Timestamp", value=get_discord_timestamp(style='F'), inline=True)
    
    await log_to_channel(bot, 'banned_words', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="🔒 Word Filter Bypass Revoked",
        description=f"User `{user_id}` can no longer bypass the word filter.",
        color=discord.Color.orange()
    )
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Revoked By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="DM Notification", value="✅ Sent" if dm_sent else "❌ Failed", inline=True)
    
    await ctx.send(embed=embed)


@bot.hybrid_command(name="listwords", description="Owner/Admin: List all banned words.")
@owner_or_bot_admin()
async def list_words(ctx):
    await bw_group.invoke(ctx)

@bot.hybrid_command(name="logs", description="Owner/Admin: View recent moderation logs.")
@owner_or_bot_admin()
async def view_logs(ctx):
    res = db_query("SELECT log, timestamp FROM admin_logs ORDER BY timestamp DESC LIMIT 15", fetch=True)
    
    if not res:
        await ctx.send("📋 **No admin logs found**\nNo moderation actions have been logged yet.")
        return
    
    log_text = "\n".join([f"[{r[1]}] {r[0]}" for r in res])
    
    await ctx.send(f"```\n{log_text}\n```")

@bot.hybrid_command(name="clearadminlogs", description="Owner/Admin: Clear all admin logs.")
@owner_or_bot_admin()
async def clear_admin_logs(ctx):
    count = db_query("SELECT COUNT(*) FROM admin_logs", fetch=True)[0][0]
    db_query("DELETE FROM admin_logs")
    
    # Log this action to admin logs channel before clearing
    log_embed = discord.Embed(
        title="🗑️ Admin Logs Cleared",
        description=f"All admin logs have been cleared.",
        color=discord.Color.orange(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    log_embed.add_field(name="📊 Logs Cleared", value=str(count), inline=True)
    log_embed.add_field(name="⚖️ Cleared By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    
    await log_to_channel(bot, 'admin_logs', log_embed)
    
    await ctx.send(f"🗑️ **Admin logs cleared**\n**Removed:** {count} log entries")

@bot.hybrid_command(name="searchlogs", description="Owner/Admin: Search interaction logs.")
@owner_or_bot_admin()
async def search_logs(ctx, keyword: str):
    rows = db_query("SELECT * FROM interaction_logs WHERE prompt LIKE ? OR response LIKE ? ORDER BY timestamp DESC LIMIT 20", (f"%{keyword}%", f"%{keyword}%"), fetch=True)

    if not rows:
        await ctx.send(f"❌ **No results found for:** `{keyword}`")
        return

    text = "\n".join([f"[{r[3]}]: {r[5][:50]}..." for r in rows])
    await ctx.send(f"🔍 **Search Results for `{keyword}`**\n```\n{text}\n```")

# Report Action View with Buttons
class ReportActionView(discord.ui.View):
    def __init__(self, report_id, reported_user_id, reported_user_name):
        super().__init__(timeout=None)  # No timeout for report actions
        self.report_id = report_id
        self.reported_user_id = reported_user_id
        self.reported_user_name = reported_user_name
    
    @discord.ui.button(label="Claim Report", style=discord.ButtonStyle.primary, emoji="✋", custom_id="claim_report")
    async def claim_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user is admin
        if not is_bot_admin(interaction.user.id):
            await interaction.response.send_message("❌ Only bot admins can claim reports.", ephemeral=True)
            return
        
        # Update database to mark as claimed
        db_query("UPDATE reports SET status = 'claimed' WHERE report_id = ?", (self.report_id,))
        db_query("INSERT INTO admin_logs (log) VALUES (?)", 
                (f"Report #{self.report_id} claimed by {interaction.user.name} ({interaction.user.id})",))
        
        # Update embed
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.blue()
        embed.set_footer(text=f"Report ID: {self.report_id} | Status: CLAIMED by {interaction.user.name} | {embed.footer.text.split('|')[-1]}")
        
        # Disable claim button
        button.disabled = True
        button.label = f"Claimed by {interaction.user.name}"
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Log to reports channel
        log_embed = discord.Embed(
            title=f"✋ Report #{self.report_id} Claimed",
            description=f"Report has been claimed by an administrator.",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        log_embed.add_field(name="👤 Reported User", value=f"<@{self.reported_user_id}> (`{self.reported_user_id}`)", inline=True)
        log_embed.add_field(name="⚖️ Claimed By", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
        log_embed.add_field(name="🆔 Report ID", value=f"`#{self.report_id}`", inline=True)
        
        await log_to_channel(bot, 'reports', log_embed)
    
    @discord.ui.button(label="Add Strike", style=discord.ButtonStyle.danger, emoji="⚡", custom_id="add_strike")
    async def add_strike_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user is admin
        if not is_bot_admin(interaction.user.id):
            await interaction.response.send_message("❌ Only bot admins can add strikes.", ephemeral=True)
            return
        
        # Add strike
        res = db_query("SELECT strikes FROM users WHERE user_id = ?", (str(self.reported_user_id),), fetch=True)
        current_strikes = res[0][0] if res else 0
        new_strikes = current_strikes + 1
        is_banned = 1 if new_strikes >= 3 else 0
        
        db_query("INSERT OR REPLACE INTO users (user_id, strikes, blacklisted) VALUES (?, ?, ?)", 
                (str(self.reported_user_id), new_strikes, is_banned))
        
        # Update report status
        db_query("UPDATE reports SET status = 'actioned' WHERE report_id = ?", (self.report_id,))
        
        log_msg = f"Report #{self.report_id}: Strike added to {self.reported_user_id} by {interaction.user.name} ({interaction.user.id}). Total: {new_strikes}/3. Reason: Action from report"
        if is_banned:
            log_msg += f" | User {self.reported_user_id} AUTO-BLACKLISTED."
        db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
        
        # Send DM to reported user
        dm_message = f"⚡ **Strike Issued**\n\n**You have received 1 strike**\n\n**Reason:** Action taken from user report #{self.report_id}\n**Total Strikes:** {new_strikes}/3\n**Issued By:** Administrator\n\n"
        if is_banned:
            dm_message += f"🚫 **ACCOUNT SUSPENDED**\n\nYou have reached 3 strikes and have been automatically blacklisted from {BOT_NAME} Bot.\n\n**Appeal Process:**\nContact the bot owner: <@{OWNER_ID}>\n**Join the Support Server:** {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}"
        else:
            strikes_remaining = 3 - new_strikes
            dm_message += f"⚠️ **Warning:** You are {strikes_remaining} strike(s) away from being blacklisted.\n\n**How to avoid more strikes:**\n• Follow community guidelines\n• Be respectful to others\n• Follow server and bot rules"
        
        dm_message += f"\n\n*Timestamp: {datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}*"
        dm_sent = await send_user_dm(str(self.reported_user_id), dm_message)
        
        # Log to strikes channel
        log_embed = discord.Embed(
            title="⚡ Strike Issued (From Report)" if not is_banned else "🚫 User Auto-Blacklisted (3 Strikes - From Report)",
            description=f"Strike added from report #{self.report_id}.",
            color=discord.Color.orange() if not is_banned else discord.Color.dark_red(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        log_embed.add_field(name="👤 User ID", value=f"`{self.reported_user_id}`", inline=True)
        log_embed.add_field(name="👤 User Name", value=self.reported_user_name, inline=True)
        log_embed.add_field(name="⚡ Strikes Added", value="1", inline=True)
        log_embed.add_field(name="📊 Total Strikes", value=f"{new_strikes}/3", inline=True)
        log_embed.add_field(name="⚖️ Actioned By", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
        log_embed.add_field(name="📬 DM Sent", value="✅ Delivered" if dm_sent else "❌ Failed", inline=True)
        log_embed.add_field(name="🆔 Report ID", value=f"`#{self.report_id}`", inline=True)
        log_embed.add_field(name="📌 Status", value="🚫 **AUTO-BANNED**" if is_banned else f"⚠️ Active ({3-new_strikes} remaining)", inline=True)
        log_embed.add_field(name="📝 Reason", value=f"Action from report #{self.report_id}", inline=False)
        
        await log_to_channel(bot, 'strikes', log_embed)
        
        # ALSO log to reports channel
        report_log_embed = discord.Embed(
            title=f"⚡ Report #{self.report_id} - Strike Issued",
            description=f"A strike was issued based on this report.",
            color=discord.Color.orange() if not is_banned else discord.Color.dark_red(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        report_log_embed.add_field(name="👤 Reported User", value=f"<@{self.reported_user_id}>\n`{self.reported_user_id}`", inline=True)
        report_log_embed.add_field(name="⚡ Strikes", value=f"{new_strikes}/3", inline=True)
        report_log_embed.add_field(name="⚖️ Actioned By", value=f"{interaction.user.mention}", inline=True)
        report_log_embed.add_field(name="📌 Status", value="🚫 **AUTO-BANNED**" if is_banned else "⚠️ Active", inline=True)
        report_log_embed.add_field(name="📬 DM Sent", value="✅ Yes" if dm_sent else "❌ Failed", inline=True)
        report_log_embed.add_field(name="🆔 Report ID", value=f"`#{self.report_id}`", inline=True)
        
        await log_to_channel(bot, 'reports', report_log_embed)
        
        # Update embed
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.orange() if not is_banned else discord.Color.dark_red()
        embed.set_footer(text=f"Report ID: {self.report_id} | Status: ACTIONED (Strike) by {interaction.user.name} | {new_strikes}/3 strikes" + (" | AUTO-BANNED" if is_banned else ""))
        
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(
            f"✅ **Strike Added Successfully**\n\n"
            f"**User:** <@{self.reported_user_id}>\n"
            f"**New Strike Total:** {new_strikes}/3\n"
            f"**Status:** {'🚫 AUTO-BLACKLISTED' if is_banned else '⚠️ Active'}\n"
            f"**DM Notification:** {'✅ Sent' if dm_sent else '❌ Failed'}", 
            ephemeral=True
        )
    
    @discord.ui.button(label="Blacklist", style=discord.ButtonStyle.danger, emoji="🚫", custom_id="blacklist")
    async def blacklist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user is admin
        if not is_bot_admin(interaction.user.id):
            await interaction.response.send_message("❌ Only bot admins can blacklist users.", ephemeral=True)
            return
        
        # Check if already blacklisted
        existing_blacklist = db_query("SELECT blacklisted FROM users WHERE user_id = ?", (str(self.reported_user_id),), fetch=True)
        if existing_blacklist and existing_blacklist[0][0] == 1:
            await interaction.response.send_message(
                f"⚠️ **User Already Blacklisted**\n\n<@{self.reported_user_id}> is already blacklisted from the bot.",
                ephemeral=True
            )
            return
        
        # Blacklist user
        db_query("INSERT OR REPLACE INTO users (user_id, blacklisted) VALUES (?, 1)", (str(self.reported_user_id),))
        
        # Update report status
        db_query("UPDATE reports SET status = 'actioned' WHERE report_id = ?", (self.report_id,))
        
        log_msg = f"Report #{self.report_id}: User {self.reported_user_id} BLACKLISTED by {interaction.user.name} ({interaction.user.id}). Reason: Action from report"
        db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
        
        # Send DM
        dm_message = f"🚫 **You have been blacklisted from {BOT_NAME} Bot**\n\n**Reason:** Action taken from user report #{self.report_id}\n\n**What this means:**\n• You can no longer use any bot commands\n• The bot will not respond to your messages\n• This action has been logged by bot administrators\n\n**Believe this is a mistake?**\nContact the bot owner: <@{OWNER_ID}>\n**Join the Support Server:** {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}\n\n*Timestamp: {datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}*"
        dm_sent = await send_user_dm(str(self.reported_user_id), dm_message)
        
        # Log to blacklist channel
        log_embed = discord.Embed(
            title="🚫 User Blacklisted (From Report)",
            description=f"User blacklisted from report #{self.report_id}.",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        log_embed.add_field(name="👤 User ID", value=f"`{self.reported_user_id}`", inline=True)
        log_embed.add_field(name="👤 User Name", value=self.reported_user_name, inline=True)
        log_embed.add_field(name="⚖️ Actioned By", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
        log_embed.add_field(name="🆔 Report ID", value=f"`#{self.report_id}`", inline=True)
        log_embed.add_field(name="📬 DM Notification", value="✅ Delivered" if dm_sent else "❌ Failed (DMs closed)", inline=True)
        log_embed.add_field(name="🕐 Timestamp", value=datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
        log_embed.add_field(name="📝 Reason", value=f"Action from report #{self.report_id}", inline=False)
        
        await log_to_channel(bot, 'blacklist', log_embed)
        
        # ALSO log to reports channel
        report_log_embed = discord.Embed(
            title=f"🚫 Report #{self.report_id} - User Blacklisted",
            description=f"User was blacklisted based on this report.",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        report_log_embed.add_field(name="👤 Blacklisted User", value=f"<@{self.reported_user_id}>\n`{self.reported_user_id}`", inline=True)
        report_log_embed.add_field(name="⚖️ Actioned By", value=f"{interaction.user.mention}", inline=True)
        report_log_embed.add_field(name="📬 DM Sent", value="✅ Yes" if dm_sent else "❌ Failed", inline=True)
        report_log_embed.add_field(name="🆔 Report ID", value=f"`#{self.report_id}`", inline=True)
        report_log_embed.add_field(name="🕐 Actioned At", value=datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
        
        await log_to_channel(bot, 'reports', report_log_embed)
        
        # Update embed
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.dark_red()
        embed.set_footer(text=f"Report ID: {self.report_id} | Status: ACTIONED (Blacklist) by {interaction.user.name} | User permanently banned")
        
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(
            f"✅ **User Blacklisted Successfully**\n\n"
            f"**User:** <@{self.reported_user_id}>\n"
            f"**Status:** 🚫 Permanently Banned\n"
            f"**DM Notification:** {'✅ Sent' if dm_sent else '❌ Failed'}\n\n"
            f"This user can no longer use the bot.", 
            ephemeral=True
        )


@bot.hybrid_command(name="suggest", description="Submit a suggestion for the bot")
async def suggest(ctx, suggestion_title: str, suggestion: str):
    """Submit a suggestion for the bot"""
    # Check if user is blacklisted
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT blacklisted FROM users WHERE user_id = ?", (str(ctx.author.id),))
    result = c.fetchone()
    conn.close()
    
    if result and result[0] == 1:
        await ctx.send("❌ You are blacklisted and cannot submit suggestions.", ephemeral=True)
        return
    
    # CHECK COOLDOWN
    can_suggest, remaining_time = check_suggestion_cooldown(ctx.author.id)
    if not can_suggest:
        minutes = int(remaining_time // 60)
        seconds = int(remaining_time % 60)
        await ctx.send(
            f"⏱️ **Cooldown Active**\n\n"
            f"You can submit another suggestion in **{minutes}m {seconds}s**.\n\n"
            f"This cooldown helps prevent spam and ensures all suggestions get proper attention.",
            ephemeral=True
        )
        return
    
    # Get guild info
    guild_name = ctx.guild.name if ctx.guild else "Direct Message"
    guild_icon = ctx.guild.icon.url if ctx.guild and ctx.guild.icon else None
    guild_id = str(ctx.guild.id) if ctx.guild else "DM"
    
    # Get next suggestion ID
    suggestion_id = get_next_suggestion_id()
    
    # Create forum thread
    try:
        forum_channel = bot.get_channel(SUGGESTION_FORUM_CHANNEL)
        if not forum_channel:
            await ctx.send("❌ Suggestion forum channel not found. Please contact a bot admin.", ephemeral=True)
            return
        
        # Create embed
        embed = discord.Embed(
            title=f"New suggestion #{suggestion_id}",
            description=suggestion,
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        
        embed.set_author(
            name=guild_name,
            icon_url=guild_icon
        )
        
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        
        embed.set_footer(text=f"Suggested by {ctx.author.name} | {ctx.author.id}")
        
        # Create the thread
        thread = await forum_channel.create_thread(
            name=suggestion_title[:100],  # Discord limit
            content=None,
            embed=embed,
            view=SuggestionButtonView(suggestion_id, str(ctx.author.id), embed)
        )
        
        # Store in database
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT INTO suggestions 
                     (user_id, user_name, guild_id, guild_name, guild_icon, title, suggestion, thread_id)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                 (str(ctx.author.id), ctx.author.name, guild_id, guild_name, guild_icon, 
                  suggestion_title, suggestion, str(thread.thread.id)))
        conn.commit()
        conn.close()
        
        # UPDATE COOLDOWN
        update_suggestion_cooldown(ctx.author.id)
        
        # Send confirmation
        confirm_embed = discord.Embed(
            title="✅ Suggestion Submitted",
            description=f"Your suggestion has been submitted successfully!\n\n**Suggestion ID:** #{suggestion_id}\n**Thread:** {thread.thread.mention}\n\n⏱️ **Next suggestion available in:** 1 hour",
            color=discord.Color.green()
        )
        
        await ctx.send(embed=confirm_embed, ephemeral=True)
        
        # Log to suggestion log channel
        try:
            log_channel = bot.get_channel(SUGGESTION_LOG_CHANNEL)
            if log_channel:
                log_embed = discord.Embed(
                    title=f"📋 New Suggestion #{suggestion_id}",
                    description=f"**Title:** {suggestion_title}\n**Suggestion:** {suggestion[:200]}{'...' if len(suggestion) > 200 else ''}",
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                
                log_embed.add_field(name="Submitted By", value=f"{ctx.author.name} (`{ctx.author.id}`)", inline=True)
                log_embed.add_field(name="From Server", value=f"{guild_name} (`{guild_id}`)", inline=True)
                log_embed.add_field(name="Thread", value=thread.thread.mention, inline=False)
                
                await log_channel.send(embed=log_embed)
        except Exception as e:
            print(f"Error logging suggestion: {e}")
            
    except Exception as e:
        await ctx.send(f"❌ Error creating suggestion: {e}", ephemeral=True)
        import traceback
        traceback.print_exc()

@bot.hybrid_command(name="votereminder", description="Manage your vote reminders")
async def vote_reminder_settings(ctx, action: str = None):
    """Manage vote reminder settings"""
    
    if action is None:
        # Show current status
        status = db_query(
            "SELECT enabled, last_vote, next_reminder, total_votes FROM vote_reminders WHERE user_id = ?",
            (str(ctx.author.id),),
            fetch=True
        )
        
        if not status:
            embed = discord.Embed(
                title="🔔 Vote Reminders",
                description="You haven't voted yet! Vote on Top.gg to unlock reminders.",
                color=discord.Color.orange()
            )
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                label="Vote Now",
                url=f"https://top.gg/bot/{bot.user.id}/vote",
                style=discord.ButtonStyle.link,
                emoji="🗳️"
            ))
            await ctx.send(embed=embed, view=view)
            return
        
        enabled, last_vote, next_reminder, total_votes = status[0]
        
        embed = discord.Embed(
            title="🔔 Your Vote Reminder Settings",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📊 Status",
            value=f"**Reminders:** {'✅ Enabled' if enabled else '❌ Disabled'}\n**Total Votes:** {total_votes}",
            inline=False
        )
        
        if last_vote:
            embed.add_field(name="🕐 Last Vote", value=last_vote, inline=True)
        if next_reminder and enabled:
            embed.add_field(name="⏰ Next Reminder", value=next_reminder, inline=True)
        
        embed.add_field(
            name="⚙️ Commands",
            value="`/votereminder enable` - Enable reminders\n`/votereminder disable` - Disable reminders",
            inline=False
        )
        
        await ctx.send(embed=embed)
        return
    
    if action.lower() == "enable":
        # Enable reminders
        next_reminder = (datetime.utcnow() + timedelta(hours=12)).isoformat()
        db_query(
            "UPDATE vote_reminders SET enabled = 1, next_reminder = ? WHERE user_id = ?",
            (next_reminder, str(ctx.author.id))
        )
        await ctx.send("✅ **Vote reminders enabled!** I'll remind you every 12 hours.")
    
    elif action.lower() == "disable":
        # Disable reminders
        db_query(
            "UPDATE vote_reminders SET enabled = 0 WHERE user_id = ?",
            (str(ctx.author.id),)
        )
        await ctx.send("❌ **Vote reminders disabled.** You won't receive any more reminders.")
    
    else:
        await ctx.send("❌ Invalid action. Use `enable` or `disable`.")
        
# --- REPORT COMMAND ---
@bot.hybrid_command(name="report", description="Report a user for misbehavior.")
async def report_user(ctx, member: discord.Member, proof: str, *, reason: str):
    """
    Report a user for misbehavior
    Usage: /report @user <proof_url_or_text> <reason>
    """
    if not ctx.guild:
        await ctx.send("❌ **This command can only be used in servers.**")
        return
    
    # Prevent self-reporting
    if member.id == ctx.author.id:
        await ctx.send("❌ **You cannot report yourself.**")
        return
    
    # Prevent reporting bots
    if member.bot:
        await ctx.send("❌ **You cannot report bots.**")
        return
    
    # CHECK COOLDOWN
    can_report, remaining_time = check_report_cooldown(ctx.author.id)
    if not can_report:
        minutes = int(remaining_time // 60)
        seconds = int(remaining_time % 60)
        await ctx.send(
            f"⏱️ **Cooldown Active**\n\n"
            f"You can submit another report in **{minutes}m {seconds}s**.\n\n"
            f"This cooldown helps prevent spam and ensures all reports get proper review.",
            ephemeral=True
        )
        return
    
    # Collect proof from attachments if available
    attachments_list = []
    if ctx.message and ctx.message.attachments:
        attachments_list = [att.url for att in ctx.message.attachments]
    
    # Combine proof text and attachments
    full_proof = proof
    if attachments_list:
        full_proof += "\n" + "\n".join(attachments_list)
    
    # Store in database
    db_query(
        "INSERT INTO reports (reporter_id, reporter_name, reported_user_id, reported_user_name, guild_id, guild_name, reason, proof) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(ctx.author.id), ctx.author.name, str(member.id), member.name, str(ctx.guild.id), ctx.guild.name, reason, full_proof)
    )
    
    # Get report ID
    report_id = db_query("SELECT last_insert_rowid()", fetch=True)[0][0]
    
    # UPDATE COOLDOWN
    update_report_cooldown(ctx.author.id)
    
    # Log to database
    db_query("INSERT INTO admin_logs (log) VALUES (?)", 
             (f"Report #{report_id}: {ctx.author.name} ({ctx.author.id}) reported {member.name} ({member.id}) in {ctx.guild.name}. Reason: {reason}",))
    
    # Create detailed embed for logging channel
    log_embed = discord.Embed(
        title=f"📢 New User Report - #{report_id}",
        description="A user has been reported for misbehavior.",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    
    log_embed.add_field(name="👤 Reported User", value=f"{member.mention} (`{member.id}`)\n**Username:** {member.name}\n**Display Name:** {member.display_name}", inline=True)
    log_embed.add_field(name="🚨 Reported By", value=f"{ctx.author.mention} (`{ctx.author.id}`)\n**Username:** {ctx.author.name}", inline=True)
    log_embed.add_field(name="🆔 Report ID", value=f"`#{report_id}`", inline=True)
    
    log_embed.add_field(name="🏠 Server", value=f"**Name:** {ctx.guild.name}\n**ID:** `{ctx.guild.id}`", inline=True)
    log_embed.add_field(name="📍 Channel", value=f"{ctx.channel.mention}\n**ID:** `{ctx.channel.id}`", inline=True)
    log_embed.add_field(name="📅 Report Date", value=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'), inline=True)
    
    log_embed.add_field(name="📝 Reason", value=reason, inline=False)
    
    # Add proof section with better formatting
    proof_lines = full_proof.split('\n')
    proof_display = []
    
    for line in proof_lines:
        if line.startswith('http://') or line.startswith('https://'):
            file_ext = line.split('.')[-1].split('?')[0].lower()
            if file_ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                file_type = "🖼️ Image"
                if len(proof_display) == 0:
                    log_embed.set_image(url=line)
            elif file_ext in ['mp4', 'mov', 'avi', 'webm']:
                file_type = "🎥 Video"
            elif file_ext in ['pdf', 'txt', 'doc', 'docx']:
                file_type = "📄 Document"
            else:
                file_type = "📎 File"
            proof_display.append(f"{file_type}: [View]({line})")
        else:
            proof_display.append(f"📝 {line}")
    
    log_embed.add_field(name="📎 Proof", value="\n".join(proof_display) if proof_display else "No proof provided", inline=False)
    
    # Timezone-aware datetime calculation
    now = datetime.datetime.now(datetime.timezone.utc)
    account_age = (now - member.created_at).days
    join_age = (now - member.joined_at).days if member.joined_at else 0
    
    log_embed.add_field(name="📊 User Info", value=f"**Account Age:** {account_age} days\n**Server Join:** {join_age} days ago\n**Roles:** {len(member.roles) - 1}", inline=False)
    
    log_embed.set_thumbnail(url=member.display_avatar.url)
    log_embed.set_footer(text=f"Report ID: {report_id} | Status: PENDING")
    
    # Send to reports log channel with action buttons
    try:
        await log_to_channel(bot, 'reports', log_embed, view=ReportActionView(report_id, str(member.id), member.name))
    except Exception as e:
        print(f"Error sending report to log channel: {e}")
    
    # Send confirmation to reporter
    confirm_embed = discord.Embed(
        title="✅ Report Submitted",
        description=f"Your report has been submitted and will be reviewed by the moderation team.\n\n**Report ID:** `#{report_id}`\n\n⏱️ **Next report available in:** 1 hour",
        color=discord.Color.green()
    )
    confirm_embed.add_field(name="Reported User", value=member.mention, inline=True)
    confirm_embed.add_field(name="Report ID", value=f"`#{report_id}`", inline=True)
    confirm_embed.set_footer(text="Thank you for helping keep our community safe!")
    
    await ctx.send(embed=confirm_embed, ephemeral=True)


class ReportsPaginationView(discord.ui.View):
    def __init__(self, reports, status, per_page=10):
        super().__init__(timeout=300)  # 5 minute timeout
        self.reports = reports
        self.status = status
        self.per_page = per_page
        self.current_page = 0
        self.max_page = (len(reports) - 1) // per_page
        
        # Update button states on init
        self.update_buttons()
    
    def update_buttons(self):
        """Enable/disable buttons based on current page"""
        # First Page button
        self.first_page.disabled = (self.current_page == 0)
        
        # Previous Page button
        self.previous_page.disabled = (self.current_page == 0)
        
        # Next Page button
        self.next_page.disabled = (self.current_page >= self.max_page)
        
        # Last Page button
        self.last_page.disabled = (self.current_page >= self.max_page)
    
    def get_page_embed(self):
        """Generate embed for current page"""
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_reports = self.reports[start_idx:end_idx]
        
        embed = discord.Embed(
            title=f"📋 Reports ({self.status.capitalize()})",
            description=f"Page {self.current_page + 1}/{self.max_page + 1} • Total: {len(self.reports)} reports",
            color=discord.Color.blue()
        )
        
        for report in page_reports:
            # Handle variable number of columns
            report_id = report[0]
            reporter_id = report[1]
            reporter_name = report[2]
            reported_user_id = report[3]
            reported_user_name = report[4]
            guild_id = report[5]
            guild_name = report[6]
            reason = report[7]
            proof = report[8] if len(report) > 8 else "No proof"
            timestamp = report[9] if len(report) > 9 else "Unknown"
            report_status = report[10] if len(report) > 10 else "pending"
            
            # Truncate long reasons
            reason_short = reason[:100] + "..." if len(reason) > 100 else reason
            
            # Status emoji
            status_emoji = {
                "pending": "⏳",
                "claimed": "✋",
                "actioned": "✅",
                "deleted": "🗑️"
            }.get(report_status.lower(), "❓")
            
            embed.add_field(
                name=f"{status_emoji} Report #{report_id} - {report_status.upper()}",
                value=f"**Reporter:** <@{reporter_id}>\n**Reported:** <@{reported_user_id}>\n**Reason:** {reason_short}\n**Server:** {guild_name}",
                inline=False
            )
        
        embed.set_footer(text=f"Use /reportview <id> for full details • Page {self.current_page + 1}/{self.max_page + 1}")
        
        return embed
    
    @discord.ui.button(label="⏮️ First", style=discord.ButtonStyle.secondary, custom_id="first_page")
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.primary, custom_id="previous_page")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)
    
    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.primary, custom_id="next_page")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = min(self.max_page, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)
    
    @discord.ui.button(label="⏭️ Last", style=discord.ButtonStyle.secondary, custom_id="last_page")
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = self.max_page
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)


@bot.hybrid_command(name="reports", description="Owner/Admin: View all reports.")
@owner_or_bot_admin()
async def view_reports(ctx, status: str = "all"):
    """View all reports or filter by status (pending/claimed/actioned/all)"""
    
    if status.lower() not in ["all", "pending", "claimed", "actioned"]:
        await ctx.send("❌ **Invalid status**\nValid options: `all`, `pending`, `claimed`, `actioned`")
        return
    
    # Get reports based on status filter
    if status.lower() == "all":
        reports = db_query("SELECT * FROM reports ORDER BY timestamp DESC", fetch=True)
    else:
        reports = db_query("SELECT * FROM reports WHERE status = ? ORDER BY timestamp DESC", (status.lower(),), fetch=True)
    
    if not reports:
        await ctx.send(f"✅ **No {status} reports found**\nThe reports database is empty for this filter.")
        return
    
    # Create pagination view
    view = ReportsPaginationView(reports, status, per_page=10)
    embed = view.get_page_embed()
    
    await ctx.send(embed=embed, view=view)

@bot.hybrid_command(name="reportview", description="Owner/Admin: View detailed report.")
@owner_or_bot_admin()
async def view_report_detail(ctx, report_id: int):
    """View detailed information about a specific report (including deleted ones)"""
    report = db_query("SELECT * FROM reports WHERE report_id = ?", (report_id,), fetch=True)
    
    if not report:
        await ctx.send(f"❌ **Report #{report_id} not found.**")
        return
    
    report = report[0]
    r_id, reporter_id, reporter_name, reported_id, reported_name, guild_id, guild_name, reason, proof, timestamp, status, is_deleted = report
    
    # Determine color based on status
    if is_deleted:
        embed_color = discord.Color.dark_gray()
    elif status == 'actioned':
        embed_color = discord.Color.green()
    elif status == 'claimed':
        embed_color = discord.Color.blue()
    else:
        embed_color = discord.Color.orange()
    
    embed = discord.Embed(
        title=f"📋 Report Details - #{r_id}",
        description=f"**Status:** {status.upper()}" + (" 🗑️ **(DELETED/ARCHIVED)**" if is_deleted else ""),
        color=embed_color,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    
    embed.add_field(name="👤 Reported User", value=f"<@{reported_id}>\n`{reported_id}`\n{reported_name}", inline=True)
    embed.add_field(name="🚨 Reporter", value=f"<@{reporter_id}>\n`{reporter_id}`\n{reporter_name}", inline=True)
    embed.add_field(name="🏠 Server", value=f"{guild_name}\n`{guild_id}`", inline=True)
    
    embed.add_field(name="📝 Reason", value=reason, inline=False)
    embed.add_field(name="📎 Proof", value=proof if proof != "No proof attached" else "No attachments", inline=False)
    embed.add_field(name="📅 Submitted", value=timestamp, inline=True)
    
    if is_deleted:
        embed.add_field(name="🗑️ Archive Status", value="This report has been cleared/removed but remains viewable for record-keeping.", inline=False)
    
    # Check reported user's current status
    user_status = db_query("SELECT strikes, blacklisted FROM users WHERE user_id = ?", (str(reported_id),), fetch=True)
    if user_status and user_status[0]:
        strikes, blacklisted = user_status[0]
        status_text = "🚫 Blacklisted" if blacklisted else f"⚡ {strikes}/3 Strikes"
    else:
        status_text = "✅ Clean Record"
    
    embed.add_field(name="📊 User Status", value=status_text, inline=True)
    
    embed.set_footer(text=f"Report ID: {r_id}" + (" | ARCHIVED" if is_deleted else ""))
    
    await ctx.send(embed=embed)


@bot.hybrid_command(name="reportclear", description="Owner/Admin: Clear ALL reports filed AGAINST a specific user.")
@owner_or_bot_admin()
async def report_clear(ctx, user_id: str):
    """Clear all reports filed AGAINST a specific user (reported user)"""
    # For hybrid commands, use ctx.send() not ctx.followup
    
    # Get all reports against this user
    reports = db_query(
        "SELECT report_id, reporter_id, reason FROM reports WHERE reported_user_id = ?",
        (user_id,),
        fetch=True
    )
    
    if not reports:
        await ctx.send(f"⚠️ **No reports found against user `{user_id}`**\n\nThis user has not been reported.")
        return
    
    report_count = len(reports)
    
    # DELETE reports completely
    db_query("DELETE FROM reports WHERE reported_user_id = ?", (user_id,))
    
    # Log the action
    log_msg = f"All {report_count} report(s) against user {user_id} cleared by {ctx.author.name} ({ctx.author.id})"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Get current time
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # Log to reports channel
    log_embed = discord.Embed(
        title=f"🗑️ Bulk Report Clear - {report_count} Reports",
        description=f"All reports filed against a user have been cleared.",
        color=discord.Color.orange(),
        timestamp=now
    )
    log_embed.add_field(name="🎯 Reported User (Cleared)", value=f"<@{user_id}> (`{user_id}`)", inline=True)
    log_embed.add_field(name="📊 Reports Cleared", value=str(report_count), inline=True)
    log_embed.add_field(name="⚖️ Cleared By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    
    # Add list of cleared report IDs (max 10)
    report_ids = [str(r[0]) for r in reports[:10]]
    if len(reports) > 10:
        report_ids_text = ", ".join(report_ids) + f"... (+{len(reports) - 10} more)"
    else:
        report_ids_text = ", ".join(report_ids)
    
    log_embed.add_field(name="🆔 Report IDs", value=report_ids_text, inline=False)
    
    await log_to_channel(bot, 'reports', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title=f"🗑️ Cleared {report_count} Report(s)",
        description=f"All reports filed **against** <@{user_id}> have been permanently deleted.",
        color=discord.Color.orange()
    )
    embed.add_field(name="Reported User", value=f"<@{user_id}>\n`{user_id}`", inline=True)
    embed.add_field(name="Reports Cleared", value=str(report_count), inline=True)
    embed.add_field(name="Cleared By", value=ctx.author.mention, inline=True)
    
    # Show first few report IDs with reporters
    if report_count <= 5:
        details = "\n".join([f"• Report #{r[0]} by <@{r[1]}> - {r[2][:50]}..." for r in reports])
    else:
        details = "\n".join([f"• Report #{r[0]} by <@{r[1]}> - {r[2][:50]}..." for r in reports[:5]])
        details += f"\n*...and {report_count - 5} more*"
    
    embed.add_field(name="📋 Cleared Reports", value=details, inline=False)
    embed.set_footer(text=f"All reports against user {user_id} have been permanently deleted")
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="reportremove", description="Owner/Admin: Remove a specific report by ID.")
@owner_or_bot_admin()
async def report_remove(ctx, report_id: int):
    """Remove/delete a single specific report by ID"""
    # DEFER RESPONSE IMMEDIATELY
    await ctx.defer()
    
    # Check if report exists
    existing = db_query("SELECT reporter_id, reported_user_id, reason, status FROM reports WHERE report_id = ?", (report_id,), fetch=True)
    
    if not existing:
        await ctx.send(f"⚠️ **Report #{report_id} not found.**")
        return
    
    reporter_id, reported_user_id, reason, status = existing[0]
    
    # Mark as deleted
    db_query("UPDATE reports SET deleted = 1, status = 'deleted' WHERE report_id = ?", (report_id,))
    
    # Log the action
    log_msg = f"Report #{report_id} removed/deleted by {ctx.author.name} ({ctx.author.id})"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Get current time
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # Log to reports channel
    log_embed = discord.Embed(
        title=f"🗑️ Report #{report_id} Removed",
        description=f"Report has been deleted.",
        color=discord.Color.red(),
        timestamp=now
    )
    log_embed.add_field(name="🆔 Report ID", value=f"`#{report_id}`", inline=True)
    log_embed.add_field(name="👤 Reporter", value=f"<@{reporter_id}>", inline=True)
    log_embed.add_field(name="🎯 Reported User", value=f"<@{reported_user_id}>", inline=True)
    log_embed.add_field(name="📝 Reason", value=reason[:100] if len(reason) > 100 else reason, inline=False)
    log_embed.add_field(name="📊 Previous Status", value=status, inline=True)
    log_embed.add_field(name="⚖️ Removed By", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    
    await log_to_channel(bot, 'reports', log_embed)
    
    # Confirm to command user
    embed = discord.Embed(
        title="🗑️ Report Removed",
        description=f"Report #{report_id} has been deleted.",
        color=discord.Color.red()
    )
    embed.add_field(name="Report ID", value=f"`#{report_id}`", inline=True)
    embed.add_field(name="Reporter", value=f"<@{reporter_id}>", inline=True)
    embed.add_field(name="Reported User", value=f"<@{reported_user_id}>", inline=True)
    embed.add_field(name="Removed By", value=ctx.author.mention, inline=True)
    
    await ctx.send(embed=embed)
    
# Bot Admin Management Commands (Owner Only)
@bot.command(name="add-admin", description="Owner: Add a bot admin.")
@commands.is_owner()
async def add_admin(ctx, user: discord.User):
    """Add a user as bot admin"""
    if user.id == OWNER_ID:
        await ctx.send("❌ **Owner is already a permanent admin.**")
        return
    
    existing = db_query("SELECT user_id FROM bot_admins WHERE user_id = ?", (str(user.id),), fetch=True)
    if existing:
        await ctx.send(f"⚠️ **{user.mention} is already a bot admin.**")
        return
    
    # Add to database
    db_query("INSERT INTO bot_admins (user_id, added_by) VALUES (?, ?)", (str(user.id), str(ctx.author.id)))
    
    # Log to database
    log_msg = f"Bot Admin added: {user.name} ({user.id}) by {ctx.author.name} ({ctx.author.id})"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to new admin
    dm_message = f"""🎉 **Congratulations, {user.name}!**

You have been promoted to **Bot Admin** for {BOT_NAME} Bot by {ctx.author.name}!

**📊 Your New Permissions:**
✅ User Moderation (strikes, blacklist)
✅ Word Filter Management
✅ Report Review & Actions
✅ Data & Log Exports
✅ Server Configuration

**🔑 Admin Commands You Can Now Use:**
• `/sync` - Sync slash commands
• `/blacklist add/remove` - Manage blacklisted users
• `/addstrike` / `/removestrike` - Manage user strikes
• `/bannedword add/remove` - Manage word filter
• `/bypass add/remove` - Manage word filter bypass
• `/reports` / `/reportview` - Review user reports
• `/messages` / `/backup` / `/data` - Export logs & data
• All other admin commands - Type `/help` to see full list

**⚠️ Important Reminders:**
• All your actions are logged and monitored
• Users receive DM notifications for moderation actions
• Use your powers responsibly and fairly
• If unsure about something, contact the owner

**📞 Need Help?**
• Contact Owner: <@{OWNER_ID}>
• Support Server: {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}

**Welcome to the admin team! 🚀**

*Granted: {datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}*
"""
    
    dm_sent = await send_user_dm(str(user.id), dm_message)
    
    # Log to admin_logs channel with rich embed
    log_embed = discord.Embed(
        title="✨ New Bot Admin Appointed",
        description="A new administrator has been added to the bot team.",
        color=discord.Color.gold(),
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    
    # User information
    log_embed.add_field(
        name="👤 New Admin",
        value=f"{user.mention}\n**Username:** {user.name}\n**ID:** `{user.id}`",
        inline=True
    )
    
    # Appointer information
    log_embed.add_field(
        name="👑 Appointed By",
        value=f"{ctx.author.mention}\n**Username:** {ctx.author.name}\n**ID:** `{ctx.author.id}`",
        inline=True
    )
    
    # Timestamp
    log_embed.add_field(
        name="📅 Appointment Date",
        value=datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S UTC'),
        inline=True
    )
    
    # Account info - FIXED timezone issue
    account_age = (datetime.datetime.now(datetime.UTC) - user.created_at).days
    log_embed.add_field(
        name="ℹ️ Account Information",
        value=f"**Created:** {user.created_at.strftime('%Y-%m-%d')}\n**Age:** {account_age} days old",
        inline=True
    )
    
    # Notification status
    log_embed.add_field(
        name="📬 DM Notification",
        value="✅ Delivered successfully" if dm_sent else "❌ Failed (DMs disabled)",
        inline=True
    )
    
    # Current admin count
    total_admins = len(db_query("SELECT user_id FROM bot_admins", fetch=True))
    log_embed.add_field(
        name="📊 Total Admins",
        value=f"**{total_admins}** bot admin(s)",
        inline=True
    )
    
    # Permissions granted
    log_embed.add_field(
        name="🔑 Permissions Granted",
        value="```\n• User Moderation (strikes/blacklist)\n• Word Filter Management\n• Report Review & Actions\n• Data & Log Exports\n• Server Configuration\n• All Admin Commands```",
        inline=False
    )
    
    log_embed.set_thumbnail(url=user.display_avatar.url)
    log_embed.set_footer(text=f"Admin ID: {user.id} • Appointed by: {ctx.author.name}")
    
    # Send to admin logs channel
    await log_to_channel(bot, 'admin_logs', log_embed)
    
    # Confirm to owner with detailed embed
    confirm_embed = discord.Embed(
        title="✅ Bot Admin Added Successfully",
        description=f"{user.mention} has been promoted to **Bot Admin**!",
        color=discord.Color.green()
    )
    
    confirm_embed.add_field(
        name="👤 New Admin",
        value=f"**Name:** {user.name}\n**ID:** `{user.id}`",
        inline=True
    )
    
    confirm_embed.add_field(
        name="📊 Status",
        value=f"**Total Admins:** {total_admins}\n**Appointed By:** {ctx.author.name}",
        inline=True
    )
    
    confirm_embed.add_field(
        name="📬 Notifications",
        value=f"**DM to User:** {'✅ Sent' if dm_sent else '❌ Failed'}\n**Admin Log:** ✅ Logged",
        inline=False
    )
    
    confirm_embed.set_thumbnail(url=user.display_avatar.url)
    confirm_embed.set_footer(text="The new admin has been notified of their permissions")
    
    await ctx.send(embed=confirm_embed)
    
    # Also send a follow-up message with next steps
    await ctx.send(
        f"💡 **Next Steps:**\n"
        f"• {user.mention} can now use `/help` to see all admin commands\n"
        f"• They should join the support server if not already there\n"
        f"• Review admin guidelines and best practices\n"
        f"• Test permissions in a controlled environment first",
        delete_after=30
    )

@bot.command(name="remove-admin", description="Owner: Remove a bot admin.")
@commands.is_owner()
async def remove_admin(ctx, user: discord.User):
    """Remove a user from bot admins"""
    if user.id == OWNER_ID:
        await ctx.send("❌ **Cannot remove owner from admin privileges.**")
        return
    
    # Check if user is actually an admin
    existing = db_query("SELECT added_by, added_at FROM bot_admins WHERE user_id = ?", (str(user.id),), fetch=True)
    
    if not existing:
        await ctx.send(f"⚠️ **{user.mention} is not a bot admin.**")
        return
    
    # Extract info for the log/DM
    added_by, added_at = existing[0]
    
    # Remove from database
    db_query("DELETE FROM bot_admins WHERE user_id = ?", (str(user.id),))
    
    # Log to database
    log_msg = f"Bot Admin removed: {user.name} ({user.id}) by {ctx.author.name} ({ctx.author.id})"
    db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
    
    # Send DM to removed admin
    dm_message = f"""📋 **Bot Admin Status Update**

Your **Bot Admin** privileges for {BOT_NAME} Bot have been removed by {ctx.author.name}.

**What Changed:**
• You no longer have access to administrative commands
• You cannot manage user moderation (strikes, blacklist)
• You cannot modify word filters or view admin logs
• You can still use regular bot features

**Your Service:**
• **Originally Added:** {added_at}
• **Added By:** <@{added_by}>
• **Removed By:** {ctx.author.name}

Thank you for your service! 🙏

*Timestamp: {get_discord_timestamp(style='F')}*
"""
    dm_sent = await send_user_dm(str(user.id), dm_message)
    
    # Log to admin_logs channel
    log_embed = discord.Embed(
        title="📋 Bot Admin Removed",
        description="A bot administrator has been removed from their position.",
        color=discord.Color.orange(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    log_embed.add_field(
        name="👤 Removed Admin", 
        value=f"{user.mention}\n**Username:** {user.name}\n**ID:** `{user.id}`", 
        inline=True
    )
    log_embed.add_field(
        name="⚖️ Removed By", 
        value=f"{ctx.author.mention}\n**Username:** {ctx.author.name}\n**ID:** `{ctx.author.id}`", 
        inline=True
    )
    log_embed.add_field(
        name="📅 Removal Date", 
        value=get_discord_timestamp(style='F'), 
        inline=True
    )
    log_embed.add_field(
        name="📜 Admin History", 
        value=f"**Originally Added:** {added_at}\n**Added By:** <@{added_by}>", 
        inline=True
    )
    log_embed.add_field(
        name="📬 DM Notification", 
        value="✅ Sent successfully" if dm_sent else "❌ Failed (DMs disabled)", 
        inline=True
    )
    
    # Current admin count
    total_admins = len(db_query("SELECT user_id FROM bot_admins", fetch=True))
    log_embed.add_field(
        name="📊 Remaining Admins",
        value=f"**{total_admins}** bot admin(s)",
        inline=True
    )
    
    log_embed.set_thumbnail(url=user.display_avatar.url)
    log_embed.set_footer(text=f"Admin ID: {user.id} | Removed by: {ctx.author.name}")
    
    # Send to admin logs channel
    await log_to_channel(bot, 'admin_logs', log_embed)
    
    # Confirm to owner
    embed = discord.Embed(
        title="📋 Bot Admin Removed",
        description=f"{user.mention} has been removed from **Bot Admin**.",
        color=discord.Color.orange()
    )
    embed.add_field(
        name="👤 Removed Admin",
        value=f"**Name:** {user.name}\n**ID:** `{user.id}`",
        inline=True
    )
    embed.add_field(
        name="📊 Status",
        value=f"**Remaining Admins:** {total_admins}\n**Removed By:** {ctx.author.name}",
        inline=True
    )
    embed.add_field(
        name="📬 Notifications",
        value=f"**DM to User:** {'✅ Sent' if dm_sent else '❌ Failed'}\n**Admin Log:** ✅ Logged",
        inline=False
    )
    
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="Admin privileges have been revoked")
    
    await ctx.send(embed=embed)

@bot.command(name="list-admins", description="Owner: List all bot admins.")
@commands.is_owner()
async def list_admins(ctx):
    """List all bot admins"""
    admins = db_query("SELECT user_id, added_by, added_at FROM bot_admins", fetch=True)
    
    embed = discord.Embed(title="👑 Bot Admin List", color=discord.Color.gold())
    embed.add_field(name="Owner", value=f"<@{OWNER_ID}> (Permanent)", inline=False)
    
    if admins:
        admin_list = []
        for admin in admins:
            user_id, added_by, added_at = admin
            admin_list.append(f"<@{user_id}> - Added by <@{added_by}> on {added_at}")
        
        embed.add_field(name="Bot Admins", value="\n".join(admin_list), inline=False)
        embed.set_footer(text=f"Total admins: {len(admins)}")
    else:
        embed.add_field(name="Bot Admins", value="None (only owner)", inline=False)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="leave", description="Owner: Leave a server.")
@commands.is_owner()
@commands.dm_only()
async def leave_server(ctx, server_id: str, *, reason: str = None):
    """Leave a server with optional reason sent to server owner"""
    try:
        guild = bot.get_guild(int(server_id))
        if not guild:
            await ctx.send(f"❌ **Server not found**\nCannot find server with ID: `{server_id}`")
            return
        
        guild_name = guild.name
        guild_owner = guild.owner
        owner_notified = False
        
        if guild_owner:
            try:
                if reason:
                    leave_message = f"""📢 **{BOT_NAME} Bot Leaving Server**

Hello {guild_owner.name},

{BOT_NAME} Bot is leaving **{guild_name}**.

**Reason:** {reason}

If you have questions, 
Contact: <@{OWNER_ID}> or
Support Server: {os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}

Thank you for using {BOT_NAME} Bot!
"""
                else:
                    leave_message = f"""📢 **{BOT_NAME} Bot Leaving Server**

Hello {guild_owner.name},

{BOT_NAME} Bot is leaving **{guild_name}**.

Thank you for using {BOT_NAME} Bot!
"""
                await guild_owner.send(leave_message)
                owner_notified = True
            except:
                owner_notified = False
        
        log_msg = f"Manually left server: {guild_name} (ID: {server_id}, Owner: {guild_owner.name} - {guild_owner.id}). Reason: {reason if reason else 'No reason provided'}"
        db_query("INSERT INTO admin_logs (log) VALUES (?)", (log_msg,))
        
        await guild.leave()
        
        embed = discord.Embed(
            title="✅ Server Left Successfully", 
            description=f"The bot has left **{guild_name}**",
            color=discord.Color.green()
        )
        embed.add_field(name="Server Name", value=guild_name, inline=False)
        embed.add_field(name="Server ID", value=server_id, inline=True)
        embed.add_field(name="Owner", value=f"{guild_owner.name} (`{guild_owner.id}`)", inline=True)
        embed.add_field(name="Reason", value=reason if reason else "No reason provided", inline=False)
        embed.add_field(name="Owner Notified", value="✅ Yes" if owner_notified else "❌ No", inline=True)
        
        await ctx.send(embed=embed)
        
    except ValueError:
        await ctx.send("❌ **Invalid server ID**")
    except Exception as e:
        await ctx.send(f"❌ **Error:** {str(e)}")

@bot.hybrid_command(name="start", description="Set bot to respond to all messages in this channel.")
async def start_mode(ctx):
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\n**Required:** Administrator permissions")
            return
    
    db_query("INSERT OR REPLACE INTO settings (id, mode) VALUES (?, 'start')", (str(ctx.channel.id),))
    embed = discord.Embed(
        title="🟢 Start Mode Activated",
        description="The bot will now respond to **all messages** in this channel.",
        color=discord.Color.green()
    )
    embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
    embed.add_field(name="Mode", value="**START** (Respond to all)", inline=True)
    embed.set_footer(text="Use /stop to return to normal mode")
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="stop", description="Set bot to respond only to pings/triggers.")
async def stop_mode(ctx):
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\n**Required:** Administrator permissions")
            return
    
    db_query("INSERT OR REPLACE INTO settings (id, mode) VALUES (?, 'stop')", (str(ctx.channel.id),))
    
    embed = discord.Embed(
        title="🔴 Stop Mode Activated",
        description=f"The bot will now **only respond** to:\n• Direct mentions/pings\n• Messages containing '{BOT_NAME}'\n• Images/attachments",
        color=discord.Color.red()
    )
    embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
    embed.add_field(name="Mode", value="**STOP** (Selective response)", inline=True)
    embed.set_footer(text="Use /start to enable response to all messages")
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="lang", description="Set channel language (Admin only).")
async def set_lang_slash(ctx, lang: str = None):
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\n**Required:** Administrator permissions")
            return
    
    if ctx.interaction and lang is None:
        view = LanguageSelectView(ctx.channel.id, ctx.author.id)
        await ctx.send("🌐 **Select a language for this channel:**", view=view, ephemeral=True)
        return
    
    if lang:
        if lang not in AVAILABLE_LANGUAGES:
            await ctx.send(f"❌ **Invalid language**\n\n**Available languages:**\n{', '.join(AVAILABLE_LANGUAGES)}", ephemeral=True)
            return
        
        db_query("INSERT OR REPLACE INTO settings (id, language) VALUES (?, ?)", (str(ctx.channel.id), lang))
        
        embed = discord.Embed(
            title="🌐 Language Changed",
            description=f"Channel language set to **{lang}**",
            color=discord.Color.blue()
        )
        embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
        embed.add_field(name="Language", value=lang, inline=True)
        
        await ctx.send(embed=embed, ephemeral=True)
        return
    
    if not ctx.interaction:
        view = LanguageButtonView(ctx.channel.id, ctx.author.id, OWNER_ID)
        await ctx.send(f"🌐 **Select Language for this Channel**\n\n**Available:** {', '.join(AVAILABLE_LANGUAGES)}\n\nClick a button below:", view=view)

@set_lang_slash.autocomplete('lang')
async def lang_autocomplete(interaction: discord.Interaction, current: str):
    return [
        discord.app_commands.Choice(name=lang, value=lang)
        for lang in AVAILABLE_LANGUAGES if current.lower() in lang.lower()
    ][:25]

@bot.hybrid_command(name="prefix", description="Change command prefix.")
async def set_prefix(ctx, new_prefix: str):
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\n**Required:** Administrator permissions")
            return
    
    guild_or_user_id = str(ctx.guild.id if ctx.guild else ctx.author.id)
    db_query("INSERT OR REPLACE INTO settings (id, prefix) VALUES (?, ?)", (guild_or_user_id, new_prefix))
    
    embed = discord.Embed(
        title="⚙️ Prefix Changed",
        description=f"Command prefix updated to `{new_prefix}`",
        color=discord.Color.blue()
    )
    embed.add_field(name="New Prefix", value=f"`{new_prefix}`", inline=True)
    embed.add_field(name="Example", value=f"`{new_prefix}help`", inline=True)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="setupupdates", description="Setup channel for bot announcements (Admin only).")
async def setup_updates(ctx, channel: discord.TextChannel = None):
    """Setup updates channel for important bot announcements"""
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\n**Required:** Administrator permissions")
            return
    
    if not ctx.guild:
        await ctx.send("❌ **This command can only be used in servers.**")
        return
    
    # If no channel provided, use the current channel
    if channel is None:
        channel = ctx.channel
    
    # Check if bot has permissions in the channel
    bot_perms = channel.permissions_for(ctx.guild.me)
    if not bot_perms.send_messages or not bot_perms.embed_links:
        await ctx.send(f"❌ **Missing Permissions**\n\nI need **Send Messages** and **Embed Links** permissions in {channel.mention}")
        return
    
    # Check if already configured
    existing = db_query("SELECT channel_id FROM updates_channels WHERE guild_id = ?", (str(ctx.guild.id),), fetch=True)
    
    if existing:
        old_channel_id = existing[0][0]
        # Update existing
        db_query("UPDATE updates_channels SET channel_id = ?, setup_by = ?, setup_at = CURRENT_TIMESTAMP WHERE guild_id = ?", 
                (str(channel.id), str(ctx.author.id), str(ctx.guild.id)))
        action = "updated"
        was_updated = True
    else:
        # Insert new
        db_query("INSERT INTO updates_channels (guild_id, channel_id, setup_by) VALUES (?, ?, ?)",
                (str(ctx.guild.id), str(channel.id), str(ctx.author.id)))
        action = "set"
        was_updated = False
    
    # Log the action
    db_query("INSERT INTO admin_logs (log) VALUES (?)", 
            (f"Updates channel {action} in {ctx.guild.name} ({ctx.guild.id}) to #{channel.name} ({channel.id}) by {ctx.author.name} ({ctx.author.id})",))
    
    # Send confirmation
    embed = discord.Embed(
        title=f"✅ Updates Channel {action.capitalize()}",
        description=f"Bot announcements will be sent to {channel.mention}",
        color=discord.Color.green()
    )
    embed.add_field(name="Channel", value=f"{channel.mention}\n`{channel.id}`", inline=True)
    embed.add_field(name="Setup By", value=ctx.author.mention, inline=True)
    
    if was_updated:
        embed.add_field(name="Previous Channel", value=f"<#{old_channel_id}>", inline=False)
    
    embed.set_footer(text="Important bot announcements will be posted here")
    
    await ctx.send(embed=embed)
    
    # Send test message to the channel
    try:
        test_embed = discord.Embed(
            title="📢 Updates Channel Configured",
            description=f"This channel has been set as the updates channel for **{ctx.guild.name}**.\n\nImportant announcements from the bot owner will be posted here.",
            color=discord.Color.blue()
        )
        test_embed.set_footer(text=f"Setup by {ctx.author.name}")
        await channel.send(embed=test_embed)
    except Exception as e:
        print(f"Failed to send test message to updates channel: {e}")

@bot.hybrid_command(name="changeupdates", description="Change the updates channel (Admin only).")
async def change_updates(ctx, channel: discord.TextChannel = None):
    """Change the existing updates channel to a new one"""
    if ctx.author.id != OWNER_ID:
        if not ctx.guild or not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ **Permission Denied**\n**Required:** Administrator permissions")
            return
    
    if not ctx.guild:
        await ctx.send("❌ **This command can only be used in servers.**")
        return
    
    # If no channel provided, use the current channel
    if channel is None:
        channel = ctx.channel
    
    # Check if already configured
    existing = db_query("SELECT channel_id FROM updates_channels WHERE guild_id = ?", (str(ctx.guild.id),), fetch=True)
    
    if not existing:
        await ctx.send(f"⚠️ **No updates channel configured yet**\n\nUse `/setupupdates` to set up an updates channel first.\n\n*Alternatively, I'll set {channel.mention} as your updates channel now.*")
        # Call setupupdates instead
        await setup_updates(ctx, channel)
        return
    
    old_channel_id = existing[0][0]
    
    # Don't allow changing to the same channel
    if old_channel_id == str(channel.id):
        await ctx.send(f"⚠️ **Already configured**\n\n{channel.mention} is already set as your updates channel.")
        return
    
    # Check if bot has permissions in the new channel
    bot_perms = channel.permissions_for(ctx.guild.me)
    if not bot_perms.send_messages or not bot_perms.embed_links:
        await ctx.send(f"❌ **Missing Permissions**\n\nI need **Send Messages** and **Embed Links** permissions in {channel.mention}")
        return
    
    # Update to new channel
    db_query("UPDATE updates_channels SET channel_id = ?, setup_by = ?, setup_at = CURRENT_TIMESTAMP WHERE guild_id = ?", 
            (str(channel.id), str(ctx.author.id), str(ctx.guild.id)))
    
    # Log the action
    db_query("INSERT INTO admin_logs (log) VALUES (?)", 
            (f"Updates channel changed in {ctx.guild.name} ({ctx.guild.id}) from <#{old_channel_id}> to #{channel.name} ({channel.id}) by {ctx.author.name} ({ctx.author.id})",))
    
    # Send confirmation
    embed = discord.Embed(
        title="✅ Updates Channel Changed",
        description=f"Bot announcements will now be sent to {channel.mention}",
        color=discord.Color.blue()
    )
    embed.add_field(name="New Channel", value=f"{channel.mention}\n`{channel.id}`", inline=True)
    embed.add_field(name="Changed By", value=ctx.author.mention, inline=True)
    embed.add_field(name="Previous Channel", value=f"<#{old_channel_id}>", inline=False)
    embed.set_footer(text="Important bot announcements will be posted here")
    
    await ctx.send(embed=embed)
    
    # Send notification to the new channel
    try:
        notification_embed = discord.Embed(
            title="📢 Updates Channel Changed",
            description=f"This channel is now the updates channel for **{ctx.guild.name}**.\n\nImportant announcements from the bot owner will be posted here.",
            color=discord.Color.blue()
        )
        notification_embed.add_field(name="Previous Channel", value=f"<#{old_channel_id}>", inline=True)
        notification_embed.add_field(name="Changed By", value=ctx.author.mention, inline=True)
        notification_embed.set_footer(text=f"Changed at {get_discord_timestamp(style='F')}")
        await channel.send(embed=notification_embed)
    except Exception as e:
        print(f"Failed to send notification to new updates channel: {e}")

@bot.hybrid_command(name="announce", description="Owner/Admin: Send announcement to all servers.")
@owner_or_bot_admin()
async def announce(ctx, *, message: str):
    """Send an announcement to all configured updates channels and ALL server owners"""
    
    # Initial confirmation
    await ctx.send("📢 **Starting announcement broadcast...**\nThis may take a moment.")
    
    # Get all guilds with configured updates channels
    updates_channels = db_query("SELECT guild_id, channel_id FROM updates_channels", fetch=True)
    configured_guild_ids = {str(uc[0]) for uc in updates_channels} if updates_channels else set()
    
    # Get current timestamp for the embed
    current_time = datetime.datetime.now(datetime.timezone.utc)
    
    # Create announcement embed
    announcement_embed = discord.Embed(
        title=f"📢 {BOT_NAME} Announcement",
        description=message,
        color=discord.Color.blue(),
        timestamp=current_time
    )
    announcement_embed.set_footer(text=f"Announcement from {ctx.author.name}")
    announcement_embed.set_author(name=BOT_NAME, icon_url=bot.user.display_avatar.url)
    
    # Statistics
    total_guilds = len(bot.guilds)
    channel_success = 0
    channel_fail = 0
    dm_success = 0
    dm_fail = 0
    
    # Process all guilds
    for guild in bot.guilds:
        guild_id = str(guild.id)
        
        # Try to send to configured channel if it exists
        if guild_id in configured_guild_ids:
            channel_sent = False
            # Find the channel_id for this guild
            channel_id = next((uc[1] for uc in updates_channels if str(uc[0]) == guild_id), None)
            
            if channel_id:
                try:
                    channel = guild.get_channel(int(channel_id))
                    if channel:
                        await channel.send(embed=announcement_embed)
                        channel_success += 1
                        channel_sent = True
                    else:
                        channel_fail += 1
                except Exception as e:
                    print(f"Failed to send announcement to channel in {guild.name}: {e}")
                    channel_fail += 1
        else:
            # Guild doesn't have updates channel configured, count as N/A
            channel_fail += 1
        
        # ALWAYS try to send DM to server owner (regardless of updates channel setup)
        try:
            if guild.owner:
                owner_dm_embed = announcement_embed.copy()
                owner_dm_embed.title = f"📢 {BOT_NAME} Announcement for {guild.name}"
                
                # Add a note if they haven't set up updates channel
                if guild_id not in configured_guild_ids:
                    owner_dm_embed.add_field(
                        name="💡 Setup Tip",
                        value=f"Your server hasn't configured an updates channel yet! Use `/setupupdates #channel` in your server to receive announcements directly in a channel.",
                        inline=False
                    )
                
                await guild.owner.send(embed=owner_dm_embed)
                dm_success += 1
        except discord.Forbidden:
            # Owner has DMs disabled
            dm_fail += 1
            print(f"DMs disabled for owner of {guild.name}")
        except Exception as e:
            dm_fail += 1
            print(f"Failed to DM owner of {guild.name}: {e}")
        
        # Small delay to avoid rate limits
        await asyncio.sleep(0.5)
    
    # Log the announcement
    db_query("INSERT INTO admin_logs (log) VALUES (?)", 
            (f"Global announcement sent by {ctx.author.name} ({ctx.author.id}). Channel success: {channel_success}, DM success: {dm_success}. Message: {message[:200]}",))
    
    # Send results with better breakdown
    result_embed = discord.Embed(
        title="✅ Announcement Broadcast Complete",
        description=f"Your announcement has been sent!",
        color=discord.Color.green()
    )
    result_embed.add_field(
        name="📊 Server Statistics", 
        value=f"**Total Servers:** {total_guilds}\n"
              f"**Servers with Updates Channel:** {len(configured_guild_ids)}\n"
              f"**Servers without Updates Channel:** {total_guilds - len(configured_guild_ids)}",
        inline=False
    )
    result_embed.add_field(
        name="📨 Delivery Statistics",
        value=f"**Channel Messages:**\n"
              f"  ✅ Sent: {channel_success}\n"
              f"  ❌ Failed/N/A: {channel_fail}\n\n"
              f"**Owner DMs (All Servers):**\n"
              f"  ✅ Delivered: {dm_success}\n"
              f"  ❌ Failed (DMs disabled): {dm_fail}\n\n"
              f"**Total Delivered:** {channel_success + dm_success} messages\n"
              f"**Success Rate:** {round((dm_success / total_guilds) * 100, 1)}% owners reached",
        inline=False
    )
    result_embed.add_field(name="📝 Message", value=message[:1000], inline=False)
    result_embed.set_footer(text="Note: All server owners receive DMs regardless of updates channel setup")
    
    await ctx.send(embed=result_embed)


@bot.hybrid_command(name="viewupdates", description="View your server's updates channel configuration.")
async def view_updates(ctx):
    """View the current updates channel configuration"""
    if not ctx.guild:
        await ctx.send("❌ **This command can only be used in servers.**")
        return
    
    config = db_query("SELECT channel_id, setup_by, setup_at FROM updates_channels WHERE guild_id = ?", 
                     (str(ctx.guild.id),), fetch=True)
    
    if not config:
        embed = discord.Embed(
            title="⚠️ No Updates Channel Configured",
            description="This server hasn't set up an updates channel yet!",
            color=discord.Color.orange()
        )
        embed.add_field(name="Setup Now", 
                       value="Use `/setupupdates #channel` to configure one.\n\n**This is required for the bot to function properly!**",
                       inline=False)
        await ctx.send(embed=embed)
        return
    
    channel_id, setup_by, setup_at = config[0]
    
    embed = discord.Embed(
        title="📢 Updates Channel Configuration",
        description="Current updates channel setup for this server:",
        color=discord.Color.blue()
    )
    embed.add_field(name="Channel", value=f"<#{channel_id}>\n`{channel_id}`", inline=True)
    embed.add_field(name="Setup By", value=f"<@{setup_by}>", inline=True)
    embed.add_field(name="Setup Date", value=setup_at, inline=False)
    embed.set_footer(text="Use /changeupdates to change the channel")
    
    await ctx.send(embed=embed)


@bot.hybrid_command(name="help", description=f"Display {BOT_NAME} command center.")
async def help_cmd(ctx):
    is_admin = is_bot_admin(ctx.author.id)
    is_owner = ctx.author.id == OWNER_ID
    
    # EMBED 1: User & Server Admin Commands
    user_embed = discord.Embed(
        title=f"📚 {BOT_NAME} Command Guide",
        description="User commands and server configuration (Page 1/2)",
        color=discord.Color.green()
    )
    
    # Split user commands into TWO fields to stay under 1024 char limit
    user_commands_part1 = """
**`/help`** - Display this guide
**`/whoami`** - Show your profile & bot status
**`/stats`** - Display bot statistics
**`/ping`** - Check bot response time
**`/forget`** - Clear conversation memory
**`/report <@user> <proof> <reason>`** - Report user to admins
**`/invite`** - Get bot invite link
"""
    
    user_commands_part2 = """
**`/encode <message>`** - Encode text with cipher
**`/decode <encoded>`** - Decode cipher text
└─ Note: Remove backticks before decoding
└─ Strike issued if decoded text has banned words
"""
    
    user_embed.add_field(name="👤 User Commands (1/2)", value=user_commands_part1.strip(), inline=False)
    user_embed.add_field(name="👤 User Commands (2/2)", value=user_commands_part2.strip(), inline=False)
    
    # Split server admin commands into TWO fields
    server_admin_part1 = f"""
**`/start`** - Enable auto-response mode
└─ Bot responds to ALL messages
└─ Requires: Administrator

**`/stop`** - Enable selective-response mode
└─ Bot only responds to mentions
└─ Requires: Administrator

**`/lang [language]`** - Set channel language
└─ {len(AVAILABLE_LANGUAGES)} languages available
└─ Requires: Administrator

**`/prefix <new_prefix>`** - Change command prefix
└─ Requires: Administrator
"""
    
    server_admin_part2 = """
**`/setupupdates [#channel]`** - Setup updates channel
└─ REQUIRED for bot to function
└─ Requires: Administrator

**`/changeupdates [#channel]`** - Change updates channel
└─ Requires: Administrator

**`/viewupdates`** - View current updates channel
└─ Available to all users
"""
    
    user_embed.add_field(name="⚙️ Server Admin (1/2)", value=server_admin_part1.strip(), inline=False)
    user_embed.add_field(name="⚙️ Server Admin (2/2)", value=server_admin_part2.strip(), inline=False)
    
    # Features field - also split if needed
    features = f"""
**🎯 Response Modes:**
• START: Responds to every message
• STOP: Only mentions/triggers

**⚡ Strike System:**
• 3 strikes = auto-blacklist
• All actions logged with DM notifications

**🔇 Word Filter:**
• Banned words auto-deleted
• Admins/bypass users exempt

**📊 Multi-Language:**
• {len(AVAILABLE_LANGUAGES)} languages supported
• Channel-specific settings

**💾 Memory:**
• Remembers last 6 messages
• Use `/forget` to clear

**⏱️ Cooldown:**
• 0.6s between responses
• Prevents API rate limiting

**🎭 Reaction Detection:**
• Responds to reactions on messages (14 days)
• AI-generated contextual responses
• Toggle per-channel with /togglereactions
"""
    user_embed.add_field(name="✨ Bot Features", value=features.strip(), inline=False)
    
    user_embed.set_footer(text=f"{BOT_NAME} • Created by {OWNER_NAME} • Page 1/2")
    user_embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    # EMBED 2: Bot Admin & Owner Commands
    admin_embed = discord.Embed(
        title=f"🛡️ {BOT_NAME} Admin Command Guide",
        description=f"Bot admin and owner commands (Page 2/2)\n**Your Access:** {'👑 Owner' if is_owner else '✨ Bot Admin' if is_admin else '❌ No Access'}",
        color=discord.Color.gold() if is_owner else discord.Color.blue()
    )
    
    if is_owner:
        owner_cmds = """
**`add-admin <user>`** - Grant admin privileges
**`remove-admin <user>`** - Revoke admin privileges
**`list-admins`** - Display all admins
**`leave <server_id> [reason]`** - Leave server (DM only)
"""
        admin_embed.add_field(name="👑 Owner Only", value=owner_cmds.strip(), inline=False)
    
    # Split utility commands into multiple fields
    utility_part1 = """
**`/sync`** - Sync slash commands
**`/messages`** - Export 24h logs (DM only)
**`/allinteractions`** - Export ALL logs (DM only)
**`/clearlogs`** - Wipe interaction logs (DM only)
**`server-list`** - Export server list (DM only)
**`/backup`** - Trigger backup (DM only)
**`/data`** - Export complete data (DM only)
"""
    
    utility_part2 = """
**`/logs`** - View recent 15 action logs
**`/clearadminlogs`** - Clear admin logs
**`/searchlogs <keyword>`** - Search logs
**`/announce <message>`** - Broadcast to all servers
**`ids`** - Display command IDs
"""
    
    admin_embed.add_field(name="🛠️ Admin Utility (1/2)", value=utility_part1.strip(), inline=False)
    admin_embed.add_field(name="🛠️ Admin Utility (2/2)", value=utility_part2.strip(), inline=False)
    
    # Split moderation into MULTIPLE fields (it's very long)
    mod_part1 = """
**`/blacklist`** - View blacklisted users
**`/blacklist add <id> [reason]`** - Ban user from bot
**`/blacklist remove <id> [reason]`** - Unban user
**`/blacklist-guild`** - View blacklisted servers
**`/blacklist-guild add <id> [reason]`** - Ban server
**`/blacklist-guild remove <id> [reason]`** - Unban server
"""
    
    mod_part2 = """
**`/addstrike <id> [amt] [reason]`** - Add strikes
**`/removestrike <id> [amt] [reason]`** - Remove strikes
**`/clearstrike <id> [reason]`** - Clear all strikes
**`/strikelist`** - View users with strikes
"""
    
    mod_part3 = """
**`/bannedword`** - List banned words
**`/bannedword add <word>`** - Add to filter
**`/bannedword remove <word>`** - Remove from filter
**`/listwords`** - Alternative list command
"""
    
    mod_part4 = """
**`/bypass`** - List bypass users
**`/bypass add <id> [reason]`** - Grant bypass
**`/bypass remove <id> [reason]`** - Revoke bypass
"""
    
    mod_part5 = """
**`/reports [status]`** - View reports
**`/reportview <id>`** - View report details
**`/reportclear <id> [reason]`** - Clear user reports
**`/reportremove <id> [reason]`** - Delete report
"""
    
    admin_embed.add_field(name="🔨 Moderation (1/5)", value=mod_part1.strip(), inline=False)
    admin_embed.add_field(name="🔨 Moderation (2/5)", value=mod_part2.strip(), inline=False)
    admin_embed.add_field(name="🔨 Moderation (3/5)", value=mod_part3.strip(), inline=False)
    admin_embed.add_field(name="🔨 Moderation (4/5)", value=mod_part4.strip(), inline=False)
    admin_embed.add_field(name="🔨 Moderation (5/5)", value=mod_part5.strip(), inline=False)
    
    admin_embed.set_footer(text=f"Bot Admin Guide • All actions are logged • Page 2/2")
    admin_embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    # Views with working buttons
    class Page1View(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)
            self.add_item(discord.ui.Button(
                label="Support Server",
                style=discord.ButtonStyle.link,
                url=f"{os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}",
                emoji="🆘",
                row=1
            ))
            self.add_item(discord.ui.Button(
                label="Invite Bot",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions=4503599627488320&integration_type=0&scope=bot+applications.commands",
                emoji="🤖",
                row=1
            ))
            
        @discord.ui.button(label="Next Page →", style=discord.ButtonStyle.primary, emoji="📄", row=0)
        async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ Only the command user can navigate pages.", ephemeral=True)
                return
            await interaction.response.edit_message(embed=admin_embed, view=Page2View())
    
    class Page2View(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)
            self.add_item(discord.ui.Button(
                label="Support Server",
                style=discord.ButtonStyle.link,
                url=f"{os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}",
                emoji="🆘",
                row=1
            ))
            self.add_item(discord.ui.Button(
                label="Invite Bot",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions=4503599627488320&integration_type=0&scope=bot+applications.commands",
                emoji="🤖",
                row=1
            ))
            
        @discord.ui.button(label="← Previous Page", style=discord.ButtonStyle.secondary, emoji="📄", row=0)
        async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ Only the command user can navigate pages.", ephemeral=True)
                return
            await interaction.response.edit_message(embed=user_embed, view=Page1View())
    
    class UserOnlyView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)
            self.add_item(discord.ui.Button(
                label="Support Server",
                style=discord.ButtonStyle.link,
                url=f"{os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}",
                emoji="🆘"
            ))
            self.add_item(discord.ui.Button(
                label="Invite Bot",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions=4503599627488320&integration_type=0&scope=bot+applications.commands",
                emoji="🤖"
            ))
    
    # Send appropriate view based on user permissions
    if is_admin:
        await ctx.send(embed=user_embed, view=Page1View())
    else:
        await ctx.send(embed=user_embed, view=UserOnlyView())

@bot.hybrid_command(name="ping", description="Check bot response time.")
async def ping(ctx):
    latency = round(bot.latency * 1000)
    
    if latency < 100:
        emoji = "🟢"
        status = "Excellent"
    elif latency < 200:
        emoji = "🟡"
        status = "Good"
    else:
        emoji = "🔴"
        status = "Slow"
    
    await ctx.send(f"🏓 **Pong!** {emoji}\n**Latency:** {latency}ms ({status})")

# Updated Leaderboard Command - Keeps dropdown visible when category is selected
# Tic-Tac-Toe section now shows ONLY leaderboards with two rows of dropdowns

# ==================== LEADERBOARD COMMAND ====================

@bot.hybrid_command(name="leaderboard", description="View server or global leaderboards")
async def leaderboard(ctx, server_leaderboard: bool = True):
    """
    Display leaderboards for various game modes
    
    Parameters:
    -----------
    server_leaderboard: bool
        True for server leaderboard, False for global leaderboard
    """
    await ctx.defer()
    
    # Create the category selection view (PERSISTENT - doesn't get removed)
    class LeaderboardCategoryView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)  # Increased timeout
            self.selected_category = None
            
        @discord.ui.select(
            placeholder="Choose a leaderboard category",
            options=[
                discord.SelectOption(
                    label="Chat with AI",
                    description="Messages exchanged with AI",
                    emoji="💬",
                    value="ai_chat"
                ),
                discord.SelectOption(
                    label="Chess",
                    description="Wins against Stockfish",
                    emoji="♟️",
                    value="chess"
                ),
                discord.SelectOption(
                    label="Tic-Tac-Toe",
                    description="Wins in Tic-Tac-Toe",
                    emoji="⭕",
                    value="tictactoe"
                )
            ]
        )
        async def category_select(self, interaction: discord.Interaction, select: discord.ui.Select):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("❌ This is not your leaderboard!", ephemeral=True)
                return
                
            self.selected_category = select.values[0]
            
            # Edit message but KEEP the view (dropdown stays visible)
            if self.selected_category == "ai_chat":
                await show_ai_chat_leaderboard(interaction, server_leaderboard, self)
            elif self.selected_category == "chess":
                await show_chess_leaderboard(interaction, server_leaderboard, self)
            elif self.selected_category == "tictactoe":
                await show_tictactoe_difficulty_select(interaction, server_leaderboard, self)
    
    # AI Chat Leaderboard - NOW ACCEPTS VIEW PARAMETER
    async def show_ai_chat_leaderboard(interaction, is_server, view):
        today = datetime.date.today()
        
        if is_server:
            query = '''
                SELECT user_id, message_count 
                FROM leaderboard_ai_chat 
                WHERE guild_id = ? AND DATE(first_message_date) >= DATE(?)
                ORDER BY message_count DESC 
                LIMIT 10
            '''
            results = db_query(query, (str(ctx.guild.id), today), fetch=True)
            title = f"🏆 {ctx.guild.name} - AI Chat Leaderboard"
        else:
            query = '''
                SELECT user_id, SUM(message_count) as total
                FROM leaderboard_ai_chat 
                WHERE DATE(first_message_date) >= DATE(?)
                GROUP BY user_id 
                ORDER BY total DESC 
                LIMIT 10
            '''
            results = db_query(query, (today,), fetch=True)
            title = "🌍 Global AI Chat Leaderboard"
        
        embed = discord.Embed(
            title=title,
            description=f"*Tracking started: {today}*",
            color=discord.Color.blue()
        )
        
        if results:
            leaderboard_text = ""
            for idx, row in enumerate(results, 1):
                user_id = row[0]
                count = row[1]
                
                try:
                    user = bot.get_user(int(user_id)) or await bot.fetch_user(int(user_id))
                    name = user.name
                except:
                    name = f"User {user_id}"
                
                medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"**{idx}.**"
                leaderboard_text += f"{medal} {name} - **{count}** messages\n"
            
            embed.add_field(name="Top Players", value=leaderboard_text, inline=False)
        else:
            embed.description = "No data available yet. Start chatting with the AI!"
        
        # Keep the view (dropdown) visible
        await interaction.response.edit_message(embed=embed, view=view)
    
    # Chess Leaderboard - NOW ACCEPTS VIEW PARAMETER
    async def show_chess_leaderboard(interaction, is_server, view):
        today = datetime.date.today()
        
        if is_server:
            query = '''
                SELECT user_id, wins 
                FROM leaderboard_chess 
                WHERE guild_id = ? AND DATE(first_win_date) >= DATE(?)
                ORDER BY wins DESC 
                LIMIT 10
            '''
            results = db_query(query, (str(ctx.guild.id), today), fetch=True)
            title = f"🏆 {ctx.guild.name} - Chess Leaderboard"
        else:
            query = '''
                SELECT user_id, SUM(wins) as total
                FROM leaderboard_chess 
                WHERE DATE(first_win_date) >= DATE(?)
                GROUP BY user_id 
                ORDER BY total DESC 
                LIMIT 10
            '''
            results = db_query(query, (today,), fetch=True)
            title = "🌍 Global Chess Leaderboard"
        
        embed = discord.Embed(
            title=title,
            description=f"*Wins against Stockfish • Tracking started: {today}*",
            color=discord.Color.gold()
        )
        
        if results:
            leaderboard_text = ""
            for idx, row in enumerate(results, 1):
                user_id = row[0]
                wins = row[1]
                
                try:
                    user = bot.get_user(int(user_id)) or await bot.fetch_user(int(user_id))
                    name = user.name
                except:
                    name = f"User {user_id}"
                
                medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"**{idx}.**"
                leaderboard_text += f"{medal} {name} - **{wins}** wins\n"
            
            embed.add_field(name="Top Players", value=leaderboard_text, inline=False)
        else:
            embed.description = "No wins recorded yet. Beat Stockfish to appear here!"
        
        # Keep the view (dropdown) visible
        await interaction.response.edit_message(embed=embed, view=view)
    
    # Tic-Tac-Toe Difficulty Selection - NOW WITH TWO ROWS OF DROPDOWNS
    async def show_tictactoe_difficulty_select(interaction, is_server, parent_view):
        # Create NEW view with BOTH category dropdown AND difficulty dropdown
        class TicTacToeLeaderboardView(discord.ui.View):
            def __init__(self, parent_view):
                super().__init__(timeout=180)
                self.parent_view = parent_view
                
                # Add the category dropdown from parent (FIRST ROW)
                self.add_item(parent_view.children[0])
                
            @discord.ui.select(
                placeholder="Select difficulty level",
                options=[
                    discord.SelectOption(label="Easy", emoji="🟢", value="easy"),
                    discord.SelectOption(label="Medium", emoji="🟡", value="medium"),
                    discord.SelectOption(label="Hard", emoji="🔴", value="hard"),
                    discord.SelectOption(label="Impossible", emoji="💀", value="insane")
                ],
                row=1  # SECOND ROW
            )
            async def difficulty_select(self, inter: discord.Interaction, select: discord.ui.Select):
                if inter.user.id != ctx.author.id:
                    await inter.response.send_message("❌ This is not your leaderboard!", ephemeral=True)
                    return
                
                difficulty = select.values[0]
                # Show the leaderboard for selected difficulty (KEEP BOTH DROPDOWNS)
                await show_tictactoe_leaderboard(inter, is_server, difficulty, self)
        
        # Initial embed asking to select difficulty
        embed = discord.Embed(
            title="⭕ Tic-Tac-Toe Leaderboard",
            description="Please select a difficulty level to view the leaderboard:",
            color=discord.Color.purple()
        )
        
        new_view = TicTacToeLeaderboardView(parent_view)
        await interaction.response.edit_message(embed=embed, view=new_view)
    
    # Tic-Tac-Toe Leaderboard by Difficulty - KEEPS BOTH DROPDOWNS VISIBLE
    async def show_tictactoe_leaderboard(interaction, is_server, difficulty, view):
        today = datetime.date.today()
        
        if is_server:
            query = '''
                SELECT user_id, wins 
                FROM leaderboard_tictactoe 
                WHERE guild_id = ? AND difficulty = ? AND DATE(first_win_date) >= DATE(?)
                ORDER BY wins DESC 
                LIMIT 10
            '''
            results = db_query(query, (str(ctx.guild.id), difficulty, today), fetch=True)
            title = f"🏆 {ctx.guild.name} - Tic-Tac-Toe ({difficulty.capitalize()})"
        else:
            query = '''
                SELECT user_id, SUM(wins) as total
                FROM leaderboard_tictactoe 
                WHERE difficulty = ? AND DATE(first_win_date) >= DATE(?)
                GROUP BY user_id 
                ORDER BY total DESC 
                LIMIT 10
            '''
            results = db_query(query, (difficulty, today), fetch=True)
            title = f"🌍 Global Tic-Tac-Toe ({difficulty.capitalize()})"
        
        embed = discord.Embed(
            title=title,
            description=f"*Difficulty: {difficulty.capitalize()} • Tracking started: {today}*",
            color=discord.Color.purple()
        )
        
        if results:
            leaderboard_text = ""
            for idx, row in enumerate(results, 1):
                user_id = row[0]
                wins = row[1]
                
                try:
                    user = bot.get_user(int(user_id)) or await bot.fetch_user(int(user_id))
                    name = user.name
                except:
                    name = f"User {user_id}"
                
                medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"**{idx}.**"
                leaderboard_text += f"{medal} {name} - **{wins}** wins\n"
            
            embed.add_field(name="Top Players", value=leaderboard_text, inline=False)
        else:
            embed.description = f"No wins recorded yet at {difficulty} difficulty!\n\n*Difficulty: {difficulty.capitalize()} • Tracking started: {today}*"
        
        # Keep BOTH dropdowns visible (category + difficulty)
        await interaction.response.edit_message(embed=embed, view=view)
    
    # Show initial category selection
    scope = "Server" if server_leaderboard else "Global"
    embed = discord.Embed(
        title=f"📊 {scope} Leaderboards",
        description="Select a category to view:",
        color=discord.Color.blurple()
    )
    
    view = LeaderboardCategoryView()
    await ctx.send(embed=embed, view=view)


@bot.hybrid_command(name="invite", description=f"Add {BOT_NAME} to your own server!")
async def invite(ctx):
    invite_url = f"https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions=4503599627488320&integration_type=0&scope=bot+applications.commands"
    
    embed = discord.Embed(
        title=f"🔗 Invite {BOT_NAME}",
        description=f"Want to bring {BOT_NAME} to your community? Click the button below to authorize the bot!",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Add to Server", url=invite_url, style=discord.ButtonStyle.link, emoji="🤖"))
    
    await ctx.send(embed=embed, view=view)


@bot.hybrid_command(name="forget", description="Clear AI memory for this conversation.")
async def forget(ctx):
    tid = f"{ctx.channel.id}-{ctx.author.id}"
    if tid in bot.memory:
        messages_cleared = len(bot.memory[tid])
        bot.memory[tid].clear()
        await ctx.send(f"🧠 **Memory cleared**\nRemoved {messages_cleared} message(s) from conversation history.")
    else:
        await ctx.send("🧠 **No memory to clear**\nThis conversation has no stored history.")

@bot.command(name="ids", description="Owner/Admin: List all slash command IDs.")
@owner_or_bot_admin()
async def command_ids(ctx):
    """Display all slash commands with their IDs"""
    
    try:
        synced_commands = await bot.tree.fetch_commands()
        
        if not synced_commands:
            await ctx.send("❌ **No slash commands found**\nTry running `/sync` first.")
            return
        
        embed = discord.Embed(
            title="Slash Command IDs",
            description="All registered slash commands and their Discord IDs",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        
        # Sort commands alphabetically
        sorted_commands = sorted(synced_commands, key=lambda x: x.name)
        
        # Build command list
        command_list = []
        for cmd in sorted_commands:
            command_list.append(f"**/{cmd.name}** → `{cmd.id}`")
        
        # Split into chunks if too long
        command_text = "\n".join(command_list)
        
        if len(command_text) > 1024:
            # Split into multiple fields
            chunks = []
            current_chunk = []
            current_length = 0
            
            for line in command_list:
                if current_length + len(line) + 1 > 1024:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = [line]
                    current_length = len(line)
                else:
                    current_chunk.append(line)
                    current_length += len(line) + 1
            
            if current_chunk:
                chunks.append("\n".join(current_chunk))
            
            for i, chunk in enumerate(chunks, 1):
                embed.add_field(
                    name=f"Commands (Part {i}/{len(chunks)})",
                    value=chunk,
                    inline=False
                )
        else:
            embed.add_field(
                name="Commands",
                value=command_text,
                inline=False
            )
        
        embed.add_field(
            name="📊 Total Commands",
            value=f"**{len(sorted_commands)}** slash commands registered",
            inline=False
        )
        
        embed.set_footer(text=f"Requested by {ctx.author.name} | Use format: </command:id> to mention commands")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ **Error fetching command IDs:**\n```\n{str(e)}\n```")


# Allowed characters only
ALLOWED_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789&,-/.!?="

# ==================== ENCODING FUNCTIONS ====================

def generate_key_lvl0(text_length):
    """Level 0: Simple timestamp-based key (2 chars)"""
    timestamp = str(int(time.time()))
    seed = f"{timestamp}{text_length}"
    hash_val = hashlib.md5(seed.encode()).hexdigest()
    result = ""
    for i in range(2):
        idx = int(hash_val[i*4:i*4+4], 16) % len(ALLOWED_CHARS)
        result += ALLOWED_CHARS[idx]
    return result

def generate_key_lvl1(text_length):
    """Level 1: Timestamp + random (4 chars)"""
    timestamp = str(int(time.time() * 1000))
    seed = f"{timestamp}{text_length}{random.randint(10, 99)}"
    hash_val = hashlib.md5(seed.encode()).hexdigest()
    result = ""
    for i in range(4):
        idx = int(hash_val[i*4:i*4+4], 16) % len(ALLOWED_CHARS)
        result += ALLOWED_CHARS[idx]
    return result

def generate_key_lvl2(text_length):
    """Level 2: More random (6 chars)"""
    timestamp = str(int(time.time() * 1000))
    seed = f"{timestamp}{text_length}{random.randint(1000, 9999)}"
    hash_val = hashlib.md5(seed.encode()).hexdigest()
    result = ""
    for i in range(6):
        idx = int(hash_val[i*2:i*2+2], 16) % len(ALLOWED_CHARS)
        result += ALLOWED_CHARS[idx]
    return result

def generate_key_lvl3(text_length):
    """Level 3: Maximum randomness (8 chars)"""
    timestamp = str(int(time.time() * 10000))
    seed = f"{timestamp}{text_length}{random.randint(10000, 99999)}{random.random()}"
    hash_val = hashlib.sha256(seed.encode()).hexdigest()
    result = ""
    for i in range(8):
        idx = int(hash_val[i*2:i*2+2], 16) % len(ALLOWED_CHARS)
        result += ALLOWED_CHARS[idx]
    return result

def encode_base(text, key):
    """Base encoding function used by all levels"""
    if not text:
        return ""
    
    # Convert entire text to single large number
    text_bytes = text.encode('utf-8')
    big_num = int.from_bytes(text_bytes, 'big')
    
    # Mix with key
    key_num = sum(ord(c) * (i + 1) for i, c in enumerate(key))
    mixed = big_num + key_num
    
    # Convert to base using allowed chars
    base = len(ALLOWED_CHARS)
    encoded = ""
    while mixed > 0:
        encoded = ALLOWED_CHARS[mixed % base] + encoded
        mixed //= base
    
    if not encoded:
        encoded = ALLOWED_CHARS[0]
    
    return encoded

def encode_text_lvl0(text):
    """
    Level 0: Simple encoding (minimal)
    Format: key.data
    Length: ~original + 3-4 chars
    """
    key = generate_key_lvl0(len(text))
    encoded = encode_base(text, key)
    return f"{key}.{encoded}"

def encode_text_lvl1(text):
    """
    Level 1: Standard encoding
    Format: key.data.checksum
    Length: ~original + 6-8 chars (guaranteed 5+ total)
    """
    key = generate_key_lvl1(len(text))
    encoded = encode_base(text, key)
    
    # Add 2-char checksum
    checksum_hash = hashlib.md5(f"{text}{key}".encode()).hexdigest()
    checksum = ""
    for i in range(2):
        idx = int(checksum_hash[i*2:i*2+2], 16) % len(ALLOWED_CHARS)
        checksum += ALLOWED_CHARS[idx]
    
    result = f"{key}.{encoded}.{checksum}"
    
    # Ensure minimum 5 chars total
    if len(result) < 5:
        padding = ALLOWED_CHARS[0] * (5 - len(result))
        result += padding
    
    return result

def encode_text_lvl2(text):
    """
    Level 2: Enhanced encoding with noise
    Format: key.noise.data.checksum
    Length: ~original + 10-12 chars (guaranteed 7+ total)
    """
    key = generate_key_lvl2(len(text))
    encoded = encode_base(text, key)
    
    # Add 2-char noise
    noise = ""
    for i in range(2):
        noise += ALLOWED_CHARS[random.randint(0, len(ALLOWED_CHARS) - 1)]
    
    # Add 3-char checksum
    checksum_hash = hashlib.md5(f"{text}{key}{noise}".encode()).hexdigest()
    checksum = ""
    for i in range(3):
        idx = int(checksum_hash[i*2:i*2+2], 16) % len(ALLOWED_CHARS)
        checksum += ALLOWED_CHARS[idx]
    
    result = f"{key}.{noise}.{encoded}.{checksum}"
    
    # Ensure minimum 7 chars total
    if len(result) < 7:
        padding = ALLOWED_CHARS[0] * (7 - len(result))
        result += padding
    
    return result

def encode_text_lvl3(text):
    """
    Level 3: Maximum security with salt and extended checksum
    Format: key.salt.data.checksum
    Length: ~original + 18-22 chars (guaranteed 12+ total)
    """
    key = generate_key_lvl3(len(text))
    encoded = encode_base(text, key)
    
    # Add 4-char salt
    salt = ""
    for i in range(4):
        salt += ALLOWED_CHARS[random.randint(0, len(ALLOWED_CHARS) - 1)]
    
    # Add 5-char checksum
    checksum_hash = hashlib.sha256(f"{text}{key}{salt}".encode()).hexdigest()
    checksum = ""
    for i in range(5):
        idx = int(checksum_hash[i*2:i*2+2], 16) % len(ALLOWED_CHARS)
        checksum += ALLOWED_CHARS[idx]
    
    result = f"{key}.{salt}.{encoded}.{checksum}"
    
    # Ensure minimum 12 chars total
    if len(result) < 12:
        padding = ALLOWED_CHARS[0] * (12 - len(result))
        result += padding
    
    return result

# ==================== DECODING FUNCTION ====================

def decode_text_universal(encoded):
    """Universal decoder - works for all encoding levels"""
    if not encoded or "." not in encoded:
        return "Invalid format - missing separator"
    
    try:
        parts = encoded.split(".")
        
        # Detect encoding level by number of parts and key length
        if len(parts) == 2:
            # Level 0: key.data
            key, data = parts
            if len(key) != 2:
                return "Invalid Level 0 format"
            
            # Decode
            base = len(ALLOWED_CHARS)
            mixed = 0
            for char in data:
                if char not in ALLOWED_CHARS:
                    continue
                mixed = mixed * base + ALLOWED_CHARS.index(char)
            
            # Unmix with key
            key_num = sum(ord(c) * (i + 1) for i, c in enumerate(key))
            big_num = mixed - key_num
            
            if big_num < 0:
                return "Invalid encoding"
            
            # Convert back to bytes
            byte_length = max(1, (big_num.bit_length() + 7) // 8)
            text_bytes = big_num.to_bytes(byte_length, 'big')
            return text_bytes.decode('utf-8', errors='ignore')
        
        elif len(parts) == 3:
            # Level 1: key.data.checksum
            key, data, checksum = parts
            if len(key) != 4 or len(checksum) != 2:
                return "Invalid Level 1 format"
            
            # Remove padding
            data = data.rstrip(ALLOWED_CHARS[0])
            
            # Decode
            base = len(ALLOWED_CHARS)
            mixed = 0
            for char in data:
                if char not in ALLOWED_CHARS:
                    continue
                mixed = mixed * base + ALLOWED_CHARS.index(char)
            
            # Unmix with key
            key_num = sum(ord(c) * (i + 1) for i, c in enumerate(key))
            big_num = mixed - key_num
            
            if big_num < 0:
                return "Invalid encoding"
            
            # Convert back to bytes
            byte_length = max(1, (big_num.bit_length() + 7) // 8)
            text_bytes = big_num.to_bytes(byte_length, 'big')
            result = text_bytes.decode('utf-8', errors='ignore')
            
            # Verify checksum
            checksum_hash = hashlib.md5(f"{result}{key}".encode()).hexdigest()
            expected_checksum = ""
            for i in range(2):
                idx = int(checksum_hash[i*2:i*2+2], 16) % len(ALLOWED_CHARS)
                expected_checksum += ALLOWED_CHARS[idx]
            
            if checksum != expected_checksum:
                return f"{result} (Warning: Checksum mismatch)"
            
            return result
        
        elif len(parts) == 4:
            # Could be Level 2 or Level 3
            key, noise_or_salt, data, checksum = parts
            
            if len(key) == 6 and len(noise_or_salt) == 2 and len(checksum) == 3:
                # Level 2: key(6).noise(2).data.checksum(3)
                key, noise, data, checksum = parts
                
                # Remove padding
                data = data.rstrip(ALLOWED_CHARS[0])
                
                # Decode
                base = len(ALLOWED_CHARS)
                mixed = 0
                for char in data:
                    if char not in ALLOWED_CHARS:
                        continue
                    mixed = mixed * base + ALLOWED_CHARS.index(char)
                
                # Unmix with key
                key_num = sum(ord(c) * (i + 1) for i, c in enumerate(key))
                big_num = mixed - key_num
                
                if big_num < 0:
                    return "Invalid encoding"
                
                # Convert back to bytes
                byte_length = max(1, (big_num.bit_length() + 7) // 8)
                text_bytes = big_num.to_bytes(byte_length, 'big')
                result = text_bytes.decode('utf-8', errors='ignore')
                
                # Verify checksum
                checksum_hash = hashlib.md5(f"{result}{key}{noise}".encode()).hexdigest()
                expected_checksum = ""
                for i in range(3):
                    idx = int(checksum_hash[i*2:i*2+2], 16) % len(ALLOWED_CHARS)
                    expected_checksum += ALLOWED_CHARS[idx]
                
                if checksum != expected_checksum:
                    return f"{result} (Warning: Checksum mismatch)"
                
                return result
            
            elif len(key) == 8 and len(noise_or_salt) == 4 and len(checksum) == 5:
                # Level 3: key(8).salt(4).data.checksum(5)
                key, salt, data, checksum = parts
                
                # Remove padding
                data = data.rstrip(ALLOWED_CHARS[0])
                
                # Decode
                base = len(ALLOWED_CHARS)
                mixed = 0
                for char in data:
                    if char not in ALLOWED_CHARS:
                        continue
                    mixed = mixed * base + ALLOWED_CHARS.index(char)
                
                # Unmix with key
                key_num = sum(ord(c) * (i + 1) for i, c in enumerate(key))
                big_num = mixed - key_num
                
                if big_num < 0:
                    return "Invalid encoding"
                
                # Convert back to bytes
                byte_length = max(1, (big_num.bit_length() + 7) // 8)
                text_bytes = big_num.to_bytes(byte_length, 'big')
                result = text_bytes.decode('utf-8', errors='ignore')
                
                # Verify checksum
                checksum_hash = hashlib.sha256(f"{result}{key}{salt}".encode()).hexdigest()
                expected_checksum = ""
                for i in range(5):
                    idx = int(checksum_hash[i*2:i*2+2], 16) % len(ALLOWED_CHARS)
                    expected_checksum += ALLOWED_CHARS[idx]
                
                if checksum != expected_checksum:
                    return f"{result} (Warning: Checksum mismatch)"
                
                return result
            else:
                return "Invalid format - unknown level"
        else:
            return "Invalid format - too many parts"
        
    except Exception as e:
        return f"Decoding error: {str(e)}"

@bot.hybrid_command(name="whoami", description="Show your Discord profile.")
async def whoami(ctx):
    user = ctx.author
    roles = ", ".join([r.name for r in user.roles[1:]]) if ctx.guild else "N/A"
    
    # Get user's moderation status
    user_data = db_query("SELECT strikes, blacklisted FROM users WHERE user_id = ?", (str(user.id),), fetch=True)
    
    if user_data:
        strikes, blacklisted = user_data[0]
    else:
        strikes, blacklisted = 0, 0
    
    # Check additional statuses
    is_owner = user.id == OWNER_ID
    is_admin = is_bot_admin(user.id)
    has_bypass = is_bypass_user(user.id)
    is_blacklisted = bool(blacklisted)
    
    # Calculate account age - FIXED: use timezone-aware datetime
    account_age = (datetime.datetime.now(datetime.timezone.utc) - user.created_at).days
    
    embed = discord.Embed(
        title=f"👤 {user.name}",
        description=f"Here's your profile information:",
        color=user.color if ctx.guild else discord.Color.blue()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    
    # Basic Info
    embed.add_field(name="🆔 User ID", value=f"`{user.id}`", inline=True)
    embed.add_field(name="📝 Display Name", value=user.display_name, inline=True)
    embed.add_field(name="📅 Account Age", value=f"{account_age} days", inline=True)
    
    # Server Info (if in a server)
    if ctx.guild:
        # FIXED: use timezone-aware datetime here too
        join_age = (datetime.datetime.now(datetime.timezone.utc) - user.joined_at).days if user.joined_at else 0
        embed.add_field(name="🏠 Server Roles", value=roles if roles != "N/A" else "None", inline=False)
        embed.add_field(name="📆 Joined Server", value=f"{join_age} days ago", inline=True)
    
    # Bot Status
    status_lines = []
    if is_owner:
        status_lines.append("👑 **Bot Owner**")
    if is_admin:
        status_lines.append("✨ **Bot Admin**")
    if has_bypass:
        status_lines.append("🔓 **Word Filter Bypass**")
    
    if status_lines:
        embed.add_field(name="🎖️ Bot Privileges", value="\n".join(status_lines), inline=False)
    
    # Moderation Status
    if is_blacklisted:
        mod_status = "🚫 **BLACKLISTED**"
        mod_color = discord.Color.dark_red()
        embed.color = mod_color
    elif strikes >= 2:
        mod_status = f"⚠️ **{strikes}/3 Strikes** (High Risk)"
        mod_color = discord.Color.orange()
    elif strikes >= 1:
        mod_status = f"⚡ **{strikes}/3 Strikes**"
        mod_color = discord.Color.gold()
    else:
        mod_status = "✅ **Clean Record**"
        mod_color = discord.Color.green()
    
    embed.add_field(name="📊 Moderation Status", value=mod_status, inline=True)
    
    # Account standing summary
    if is_blacklisted:
        embed.add_field(
            name="⚠️ Account Standing", 
            value="Your account is **suspended** from using the bot.\nContact the bot owner or [join the support server](<{os.getenv('SUPPORT_SERVER_INVITE')}>)for appeals.",
            inline=False
        )
    elif strikes >= 2:
        embed.add_field(
            name="⚠️ Account Standing",
            value=f"You are **{3 - strikes} strike(s)** away from being blacklisted.\nPlease follow community guidelines.",
            inline=False
        )
    elif strikes >= 1:
        embed.add_field(
            name="📌 Account Standing",
            value=f"You have **{strikes} strike(s)**. Be careful to avoid more violations.",
            inline=False
        )
    else:
        embed.add_field(
            name="✅ Account Standing",
            value="Your account is in **good standing**!",
            inline=False
        )
    
    # Footer with creation date
    embed.set_footer(text=f"Account Created: {user.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    await ctx.send(embed=embed)


    

# ==================== DISCORD COMMANDS ====================

@bot.hybrid_command(name="encode", description="Encode text (Level 0 - Simple)")
async def encode_cmd(ctx, *, message: str):
    """Encode a message using Level 0 encoding (simple, minimal length)"""
    
    # Check for banned words if not bypass user
    if not is_bypass_user(ctx.author.id):
        banned = db_query("SELECT word FROM banned_words", fetch=True)
        content_low = message.lower()
        if banned and any(bw[0].lower() in content_low for bw in banned):
            await ctx.send("❌ **Cannot encode** - Message contains banned words.", ephemeral=True)
            return
    
    try:
        encoded = encode_text_lvl0(message)
        
        embed = discord.Embed(title="🔐 Message Encoded (Level 0)", color=discord.Color.green())
        
        original_display = (message[:100] + "...") if len(message) > 100 else message
        embed.add_field(name="📝 Original", value=f"`{original_display}`", inline=False)
        
        encoded_display = (encoded[:1000] + "...") if len(encoded) > 1000 else encoded
        embed.add_field(name="🔒 Encoded", value=f"`{encoded_display}`", inline=False)
        
        embed.add_field(name="ℹ️ Level", value="**Level 0** - Simple encoding", inline=True)
        embed.add_field(name="📏 Length", value=f"{len(encoded)} chars", inline=True)
        
        embed.set_footer(text="Use /decode to decrypt • Level 0: Minimal security")
        
        await ctx.send(embed=embed)
        
        # Send full encoded message
        if len(encoded) <= 1990:
            await ctx.send(f"`{encoded}`")
            
    except Exception as e:
        await ctx.send(f"❌ **Encoding failed:** `{str(e)}`", ephemeral=True)

@bot.hybrid_command(name="encode-lvl-1", description="Encode text (Level 1 - Standard)")
async def encode_lvl1_cmd(ctx, *, message: str):
    """Encode a message using Level 1 encoding (standard with checksum)"""
    
    # Check for banned words if not bypass user
    if not is_bypass_user(ctx.author.id):
        banned = db_query("SELECT word FROM banned_words", fetch=True)
        content_low = message.lower()
        if banned and any(bw[0].lower() in content_low for bw in banned):
            await ctx.send("❌ **Cannot encode** - Message contains banned words.", ephemeral=True)
            return
    
    try:
        encoded = encode_text_lvl1(message)
        
        embed = discord.Embed(title="🔐 Message Encoded (Level 1)", color=discord.Color.blue())
        
        original_display = (message[:100] + "...") if len(message) > 100 else message
        embed.add_field(name="📝 Original", value=f"`{original_display}`", inline=False)
        
        encoded_display = (encoded[:1000] + "...") if len(encoded) > 1000 else encoded
        embed.add_field(name="🔒 Encoded", value=f"`{encoded_display}`", inline=False)
        
        embed.add_field(name="ℹ️ Level", value="**Level 1** - Standard encoding", inline=True)
        embed.add_field(name="📏 Length", value=f"{len(encoded)} chars (min 5+)", inline=True)
        
        embed.set_footer(text="Use /decode to decrypt • Level 1: Standard security with checksum")
        
        await ctx.send(embed=embed)
        
        # Send full encoded message
        if len(encoded) <= 1990:
            await ctx.send(f"`{encoded}`")
            
    except Exception as e:
        await ctx.send(f"❌ **Encoding failed:** `{str(e)}`", ephemeral=True)

@bot.hybrid_command(name="encode-lvl-2", description="Encode text (Level 2 - Enhanced)")
async def encode_lvl2_cmd(ctx, *, message: str):
    """Encode a message using Level 2 encoding (enhanced with noise)"""
    
    # Check for banned words if not bypass user
    if not is_bypass_user(ctx.author.id):
        banned = db_query("SELECT word FROM banned_words", fetch=True)
        content_low = message.lower()
        if banned and any(bw[0].lower() in content_low for bw in banned):
            await ctx.send("❌ **Cannot encode** - Message contains banned words.", ephemeral=True)
            return
    
    try:
        encoded = encode_text_lvl2(message)
        
        embed = discord.Embed(title="🔐 Message Encoded (Level 2)", color=discord.Color.purple())
        
        original_display = (message[:100] + "...") if len(message) > 100 else message
        embed.add_field(name="📝 Original", value=f"`{original_display}`", inline=False)
        
        encoded_display = (encoded[:1000] + "...") if len(encoded) > 1000 else encoded
        embed.add_field(name="🔒 Encoded", value=f"`{encoded_display}`", inline=False)
        
        embed.add_field(name="ℹ️ Level", value="**Level 2** - Enhanced encoding", inline=True)
        embed.add_field(name="📏 Length", value=f"{len(encoded)} chars (min 7+)", inline=True)
        
        embed.set_footer(text="Use /decode to decrypt • Level 2: Enhanced security with noise")
        
        await ctx.send(embed=embed)
        
        # Send full encoded message
        if len(encoded) <= 1990:
            await ctx.send(f"`{encoded}`")
            
    except Exception as e:
        await ctx.send(f"❌ **Encoding failed:** `{str(e)}`", ephemeral=True)

@bot.hybrid_command(name="encode-lvl-3", description="Encode text (Level 3 - Maximum)")
async def encode_lvl3_cmd(ctx, *, message: str):
    """Encode a message using Level 3 encoding (maximum security)"""
    
    # Check for banned words if not bypass user
    if not is_bypass_user(ctx.author.id):
        banned = db_query("SELECT word FROM banned_words", fetch=True)
        content_low = message.lower()
        if banned and any(bw[0].lower() in content_low for bw in banned):
            await ctx.send("❌ **Cannot encode** - Message contains banned words.", ephemeral=True)
            return
    
    try:
        encoded = encode_text_lvl3(message)
        
        embed = discord.Embed(title="🔐 Message Encoded (Level 3)", color=discord.Color.gold())
        
        original_display = (message[:100] + "...") if len(message) > 100 else message
        embed.add_field(name="📝 Original", value=f"`{original_display}`", inline=False)
        
        encoded_display = (encoded[:1000] + "...") if len(encoded) > 1000 else encoded
        embed.add_field(name="🔒 Encoded", value=f"`{encoded_display}`", inline=False)
        
        embed.add_field(name="ℹ️ Level", value="**Level 3** - Maximum encoding", inline=True)
        embed.add_field(name="📏 Length", value=f"{len(encoded)} chars (min 12+)", inline=True)
        
        embed.set_footer(text="Use /decode to decrypt • Level 3: Maximum security with salt")
        
        await ctx.send(embed=embed)
        
        # Send full encoded message
        if len(encoded) <= 1990:
            await ctx.send(f"`{encoded}`")
            
    except Exception as e:
        await ctx.send(f"❌ **Encoding failed:** `{str(e)}`", ephemeral=True)

@bot.tree.command(name="tic-tac-toe", description="Play Tic-Tac-Toe against AI or another player")
async def tictactoe_cmd(interaction: discord.Interaction, opponent: discord.Member = None):
    """
    Start a tic-tac-toe game
    
    Parameters:
    opponent: Challenge another user (leave empty to play against AI)
    """
    try:
        # Check blacklist
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        user_data = c.execute(
            "SELECT blacklisted FROM users WHERE user_id = ?",
            (str(interaction.user.id),)
        ).fetchone()
        conn.close()
        
        if user_data and user_data[0] == 1:
            await interaction.response.send_message(
                "❌ You are blacklisted from using this bot.",
                ephemeral=True
            )
            return
        
        if opponent:
            # PvP mode
            if opponent.id == interaction.user.id:
                await interaction.response.send_message(
                    "❌ You cannot play against yourself!",
                    ephemeral=True
                )
                return
            
            if opponent.bot:
                await interaction.response.send_message(
                    "❌ You cannot play against bots!",
                    ephemeral=True
                )
                return
            
            # Send invite with ping
            embed = discord.Embed(
                title="🎮 Tic-Tac-Toe Challenge",
                description=(
                    f"**{interaction.user.mention}** has challenged you to a game!\n\n"
                    f"⏰ Time to accept: <t:{int((datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=600)).timestamp())}:R>"
                ),
                color=discord.Color.blue()
            )
            embed.set_footer(text="Accept or decline the challenge below!")
            
            invite_view = TicTacToeInvite(
                str(interaction.user.id),
                str(opponent.id),
                str(interaction.channel.id)
            )
            
            # Send with ping in content
            await interaction.response.send_message(
                content=f"{opponent.mention}",
                embed=embed,
                view=invite_view
            )
            
            # Store message for timeout edit
            message = await interaction.original_response()
            invite_view.message = message
            invite_view.challenger_mention = interaction.user.mention
            invite_view.opponent_mention = opponent.mention
            
        else:
            # AI mode - show difficulty selector
            embed = discord.Embed(
                title="🎮 Tic-Tac-Toe - AI Mode",
                description=(
                    "Select your difficulty:\n\n"
                    "🟢 **Easy** - AI has 30% win chance\n"
                    "🟡 **Middle** - AI has 50% win chance\n"
                    "🟠 **Hard** - AI has 70% win chance\n"
                    "🔴 **Insane** - AI has 85% win chance"
                ),
                color=discord.Color.blue()
            )
            
            await interaction.response.send_message(
                embed=embed,
                view=DifficultyView()
            )
    
    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )
        print(f"Error in tictactoe command: {e}")




@bot.tree.command(name="tictactoe-stats", description="View your tic-tac-toe statistics")
async def tictactoe_stats_cmd(interaction: discord.Interaction):
    """View your game stats"""
    user_id = str(interaction.user.id)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    total = c.execute(
        "SELECT COUNT(*) FROM tictactoe_games WHERE (player1_id = ? OR player2_id = ?) AND status != 'active'",
        (user_id, user_id)
    ).fetchone()[0]
    
    wins = c.execute(
        "SELECT COUNT(*) FROM tictactoe_games WHERE winner_id = ? AND status IN ('finished', 'forfeit')",
        (user_id,)
    ).fetchone()[0]
    
    draws = c.execute(
        "SELECT COUNT(*) FROM tictactoe_games WHERE (player1_id = ? OR player2_id = ?) AND status = 'draw'",
        (user_id, user_id)
    ).fetchone()[0]
    
    conn.close()
    
    losses = total - wins - draws
    win_rate = (wins / total * 100) if total > 0 else 0
    
    embed = discord.Embed(
        title="📊 Tic-Tac-Toe Stats",
        color=discord.Color.blue()
    )
    embed.add_field(name="Games Played", value=str(total), inline=True)
    embed.add_field(name="Wins", value=f"🏆 {wins}", inline=True)
    embed.add_field(name="Losses", value=f"💀 {losses}", inline=True)
    embed.add_field(name="Draws", value=f"🤝 {draws}", inline=True)
    embed.add_field(name="Win Rate", value=f"📈 {win_rate:.1f}%", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.hybrid_command(name="decode", description="Decode message (works for all levels)")
async def decode_cmd(ctx, *, encoded_message: str):
    """Universal decoder - works for all encoding levels (0, 1, 2, 3)"""
    try:
        # Strip backticks if present
        encoded_clean = encoded_message.strip().strip('`')
        decoded = decode_text_universal(encoded_clean)
        
        if not decoded or decoded.startswith("Invalid") or decoded.startswith("Decoding error"):
            await ctx.send(f"❌ **Decoding failed:** {decoded}", ephemeral=True)
            return
        
        # Check for banned words if not bypass user
        if not is_bypass_user(ctx.author.id):
            banned = db_query("SELECT word FROM banned_words", fetch=True)
            decoded_low = decoded.lower()
            if banned and any(bw[0].lower() in decoded_low for bw in banned):
                # Issue strike
                res = db_query("SELECT strikes FROM users WHERE user_id = ?", (str(ctx.author.id),), fetch=True)
                current = res[0][0] if res else 0
                new_strikes = current + 1
                is_banned = 1 if new_strikes >= 3 else 0
                db_query("INSERT OR REPLACE INTO users (user_id, strikes, blacklisted) VALUES (?, ?, ?)", 
                        (str(ctx.author.id), new_strikes, is_banned))
                await ctx.send(f"⚠️ **Decoded message contains banned words**\n⚡ Strike issued: {new_strikes}/3", ephemeral=True)
                return
        
        # Detect level
        parts = encoded_clean.split(".")
        if len(parts) == 2:
            level = "Level 0"
            level_color = discord.Color.green()
        elif len(parts) == 3:
            level = "Level 1"
            level_color = discord.Color.blue()
        elif len(parts) == 4:
            key = parts[0]
            if len(key) == 6:
                level = "Level 2"
                level_color = discord.Color.purple()
            else:
                level = "Level 3"
                level_color = discord.Color.gold()
        else:
            level = "Unknown"
            level_color = discord.Color.greyple()
        
        embed = discord.Embed(title="🔓 Message Decoded", color=level_color)
        decoded_display = (decoded[:1000] + "...") if len(decoded) > 1000 else decoded
        embed.add_field(name="📝 Decoded Message", value=f"`{decoded_display}`", inline=False)
        embed.add_field(name="ℹ️ Detected Level", value=level, inline=True)
        embed.add_field(name="📏 Original Length", value=f"{len(decoded)} chars", inline=True)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ **Decoding failed:** `{str(e)}`", ephemeral=True)

# ==================== TEST CODE ====================
if __name__ == "__main__":
    print("=== ENCODING LEVEL TESTS ===\n")
    
    test_text = "Hello World!"
    
    print(f"Original text: {test_text} ({len(test_text)} chars)\n")
    
    # Test Level 0
    print("--- LEVEL 0 (Simple) ---")
    for i in range(3):
        enc = encode_text_lvl0(test_text)
        dec = decode_text_universal(enc)
        print(f"{i+1}. Encoded ({len(enc)} chars): {enc}")
        print(f"   Decoded: {dec} - Match: {dec == test_text}\n")
    
    # Test Level 1
    print("--- LEVEL 1 (Standard, 5+ chars) ---")
    for i in range(3):
        enc = encode_text_lvl1(test_text)
        dec = decode_text_universal(enc)
        print(f"{i+1}. Encoded ({len(enc)} chars): {enc}")
        print(f"   Decoded: {dec} - Match: {dec == test_text}\n")
    
    # Test Level 2
    print("--- LEVEL 2 (Enhanced, 7+ chars) ---")
    for i in range(3):
        enc = encode_text_lvl2(test_text)
        dec = decode_text_universal(enc)
        print(f"{i+1}. Encoded ({len(enc)} chars): {enc}")
        print(f"   Decoded: {dec} - Match: {dec == test_text}\n")
    
    # Test Level 3
    print("--- LEVEL 3 (Maximum, 12+ chars) ---")
    for i in range(3):
        enc = encode_text_lvl3(test_text)
        dec = decode_text_universal(enc)
        print(f"{i+1}. Encoded ({len(enc)} chars): {enc}")
        print(f"   Decoded: {dec} - Match: {dec == test_text}\n")
    
    # Test short text
    print("--- SHORT TEXT TEST ('ab') ---")
    short = "ab"
    print(f"Original: {short}\n")
    print(f"Level 0: {encode_text_lvl0(short)} ({len(encode_text_lvl0(short))} chars)")
    print(f"Level 1: {encode_text_lvl1(short)} ({len(encode_text_lvl1(short))} chars)")
    print(f"Level 2: {encode_text_lvl2(short)} ({len(encode_text_lvl2(short))} chars)")
    print(f"Level 3: {encode_text_lvl3(short)} ({len(encode_text_lvl3(short))} chars)")


        
async def add_smart_reaction(message, user_message: str, bot_response: str):
    """Let AI decide if and which emoji reactions to add"""
    if random.random() > bot.reaction_chance:
        return  # Skip adding reactions 90% of the time
    
    try:
        # Ask AI to analyze the conversation and suggest emojis
        reaction_prompt = f"""Analyze this Discord conversation and suggest 1-2 emoji reactions that would be appropriate and natural.

User message: "{user_message[:200]}"
Bot response: "{bot_response[:200]}"

Consider the message tone, content, and context. Suggest Discord-compatible emoji reactions.
Respond with ONLY emoji characters separated by spaces, or "none" if no reaction is appropriate.
Examples of good responses: "👍", "😂 👍", "🎉", "❤️", "🤔", "none"

Your response:"""

        # Gemini API call for reaction suggestions
        suggested_reactions = await bot.api_manager.generate(
            messages=[{"role": "user", "content": reaction_prompt}],
            max_tokens=50,
            temp=0.7
        )
        
        suggested_reactions = suggested_reactions.strip()
        
        if suggested_reactions.lower() == "none":
            return
        
        # Extract emojis from response
        emojis = [e.strip() for e in suggested_reactions.split() if e.strip()]
        
        # Add reactions (max 2)
        for emoji in emojis[:2]:
            try:
                await message.add_reaction(emoji)
                await asyncio.sleep(0.3)  # Small delay between reactions
            except discord.HTTPException:
                # Invalid emoji, skip it
                continue
                
    except Exception as e:
        # Silently fail if reaction system has issues
        print(f"⚠️ Reaction system error: {e}")
        pass
        
@bot.event
async def on_message(message):
    if message.author.bot:
        print("❌ SKIP: Message is from a bot")
        return
    user_check = db_query("SELECT blacklisted FROM users WHERE user_id = ?", (str(message.author.id),), fetch=True)
    if user_check and user_check[0][0] == 1:
        print(f"❌ SKIP: User {message.author.id} is blacklisted")
        return

    content_low = message.content.lower()
    was_deleted = False
    original_message = message  # Store reference before potential deletion

    # Word filter check (with bypass)
    if message.guild:
        # Server-specific filter
        if has_server_banned_words(message.guild.id):
            # Use only server-specific banned words, ignore global
            if not is_server_censor_bypass(message.guild.id, message.author.id):
                server_banned = get_server_banned_words(message.guild.id)
                if any(bw in content_low for bw in server_banned):
                    try:
                        await message.delete()
                        was_deleted = True
                        print(f"🔇 DELETED: Message from {message.author.name} contained server-banned word")
                        warning = await message.channel.send(
                            f"⚠️ {message.author.mention}, your message contained a banned word (server filter) and has been removed.\n\n**Warning:** Repeated violations may result in action by server moderators.",
                            delete_after=10
                        )
                    except Exception as e:
                        print(f"❌ ERROR deleting message: {e}")
                        pass
        else:
            # Use global banned words (existing behavior)
            if not is_bypass_user(message.author.id):
                banned = db_query("SELECT word FROM banned_words", fetch=True)
                if any(bw[0] in content_low for bw in banned):
                    try:
                        await message.delete()
                        was_deleted = True
                        print(f"🔇 DELETED: Message from {message.author.name} contained banned word")
                        warning = await message.channel.send(
                            f"⚠️ {message.author.mention}, your message contained a banned word and has been removed.\n\n**Warning:** Repeated violations may result in strikes or blacklisting.",
                            delete_after=10
                        )
                    except Exception as e:
                        print(f"❌ ERROR deleting message: {e}")
                        pass
    else:
        # DM - use global filter only
        if not is_bypass_user(message.author.id):
            banned = db_query("SELECT word FROM banned_words", fetch=True)
            if any(bw[0] in content_low for bw in banned):
                try:
                    await message.delete()
                    was_deleted = True
                    print(f"🔇 DELETED: Message from {message.author.name} contained banned word")
                    warning = await message.channel.send(
                        f"⚠️ {message.author.mention}, your message contained a banned word and has been removed.\n\n**Warning:** Repeated violations may result in strikes or blacklisting.",
                        delete_after=10
                    )
                except Exception as e:
                    print(f"❌ ERROR deleting message: {e}")
                    pass

    await bot.process_commands(message)
    ctx = await bot.get_context(message)
    if ctx.valid:
        return

    mode_check = db_query("SELECT mode FROM settings WHERE id = ?", (str(message.channel.id),), fetch=True)
    mode = mode_check[0][0] if mode_check else "stop"

    # Check if server has configured updates channel (required)
    if message.guild and not has_updates_channel(message.guild.id):
        # Only respond to setup command
        if not message.content.lower().startswith(tuple(['/setupupdates', '!setupupdates'])):
            # Silently ignore - server needs to setup updates channel first
            return

    should_respond = False
    bot_trigger_name = BOT_NAME.lower()
    if mode == "start":
        should_respond = True
    elif bot.user.mentioned_in(message) or (message.reference and message.reference.resolved and message.reference.resolved.author == bot.user):
        should_respond = True
    elif bot_trigger_name in content_low:
        should_respond = True
    elif not message.guild:
        should_respond = True

    if not should_respond:
        return

    # ====== EXISTING COOLDOWN CHECK (1.0s global) ======
    current_time = time.time()
    time_since_last_response = current_time - bot.last_response_time
    
    if time_since_last_response < 1.0:
        # Cooldown active - remain silent
        print(f"⏱️ COOLDOWN: Ignoring message from {message.author.name} (last response {time_since_last_response:.2f}s ago)")
        return
    # ====== END EXISTING COOLDOWN CHECK ======

    # ====== NEW COOLDOWN CHECK (1s per user & 1s per channel) ======
    user_id = str(message.author.id)
    channel_id = str(message.channel.id)
    
    # Check if this specific user is on cooldown (1 second per user)
    can_user_send, user_remaining = check_user_cooldown(channel_id, user_id, cooldown_seconds=1.0)
    if not can_user_send:
        # User sent message too quickly, silently ignore
        print(f"⏱️ USER COOLDOWN: Ignoring message from {message.author.name} ({user_remaining:.2f}s remaining)")
        return
    
    # Check if the channel has global cooldown (any user just sent)
    can_channel_send, channel_remaining, last_user = check_channel_cooldown(channel_id, cooldown_seconds=1.0)
    if not can_channel_send:
        # Someone else just sent a message, silently ignore
        print(f"⏱️ CHANNEL COOLDOWN: Ignoring message (last user: {last_user}, {channel_remaining:.2f}s remaining)")
        return
    # ====== END NEW COOLDOWN CHECK ======

    
    lang = get_channel_language(message.channel.id)

    tid = f"{message.channel.id}-{message.author.id}"
    if tid not in bot.memory:
        bot.memory[tid] = deque(maxlen=6)

    async with message.channel.typing():
        server_name = message.guild.name if message.guild else "DM"
        roles = ", ".join([r.name for r in message.author.roles[1:]]) if message.guild else "None"

        user_content, was_truncated = truncate_message(message.content)
        
        # Get comprehensive bot statistics
        total_users = sum(g.member_count for g in bot.guilds)
        total_banned_words = len(db_query("SELECT word FROM banned_words", fetch=True) or [])
        total_blacklisted = len(db_query("SELECT user_id FROM users WHERE blacklisted = 1", fetch=True) or [])
        total_admins = len(db_query("SELECT user_id FROM bot_admins", fetch=True) or [])
        total_reports = len(db_query("SELECT report_id FROM reports", fetch=True) or [])
        total_interactions = db_query("SELECT COUNT(*) FROM interaction_logs", fetch=True)[0][0]
        total_blacklisted_guilds = len(db_query("SELECT guild_id FROM blacklisted_guilds", fetch=True) or [])
        
        # Get user's personal stats
        user_strikes = db_query("SELECT strikes FROM users WHERE user_id = ?", (str(message.author.id),), fetch=True)
        user_strike_count = user_strikes[0][0] if user_strikes else 0
        user_is_blacklisted = db_query("SELECT blacklisted FROM users WHERE user_id = ?", (str(message.author.id),), fetch=True)
        user_blacklist_status = bool(user_is_blacklisted[0][0]) if user_is_blacklisted else False
        user_has_bypass = is_bypass_user(message.author.id)
        user_is_admin = is_bot_admin(message.author.id)
        
        # Calculate bot uptime (approximate based on current session)
        # Note: This resets on bot restart, but gives session uptime
        bot_latency = round(bot.latency * 1000, 2)
        
        # Get current channel mode
        channel_mode = mode
        
        # Build comprehensive system prompt
        system = f"""You are {BOT_NAME}, a Discord AI bot. Respond naturally and concisely.

CURRENT CONTEXT:
• User: {message.author.name} (ID: {message.author.id})
• Server: {server_name}
• Channel: #{message.channel.name if hasattr(message.channel, 'name') else 'DM'}
• Language: {lang}

USER STATUS:
• Strikes: {user_strike_count}/3
• Bot Admin: {"Yes" if user_is_admin else "No"}
• Roles: {roles}

CRITICAL RULES:
1. MATCH THE USER'S TONE AND LENGTH
   - If they send 5 words, respond with ~5-15 words
   - If they're casual, be casual
   - If they're formal, be formal
   - Don't always bring up previous topic if not needed.
   - Don't create big paragraphs, try to respond shortly.
   - IMPORTANT: Only reference past conversations when directly relevant to the current query. Do not bring up unrelated past topics. Stay focused on what the user is currently asking about.
   
2. KEEP IT SHORT (target 50-150 characters for normal messages)
   - Only go longer if the question genuinely needs it
   - Use abbreviations when natural
   - Try to keep the responses shortest and use abbreviations if needed.
   - If the user is not going professional, don't use any caps in the sentence.
3. RESPOND ONLY IN {lang}
   
4. BE NATURAL
   - Don't list features unless asked
   - Don't mention creator unless asked
   - Match their vibe (emojis, slang, etc.)
   - IMPORTANT: Only reference past conversations when directly relevant to the current query. Do not bring up unrelated past topics. Stay focused on what the user is currently asking about.
EXAMPLES:
User: "hey"
You: "hi, wsp 👋"

User: "what can you do"
You: "i can chat, remember context, help with moderation stuff. what do you need?"

User: "who made you"
You: "{OWNER_INFO['name']}!"

User: "tell me about quantum physics"
You: [longer response explaining the topic]

Remember: SHORT responses are your superpower. Match their energy!
IMPORTANT: Only reference past conversations when directly relevant to the current query. Do not bring up unrelated past topics. Stay focused on what the user is currently asking about."""



        # Let AI decide if chat history is relevant
        history_context = ""
        if len(bot.memory[tid]) > 0:
            # Format the history for AI to review
            history_items = []
            for msg in bot.memory[tid]:
                role = msg['role']
                content = msg['content'][:100]  # Truncate for brevity
                history_items.append(f"{role}: {content}")
            history_context = "\n".join(history_items)
            
            # Add history decision prompt to system message
            system_with_history = system + f"""

CONVERSATION HISTORY (Last 6 messages):
{history_context}

INSTRUCTIONS: Review the conversation history above. ONLY reference or use this history if the user's current message is directly related to a previous topic. If the user is asking something new or unrelated, completely ignore the history and respond fresh. Do not mention past topics unless the user explicitly refers to them."""
            
            msgs = [{"role": "system", "content": system_with_history}] + [{"role": "user", "content": user_content}]
        else:
            # No history - fresh conversation
            msgs = [{"role": "system", "content": system}] + [{"role": "user", "content": user_content}]


        try:
            print(f"🤖 Generating AI response for {message.author.name}...")
            
            # Use API manager with auto-rotation
            reply = await bot.api_manager.generate(
                messages=msgs,
                max_tokens=650,
                temp=0.7
            )
            
            print(f"✅ Got AI response ({len(reply)} chars)")
            
            if was_truncated:
                reply = "⚠️ *Your message was very long and had to be shortened.*\n\n" + reply
            
            # Send response - use channel.send if message was deleted
            if was_deleted:
                print("📤 Sending response to channel (original message deleted)")
                await message.channel.send(f"{message.author.mention} {reply}")
            else:
                print("📤 Sending response as reply")
                await split_and_send(message, reply)
            
            # Update last response time after successful send
            bot.last_response_time = time.time()
            
            # ====== UPDATE USER COOLDOWN AFTER RESPONSE ======
            update_user_cooldown(channel_id, user_id)
            # ====== END UPDATE COOLDOWN ======

            # Add smart AI reactions (10% chance) - only if message wasn't deleted
            if not was_deleted:
                await add_smart_reaction(message, user_content, reply)

            bot.memory[tid].append({"role": "user", "content": user_content})
            bot.memory[tid].append({"role": "assistant", "content": reply})

            db_query("INSERT INTO interaction_logs VALUES (?, ?, ?, ?, ?, ?, ?)", (time.time(), str(message.guild.id) if message.guild else "DM", str(message.channel.id), message.author.name, str(message.author.id), message.content[:1000], reply[:1000]))
            print(f"✅ Response sent successfully to {message.author.name}")
            if message.guild:
                increment_ai_chat_count(message.author.id, message.guild.id)
            # Patreon promotion check
            should_promote = patreon_promoter.track_message(str(message.channel.id))
            if should_promote:
                try:
                    embed, view = patreon_promoter.create_promotion_message()
                    await message.channel.send(embed=embed, view=view)
                    print(f"💎 Sent Patreon promotion in {message.channel.name if message.guild else 'DM'}")
                except Exception as e:
                    print(f"⚠️ Failed to send Patreon promotion: {e}")
            
        
        except discord.errors.HTTPException as e:
            print(f"❌ HTTPException ERROR:")
            print(f"   Status: {e.status}")
            print(f"   Code: {e.code}")
            print(f"   Message: {e.text}")
            print(f"   Response length: {len(reply)} chars")
            print(f"   First 100 chars: {reply[:100]}")
            
            # Try to send error with more details
            error_msg = f"❌ **Failed to send response**\n"
            
            if e.status == 403:
                error_msg += "I don't have permission to send messages here."
            elif e.status == 404:
                error_msg += "The message or channel was deleted."
            elif e.code == 50035:
                error_msg += f"Response was too long ({len(reply)} chars). Please ask a shorter question."
            elif e.status == 429:
                error_msg += "I'm being rate limited. Please wait a moment."
            else:
                error_msg += f"Discord API error: {e.text}\n{message.author.mention}, please try again."
            
            try:
                await message.channel.send(error_msg)
            except Exception as send_error:
                print(f"❌ Error sending error message: {send_error}")
        except Exception as e:
            print(f"❌ ERROR in AI response generation:")
            print(f"   Error type: {type(e).__name__}")
            print(f"   Error message: {e}")
            error_msg = f"❌ **An error occurred**\n```\n{str(e)}\n```\nPlease try again or [report it in the support server](<{os.getenv('SUPPORT_SERVER_INVITE', 'https://discord.com/invite/XMvPq7W5N4')}>) if the issue persists."
            try:
                await message.channel.send(error_msg)
            except Exception as send_error:
                print(f"❌ Error sending error message: {send_error}")



@bot.event
async def on_reaction_add(reaction, user):
    """
    Detect reactions added to messages within the past 14 days
    Generate AI response based on the reaction context
    Now handles ALL reactions on a message and uses server emojis
    Mentions the reactor at the start of the response
    """
    # Ignore bot's own reactions
    if user.bot:
        print(f"❌ REACTION SKIP: Reaction from bot {user.name}")
        return
    
    # Check if user is blacklisted
    user_check = db_query("SELECT blacklisted FROM users WHERE user_id = ?", (str(user.id),), fetch=True)
    if user_check and user_check[0][0] == 1:
        print(f"❌ REACTION SKIP: User {user.id} is blacklisted")
        return
    
    # Check if message is within 14 days
    message = reaction.message
    message_age = datetime.datetime.now(datetime.timezone.utc) - message.created_at
    if message_age.days > 14:
        print(f"❌ REACTION SKIP: Message too old ({message_age.days} days)")
        return
    
    # Check if server has configured updates channel (for guild messages)
    if message.guild and not has_updates_channel(message.guild.id):
        print(f"❌ REACTION SKIP: Guild {message.guild.id} has no updates channel configured")
        return
    
    # Get channel mode
    mode_check = db_query("SELECT mode FROM settings WHERE id = ?", (str(message.channel.id),), fetch=True)
    mode = mode_check[0][0] if mode_check else "stop"
    
    # Check if reactions are enabled for this channel
    try:
        reactions_setting = db_query(
            "SELECT reactions_enabled FROM settings WHERE id = ?",
            (str(message.channel.id),),
            fetch=True
        )
        reactions_enabled = reactions_setting[0][0] if reactions_setting else 1
    except:
        # Column might not exist yet
        reactions_enabled = 1
    
    if not reactions_enabled:
        print(f"❌ REACTION SKIP: Reactions disabled in channel {message.channel.id}")
        return
    
    # Only respond in START mode or if it's the bot's message that got reacted to
    if mode != "start" and message.author != bot.user:
        print(f"❌ REACTION SKIP: Channel in STOP mode and message not from bot")
        return
    
    # Don't respond to reactions on very old messages (avoid spam on reaction spam)
    if message_age.days > 7:
        # Still within 14 days but older than 7 - only respond to bot's messages
        if message.author != bot.user:
            print(f"⚠️ REACTION SKIP: Message is {message_age.days} days old (>7 days, not bot message)")
            return
    
    # Check if we already responded to this exact reaction from this user
    existing = db_query(
        "SELECT message_id FROM reaction_responses WHERE message_id = ? AND reactor_id = ? AND reaction_emoji = ?",
        (str(message.id), str(user.id), str(reaction.emoji)),
        fetch=True
    )
    if existing:
        print(f"❌ REACTION SKIP: Already responded to this reaction")
        return
    
    # Rate limiting - prevent spam (max 1 reaction response per 5 seconds per channel)
    channel_key = f"reaction_cooldown_{message.channel.id}"
    if not hasattr(bot, 'reaction_cooldowns'):
        bot.reaction_cooldowns = {}
    
    current_time = time.time()
    if channel_key in bot.reaction_cooldowns:
        time_since_last = current_time - bot.reaction_cooldowns[channel_key]
        if time_since_last < 5:
            print(f"⏱️ REACTION SKIP: Cooldown active ({5 - time_since_last:.1f}s remaining)")
            return
    
    bot.reaction_cooldowns[channel_key] = current_time
    
    # Get language setting
    lang = get_channel_language(message.channel.id)
    
    # Prepare context for AI
    try:
        print(f"🎭 REACTION DETECTED: {user.name} reacted {reaction.emoji} to message {message.id}")
        
        async with message.channel.typing():
            # Get message context
            original_author = message.author
            original_content = message.content if message.content else "[No text content]"
            
            # Handle attachments
            attachment_info = ""
            if message.attachments:
                attachment_types = [att.content_type.split('/')[0] if att.content_type else 'file' for att in message.attachments]
                attachment_info = f"\n• Attachments: {', '.join(attachment_types)}"
            
            # Handle embeds
            embed_info = ""
            if message.embeds:
                embed_info = f"\n• Contains {len(message.embeds)} embed(s)"
            
            # Get ALL reactions on the message
            all_reactions = []
            total_reaction_count = 0
            for msg_reaction in message.reactions:
                # Determine emoji representation
                if isinstance(msg_reaction.emoji, str):
                    # Unicode emoji
                    emoji_repr = msg_reaction.emoji
                    emoji_name = msg_reaction.emoji
                else:
                    # Custom Discord emoji
                    emoji_repr = f"<:{msg_reaction.emoji.name}:{msg_reaction.emoji.id}>"
                    emoji_name = msg_reaction.emoji.name
                
                all_reactions.append({
                    'emoji': emoji_repr,
                    'name': emoji_name,
                    'count': msg_reaction.count,
                    'is_current': str(msg_reaction.emoji) == str(reaction.emoji)
                })
                total_reaction_count += msg_reaction.count
            
            # Sort reactions by count (most popular first)
            all_reactions.sort(key=lambda x: x['count'], reverse=True)
            
            # Format all reactions for context
            reactions_summary = "\n".join([
                f"  {'→ ' if r['is_current'] else '  '}{r['emoji']} ({r['name']}) - {r['count']} reaction(s){'  ← THIS ONE WAS JUST ADDED' if r['is_current'] else ''}"
                for r in all_reactions
            ])
            
            # Determine current reaction details
            current_reaction_emoji = str(reaction.emoji)
            current_reaction_count = reaction.count
            
            # Handle custom emoji details
            emoji_type = "unicode"
            emoji_name = current_reaction_emoji
            if isinstance(reaction.emoji, discord.PartialEmoji) or isinstance(reaction.emoji, discord.Emoji):
                emoji_type = "custom_server"
                emoji_name = reaction.emoji.name
                if hasattr(reaction.emoji, 'id'):
                    current_reaction_emoji = f"<:{reaction.emoji.name}:{reaction.emoji.id}>"
            
            # Get user's strike status for context
            user_strikes = db_query("SELECT strikes FROM users WHERE user_id = ?", (str(user.id),), fetch=True)
            user_strike_count = user_strikes[0][0] if user_strikes else 0
            
            # Check if user is bot admin
            user_is_admin = is_bot_admin(user.id)
            
            # Build comprehensive AI prompt
            system_prompt = f"""You are {BOT_NAME}, an AI Discord bot with advanced reaction detection capabilities.

═══════════════════════════════════════════════════════════════
🎭 REACTION EVENT CONTEXT
═══════════════════════════════════════════════════════════════
Reactor Information:
├─ Name: {user.name}
├─ Display Name: {user.display_name}
├─ User ID: {user.id}
├─ Strikes: {user_strike_count}/3
├─ Bot Admin: {"Yes ✨" if user_is_admin else "No"}
└─ Account Age: {(datetime.datetime.now(datetime.timezone.utc) - user.created_at).days} days

Original Message:
├─ Author: {original_author.name} (ID: {original_author.id})
├─ Content: "{original_content[:500]}"
├─ Message Age: {message_age.days} days, {message_age.seconds // 3600} hours{attachment_info}{embed_info}
├─ Channel: #{message.channel.name if hasattr(message.channel, 'name') else 'DM'}
└─ Server: {message.guild.name if message.guild else 'DM'}

Current Reaction (Just Added):
├─ Emoji: {current_reaction_emoji}
├─ Emoji Name: {emoji_name}
├─ Emoji Type: {emoji_type}
├─ Count of This Reaction: {current_reaction_count} (including this one)
├─ Is First of This Type: {"Yes" if current_reaction_count == 1 else "No"}
└─ Same Author: {"Yes (self-reaction)" if user.id == original_author.id else "No"}

ALL Reactions on This Message:
├─ Total Different Reactions: {len(all_reactions)}
├─ Total Reaction Count: {total_reaction_count}
└─ Breakdown:
{reactions_summary}

Bot Context:
├─ Total Servers: {len(bot.guilds)}
├─ Channel Mode: {mode.upper()}
└─ Language Setting: {lang}

═══════════════════════════════════════════════════════════════
⚠️ CRITICAL LANGUAGE REQUIREMENT
═══════════════════════════════════════════════════════════════
You MUST respond ONLY in {lang} language. This is non-negotiable.

═══════════════════════════════════════════════════════════════
🎯 YOUR TASK - AI RESPONSE GENERATION
═══════════════════════════════════════════════════════════════
Generate a natural, conversational, AI-powered response acknowledging the reaction.

CRITICAL FORMAT INFO:
Your response will be automatically formatted as: "@User {current_reaction_emoji} [YOUR RESPONSE]"

DO NOT INCLUDE:
❌ The user's name or mention (already added)
❌ The emoji (already displayed)
❌ Any @ symbols or user references

RESPONSE REQUIREMENTS:
✅ Minimum 10 words, maximum 50 words
✅ Complete sentences only
✅ Natural, conversational AI tone
✅ Talk directly TO the reactor (use "you", "your")
✅ Acknowledge the reaction contextually
✅ Be creative, witty, and engaging
✅ Match the emotional tone of the reaction

RESPONSE STYLE GUIDE BY REACTION TYPE:

1. POSITIVE (👍, ❤️, 🔥, ✅, 🎉, ⭐, 💯):
   → Be warm, appreciative, enthusiastic
   Examples:
   • "Thanks for the support! Really appreciate the positive energy."
   • "Love seeing this reaction! Your feedback means a lot."
   • "Glad this resonated with you! Thanks for engaging."

2. LOVE/AFFECTION (💕, 💖, 😍, 🥰, 💝):
   → Be warm, grateful, heartfelt
   Examples:
   • "Aww, thanks for the love! Your support is amazing."
   • "This made my day! Appreciate the positive vibes you bring."
   • "Love getting reactions like this! Thanks for being awesome."

3. FUNNY (😂, 🤣, 💀, 😆, 🤪):
   → Be playful, humorous, light
   Examples:
   • "Haha, mission accomplished! Love making people laugh."
   • "Your laughter is the best feedback! Glad this landed well."
   • "If I got you cracking up, then I'm doing something right!"

4. CONFUSED (❓, 🤔, 😕, 🤷, 😵):
   → Be helpful, clarifying, friendly
   Examples:
   • "Good question! Feel free to ask if you need more clarity."
   • "I see the confusion there! Happy to explain further if needed."
   • "Fair reaction - this one definitely deserves some thought!"

5. NEGATIVE (👎, ❌, 😢, 😡, 💔):
   → Be understanding, empathetic, constructive
   Examples:
   • "I understand this didn't quite hit the mark. Feedback noted!"
   • "Fair reaction! Not everything works for everyone, and that's okay."
   • "Thanks for the honest feedback! I appreciate the input."

6. CELEBRATORY (🎊, 🥳, 🍾, 🎈):
   → Be enthusiastic, energetic, celebratory
   Examples:
   • "Let's celebrate! Love your enthusiastic energy here!"
   • "Party time! Your excitement is totally infectious!"
   • "Yes! Thanks for joining in the celebration with me!"

7. THINKING (🧐, 💭, 🎯, 💡):
   → Be thoughtful, engaging, intellectual
   Examples:
   • "Love when people really engage deeply like this!"
   • "Good point to ponder! This definitely deserves reflection."
   • "I see the wheels turning! What are your thoughts?"

8. CUSTOM SERVER EMOJI:
   → Reference the emoji name creatively
   Examples:
   • "Perfect emoji choice - that captures it so well!"
   • "Love the custom emoji reaction! Very fitting for this."

CONTEXTUAL BONUSES (add these when relevant):

• First reaction overall:
  "First reaction! Love being the icebreaker here."

• Multiple different reactions:
  "Interesting mix of reactions we're seeing here!"

• Self-reaction (reactor is message author):
  "Self-appreciation is important! I respect the confidence."

• Old message (3+ days):
  "Reacting to this {message_age.days}-day-old message? I appreciate the dedication!"

• High reaction count:
  "You're number {current_reaction_count} with this reaction - clearly resonating!"

• Reacting to bot's message:
  "Thanks for the feedback on my response! Glad it landed well."

• Mixed reactions (thumbs up AND down):
  "We've got both camps here - love the honest diversity of opinions!"

═══════════════════════════════════════════════════════════════
STRICT RULES - MUST FOLLOW
═══════════════════════════════════════════════════════════════
✅ 10-50 words (enforced)
✅ {lang} language only
✅ Conversational, direct tone (talk TO them, not ABOUT them)
✅ No user mentions/names (already added)
✅ No emoji repetition (already displayed)
✅ Complete, natural sentences
✅ Be creative and AI-like
✅ Match reaction sentiment

EXAMPLES OF PERFECT RESPONSES:

For 👍:
✓ "Thanks for the thumbs up! Your support really means a lot."
✓ "Appreciate the approval! Glad this hit the mark for you."

For ❤️:
✓ "Aww, love the heart reaction! Thanks for the positive energy."
✓ "Your support is amazing! This made my day, thank you."

For 😂:
✓ "Haha, glad I made you laugh! That's exactly what I was going for."
✓ "Your laughter makes this all worth it! Mission accomplished."

For 🤔:
✓ "Good question! Feel free to ask if you want more details."
✓ "I see the thinking happening! This deserves some contemplation."

For self-reaction:
✓ "Self-love is important! I respect owning your own message."

For old message:
✓ "Reacting to week-old content? I appreciate the thorough reading!"

For mixed reactions:
✓ "We've got diverse opinions here - that's what makes discussions interesting!"

GENERATE YOUR RESPONSE NOW:"""

            messages = [{"role": "user", "content": system_prompt}]
            
            print(f"🤖 Generating AI reaction response...")
            
            # Use API manager with auto-rotation
            ai_response = await bot.api_manager.generate(
                messages=messages,
                max_tokens=200,
                temp=0.9
            )
            
            ai_response = ai_response.strip()

            
            # Clean up any accidental mentions or emoji repetitions
            ai_response = ai_response.replace(f"@{user.name}", "").replace(f"@{user.display_name}", "")
            ai_response = ai_response.replace(current_reaction_emoji, "").strip()
            
            # Remove any leading/trailing quotes if AI added them
            ai_response = ai_response.strip('"').strip("'")
            
            # Enforce minimum length (at least 10 words)
            word_count = len(ai_response.split())
            if word_count < 8:
                # Response too short, use intelligent fallback based on reaction type
                emoji_str = str(reaction.emoji)
                
                # Determine fallback based on emoji
                if emoji_str in ['👍', '✅', '💯', '🔥', '⭐']:
                    fallback_responses = [
                        "Thanks for the positive feedback! Really appreciate your support here.",
                        "Love the positive energy! Your reaction made my day.",
                        "Appreciate you taking the time to react! Means a lot.",
                    ]
                elif emoji_str in ['❤️', '💕', '💖', '😍', '🥰']:
                    fallback_responses = [
                        "Aww, thanks for the love! Your support is amazing.",
                        "This made me smile! Really appreciate the positive vibes.",
                        "Love getting reactions like this! Thanks for being awesome.",
                    ]
                elif emoji_str in ['😂', '🤣', '💀', '😆']:
                    fallback_responses = [
                        "Haha, glad I could make you laugh! Mission accomplished.",
                        "Your laughter is the best feedback! Love the energy.",
                        "If I got you laughing, then I'm doing something right!",
                    ]
                elif emoji_str in ['🤔', '❓', '😕']:
                    fallback_responses = [
                        "Good question! Feel free to ask if you need clarification.",
                        "I see the confusion there! Happy to explain more if needed.",
                        "That's fair! This one definitely deserves some thought.",
                    ]
                elif emoji_str in ['👎', '❌', '😢']:
                    fallback_responses = [
                        "I understand this didn't quite land well. Feedback noted!",
                        "Fair reaction! Not everything works for everyone.",
                        "Thanks for the honest feedback! I appreciate it.",
                    ]
                else:
                    fallback_responses = [
                        "Thanks for the reaction! Always appreciate the engagement.",
                        "Love seeing people interact! Your reaction is noted.",
                        "Appreciate you taking the time to react to this!",
                    ]
                
                ai_response = random.choice(fallback_responses)
                print(f"⚠️ AI response too short ({word_count} words), using fallback: {ai_response}")
            
            # Enforce max length
            if len(ai_response) > 250:
                sentences = ai_response.split('. ')
                ai_response = '. '.join(sentences[:2])
                if not ai_response.endswith('.') and not ai_response.endswith('!') and not ai_response.endswith('?'):
                    ai_response += '.'
                print(f"⚠️ Truncated verbose response")
            
            word_count = len(ai_response.split())
            print(f"✅ Generated AI response ({word_count} words): {ai_response}")
            
            # Build the display emoji for the response
            display_emoji = current_reaction_emoji
            
            # Send response as a reply to the original message
            # Format: "@User emoji AI_response"
            response_msg = await message.reply(
                f"{user.mention} {display_emoji} {ai_response}",
                mention_author=False
            )
            
            # Log the reaction response
            db_query(
                "INSERT INTO reaction_responses VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (
                    str(message.id),
                    str(message.channel.id),
                    str(message.guild.id) if message.guild else "DM",
                    str(original_author.id),
                    str(user.id),
                    current_reaction_emoji,
                    ai_response
                )
            )
            
            # Also log as interaction
            all_reactions_str = ", ".join([f"{r['emoji']}×{r['count']}" for r in all_reactions])
            db_query(
                "INSERT INTO interaction_logs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    time.time(),
                    str(message.guild.id) if message.guild else "DM",
                    str(message.channel.id),
                    user.name,
                    str(user.id),
                    f"[REACTION: {current_reaction_emoji}] All reactions: [{all_reactions_str}] on message by {original_author.name}: {original_content[:100]}",
                    ai_response
                )
            )
            

            
            # Log admin action if admin reacted
            if user_is_admin or user.id == OWNER_ID:
                db_query(
                    "INSERT INTO admin_logs (log) VALUES (?)",
                    (f"Admin/Owner {user.name} ({user.id}) reacted {current_reaction_emoji} - Bot responded with AI reaction detection",)
                )
            
            print(f"✅ AI Reaction response sent successfully!")
            print(f"   Reactor: {user.name} ({user.id})")
            print(f"   Reaction: {current_reaction_emoji}")
            print(f"   Message from: {original_author.name} (ID: {message.id})")
            print(f"   Total reactions: {len(all_reactions)} types, {total_reaction_count} count")
            print(f"   Response preview: {ai_response[:80]}...")
            
    except discord.errors.Forbidden:
        print(f"❌ REACTION ERROR: Missing permissions to send message in channel {message.channel.id}")
    except discord.errors.HTTPException as e:
        print(f"❌ REACTION ERROR: HTTP error while sending response: {e}")
    except Exception as e:
        print(f"❌ REACTION ERROR: Unexpected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

@bot.command(name="edit", description="Owner: Edit a bot message. Supports text, JSON embeds, and buttons.")
@commands.is_owner()
async def edit_message(ctx, message_id: str, *, new_content: str):
    """
    Edit a message sent by the bot.
    Supports plain text, JSON embeds, and buttons.

    ─────────────────────────────────────────
    USAGE EXAMPLES:
    ─────────────────────────────────────────

    1) PLAIN TEXT:
       !edit 123456789 Hello this is the new text

    2) EMBED ONLY (raw embed JSON):
       !edit 123456789 {"description": "New description", "title": "New Title", "color": 3447003}

    3) EMBED + TEXT combined:
       !edit 123456789 {"text": "Above the embed", "embed": {"title": "Title", "description": "Desc", "color": 16711680}}

    4) EMBED + BUTTONS:
       !edit 123456789 {"embed": {"title": "Title", "description": "Desc"}, "buttons": [{"label": "Click Me", "style": 1}, {"label": "Google", "style": 5, "url": "https://google.com"}]}

    5) TEXT + BUTTONS (no embed):
       !edit 123456789 {"text": "Pick one!", "buttons": [{"label": "Option A", "style": 3}, {"label": "Option B", "style": 4}]}

    6) BUTTONS ONLY (keeps existing text/embed):
       !edit 123456789 {"buttons": [{"label": "Yes", "style": 3, "emoji": "✅"}, {"label": "No", "style": 4, "emoji": "❌"}]}

    7) CLEAR EMBED (remove embed, set plain text):
       !edit 123456789 {"text": "Just plain text now", "clear_embed": true}

    8) CLEAR BUTTONS (remove buttons, keep rest):
       !edit 123456789 {"text": "No buttons anymore", "clear_buttons": true}

    9) FULL EMBED with all fields:
       !edit 123456789 {"embed": {"title": "Big Title", "description": "Main description here", "color": 5814783, "url": "https://example.com", "timestamp": "2025-01-01T00:00:00", "footer": {"text": "Footer text", "icon_url": "https://example.com/icon.png"}, "image": {"url": "https://example.com/image.png"}, "thumbnail": {"url": "https://example.com/thumb.png"}, "author": {"name": "Author Name", "url": "https://example.com", "icon_url": "https://example.com/author.png"}, "fields": [{"name": "Field 1", "value": "Value 1", "inline": true}, {"name": "Field 2", "value": "Value 2", "inline": false}]}}

    10) BUTTON WITH CUSTOM EMOJI:
        !edit 123456789 {"text": "React!", "buttons": [{"label": "Fire", "style": 1, "emoji": "🔥"}, {"label": "Custom", "style": 2, "emoji": {"name": "customemoji", "id": 123456789}}]}

    ─────────────────────────────────────────
    BUTTON STYLES:
        1 = Primary (Blurple)
        2 = Secondary (Grey)
        3 = Success (Green)
        4 = Danger (Red)
        5 = Link (Grey, requires "url" field)
    ─────────────────────────────────────────
    """
    try:
        # Fetch message
        try:
            target_message = await ctx.channel.fetch_message(int(message_id))
        except discord.NotFound:
            await ctx.send("❌ **Message not found in this channel.**")
            return
        except ValueError:
            await ctx.send("❌ **Invalid message ID** - Must be a numeric ID.")
            return

        # Check if message is from the bot
        if target_message.author.id != bot.user.id:
            await ctx.send("❌ **Can only edit messages sent by the bot.**")
            return

        # Strip code block wrappers if present (```json ... ``` or ``` ... ```)
        cleaned = new_content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        # ───────────────────────────────────────────
        # Try to parse as JSON
        # ───────────────────────────────────────────
        is_json = False
        parsed = None
        try:
            parsed = json.loads(cleaned)
            is_json = True
        except (json.JSONDecodeError, ValueError):
            is_json = False

        # ───────────────────────────────────────────
        # CASE 1: Plain text (not JSON at all)
        # ───────────────────────────────────────────
        if not is_json:
            await target_message.edit(content=new_content, embed=None, view=None)
            await ctx.send(f"✅ **Message edited** (plain text)\nMessage ID: `{message_id}`")
            db_query("INSERT INTO admin_logs (log) VALUES (?)",
                     (f"Owner {ctx.author.name} edited message {message_id} — plain text in #{ctx.channel.name}",))
            return

        # ───────────────────────────────────────────
        # CASE 2: JSON detected — figure out what's inside
        # ───────────────────────────────────────────

        # Detect if it's a "raw embed" (has "description" or "title" at top level
        # and does NOT have "embed", "text", "buttons", "clear_embed", "clear_buttons" keys)
        # If so, wrap it so the rest of the logic is unified.
        control_keys = {"embed", "text", "buttons", "clear_embed", "clear_buttons"}
        raw_embed_keys = {"title", "description", "color", "url", "timestamp",
                          "footer", "image", "thumbnail", "author", "fields"}

        if isinstance(parsed, dict) and not any(k in parsed for k in control_keys):
            # Looks like a raw embed JSON — wrap it
            if any(k in parsed for k in raw_embed_keys):
                parsed = {"embed": parsed}
            else:
                # Unknown JSON structure, just dump it as text
                await target_message.edit(content=cleaned, embed=None, view=None)
                await ctx.send(f"✅ **Message edited** (JSON as text, no recognised structure)\nMessage ID: `{message_id}`")
                db_query("INSERT INTO admin_logs (log) VALUES (?)",
                         (f"Owner {ctx.author.name} edited message {message_id} — raw JSON text in #{ctx.channel.name}",))
                return

        # ───────────────────────────────────────────
        # Extract parts from the unified structure
        # ───────────────────────────────────────────
        text_content = parsed.get("text", None)          # str or None
        embed_data   = parsed.get("embed", None)         # dict or None
        buttons_data = parsed.get("buttons", None)       # list or None
        clear_embed  = parsed.get("clear_embed", False)  # bool
        clear_buttons = parsed.get("clear_buttons", False)  # bool

        # ───────────────────────────────────────────
        # Build Embed (if provided)
        # ───────────────────────────────────────────
        embed = None
        if embed_data and isinstance(embed_data, dict):
            # Guarantee "description" exists — discord.py requires it
            if "description" not in embed_data:
                embed_data["description"] = "\u200b"  # zero-width space

            # Handle color — accept int, hex string like "#ff0000" or "0xff0000", or name
            if "color" in embed_data:
                raw_color = embed_data["color"]
                if isinstance(raw_color, str):
                    raw_color = raw_color.strip().lower().lstrip("#")
                    try:
                        embed_data["color"] = int(raw_color, 16)
                    except ValueError:
                        embed_data["color"] = 0  # fallback black
                # else keep as int

            # Handle timestamp — accept ISO string or None
            if "timestamp" in embed_data:
                ts = embed_data["timestamp"]
                if isinstance(ts, str):
                    try:
                        embed_data["timestamp"] = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        del embed_data["timestamp"]  # invalid, just remove

            try:
                embed = discord.Embed.from_dict(embed_data)
            except Exception as e:
                await ctx.send(f"❌ **Failed to build embed:**\n```\n{e}\n```")
                return

        # If clear_embed is set, force embed to None
        if clear_embed:
            embed = None

        # ───────────────────────────────────────────
        # Build View / Buttons (if provided)
        # ───────────────────────────────────────────
        view = None
        if buttons_data and isinstance(buttons_data, list) and not clear_buttons:
            view = discord.ui.View()

            for idx, btn in enumerate(buttons_data):
                if not isinstance(btn, dict):
                    continue

                label    = btn.get("label", f"Button {idx + 1}")
                style_id = btn.get("style", 2)  # default Secondary
                url      = btn.get("url", None)
                custom_id_val = btn.get("custom_id", None)
                disabled = btn.get("disabled", False)
                emoji_raw = btn.get("emoji", None)

                # Clamp style to valid range 1-5
                if not isinstance(style_id, int) or style_id < 1 or style_id > 5:
                    style_id = 2

                # Map int → ButtonStyle
                style_map = {
                    1: discord.ButtonStyle.primary,
                    2: discord.ButtonStyle.secondary,
                    3: discord.ButtonStyle.success,
                    4: discord.ButtonStyle.danger,
                    5: discord.ButtonStyle.link,
                }
                style = style_map.get(style_id, discord.ButtonStyle.secondary)

                # Link buttons MUST have url; non-link buttons must NOT have url
                if style == discord.ButtonStyle.link:
                    if not url:
                        url = "https://discord.com"  # safe fallback
                    custom_id_val = None  # link buttons cannot have custom_id
                else:
                    url = None  # non-link buttons cannot have url
                    if not custom_id_val:
                        custom_id_val = f"edit_btn_{message_id}_{idx}"

                # Parse emoji
                emoji_obj = None
                if emoji_raw:
                    if isinstance(emoji_raw, str):
                        # Unicode emoji string
                        emoji_obj = emoji_raw
                    elif isinstance(emoji_raw, dict):
                        # Custom emoji dict {"name": "x", "id": 123}
                        try:
                            emoji_obj = discord.PartialEmoji(
                                name=emoji_raw.get("name", ""),
                                id=int(emoji_raw["id"]) if "id" in emoji_raw else None,
                                animated=emoji_raw.get("animated", False)
                            )
                        except (ValueError, TypeError):
                            emoji_obj = None  # invalid, skip emoji

                # Build the button
                try:
                    button = discord.ui.Button(
                        label=label[:80],  # discord label limit 80 chars
                        style=style,
                        url=url,
                        custom_id=custom_id_val,
                        disabled=disabled,
                        emoji=emoji_obj
                    )
                    view.add_item(button)
                except Exception as e:
                    print(f"⚠️ Skipped button {idx}: {e}")
                    continue

            # If view has zero items, set to None (discord rejects empty views)
            if len(view.children) == 0:
                view = None

        # If clear_buttons, force view to None
        if clear_buttons:
            view = discord.ui.View()  # empty view removes existing buttons

        # ───────────────────────────────────────────
        # Determine final text content for the message
        # ───────────────────────────────────────────
        # If only buttons were provided (no text, no embed, no clear flags)
        # then keep the EXISTING message content untouched — just swap the view.
        keep_existing_content = (
            text_content is None
            and embed_data is None
            and not clear_embed
            and buttons_data is not None
        )

        if keep_existing_content:
            # Edit only the view, preserve everything else
            await target_message.edit(view=view)
            await ctx.send(f"✅ **Buttons updated** (existing content kept)\nMessage ID: `{message_id}`\nButtons added: `{len(view.children) if view else 0}`")
            db_query("INSERT INTO admin_logs (log) VALUES (?)",
                     (f"Owner {ctx.author.name} edited message {message_id} — buttons only in #{ctx.channel.name}",))
            return

        # ───────────────────────────────────────────
        # Perform the actual edit
        # ───────────────────────────────────────────
        # Build kwargs so we only pass what we need
        edit_kwargs = {}

        # TEXT
        if text_content is not None:
            edit_kwargs["content"] = str(text_content)
        elif clear_embed and not embed:
            # If we're clearing embed but no new text provided, set content to
            # existing content so discord doesn't complain about empty message
            edit_kwargs["content"] = target_message.content if target_message.content else "\u200b"
        else:
            # No text specified and not clearing embed — preserve existing content
            edit_kwargs["content"] = target_message.content

        # EMBED
        if embed is not None:
            edit_kwargs["embed"] = embed
        elif clear_embed:
            edit_kwargs["embed"] = None
        # else: don't touch embed (preserve existing)

        # VIEW / BUTTONS
        if view is not None:
            edit_kwargs["view"] = view
        elif clear_buttons:
            edit_kwargs["view"] = discord.ui.View()  # removes buttons
        # else: don't touch view

        await target_message.edit(**edit_kwargs)

        # ───────────────────────────────────────────
        # Success response
        # ───────────────────────────────────────────
        summary_parts = []
        if text_content is not None:
            summary_parts.append(f"📝 Text: `{str(text_content)[:60]}{'...' if len(str(text_content)) > 60 else ''}`")
        if embed is not None:
            summary_parts.append(f"🖼️ Embed: `{embed.title or 'No title'}`")
        if clear_embed:
            summary_parts.append("🗑️ Embed cleared")
        if view and len(view.children) > 0:
            btn_labels = ", ".join([b.label or "?" for b in view.children])
            summary_parts.append(f"🔘 Buttons: `{btn_labels}`")
        if clear_buttons:
            summary_parts.append("🗑️ Buttons cleared")

        summary = "\n".join(summary_parts) if summary_parts else "No changes detected"

        result_embed = discord.Embed(
            title="✅ Message Edited",
            description=f"**Message ID:** `{message_id}`\n\n{summary}",
            color=discord.Color.green()
        )
        result_embed.set_footer(text=f"Edited by {ctx.author.name}")
        await ctx.send(embed=result_embed)

        db_query("INSERT INTO admin_logs (log) VALUES (?)",
                 (f"Owner {ctx.author.name} edited message {message_id} in #{ctx.channel.name} — {summary}",))

    except discord.Forbidden:
        await ctx.send("❌ **Missing permissions** — Cannot edit this message.")
    except Exception as e:
        await ctx.send(f"❌ **Error editing message:**\n```\n{e}\n```")
        import traceback
        traceback.print_exc()
        
bot.run(DISCORD_TOKEN)
