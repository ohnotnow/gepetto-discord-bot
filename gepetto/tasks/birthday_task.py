import logging
from datetime import time
import pytz
from discord.ext import tasks
from gepetto import birthdays

logger = logging.getLogger('discord')

def register_birthday_task(bot, chatbot):
    @tasks.loop(time=time(hour=11, tzinfo=pytz.timezone('Europe/London')))
    async def say_happy_birthday():
        logger.info("In say_happy_birthday")
        await birthdays.get_birthday_message(bot, chatbot)
    say_happy_birthday.start()
