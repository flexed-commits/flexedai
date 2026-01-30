<h1 align="center">
  <img src="https://cdn.discordapp.com/attachments/1460858336667893863/1462511553374060757/20260118_234729.png?ex=696e7586&is=696d2406&hm=ea652c2c04d8bed66dbe2016b72d4f4eaddc3d06233d9934b4fbe4457aa4fceb&" width="60" height="60" align="center"> 
  flexedAI Discord Bot
</h1>

<div align="center">

  ![Discord](https://img.shields.io/badge/Discord-Bot-5865F2?style=for-the-badge&logo=discord&logoColor=white)
  ![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)
  ![discord.py](https://img.shields.io/badge/library-discord.py-blue?style=for-the-badge&logo=discord)
  ![Groq](https://img.shields.io/badge/Groq-AI-FF6B00?style=for-the-badge)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
  ![Views](https://komarev.com/ghpvc/?username=flexed-commits&repo=flexedai&label=Repository%20Views&style=for-the-badge&color=blue)

</div>

**An advanced AI-powered Discord bot with comprehensive moderation, voting rewards, and conversation capabilities**

[Invite Bot](https://discord.com/oauth2/authorize?client_id=1379152032358858762&permissions=4503599627488320&integration_type=0&scope=bot+applications.commands) • [Support Server](https://discord.com/invite/XMvPq7W5N4) • [Vote on Top.gg](https://top.gg/bot/1379152032358858762/vote) • [Support on Patreon](https://patreon.com/flexedAI/membership)

---

## ✨ Features

### 🧠 AI-Powered Conversations
- **Multi-language support** - 16 languages including English, Hindi, Spanish, French, Japanese, and more
- **Context memory** - Remembers last 6 messages per user/channel for natural conversations
- **Smart emoji reactions** - AI-suggested reactions (10% chance) based on conversation context
- **0.6s Response Cooldown** - Prevents API rate limiting while maintaining responsive service
- **Powered by Groq API** - Using `meta-llama/llama-4-maverick-17b-128e-instruct` model

### 🗳️ Top.gg Voting System (NEW!)
- **Voter Role Rewards** - Get exclusive Voter role for 12 hours after voting
- **Vote Reminders** - Optional DM reminders every 12 hours
- **Weekend Bonuses** - Special recognition for weekend votes
- **Auto-Role Management** - Automatic role assignment and expiration
- **Vote Tracking** - Track total votes per user
- **Join Retention** - Users who voted recently get role when joining support server
- **Webhook Integration** - Real-time vote processing via Top.gg webhook
- **Vote Logs** - Dedicated channel for vote notifications with detailed stats

### 💎 Patreon Integration (NEW!)
- **Smart Promotion** - Automatic Patreon messages every 15-20 messages per channel
- **Non-Intrusive** - Randomized intervals prevent spam
- **Beautiful Embeds** - Professional promotional messages
- **One-Click Support** - Direct link to become a Patron
- **Channel-Specific Tracking** - Independent counters per channel

### 📢 Updates Channel System (NEW!)
- **Required Setup** - Servers must configure updates channel to use bot
- **Global Announcements** - Send announcements to all servers at once
- **Dual Notification** - Sends to both configured channel AND server owner DM
- **Setup Verification** - Bot checks for updates channel on every interaction
- **Easy Configuration** - Simple `/setupupdates` and `/changeupdates` commands
- **View Settings** - Check current updates channel with `/viewupdates`

### 🛡️ Advanced Moderation System
- **Strike System** - 3-strike auto-blacklist with DM notifications to users
- **User Blacklisting** - Permanent user bans with notification system
- **Guild Blacklisting** - Auto-leave and prevent blacklisted servers from re-adding bot
- **Word Filter** - Customizable banned word list with automatic message deletion
- **Filter Bypass System** - Grant trusted users permission to bypass word filters
- **Report System** - User-generated reports with interactive admin action buttons
- **Bot Admin System** - Multi-tier permission system (Owner → Bot Admins → Server Admins)

### 📊 Comprehensive Logging
All actions are logged to dedicated channels with rich embeds:
- Server join/leave events with detailed server information
- Strike and blacklist actions with timestamps and reasons
- Banned word violations with automatic strike issuance
- Admin actions (all moderation commands)
- User reports with action tracking
- Complete interaction logs (24h rolling + full export)
- **Vote logs** - Track all Top.gg votes with user stats
- **Updates tracking** - Monitor announcement delivery

### 🔐 Custom Encoding System
- **Message Encoder/Decoder** - Custom cipher for encoding messages
- **Randomized Character Mapping** - Unique encoding map generated per bot instance
- **Banned Word Protection** - Encoded messages are still checked for violations
- Commands: `/encode` and `/decode`

### ⚙️ Customization
- **Custom Prefix** - Set per-server command prefix (default: `/`)
- **Language Settings** - Channel-specific language configuration with dropdown UI
- **Response Modes** - Toggle between "start" (respond to all) and "stop" (selective) modes
- **Trigger Words** - Bot responds to mentions, bot name, replies, and attachments
- **Admin Permissions** - Granular permission system for different command levels

### 💾 Data Management
- **SQLite Database** - Persistent storage for all bot data
- **JSON Migration** - Legacy JSON to SQLite migration support
- **Export Tools** - Export logs, data, server lists, and complete configurations
- **10 Database Tables** - Comprehensive data structure for all features (including vote_reminders, vote_logs, updates_channels)

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Discord Bot Token
- Groq API Key
- Discord User ID (for owner configuration)
- Top.gg Webhook Secret (optional, for voting features)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/flexed-commits/flexedai
cd flexedai/src
```

2. **Install dependencies**
```bash
pip install discord.py groq python-dotenv aiohttp
```

3. **Create and configure `.env` file**

Create a file named `.env` in the root directory:

```env
# Required: Discord Bot Token
DISCORD_TOKEN=your_discord_bot_token_here

# Required: Groq API Key
GROQ_API_KEY=your_groq_api_key_here

# Required: Bot Configuration
OWNER_ID=your_discord_user_id
OWNER_NAME=Your Name
BOT_NAME=flexedAI
OWNER_BIO=Creator and core maintainer of flexedAI Discord Bot

# Optional: AI Model (default shown)
MODEL_NAME=meta-llama/llama-4-maverick-17b-128e-instruct

# Required: Logging Channels
LOG_CHANNEL_SERVER_JOIN_LEAVE=channel_id_here
LOG_CHANNEL_STRIKES=channel_id_here
LOG_CHANNEL_BLACKLIST=channel_id_here
LOG_CHANNEL_BANNED_WORDS=channel_id_here
LOG_CHANNEL_ADMIN_LOGS=channel_id_here
LOG_CHANNEL_REPORTS=channel_id_here

# Optional: Support Server
SUPPORT_SERVER_INVITE=https://discord.com/invite/XMvPq7W5N4

# Optional: Top.gg Integration (for voting features)
TOPGG_WEBHOOK_SECRET=your_topgg_webhook_secret
SUPPORT_SERVER_ID=your_support_server_id
```

**How to get these values:**
- **DISCORD_TOKEN**: [Discord Developer Portal](https://discord.com/developers/applications) → Your App → Bot → Token
- **GROQ_API_KEY**: [Groq Console](https://console.groq.com) → API Keys
- **OWNER_ID**: Enable Developer Mode in Discord → Right-click your profile → Copy User ID
- **LOG_CHANNEL_IDs**: Right-click channels in Discord → Copy Channel ID
- **TOPGG_WEBHOOK_SECRET**: [Top.gg](https://top.gg/) → Your Bot → Webhooks → Secret
- **SUPPORT_SERVER_ID**: Right-click your support server → Copy Server ID

4. **Set up Top.gg Webhook (Optional)**

If you want voting features:
1. Go to [Top.gg](https://top.gg/bot/your-bot-id/webhooks)
2. Set webhook URL to: `https://your-domain.com/topgg/webhook`
3. Set authorization header to your `TOPGG_WEBHOOK_SECRET`
4. The bot automatically starts a webhook server on port 8080

5. **Run the bot**
```bash
python main.py
```

### First Time Setup

After starting the bot:
1. The bot will automatically create `bot_data.db` (SQLite database)
2. It will migrate any existing JSON data if present
3. Daily backup task will start automatically
4. **Top.gg webhook server starts on port 8080**
5. **Vote reminder loop and role expiration loop start**
6. Invite the bot to your server using the link generated
7. **IMPORTANT**: Run `/setupupdates #channel` in your server to enable bot functionality

---

## 📋 Command Reference

### 👥 User Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/help` | Display all available commands | `/help` |
| `/whoami` | Show your Discord profile and bot status | `/whoami` |
| `/stats` | Display bot statistics (latency, servers, users) | `/stats` |
| `/ping` | Check bot latency and response time | `/ping` |
| `/forget` | Clear AI conversation memory for your context | `/forget` |
| `/report <user> <proof> <reason>` | Report a user for misbehavior | `/report @BadUser https://proof.com Spamming` |
| `/invite` | Get bot invite link | `/invite` |
| `/encode <message>` | Encode a message using custom cipher | `/encode Hello World` |
| `/decode <encoded>` | Decode an encoded message | `/decode Ke3r...` |
| `/votereminder [action]` | Manage vote reminder settings | `/votereminder enable` |

### 🗳️ Voting Commands (NEW!)

| Command | Description | Example |
|---------|-------------|---------|
| `/votereminder` | View your voting reminder status | `/votereminder` |
| `/votereminder enable` | Enable 12-hour vote reminders | `/votereminder enable` |
| `/votereminder disable` | Disable vote reminders | `/votereminder disable` |

**Voting Features:**
- Vote on [Top.gg](https://top.gg/bot/1379152032358858762/vote) every 12 hours
- Get exclusive Voter role for 12 hours
- Enable reminders to never miss a vote
- Weekend votes get special recognition
- If you join the support server within 12 hours of voting, you'll automatically get the Voter role

### ⚙️ Configuration Commands (Admin/Owner)

| Command | Description | Permissions | Example |
|---------|-------------|-------------|---------|
| `/start` | Bot responds to all messages in channel | Admin/Owner | `/start` |
| `/stop` | Bot responds only to mentions/triggers | Admin/Owner | `/stop` |
| `/lang [language]` | Set channel language (dropdown UI) | Admin/Owner | `/lang Spanish` |
| `/prefix <new_prefix>` | Change command prefix for server | Admin/Owner | `/prefix !` |
| `/setupupdates [#channel]` | **REQUIRED** - Setup updates channel | Admin/Owner | `/setupupdates #announcements` |
| `/changeupdates [#channel]` | Change existing updates channel | Admin/Owner | `/changeupdates #news` |
| `/viewupdates` | View current updates channel | Any User | `/viewupdates` |

**Available Languages:**
English, Hindi, Hinglish, Spanish, French, German, Portuguese, Italian, Japanese, Korean, Chinese, Russian, Arabic, Turkish, Dutch, Marathi

### 🔨 Moderation Commands (Bot Admin/Owner)

#### Blacklist Management
| Command | Description | Example |
|---------|-------------|---------|
| `/blacklist` | View all blacklisted users | `/blacklist` |
| `/blacklist add <user_id> <reason>` | Blacklist a user (sends DM notification) | `/blacklist add 123456789 Harassment` |
| `/blacklist remove <user_id> <reason>` | Remove user from blacklist | `/blacklist remove 123456789 Appeal approved` |

#### Guild Blacklist Management
| Command | Description | Example |
|---------|-------------|---------|
| `/blacklist-guild` | View all blacklisted guilds | `/blacklist-guild` |
| `/blacklist-guild add <guild_id> <reason>` | Blacklist server (bot auto-leaves) | `/blacklist-guild add 987654321 ToS violation` |
| `/blacklist-guild remove <guild_id> <reason>` | Unblacklist server | `/blacklist-guild remove 987654321 Resolved` |

#### Strike System
| Command | Description | Example |
|---------|-------------|---------|
| `/addstrike <user_id> [amount] <reason>` | Add strikes (3 = auto-blacklist) | `/addstrike 123456789 1 Spam` |
| `/removestrike <user_id> [amount] <reason>` | Remove strikes from user | `/removestrike 123456789 1 False positive` |
| `/clearstrike <user_id> <reason>` | Clear all strikes for user | `/clearstrike 123456789 Clean slate` |
| `/strikelist` | View all users with strikes | `/strikelist` |

#### Word Filter Management
| Command | Description | Example |
|---------|-------------|---------|
| `/bannedword` | List all banned words | `/bannedword` |
| `/bannedword add <word>` | Add word to filter | `/bannedword add badword` |
| `/bannedword remove <word>` | Remove word from filter | `/bannedword remove badword` |
| `/listwords` | Alias for `/bannedword` | `/listwords` |

#### Filter Bypass Management
| Command | Description | Example |
|---------|-------------|---------|
| `/bypass` | List users with filter bypass | `/bypass` |
| `/bypass add <user_id> <reason>` | Grant filter bypass permission | `/bypass add 123456789 Trusted moderator` |
| `/bypass remove <user_id> <reason>` | Revoke filter bypass | `/bypass remove 123456789 No longer needed` |

#### Report System
| Command | Description | Example |
|---------|-------------|---------|
| `/reports [status]` | View reports (pending/reviewed/dismissed/all) | `/reports pending` |
| `/reportview <report_id>` | View detailed report information | `/reportview 5` |
| `/reportremove <report_id> <reason>` | Delete a specific report | `/reportremove 5 Duplicate` |
| `/reportclear <user_id> <reason>` | Clear all reports for a user | `/reportclear 123456789 Resolved` |

**Report Action Buttons** (appear in log channel):
- **Claim Report** - Mark report as being reviewed
- **Add Strike** - Add 1 strike to reported user
- **Blacklist** - Immediately blacklist reported user

### 📊 Data Management (Bot Admin/Owner)

| Command | Description | DM Only | Example |
|---------|-------------|---------|---------|
| `/sync` | Sync slash commands globally | No | `/sync` |
| `/messages` | Export interaction logs (last 24h) | Yes | `/messages` |
| `/allinteractions` | Export ALL interaction logs | Yes | `/allinteractions` |
| `/clearlogs` | Clear all interaction logs | Yes | `/clearlogs` |
| `/backup` | Trigger manual database backup | Yes | `/backup` |
| `/data` | Export complete bot configuration | Yes | `/data` |
| `server-list` | Export server list (prefix command) | Yes | `!server-list` |
| `/logs` | View recent 15 admin action logs | No | `/logs` |
| `/clearadminlogs` | Clear all admin logs | No | `/clearadminlogs` |
| `/searchlogs <keyword>` | Search interaction logs | No | `/searchlogs username` |
| `ids` | List all slash command IDs | No | `!ids` |
| `/announce <message>` | Broadcast to all servers (NEW!) | No | `/announce Important update!` |

### 👑 Owner-Only Commands

| Command | Description | Example |
|---------|-------------|---------|
| `add-admin <user>` | Promote user to bot admin | `!add-admin @User` |
| `remove-admin <user>` | Remove bot admin privileges | `!remove-admin @User` |
| `list-admins` | List all bot admins | `!list-admins` |
| `leave <server_id> [reason]` | Force bot to leave a server | `!leave 123456789 Owner request` |

**Note:** Owner commands use prefix (default `!`), not slash commands.

---

## 🗄️ Database Structure

The bot uses SQLite (`bot_data.db`) with **10 tables**:

### Core Tables

**users** - User moderation data
```sql
user_id TEXT PRIMARY KEY
strikes INTEGER DEFAULT 0
blacklisted INTEGER DEFAULT 0
```

**banned_words** - Word filter list
```sql
word TEXT PRIMARY KEY
```

**settings** - Server/channel configurations
```sql
id TEXT PRIMARY KEY
prefix TEXT DEFAULT "/"
language TEXT DEFAULT "English"
mode TEXT DEFAULT "stop"
```

**admin_logs** - Moderation action history
```sql
log TEXT
timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
```

**interaction_logs** - AI conversation logs
```sql
timestamp REAL
guild_id TEXT
channel_id TEXT
user_name TEXT
user_id TEXT
prompt TEXT
response TEXT
```

### Advanced Tables

**bot_admins** - Bot administrator list
```sql
user_id TEXT PRIMARY KEY
added_by TEXT
added_at DATETIME DEFAULT CURRENT_TIMESTAMP
```

**word_filter_bypass** - Filter bypass permissions
```sql
user_id TEXT PRIMARY KEY
added_by TEXT
reason TEXT
added_at DATETIME DEFAULT CURRENT_TIMESTAMP
```

**reports** - User-submitted reports
```sql
report_id INTEGER PRIMARY KEY AUTOINCREMENT
reporter_id TEXT
reporter_name TEXT
reported_user_id TEXT
reported_user_name TEXT
guild_id TEXT
guild_name TEXT
reason TEXT
proof TEXT
timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
status TEXT DEFAULT 'pending'
deleted INTEGER DEFAULT 0
```

**blacklisted_guilds** - Blacklisted servers
```sql
guild_id TEXT PRIMARY KEY
guild_name TEXT
blacklisted_by TEXT
reason TEXT
blacklisted_at DATETIME DEFAULT CURRENT_TIMESTAMP
```

### New Tables (Voting & Updates)

**vote_reminders** - Top.gg voting system (NEW!)
```sql
user_id TEXT PRIMARY KEY
enabled INTEGER DEFAULT 0
last_vote DATETIME
next_reminder DATETIME
total_votes INTEGER DEFAULT 0
role_expires_at DATETIME
```

**vote_logs** - Vote history tracking (NEW!)
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
user_id TEXT
voted_at DATETIME DEFAULT CURRENT_TIMESTAMP
is_weekend INTEGER DEFAULT 0
vote_type TEXT DEFAULT 'upvote'
```

**updates_channels** - Server updates configuration (NEW!)
```sql
guild_id TEXT PRIMARY KEY
channel_id TEXT NOT NULL
setup_by TEXT
setup_at TEXT DEFAULT CURRENT_TIMESTAMP
```

---

## 🔧 Advanced Configuration

### Top.gg Webhook Server (NEW!)

The bot automatically starts a webhook server on port 8080 to receive vote notifications:

```python
# Webhook endpoints:
POST /topgg/webhook  # Primary endpoint
POST /webhook        # Alternative
POST /topgg          # Alternative
POST /               # Fallback

GET /health          # Health check
GET /test            # Test vote simulation
```

**Features:**
- Real-time vote processing
- Automatic role assignment (12-hour duration)
- Vote logging to dedicated channel
- DM notifications to voters
- Weekend bonus tracking
- Test vote endpoint for debugging

**Setup:**
1. Configure ngrok or similar tunnel to expose port 8080
2. Set webhook URL on Top.gg to your public URL
3. Add authorization secret to `.env`

### Voter Role System (NEW!)

When users vote on Top.gg:
1. They receive the Voter role immediately (12-hour duration)
2. DM sent with vote thank you and role info
3. Vote logged to database and log channel
4. After 12 hours, role automatically removed
5. DM sent when role expires
6. If user joins support server within 12 hours of voting, role is assigned automatically

**Role Expiration:**
- Background task checks every minute for expired roles
- Automatic removal with DM notification
- Users can vote again to renew role

### Patreon Promotion System (NEW!)

The bot includes smart Patreon promotion:

```python
# Configuration
patreon_promoter = PatreonPromoter(
    patreon_url="https://patreon.com/flexedAI/membership",
    min_messages=15,    # Minimum messages before promotion
    max_messages=20     # Maximum messages before promotion
)
```

**How it works:**
- Tracks message count per channel independently
- Sends promotion after 15-20 messages (randomized)
- Beautiful embed with Patreon branding
- One-click "Become a Patron" button
- Non-intrusive, appears occasionally

### Updates Channel System (NEW!)

**Required Setup:**
Every server MUST configure an updates channel to use the bot:

```bash
/setupupdates #announcements
```

**How it works:**
1. Bot checks for updates channel on every interaction
2. If not configured, bot silently ignores most commands
3. Only `/setupupdates` command works without configuration
4. Once configured, all features become available

**Announcement System:**
When admins use `/announce`:
1. Message sent to all configured updates channels
2. DM sent to ALL server owners (even without updates channel)
3. Servers without updates channel get setup reminder in DM
4. Delivery statistics tracked and reported

### Response Cooldown System

The bot implements a **0.6-second cooldown** between responses to prevent API rate limiting:

```python
# If another user sends a message within 0.6 seconds of the last response:
# → Bot remains silent (no response)

# After 0.6 seconds have passed:
# → Bot will respond to new messages normally
```

**Why this exists:**
- Groq API has rate limits
- Prevents cost overruns
- Ensures stable service for all users
- Users are notified of this in the welcome message

### Response Modes

**START Mode** (`/start`)
- Bot responds to **every message** in the channel
- Best for dedicated bot channels
- High interaction rate

**STOP Mode** (`/stop`) - Default
- Bot responds only to:
  - Direct mentions (`@flexedAI`)
  - Messages containing bot name
  - Replies to bot messages
  - Messages with attachments
  - DMs (always responds)
- Best for general channels
- Reduces spam

### Smart Emoji Reactions

The bot has a **10% chance** to add AI-suggested emoji reactions:

```python
bot.reaction_chance = 0.10  # 10% chance
```

When triggered, the AI analyzes the conversation and suggests 1-2 contextually appropriate emojis.

### Logging Channel Configuration

Create **6 dedicated channels** in your server for different log types:

```python
LOG_CHANNELS = {
    'server_join_leave': 1234567890,    # Bot joins/leaves servers
    'strikes': 1234567890,               # Strike additions/removals
    'blacklist': 1234567890,             # User/guild blacklists
    'banned_words': 1234567890,          # Word filter violations
    'admin_logs': 1234567890,            # All admin actions
    'reports': 1234567890                # User reports
}
```

**All logs include:**
- Rich embeds with color coding
- Timestamps
- User/Admin information
- Action reasons
- DM delivery status
- Relevant IDs for tracking

---

## 🎯 Permission Hierarchy

### Owner (You)
- All permissions
- Can manage bot admins
- Can force-leave servers
- Receives daily backups
- Can send global announcements

### Bot Admins
- User moderation (blacklist, strikes)
- Word filter management
- Report review and actions
- Data exports
- Server configuration
- Global announcements
- **Cannot:** Manage other admins, force-leave servers

### Server Administrators
- Configure response mode (`/start`, `/stop`)
- Set channel language
- Change server prefix
- Setup/change updates channel
- **Cannot:** Moderate globally, access logs

### Regular Users
- Use AI conversations
- Submit reports
- Use utility commands
- Enable vote reminders
- **Cannot:** Moderation or configuration

---

## 🛡️ Moderation Workflow

### Strike System Flow
1. User violates rules (banned word, etc.)
2. Bot adds strike (1/3, 2/3, or 3/3)
3. User receives DM notification
4. Logged to strikes channel
5. At 3 strikes: **Auto-blacklist**
   - User blacklisted automatically
   - DM sent explaining suspension
   - Logged to blacklist channel

### Report System Flow
1. User submits `/report @user proof reason`
2. Report logged to database
3. Rich embed sent to reports channel with action buttons
4. Admin clicks button:
   - **Claim** → Marks as being reviewed
   - **Add Strike** → Adds 1 strike to reported user
   - **Blacklist** → Immediately blacklists user
5. Report status updated
6. All actions logged to admin_logs

### Guild Blacklist Flow
1. Admin uses `/blacklist-guild add`
2. If bot is in the server:
   - Owner receives DM notification
   - Bot automatically leaves
3. Logged to blacklist channel
4. If guild tries to re-add bot:
   - Bot auto-leaves on join
   - Owner notified of attempt
   - Logged to blacklist channel

### Voting Workflow (NEW!)
1. User votes on Top.gg
2. Webhook received by bot
3. Vote logged to database and channel
4. Voter role assigned (12 hours)
5. DM sent to user with thank you
6. Background task monitors expiration
7. After 12 hours:
   - Role automatically removed
   - DM sent to user
   - User can vote again

### Updates Channel Workflow (NEW!)
1. Server admin runs `/setupupdates #channel`
2. Bot verifies permissions in channel
3. Configuration saved to database
4. Test message sent to channel
5. All bot features now enabled
6. When owner sends `/announce`:
   - Message to all updates channels
   - DM to all server owners
   - Statistics reported back

---

## 📈 Bot Statistics

The bot tracks comprehensive statistics shown in `/stats`:

- **Live Stats:**
  - Current latency (ms)
  - Total servers
  - Total users across all servers
  
- **Moderation Stats** (shown in `/data` export):
  - Total blacklisted users
  - Total strikes issued
  - Total banned words
  - Total blacklisted guilds
  - Total bot admins
  - Total pending reports
  - Total interactions logged
  - **Total votes received (NEW!)**
  - **Total active voters (NEW!)**
  - **Total servers with updates channels (NEW!)**

---

## 🚨 Automatic Systems

### Daily Backup System
- Runs every 24 hours
- Exports complete database to JSON
- Sends to owner via DM
- Includes:
  - All users and strikes
  - Banned words
  - Bot admins
  - Filter bypass users
  - Settings
  - Last 24h interactions
  - Recent admin logs
  - **Vote statistics (NEW!)**
  - **Updates channel configs (NEW!)**

### Vote Reminder Loop (NEW!)
- Runs every 5 minutes
- Checks for users with reminders enabled
- Sends DM when 12 hours have passed since last vote
- Includes vote button and disable button
- Auto-disables if DMs are closed

### Role Expiration Loop (NEW!)
- Runs every minute
- Checks for expired voter roles
- Automatically removes role after 12 hours
- Sends DM notification to user
- Handles users who left server

### Auto-Blacklist on 3 Strikes
- Automatic when user reaches 3 strikes
- User receives detailed DM
- Logged to both strikes and blacklist channels
- Can be reversed with `/blacklist remove`

### Word Filter Auto-Delete
- Messages containing banned words are deleted
- User strike added (unless has bypass)
- Warning message sent (auto-deletes in 10s)
- Logged to banned_words channel
- DM sent to user

### Guild Blacklist Auto-Leave
- Bot leaves immediately when blacklisted
- Auto-leaves on re-add attempts
- Owner notified of server details
- Logged to blacklist channel

### Patreon Promotion (NEW!)
- Tracks messages per channel
- Sends promotion every 15-20 messages
- Randomized intervals
- Beautiful branded embeds
- Non-intrusive timing

---

## 🔐 Security Features

### User Privacy
- User IDs are hashed in exports
- DM failures are handled gracefully
- Personal data only visible to admins
- Reports are logged securely
- Vote data stored with privacy in mind

### API Key Protection
- All keys stored in `.env` (not in code)
- `.env` should be in `.gitignore`
- No keys in database or logs
- Webhook secret verification

### Permission Checks
- All admin commands verify permissions
- Owner-only commands are restricted
- Server admin checks for config commands
- DM-only restriction for sensitive exports
- Updates channel requirement prevents abuse

### Rate Limiting
- 0.6s cooldown prevents abuse
- AI request limiting via Groq
- Message truncation at 8000 tokens
- Webhook rate limiting built-in

---

## 🐛 Troubleshooting

### Bot doesn't respond
- Check if blacklisted: `/whoami`
- Verify response mode: Use `/start` in channel
- **Check if updates channel is configured: `/viewupdates`**
- Check if bot has permission to send messages
- Verify cooldown hasn't silenced bot (wait 0.6s)

### Commands not working
- Ensure you have correct permissions
- **Verify updates channel is setup: `/setupupdates`**
- Check if using slash commands vs prefix commands
- Try `/sync` (admin only) to refresh commands
- Verify bot has "Use Application Commands" permission

### Voting features not working
- Check webhook URL is correct on Top.gg
- Verify `TOPGG_WEBHOOK_SECRET` in `.env`
- Check `SUPPORT_SERVER_ID` is correct
- Test webhook with `/test` endpoint
- Check bot has manage roles permission in support server

### Updates channel issues
- Run `/setupupdates` to configure
- Verify bot has send/embed permissions in channel
- Check channel ID is saved: `/viewupdates`
- Ensure channel exists and bot is in server

### Logging not working
- Verify channel IDs in `.env`
- Check bot can send messages to log channels
- Ensure channels exist and bot is in server

### Database errors
- Delete `bot_data.db` to reset (data loss!)
- Check file permissions
- Ensure SQLite is installed

### DM notifications failing
- User has DMs disabled (expected behavior)
- Bot logs will show "DM Failed" status
- Notifications still logged to channels

---

## 📝 Best Practices

### For Server Owners
1. **ALWAYS run `/setupupdates` first**
2. Set up dedicated log channels
3. Configure `/start` mode in bot channels only
4. Use `/stop` mode in general channels
5. Regularly review `/reports`
6. Grant `/bypass` to trusted moderators only
7. Encourage users to vote on Top.gg
8. Check updates channel configuration: `/viewupdates`

### For Bot Admins
1. Always provide reasons for moderation actions
2. Review reports before taking action
3. Use `/reportview` for full context
4. Export logs regularly with `/data`
5. Communicate with users via DMs when possible
6. Use `/announce` sparingly for important updates

### For Users
1. Use `/forget` to clear conversation context
2. Submit `/report` with proof for violations
3. Check your status with `/whoami`
4. Respect the 0.6s cooldown
5. Use `/help` to discover features
6. Vote on Top.gg to support the bot
7. Enable vote reminders: `/votereminder enable`

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/AmazingFeature
   ```
3. **Make your changes**
   - Follow existing code style
   - Add comments for complex logic
   - Update README if adding features
4. **Test thoroughly**
   - Test all affected commands
   - Check database operations
   - Verify logging works
5. **Commit your changes**
   ```bash
   git commit -m 'Add some AmazingFeature'
   ```
6. **Push to your branch**
   ```bash
   git push origin feature/AmazingFeature
   ```
7. **Open a Pull Request**

### Code Guidelines
- Use async/await for Discord operations
- Include error handling with try/except
- Add DM notifications for user-facing actions
- Log all moderation actions
- Use embeds for rich responses
- Follow PEP 8 style guide

---

## 📄 License

This project is licensed under the **MIT License**.

```
MIT License

Copyright (c) 2025 flexed-commits

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 📞 Support & Links

- **Support Server**: [Join Discord](https://discord.com/invite/XMvPq7W5N4)
- **Invite Bot**: [Add to Server](https://discord.com/oauth2/authorize?client_id=1379152032358858762&permissions=4503599627488320&integration_type=0&scope=bot+applications.commands)
- **Vote on Top.gg**: [Support the Bot](https://top.gg/bot/1379152032358858762/vote)
- **Support on Patreon**: [Become a Patron](https://patreon.com/flexedAI/membership)
- **GitHub**: [flexed-commits/flexedai](https://github.com/flexed-commits/flexedai)
- **Creator**: Ψ.1nOnly.Ψ
- **Report Issues**: [GitHub Issues](https://github.com/flexed-commits/flexedai/issues)

---

## ⚠️ Important Notes

### Required Bot Permissions
When inviting the bot, ensure these permissions are enabled:
- ✅ Read Messages/View Channels
- ✅ Send Messages
- ✅ Embed Links
- ✅ Attach Files
- ✅ Add Reactions
- ✅ Manage Messages (for word filter deletion)
- ✅ **Manage Roles (for voter role - NEW!)**
- ✅ Use Slash Commands
- ✅ Read Message History

### API Rate Limits
- **Groq API**: Has request limits based on your plan
- **0.6s Cooldown**: Built-in to prevent hitting limits
- **Message Truncation**: Long messages truncated to 8000 tokens
- **Top.gg API**: Rate limited, handled by webhook

### Data Retention
- **Interaction Logs**: Stored indefinitely (use `/clearlogs` to purge)
- **Admin Logs**: Stored indefinitely (use `/clearadminlogs` to purge)
- **Daily Backups**: Last 24h interactions only
- **Vote Logs**: Stored permanently
- **Database**: No automatic cleanup (manual management required)

### Privacy Considerations
- Bot logs all interactions to database
- Admins can view interaction logs
- Reports are visible to all bot admins
- DMs to users notify them of moderation actions
- Vote data tracked per user

### Port Requirements
- **Port 8080**: Required for Top.gg webhook (configurable)
- Must be accessible from internet if using voting features
- Use ngrok or similar for testing

---

## 🎯 Roadmap

### Planned Features
- [ ] Web dashboard for bot management
- [x] Top.gg voting integration with rewards ✅
- [x] Patreon promotion system ✅
- [x] Updates channel requirement ✅
- [ ] Advanced analytics and visualizations
- [ ] Custom AI model fine-tuning options
- [ ] Multi-server configuration sync
- [ ] Webhook logging support
- [ ] Auto-moderation with configurable rules
- [ ] Economy system integration
- [ ] Custom command creation system
- [ ] Temporary bans/mutes
- [ ] Appeal system for blacklisted users
- [ ] Per-user language preferences
- [ ] Voice channel support

### Under Consideration
- [ ] Music playback features
- [ ] Leveling/XP system
- [ ] Ticket system
- [ ] Suggestion system
- [ ] Poll/voting system
- [ ] Custom triggers/responses
- [ ] Vote streak rewards
- [ ] Monthly top voters leaderboard
- [ ] Patreon role rewards

---

## 🙏 Acknowledgments

- **discord.py** - The amazing Discord API wrapper
- **Groq** - Lightning-fast AI inference platform
- **Meta AI** - Llama model development
- **SQLite** - Reliable embedded database
- **Python Community** - Excellent libraries and support
- **Top.gg** - Discord bot listing and voting platform
- **Patreon** - Supporting bot development and hosting
- **aiohttp** - Async HTTP for webhooks
- All contributors and supporters who help improve this project

---

## 📚 Additional Resources

### Helpful Links
- [discord.py Documentation](https://discordpy.readthedocs.io/)
- [Groq API Documentation](https://console.groq.com/docs)
- [Discord Developer Portal](https://discord.com/developers/docs)
- [Python SQLite Documentation](https://docs.python.org/3/library/sqlite3.html)
- [Top.gg API Documentation](https://docs.top.gg/)
- [aiohttp Documentation](https://docs.aiohttp.org/)

### Tutorials
- [How to create a Discord bot](https://discordpy.readthedocs.io/en/stable/discord.html)
- [Getting started with Groq](https://console.groq.com/docs/quickstart)
- [SQLite basics](https://www.sqlitetutorial.net/)
- [Setting up Top.gg webhooks](https://docs.top.gg/resources/webhooks/)

---

<div align="center">

**Made with ❤️ by Ψ.1nOnly.Ψ**

⭐ Star this repository if you found it helpful!

🗳️ **[Vote for this bot on Top.gg!](https://top.gg/bot/1379152032358858762/vote)**

💎 **[Support on Patreon](https://patreon.com/flexedAI/membership)**

[![Discord](https://img.shields.io/discord/1460574191072972913?color=7289da&label=Discord&logo=discord&logoColor=white&style=for-the-badge)](https://discord.com/invite/XMvPq7W5N4)
[![GitHub stars](https://img.shields.io/github/stars/flexed-commits/flexedai?style=for-the-badge)](https://github.com/flexed-commits/flexedai/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/flexed-commits/flexedai?style=for-the-badge)](https://github.com/flexed-commits/flexedai/issues)

**Version 2.1** | Last Updated: January 2025

</div>
