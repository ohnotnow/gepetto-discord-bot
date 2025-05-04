import logging
import os
import random
from datetime import datetime
from discord.ext import tasks
import pytz
from utils import truncate

logger = logging.getLogger('discord')

def register_horror_chat_task(bot, chatbot, state):
    @tasks.loop(minutes=60)
    async def horror_chat():
        # if the latest horror_history timestamp is within 8hrs, then don't do horror chat
        if state.horror_history and (datetime.now() - datetime.strptime(state.horror_history[-1]['timestamp'], "%B %dth, %Y %I:%M %p")).total_seconds() < 8 * 60 * 60:
            logger.info("Not doing horror chat because we did it recently")
            return
        logger.info("In horror chat")
        if not os.getenv("FEATURE_HORROR_CHAT", False):
            logger.info("Not doing horror chat because FEATURE_HORROR_CHAT is not set")
            return
        if random.random() > 0.1:
            logger.info("Not doing horror chat because random number is too high")
            return
        now = datetime.now()
        suffix = lambda day: "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        formatted_date = now.strftime("%B %d" + suffix(now.day) + ", %Y")
        text_date_time = now.strftime("%-I:%M %p")
        formatted_date_time = f"{formatted_date} {text_date_time}"
        start = datetime.strptime('07:00:00', '%H:%M:%S').time()
        end = datetime.strptime('19:50:00', '%H:%M:%S').time()
        now_time = now.time()
        if (now_time >= start and now_time <= end):
            logger.info("Not doing horror chat because it is day time")
            return
        channel = bot.get_channel(int(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()))
        system_prompt = f"You are an AI bot who lurks in a Discord server for UK adult horror novelists.  You task is to write one or two short sentences that are creepy, scary or unsettling and convey the sense of an out-of-context line from a horror film.  You will be given the date and time and you can use that to add a sense of timeliness and season to your response. You should ONLY respond with those sentences, no other text. <example>I'm scared.</example> <example>I think I can hear someone outside. In the dark.</example> <example>There's something in the shadows.</example> <example>I think the bleeding has stopped now.  But he deserved it.</example>  <example>That's not the first time I've had to bury a body.</example>"
        previous_horror_history_messages = [x['message'] for x in state.horror_history]
        context = [
            {
                'role': 'system',
                'content': system_prompt
            },
            {
                'role': 'user',
                'content': f"It is {formatted_date_time}. Please give me a horror line - the creepier, the more unsettling, the more disturbing the better.  It should NOT repeat any of the following :" + "\n<previous-sentences>" + "\n- ".join(previous_horror_history_messages) + "\n</previous-sentences>",
            }
        ]
        response = await chatbot.chat(context, temperature=1.0)
        state.horror_history.append({
            "message": response.message,
            "timestamp": formatted_date_time
        })
        if len(state.horror_history) > 40:
            # truncate the history to the most recent 40 entries
            state.horror_history[:] = state.horror_history[-40:]
        await channel.send(f"{truncate(response.message, 1900, '[... Truncated ...]')}\n{response.usage}")
    horror_chat.start()
