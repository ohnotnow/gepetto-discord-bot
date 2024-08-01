from datetime import datetime, timedelta
from collections import defaultdict

class BotGuard:
    def __init__(self, max_mentions=10, mention_window=timedelta(hours=1)):
        self.mention_counts = defaultdict(list)
        self.max_mentions = max_mentions
        self.mention_window = mention_window

    def should_block(self, message, bot, server_id):
        # ignore DM's
        if message.guild is None:
            print("Ignoring DM")
            return True
        # ignore messages not from our our server
        if str(message.guild.id) != server_id:
            print("Ignoring message from another server")
            return True
        # ignore messages from the bot itself
        if message.author == bot.user:
            print("Ignoring message from the bot itself")
            return True
        # ignore messages from other bots
        if message.author.bot:
            print("Ignoring message from another bot")
            return True
        # ignore messages without mentions
        if len(message.mentions) == 0:
            print("Ignoring message without mentions")
            return True
        # ignore messages where the bot is not mentioned
        if bot.user not in message.mentions:
            print("Ignoring message where the bot is not mentioned")
            return True
        # ignore messages without content
        if len(message.content.split(' ', 1)) == 1:
            print("Ignoring message without content")
            return True

        # keep track of how many times a user has mentioned the bot recently
        user_id = message.author.id
        now = datetime.utcnow()
        self.mention_counts[user_id].append(now)
        self.mention_counts[user_id] = [time for time in self.mention_counts[user_id]
                                        if now - time <= self.mention_window]

        # ignore when the user has mentioned the bot too many times recently
        if len(self.mention_counts[user_id]) > self.max_mentions:
            print("Ignoring message from user who has mentioned the bot too many times recently")
            return True

        # ignore when the message doesn't contain regular text (ie only contains mentions, emojis, spaces, etc)
        question = message.content.split(' ', 1)[1][:500].replace('\r', ' ').replace('\n', ' ')
        if not any(char.isalpha() for char in question):
            print("Ignoring message without regular text")
            return True

        # all good, allow the message
        print("Allowing message")
        return False
