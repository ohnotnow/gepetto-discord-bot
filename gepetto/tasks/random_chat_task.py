import logging
import os
import random
from datetime import datetime
from discord.ext import tasks
from gepetto import gpt

logger = logging.getLogger('discord')

def register_random_chat_task(bot, chatbot):
    @tasks.loop(minutes=60)
    async def random_chat():
        logger.info("In random_chat")
        if not os.getenv("FEATURE_RANDOM_CHAT", False):
            logger.info("Not doing random chat because FEATURE_RANDOM_CHAT is not set")
            return
        if random.random() > 0.3:
            logger.info("Not joining in with chat because random number is too high")
            return
        now = datetime.now().time()
        start = datetime.strptime('23:00:00', '%H:%M:%S').time()
        end = datetime.strptime('07:00:00', '%H:%M:%S').time()
        if (now >= start and now <= end):
            logger.info("Not joining in with chat because it is night time")
            return
        channel = bot.get_channel(int(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()))
        from main import get_history_as_openai_messages  # Avoid circular import at top
        context = await get_history_as_openai_messages(channel, include_bot_messages=False, since_hours=0.5)
        context.append({
            'role': 'system',
            'content': os.getenv('DISCORD_BOT_DEFAULT_PROMPT')
        })
        if len(context) < 5:
            logger.info("Not joining in with chat because it is too quiet")
            return
        response = await chatbot.chat(context, temperature=1.0)
        await channel.send(f"{response.message[:1900]}\n{response.usage}")
    random_chat.start()
