from datetime import datetime, timedelta
from collections import defaultdict

from src.platforms.base import ChatMessage


class BotGuard:
    def __init__(self, max_mentions=10, mention_window=timedelta(hours=1)):
        self.mention_counts = defaultdict(list)
        self.max_mentions = max_mentions
        self.mention_window = mention_window

    def should_block(self, message: ChatMessage, bot_user_id: str, server_id: str, chatbot=None) -> tuple[bool, bool]:
        """
        Check if a message should be blocked.

        Args:
            message: The platform-agnostic message to check.
            bot_user_id: The bot's user ID.
            server_id: The ID of the server the bot is running on.

        Returns:
            bool: True if the message should be blocked, False otherwise.
            bool: True if the message should get an abusive reply, False otherwise.
        """
        # ignore DM's
        if not message.server_id:
            return True, False
        # ignore messages not from our server
        if message.server_id != server_id:
            return True, False
        # ignore messages from the bot itself
        if message.author_id == bot_user_id:
            return True, False
        # ignore messages from other bots
        if message.author_is_bot:
            return True, False
        if chatbot and chatbot.omnilistens:
            if chatbot.name.lower() in message.content.lower():
                return True, False
        else:
            # ignore messages where the bot is not mentioned
            if bot_user_id not in message.content:
                return True, False
        # ignore messages without content
        if len(message.content.split(' ', 1)) == 1:
            return True, True

        # keep track of how many times a user has mentioned the bot recently
        user_id = message.author_id
        now = datetime.utcnow()
        self.mention_counts[user_id].append(now)
        self.mention_counts[user_id] = [time for time in self.mention_counts[user_id]
                                        if now - time <= self.mention_window]

        # ignore when the user has mentioned the bot too many times recently
        if len(self.mention_counts[user_id]) > self.max_mentions:
            return True, True

        # ignore when the message doesn't contain regular text (ie only contains mentions, emojis, spaces, etc)
        question = message.content.split(' ', 1)[1][:500].replace('\r', ' ').replace('\n', ' ')
        if not any(char.isalpha() for char in question):
            return True, True

        # all good, allow the message
        return False, False
