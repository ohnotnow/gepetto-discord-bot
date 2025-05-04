import logging
import os
from datetime import datetime, time as dt_time
import pytz
import requests
from discord import File
from discord.ext import tasks
from gepetto import images, replicate
import io

logger = logging.getLogger('discord')

def register_make_chat_image_task(bot, chatbot, state):
    chat_image_hour = int(os.getenv('CHAT_IMAGE_HOUR', 17))
    @tasks.loop(time=dt_time(hour=chat_image_hour, tzinfo=pytz.timezone('Europe/London')))
    async def make_chat_image():
        logger.info("In make_chat_image")
        try:
            with open('previous_image_themes.txt', 'r') as file:
                state.previous_image_themes = file.read()
        except Exception as e:
            logger.error(f'Error reading previous_image_themes.txt: {e}')
            state.previous_image_themes = ""
        state.previous_image_themes = "\n".join(state.previous_image_themes.splitlines()[-10:])
        if state.previous_image_themes:
            state.previous_image_themes = f"Please try and avoid repeating themes from the previous image themes.  Previously used themes are:\n{state.previous_image_themes}\n\n"
        if not os.getenv("CHAT_IMAGE_ENABLED", False):
            logger.info("Not making chat image because CHAT_IMAGE_ENABLED is not set")
            return
        image_model = "bytedance/sdxl-lightning-4step:5599ed30703defd1d160a25a63321b4dec97101d98b4674bcc56e41f62f35637"
        channel = bot.get_channel(int(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()))
        async with channel.typing():
            from main import get_history_as_openai_messages  # Avoid circular import
            history = await get_history_as_openai_messages(channel, limit=100, nsfw_filter=True, max_length=5000, include_timestamps=False, since_hours=8)
            if len(history) < 2:
                if datetime.now().weekday() >= 5 or datetime.now().strftime("%B %d") in ["December 25", "December 26", "December 27", "December 28", "January 1", "January 2"]:
                    logger.info("Not making chat image because today is a weekend or obvious holiday")
                    return
                date_string = datetime.now().strftime("%A, %d% %B %Y")
                response = await chatbot.chat([{
                    'role': 'user',
                    'content': f"Today is {date_string}.  Could you please write a pithy, acerbic, sarcastic comment about how quiet the chat is in this discord server today?  If the date looks like a weekend, or a UK holiday, then take that into account when writing your response.  The users are all software developers and love nice food, interesting books, obscure sci-fi, cute cats.  They enjoy a somewhat jaded, cynical tone.  Please reply with only the sentence as it will be sent directly to Discord as a message."
                }])
                await channel.send(f"{response.message}")
                return
            chat_history = ""
            for message in history:
                chat_history += f"{message['content']}\n"
            logger.info(f"Asking for chat prompt")
            combined_chat = images.get_initial_chat_image_prompt(chat_history, state.previous_image_themes)
            decoded_response = await images.get_image_response_from_llm("gemini", combined_chat)
            llm_chat_prompt = decoded_response["prompt"]
            llm_chat_themes = decoded_response["themes"]
            llm_chat_reasoning = decoded_response["reasoning"]
            state.previous_image_prompt = llm_chat_prompt
            state.previous_image_themes = llm_chat_themes
            state.previous_image_reasoning = llm_chat_reasoning
            extra_guidelines = images.get_extra_guidelines()
            full_prompt = llm_chat_prompt + f"\n{extra_guidelines}"
            logger.info(f"Calling replicate to generate image")
            image_url, model_name, cost = await replicate.generate_image(full_prompt, enhance_prompt=False, model=image_model)
            logger.info(f"Image URL: {image_url} - model: {model_name} - cost: {cost}")
            if not image_url:
                logger.info('We did not get a file from API')
                await channel.send(f"Sorry, I tried to make an image but I failed (probably because of naughty words - tsk).")
                return
            try:
                response = await chatbot.chat([{
                    'role': 'user',
                    'content': f"Could you rephrase the following sentence to make it sound more like a jaded, cynical human who works as a programmer wrote it? You can reword and restructure it any way you like - just keep it succinct and keep the sentiment and tone. <sentence>{state.previous_image_description}</sentence>.  Please reply with only the reworded sentence as it will be sent directly to Discord as a message."
                }])
            except Exception as e:
                logger.info(f'Error generating chat image response: {e}')
                from gepetto import response as gepetto_response
                response = gepetto_response.ChatResponse(message='Behold!', tokens=0, cost=0.0, model=chatbot.name)
        state.previous_image_description = response.message
        image = requests.get(image_url)
        today_string = datetime.now().strftime("%Y-%m-%d")
        discord_file = File(io.BytesIO(image.content), filename=f'channel_summary_{today_string}.png')
        message = f'{response.message}\n{chatbot.name}\'s chosen themes: _{", ".join(llm_chat_themes)}_\n_Model: {model_name}]  / Estimated cost: US${cost:.3f}_'
        if len(message) > 1900:
            message = message[:1900]
        await channel.send(f"{message}\n", file=discord_file)
        with open('previous_image_themes.txt', 'a') as file:
            file.write(f"\n{state.previous_image_themes}")
    make_chat_image.start()
