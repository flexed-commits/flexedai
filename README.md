<h1 align="center">
  <img src="https://cdn.discordapp.com/avatars/1081876265683927080/2a551f08b87409f4d56f378c37120b8a.webp?" alt="Bot Icon" width="40" height="40" style="vertical-align:middle"> 
  flexedAI Discord Bot
</h1>


<div align="center">

  ![Discord](https://img.shields.io/badge/Discord-Bot-5865F2?style=for-the-badge&logo=discord&logoColor=white)
  ![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)
  ![discord.py](https://img.shields.io/badge/library-discord.py-blue?style=for-the-badge&logo=discord)
  ![Groq](https://img.shields.io/badge/Groq-AI-FF6B00?style=for-the-badge)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
  
**An advanced AI-powered Discord bot with comprehensive moderation and conversation capabilities**

[Invite Bot](https://discord.com/oauth2/authorize?client_id=1379152032358858762&permissions=4503599627488320&integration_type=0&scope=bot+applications.commands) • [Support Server](https://discord.com/invite/XMvPq7W5N4) • [Report Issues](#)

</div>

---

## ✨ Features

### 🧠 AI-Powered Conversations
- **Multi-language support** - 16 languages including English, Hindi, Spanish, French, Japanese, and more
- **Context memory** - Remembers last 6 messages per user/channel for natural conversations
- **Smart emoji reactions** - AI-suggested reactions based on conversation context
- **Powered by Groq API** - Using `meta-llama/llama-4-maverick-17b-128e-instruct` model

### 🛡️ Advanced Moderation System
- **Strike System** - 3-strike auto-blacklist with DM notifications
- **User Blacklisting** - Permanent or temporary user bans
- **Guild Blacklisting** - Auto-leave and prevent blacklisted servers
- **Word Filter** - Customizable banned word list with bypass permissions
- **Report System** - User-generated reports with admin action buttons

### 📊 Comprehensive Logging
- Server join/leave events
- Strike and blacklist actions
- Banned word violations
- Admin actions
- User reports
- Message interactions

### ⚙️ Customization
- **Custom Prefix** - Set per-server command prefix
- **Language Settings** - Channel-specific language configuration
- **Response Modes** - Toggle between "start" (respond to all) and "stop" (selective) modes
- **Admin Roles** - Bot admin system with granular permissions

### 💾 Data Management
- **SQLite Database** - Persistent storage for all bot data
- **Daily Backups** - Automatic 24-hour backup system
- **JSON Migration** - Legacy JSON to SQLite migration support
- **Export Tools** - Export logs, data, and server lists

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Discord Bot Token
- Groq API Key

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/flexed-commits/flexedai
cd flexedai
```

2. **Install dependencies**
```bash
pip install discord.py groq
```

3. **Set up environment variables**
```bash
export DISCORD_TOKEN="your_discord_bot_token"
export GROQ_API_KEY="your_groq_api_key"
```

Or create a `.env` file:
```env
DISCORD_TOKEN=your_discord_bot_token
GROQ_API_KEY=your_groq_api_key
```

4. **Configure the bot**
Edit `main.py` and update:
```python
OWNER_ID = your_discord_user_id  # Replace with your Discord user ID

# Update log channel IDs (optional)
LOG_CHANNELS = {
    'server_join_leave': your_channel_id,
    'strikes': your_channel_id,
    'blacklist': your_channel_id,
    'banned_words': your_channel_id,
    'admin_logs': your_channel_id,
    'reports': your_channel_id
}
```

5. **Run the bot**
```bash
python main.py
```

---

## 📋 Command Reference

### 👥 User Commands

| Command | Description |
|---------|-------------|
| `/help` | Display all available commands |
| `/whoami` | Show your Discord profile and bot status |
| `/stats` | Display bot statistics |
| `/ping` | Check bot latency |
| `/forget` | Clear AI conversation memory |
| `/report <user> <proof> <reason>` | Report a user for misbehavior |
| `/invite` | Get bot invite link |

### ⚙️ Configuration Commands (Admin)

| Command | Description |
|---------|-------------|
| `/start` | Bot responds to all messages in channel |
| `/stop` | Bot responds only to mentions/triggers |
| `/lang [language]` | Set channel language |
| `/prefix <new_prefix>` | Change command prefix |

### 🔨 Moderation Commands (Admin/Owner)

| Command | Description |
|---------|-------------|
| `/sync` | Sync slash commands globally |
| `/blacklist` | View blacklisted users |
| `/blacklist add <user_id> <reason>` | Blacklist a user |
| `/blacklist remove <user_id> <reason>` | Remove user from blacklist |
| `/blacklist-guild` | View blacklisted guilds |
| `/blacklist-guild add <guild_id> <reason>` | Blacklist a server |
| `/blacklist-guild remove <guild_id> <reason>` | Unblacklist a server |
| `/addstrike <user_id> [amount] <reason>` | Add strikes to user |
| `/removestrike <user_id> [amount] <reason>` | Remove strikes from user |
| `/clearstrike <user_id> <reason>` | Clear all strikes for user |
| `/strikelist` | View all users with strikes |
| `/bannedword` | List banned words |
| `/bannedword add <word>` | Add word to filter |
| `/bannedword remove <word>` | Remove word from filter |
| `/bypass` | List users with filter bypass |
| `/bypass add <user_id> <reason>` | Grant filter bypass |
| `/bypass remove <user_id> <reason>` | Revoke filter bypass |
| `/reports [status]` | View reports by status |
| `/reportview <report_id>` | View detailed report |
| `/reportremove <report_id> <reason>` | Delete a report |
| `/reportclear <user_id> <reason>` | Clear all reports for user |

### 📊 Data Management (Admin/Owner)

| Command | Description |
|---------|-------------|
| `/messages` | Export interaction logs (24h) |
| `/allinteractions` | Export ALL interaction logs |
| `/clearlogs` | Clear interaction logs |
| `/backup` | Trigger manual backup |
| `/data` | Export complete bot configuration |
| `server-list` | Export server list (prefix command) |
| `/logs` | View recent admin logs |
| `/clearadminlogs` | Clear admin logs |
| `/searchlogs <keyword>` | Search interaction logs |

### 👑 Owner Commands

| Command | Description |
|---------|-------------|
| `add-admin <user>` | Promote user to bot admin |
| `remove-admin <user>` | Remove bot admin |
| `list-admins` | List all bot admins |
| `leave <server_id> [reason]` | Leave a server |
| `ids` | List all slash command IDs |

---

## 🗄️ Database Structure

The bot uses SQLite with the following tables:

- **users** - User strikes and blacklist status
- **banned_words** - Word filter list
- **settings** - Server/channel configurations
- **admin_logs** - Moderation action logs
- **interaction_logs** - AI conversation logs
- **bot_admins** - Bot administrator list
- **word_filter_bypass** - Users with filter bypass
- **reports** - User-submitted reports
- **blacklisted_guilds** - Blacklisted servers

---

## 🌍 Supported Languages

English • Hindi • Hinglish • Spanish • French • German • Portuguese • Italian • Japanese • Korean • Chinese • Russian • Arabic • Turkish • Dutch • Marathi

Set language per channel using `/lang [language]`

---

## 🔧 Configuration

### Environment Variables

```env
DISCORD_TOKEN=your_discord_bot_token
GROQ_API_KEY=your_groq_api_key
```

### Bot Configuration

```python
OWNER_ID = your_discord_user_id
MODEL_NAME = "meta-llama/llama-4-maverick-17b-128e-instruct"
MAX_MESSAGE_LENGTH = 2000
MAX_INPUT_TOKENS = 8000
```

### Logging Channels

Configure dedicated channels for different log types:

```python
LOG_CHANNELS = {
    'server_join_leave': channel_id,
    'strikes': channel_id,
    'blacklist': channel_id,
    'banned_words': channel_id,
    'admin_logs': channel_id,
    'reports': channel_id
}
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## ⚖️ License

This project is licensed under the **MIT License**. For more information, please see the [LICENSE](LICENSE) file located in the root directory of this repository.

---

## 📞 Support

- **Support Server**: [Join Discord](https://discord.com/invite/XMvPq7W5N4)
- **Creator**: Ψ.1nOnly.Ψ
- **Report Issues**: Use the `/report` command or open a GitHub issue

---

## ⚠️ Important Notes

### Before Running
1. Replace `OWNER_ID` with your Discord user ID
2. Update `LOG_CHANNELS` with your server's channel IDs
3. Set up environment variables for API keys
4. Ensure the bot has proper permissions in your server

### Required Bot Permissions
- Read Messages/View Channels
- Send Messages
- Embed Links
- Attach Files
- Add Reactions
- Manage Messages (for word filter)
- Use Slash Commands

### API Requirements
- **Discord Bot Token**: Create at [Discord Developer Portal](https://discord.com/developers/applications)
- **Groq API Key**: Get from [Groq Console](https://console.groq.com)

---

## 🎯 Roadmap

- [ ] Web dashboard for bot management
- [ ] Advanced analytics and statistics
- [ ] Custom AI model fine-tuning
- [ ] Multi-server configuration sync
- [ ] Webhook logging support
- [ ] Auto-moderation with configurable rules
- [ ] Economy system integration
- [ ] Custom command creation

---

## 🙏 Acknowledgments

- **discord.py** - The Discord API wrapper
- **Groq** - AI inference platform
- **Meta** - Llama model development
- All contributors and supporters

---

<div align="center">

**Made with ❤️ by Ψ.1nOnly.Ψ**

⭐ Star this repository if you found it helpful!

</div>
