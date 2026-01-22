import discord
import random
from collections import defaultdict

class PatreonPromoter:
    """
    Handles automatic Patreon promotion messages in Discord channels.
    Sends a promotion message every 15-20 messages per channel.
    """
    
    def __init__(self, patreon_url: str, min_messages: int = 15, max_messages: int = 20):
        """
        Initialize the Patreon promoter.
        
        Args:
            patreon_url: The Patreon membership URL
            min_messages: Minimum messages before promotion (default: 15)
            max_messages: Maximum messages before promotion (default: 20)
        """
        self.patreon_url = patreon_url
        self.min_messages = min_messages
        self.max_messages = max_messages
        
        # Track message counts per channel
        self.channel_counters = defaultdict(int)
        
        # Track promotion thresholds per channel (randomized)
        self.channel_thresholds = defaultdict(lambda: random.randint(min_messages, max_messages))
    
    def track_message(self, channel_id: str) -> bool:
        """
        Track a message and determine if promotion should be sent.
        
        Args:
            channel_id: The Discord channel ID as string
            
        Returns:
            bool: True if promotion message should be sent, False otherwise
        """
        self.channel_counters[channel_id] += 1
        
        # Check if threshold reached
        if self.channel_counters[channel_id] >= self.channel_thresholds[channel_id]:
            # Reset counter and set new random threshold
            self.channel_counters[channel_id] = 0
            self.channel_thresholds[channel_id] = random.randint(self.min_messages, self.max_messages)
            return True
        
        return False
    
    def create_promotion_message(self) -> tuple[discord.Embed, discord.ui.View]:
        """
        Create the Patreon promotion embed and view with button.
        
        Returns:
            tuple: (Embed, View) for the promotion message
        """
        # Create embed
        embed = discord.Embed(
            title="💎 Support the Development!",
            description=(
                "Hey there! 👋\n\n"
                "If you're enjoying this bot and want to support its continued development, "
                "consider becoming a Patreon member!\n\n"
                "**Your support helps us:**\n"
                "✨ Keep the bot running 24/7\n"
                "🚀 Add new features and improvements\n"
                "⚡ Maintain fast response times\n"
                "🛡️ Provide better moderation tools\n"
                "💝 Show appreciation for the work\n\n"
                "Every contribution matters, no matter how small! ❤️"
            ),
            color=discord.Color.from_rgb(255, 66, 77)  # Patreon orange-red
        )
        
        embed.set_footer(
            text="💡 This message appears occasionally to support development • Thank you for understanding!",
            icon_url="https://i.imgur.com/8VJLPnq.png"  # Patreon logo
        )
        
        # Create view with button
        view = discord.ui.View()
        button = discord.ui.Button(
            label="🎁 Become a Patron",
            style=discord.ButtonStyle.link,
            url=self.patreon_url,
            emoji="💎"
        )
        view.add_item(button)
        
        return embed, view
    
    def reset_channel(self, channel_id: str):
        """
        Reset counter for a specific channel.
        
        Args:
            channel_id: The Discord channel ID as string
        """
        self.channel_counters[channel_id] = 0
        self.channel_thresholds[channel_id] = random.randint(self.min_messages, self.max_messages)
    
    def get_channel_status(self, channel_id: str) -> dict:
        """
        Get current status for a channel.
        
        Args:
            channel_id: The Discord channel ID as string
            
        Returns:
            dict: Status information including count and threshold
        """
        return {
            "current_count": self.channel_counters[channel_id],
            "threshold": self.channel_thresholds[channel_id],
            "remaining": self.channel_thresholds[channel_id] - self.channel_counters[channel_id]
      }
