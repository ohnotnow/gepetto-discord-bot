import logging
import re
import io
from datetime import datetime
import requests
from discord import File
from utils import truncate
from gepetto import replicate, weather, summary, sentry

# These functions were moved from main.py to avoid circular imports

async def create_image(discord_message, prompt, model="black-forest-labs/flux-schnell"):
    logger = logging.getLogger('discord')
    logger.info(f"Creating image with model: {model} and prompt: {prompt}")
    image_url, model_name, cost = await replicate.generate_image(prompt, model=model)
    prompt_as_filename = f"{re.sub(r'[^a-zA-Z0-9]', '_', prompt)[:50]}_{datetime.now().strftime('%Y_%m_%d')}.png"
    logger.info("Fetching image")
    image = requests.get(image_url)
    discord_file = File(io.BytesIO(image.content), filename=prompt_as_filename)
    logger.info("Sending image to discord")
    await discord_message.reply(f'{discord_message.author.mention}\n_[Estimated cost: US${cost}] | Model: {model_name}_', file=discord_file)

async def get_weather_forecast(discord_message, prompt, locations, chatbot):
    forecast = await weather.get_friendly_forecast(prompt, None, locations)
    await discord_message.reply(f'{discord_message.author.mention} {forecast}', mention_author=True)

async def summarise_sentry_issue(discord_message, url, chatbot):
    issue_details, llm_prompt = await sentry.process_sentry_issue(url)
    await discord_message.reply(f'{discord_message.author.mention} {issue_details}', mention_author=True)
    messages = [
        {
            'role': 'system',
            'content': 'You are a an expert in debugging and analysing software issues.  You will be given a short overview of an issue from Sentry.  Your personality should be professional, but also a little jaded and possibly sarcastic.'
        },
        {
            'role': 'user',
            'content': f'{llm_prompt}'
        },
    ]
    response = await chatbot.chat(messages, temperature=1.0)
    message = truncate(response.message.strip(), 1800, '[... Truncated ...]') + "\n" + response.usage
    await discord_message.reply(f'{discord_message.author.mention} {message}', mention_author=True)

async def summarise_webpage_content(discord_message, prompt, url, chatbot):
    if 'sentry.io' in url:
        await summarise_sentry_issue(discord_message, url, chatbot)
        return
    original_text = await summary.get_text(url)
    words = original_text.split()
    if len(words) > 12000:
        logging.getLogger('discord').info(f"Original text to summarise is too long, truncating to 12000 words")
        original_text = ' '.join(words[:12000])
        was_truncated = True
    else:
        was_truncated = False
    prompt = prompt.replace("👀", "")
    prompt = prompt.strip()
    prompt = prompt.strip("<>")
    messages = [
        {
            'role': 'system',
            'content': 'You are a helpful assistant who specialises in providing concise, short summaries of text for Discord users. If the user doesn\'t seem to have provided text, then please politely ask them to provide it - they have probably just made a mistake when pasting into Discord. If it looks like they have pasted in some sort of "access denied" message, then please politely explain that the content is not available to a helpful assistant like yourself..'
        },
        {
            'role': 'user',
            'content': f'{prompt}? :: <text-to-summarise>\n\n{original_text}\n\n</text-to-summarise>'
        },
    ]
    response = await chatbot.chat(messages, temperature=1.0)
    summary_message = truncate(response.message, 1800, None) + "\n" + response.usage
    if was_truncated:
        summary_message = "[Note: The summary is based on a truncated version of the original text as it was too long.]\n\n" + summary_message
    await discord_message.reply(f"{summary_message}", mention_author=True)

async def extract_recipe_from_webpage(discord_message, prompt, url, chatbot):
    recipe_prompt = """
    Can you give me the ingredients (with UK quantities and weights) and the method for a recipe. Please list the
    ingredients in order and the method in order.  Please don't include any preamble or commentary.
    """
    await summarise_webpage_content(discord_message, recipe_prompt, url, chatbot)
