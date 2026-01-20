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

**An advanced AI-powered Discord bot with comprehensive moderation and conversation capabilities**

[Invite Bot](https://discord.com/oauth2/authorize?client_id=1379152032358858762&permissions=4503599627488320&integration_type=0&scope=bot+applications.commands) • [Support Server](https://discord.com/invite/XMvPq7W5N4) • [Report Issues](https://github.com/flexed-commits/flexedai/issues)

---

## ✨ Features

### 🧠 AI-Powered Conversations
- **Multi-language support** - 16 languages including English, Hindi, Spanish, French, Japanese, and more
- **Context memory** - Remembers last 6 messages per user/channel for natural conversations
- **Smart emoji reactions** - AI-suggested reactions (10% chance) based on conversation context
- **0.6s Response Cooldown** - Prevents API rate limiting while maintaining responsive service
- **Powered by Groq API** - Using `meta-llama/llama-4-maverick-17b-128e-instruct` model

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
- **8 Database Tables** - Comprehensive data structure for all features

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Discord Bot Token
- Groq API Key
- Discord User ID (for owner configuration)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/flexed-commits/flexedai
cd flexedai
```

2. **Install dependencies**
```bash
pip install discord.py groq python-dotenv
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
```

**How to get these values:**
- **DISCORD_TOKEN**: [Discord Developer Portal](https://discord.com/developers/applications) → Your App → Bot → Token
- **GROQ_API_KEY**: [Groq Console](https://console.groq.com) → API Keys
- **OWNER_ID**: Enable Developer Mode in Discord → Right-click your profile → Copy User ID
- **LOG_CHANNEL_IDs**: Right-click channels in Discord → Copy Channel ID

4. **Run the bot**
```bash
python main.py
```

### First Time Setup

After starting the bot:
1. The bot will automatically create `bot_data.db` (SQLite database)
2. It will migrate any existing JSON data if present
3. Daily backup task will start automatically
4. Invite the bot to your server using the link generated

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

### ⚙️ Configuration Commands (Admin/Owner)

| Command | Description | Permissions | Example |
|---------|-------------|-------------|---------|
| `/start` | Bot responds to all messages in channel | Admin/Owner | `/start` |
| `/stop` | Bot responds only to mentions/triggers | Admin/Owner | `/stop` |
| `/lang [language]` | Set channel language (dropdown UI) | Admin/Owner | `/lang Spanish` |
| `/prefix <new_prefix>` | Change command prefix for server | Admin/Owner | `/prefix !` |

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

The bot uses SQLite (`bot_data.db`) with **8 tables**:

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
prefix TEXT DEFAULT "!"
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
```

**blacklisted_guilds** - Blacklisted servers
```sql
guild_id TEXT PRIMARY KEY
guild_name TEXT
blacklisted_by TEXT
reason TEXT
blacklisted_at DATETIME DEFAULT CURRENT_TIMESTAMP
```

---

## 🔧 Advanced Configuration

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

Create 6 dedicated channels in your server for different log types:

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

### Bot Admins
- User moderation (blacklist, strikes)
- Word filter management
- Report review and actions
- Data exports
- Server configuration
- **Cannot:** Manage other admins, force-leave servers

### Server Administrators
- Configure response mode (`/start`, `/stop`)
- Set channel language
- Change server prefix
- **Cannot:** Moderate globally, access logs

### Regular Users
- Use AI conversations
- Submit reports
- Use utility commands
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

---

## 🔐 Security Features

### User Privacy
- User IDs are hashed in exports
- DM failures are handled gracefully
- Personal data only visible to admins
- Reports are logged securely

### API Key Protection
- All keys stored in `.env` (not in code)
- `.env` should be in `.gitignore`
- No keys in database or logs

### Permission Checks
- All admin commands verify permissions
- Owner-only commands are restricted
- Server admin checks for config commands
- DM-only restriction for sensitive exports

### Rate Limiting
- 0.6s cooldown prevents abuse
- AI request limiting via Groq
- Message truncation at 8000 tokens

---

## 🐛 Troubleshooting

### Bot doesn't respond
- Check if blacklisted: `/whoami`
- Verify response mode: Use `/start` in channel
- Check if bot has permission to send messages
- Verify cooldown hasn't silenced bot (wait 0.6s)

### Commands not working
- Ensure you have correct permissions
- Check if using slash commands vs prefix commands
- Try `/sync` (admin only) to refresh commands
- Verify bot has "Use Application Commands" permission

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
1. Set up dedicated log channels
2. Configure `/start` mode in bot channels only
3. Use `/stop` mode in general channels
4. Regularly review `/reports`
5. Grant `/bypass` to trusted moderators only

### For Bot Admins
1. Always provide reasons for moderation actions
2. Review reports before taking action
3. Use `/reportview` for full context
4. Export logs regularly with `/data`
5. Communicate with users via DMs when possible

### For Users
1. Use `/forget` to clear conversation context
2. Submit `/report` with proof for violations
3. Check your status with `/whoami`
4. Respect the 0.6s cooldown
5. Use `/help` to discover features

---

## 🔄 Migration Guide

### From JSON to SQLite

If you have old bot data in `bot_data.json`:

1. Place `bot_data.json` in the same directory as `main.py`
2. Run the bot normally
3. Bot will automatically:
   - Create `bot_data.db`
   - Migrate all data
   - Rename old file to `bot_data.json.backup`
   - Migrate interaction logs from `interaction_logs.json`

**Migrated data:**
- Blacklist → users table
- Violations → strikes in users table
- Banned words → banned_words table
- Languages → settings table
- Prefixes → settings table
- Response modes → settings table
- Admin logs → admin_logs table

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
- ✅ Use Slash Commands
- ✅ Read Message History

### API Rate Limits
- **Groq API**: Has request limits based on your plan
- **0.6s Cooldown**: Built-in to prevent hitting limits
- **Message Truncation**: Long messages truncated to 8000 tokens

### Data Retention
- **Interaction Logs**: Stored indefinitely (use `/clearlogs` to purge)
- **Admin Logs**: Stored indefinitely (use `/clearadminlogs` to purge)
- **Daily Backups**: Last 24h interactions only
- **Database**: No automatic cleanup (manual management required)

### Privacy Considerations
- Bot logs all interactions to database
- Admins can view interaction logs
- Reports are visible to all bot admins
- DMs to users notify them of moderation actions

---

## 🎯 Roadmap

### Planned Features
- [ ] Web dashboard for bot management
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

---

## 🙏 Acknowledgments

- **discord.py** - The amazing Discord API wrapper
- **Groq** - Lightning-fast AI inference platform
- **Meta AI** - Llama model development
- **SQLite** - Reliable embedded database
- **Python Community** - Excellent libraries and support
- All contributors and supporters who help improve this project

---

## 📚 Additional Resources

### Helpful Links
- [discord.py Documentation](https://discordpy.readthedocs.io/)
- [Groq API Documentation](https://console.groq.com/docs)
- [Discord Developer Portal](https://discord.com/developers/docs)
- [Python SQLite Documentation](https://docs.python.org/3/library/sqlite3.html)

### Tutorials
- [How to create a Discord bot](https://discordpy.readthedocs.io/en/stable/discord.html)
- [Getting started with Groq](https://console.groq.com/docs/quickstart)
- [SQLite basics](https://www.sqlitetutorial.net/)

---

<div align="center">

**Made with ❤️ by Ψ.1nOnly.Ψ**

⭐ Star this repository if you found it helpful!

[![Discord](https://img.shields.io/discord/1460574191072972913?color=7289da&label=Discord&logo=discord&logoColor=white&style=for-the-badge)](https://discord.com/invite/XMvPq7W5N4)
[![GitHub stars](https://img.shields.io/github/stars/flexed-commits/flexedai?style=for-the-badge)](https://github.com/flexed-commits/flexedai/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/flexed-commits/flexedai?style=for-the-badge)](https://github.com/flexed-commits/flexedai/issues)

**Version 2.0** | Last Updated: January 2025

</div>