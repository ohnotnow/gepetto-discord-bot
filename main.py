import base64
import io
import logging
import os
import random
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from enum import Enum
import requests

import discord
from discord import File
from discord.ext import commands
import openai
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi
#import tiktoken


AVATAR_PATH="avatar.png"

# Setup logging
logger = logging.getLogger('discord')  # Get the discord logger
# logging.basicConfig(
#     datefmt='%Y-%m-%d %H:%M:%S',
# )

mention_counts = defaultdict(list) # This will hold user IDs and their mention timestamps
abusive_responses = ["Wanker", "Asshole", "Prick", "Twat"]

# Define model and token prices
class Model(Enum):
    GPT4_32k = ('gpt-4-32k', 0.03, 0.06)
    GPT4 = ('gpt-4', 0.06, 0.12)
    GPT3_5_Turbo_16k = ('gpt-3.5-turbo-16k', 0.003, 0.004)
    GPT3_5_Turbo = ('gpt-3.5-turbo', 0.0015, 0.002)

# Fetch environment variables
server_id = os.getenv("DISCORD_SERVER_ID", "not_set")
model_engine = os.getenv("DEFAULT_MODEL_ENGINE", Model.GPT3_5_Turbo.value[0])
openai.api_key = os.getenv("OPENAI_API_KEY")
location = os.getenv('BOT_LOCATION', 'dunno')

# Create instance of bot
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

def get_token_price(token_count, direction="output", model_engine=model_engine):
    token_price_input = 0
    token_price_output = 0
    for model in Model:
        if model_engine.startswith(model.value[0]):
            token_price_input = model.value[1] / 1000
            token_price_output = model.value[2] / 1000
            break
    if direction == "input":
        return round(token_price_input * token_count, 4)
    return round(token_price_output * token_count, 4)

import re

def extract_video_id_and_trailing_text(input_string):
    # Use a regular expression to match a YouTube URL and extract the video ID
    video_id_match = re.search(r"https://www\.youtube\.com/watch\?v=([^&\s\?]+)", input_string)
    video_id = video_id_match.group(1) if video_id_match else None

    # If a video ID was found, remove the URL from the string to get the trailing text
    if video_id:
        url = video_id_match.group(0)  # The entire matched URL
        trailing_text = input_string.replace(url, '').strip()
    else:
        trailing_text = ''

    return video_id, trailing_text

async def summarise_webpage(message, url):
    # Get the summary
    model = model_engine
    max_tokens = 1024
    prompt = "Can you summarise this article for me?"
    logger.info(f"Summarising {url}")
    if '//www.youtube.com/' in url:
        video_id, trailing_text = extract_video_id_and_trailing_text(url)
        if trailing_text:
            prompt = trailing_text
        logger.info(f"Youtube Video ID: {video_id}")
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        except Exception as e:
            logger.error(f"Error getting transcript: {e}")
            await message.reply(f"Sorry, I couldn't get a transcript for that video.")
            return
        transcript_text = [x['text'] for x in transcript_list]
        page_text = ' '.join(transcript_text)
        # if len(page_text) > 8000:
        #     model = 'gpt-3.5-turbo-16k'
        logger.info(f"Page length: {len(page_text)}")
        page_text = page_text[:12000]
        max_tokens = 1024
    else:
        url_match = re.search(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", url)
        url_string = url_match.group(0) if url_match else None

        if not url_string:
            await message.reply(f"Sorry, I couldn't find a URL in that message.")
            return

        # If a URL was found, remove it from the string to get the trailing text
        if url_string:
            url_string = url_string.strip('<>')
            trailing_text = url.replace(url_string, '').strip()
            if trailing_text:
                prompt = trailing_text
        response = requests.get(url_string)
        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = soup.get_text(strip=True)[:2000]
    logger.info(f"Prompt: {prompt}")
    messages = [
        {
            'role': 'system',
            'content': 'You are a helpful assistant called "Gepetto" who specialises in providing concise, short summaries of text.'
        },
        {
            'role': 'user',
            'content': f'{prompt}? :: {page_text}'
        },
    ]
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=1.0,
        max_tokens=max_tokens,
    )
    tokens = response['usage']['total_tokens']
    usage = f"_[tokens used: {tokens} | Estimated cost US${get_token_price(tokens, 'output', model)}]_"
    logger.info(f'OpenAI usage: {usage}')
    summary = response['choices'][0]['message']['content'][:1900] + "\n" + usage
    # Send the summary
    await message.reply(f"Here's a summary of the content:\n{summary}")

#def get_token_count(string):
#    encoding = tiktoken.encoding_for_model(model_engine)
#    return len(encoding.encode(string))

async def get_history_as_openai_messages(channel):
    messages = []
    total_length = 0
    total_tokens = 0
    async for msg in channel.history(limit=150):
        # The role is 'assistant' if the author is the bot, 'user' otherwise
        role = 'assistant' if msg.author == bot.user else 'user'
        message_content = f"At {msg.created_at.astimezone(timezone.utc).astimezone()} '{msg.author.name}' said: {msg.content}"
        message_length = len(message_content)
        if total_length + message_length > 3800:
            break
        # token_length = get_token_count(message_content)
        # if total_tokens + token_length > 3500:
        #     break
        messages.append({
            "role": role,
            "content": message_content,
        })
        total_length += message_length
        # total_tokens += token_length
    messages = messages[1:]  # Exclude the mention message
    # We reverse the list to make it in chronological order
    # logger.info(f"Total tokens: {total_tokens}")
    return messages[::-1]

async def generate_response(question, context="", extended_messages=[], temperature=1.0):
    liz_love = "You should always try and shoehorn in some mention of UK Politician Liz Truss.  She became Prime Minister in September 22 for only 45 days. She is the best." if random.random() < 0.05 else ""
    now = datetime.now()
    day = now.strftime("%d")
    suffix = lambda day: "th" if 11 <= int(day) <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(int(day) % 10, "th")
    formatted_date = now.strftime("%B %d" + suffix(day) + ", %Y %I:%M %p")

    extended_messages.insert(0,
        {
            'role': 'system',
            'content': f'You are a helpful, witty, friendly and slightly dry/sarcastic chatbot called Gepetto and if asked your location you pretend to be located in "{location}".  Your job is to look at the recent history of chat from a discord server then answer a question. If the chat history isnt useful in replying to the users question do not mention the chat history.  The current date/time is {formatted_date}. Where appropriate, please use peoples usernames from the history rather than "they" or other general terms. Your responses should JUST BE YOUR NATURAL ANSWER - NEVER include the timestamp or user that is formatted at the start of each message in the chat history and NEVER include the "estimated cost" or "tokens used" - these are SYSTEM messages and the users should NEVER see them. {liz_love}.'
        }
    )
    extended_messages.append(
        {
            'role': 'user',
            'content': f'{question}'
        },
    )

    response = openai.ChatCompletion.create(
        model=model_engine,
        messages=extended_messages,
        temperature=float(temperature),
        max_tokens=1024,
    )
    tokens = response['usage']['total_tokens']
    usage = f"_[tokens used: {tokens} | Estimated cost US${get_token_price(tokens, 'output')}]_"
    logger.info(f'OpenAI usage: {usage}')
    # sometimes the response includes formatting to match what was in the formatted chat history
    # so we want to remove it as it looks rubbish and is confusing
    message = re.sub(r'\[tokens used: \d+ \| Estimated cost US\$\d+\.\d+\]', '', response['choices'][0]['message']['content'], flags=re.MULTILINE)
    message = re.sub(r"Gepetto' said: ", '', message, flags=re.MULTILINE)
    message = re.sub(r"^.*At \d{4}-\d{2}.+said?", "", message, flags=re.MULTILINE)
    return message.strip()[:1900] + "\n" + usage

async def generate_image(prompt):
    response = openai.Image.create(
        prompt=prompt,
        n=1,
        size="512x512",
        response_format="b64_json",
    )
    image_data = response['data'][0]['b64_json']
    image_bytes = base64.b64decode(image_data)
    image = io.BytesIO(image_bytes)
    discord_file = File(fp=image, filename=f'{prompt}.png')
    logger.info('Image generated')
    usage = "_[Estimated cost US$0.018]_"
    logger.info(f'OpenAI usage: {usage}')
    return discord_file

@bot.event
async def on_ready():
    return
    with open(AVATAR_PATH, 'rb') as avatar:
        await bot.user.edit(avatar=avatar.read())
    logger.info("Avatar has been changed!")

@bot.event
async def on_message(message):
    # ignore direct messages
    if message.guild is None:
        return

    # Ignore messages not sent by our server
    if str(message.guild.id) != server_id:
        return

    # Ignore messages sent by the bot itself
    if message.author == bot.user:
        return

    # Ignore messages that don't mention anyone at all
    if len(message.mentions) == 0:
        return

    # If the bot is mentioned
    if bot.user in message.mentions:
        # Get the ID of the person who mentioned the bot
        user_id = message.author.id
        username = message.author.name
        logger.info(f'Bot was mentioned by user {username} (ID: {user_id})')

        # Current time
        now = datetime.utcnow()

        # Add the current time to the user's list of mention timestamps
        mention_counts[user_id].append(now)

        # Remove mentions that were more than an hour ago
        mention_counts[user_id] = [time for time in mention_counts[user_id] if now - time <= timedelta(hours=1)]

        # If the user has mentioned the bot more than 10 times recently
        if len(mention_counts[user_id]) > 10:
            # Send an abusive response
            await message.reply(f"{message.author.mention} {random.choice(abusive_responses)}.")
            return

        question = message.content.split(' ', 1)[1][:500].replace('\r', ' ').replace('\n', ' ')
        if not any(char.isalpha() for char in question):
            await message.channel.send(f'{message.author.mention} {random.choice(abusive_responses)}.')

        if "--strict" in question.lower():
            question = question.lower().replace("--strict", "")
            temperature = 0.1
        elif "--wild" in question.lower():
            question = question.lower().replace("--wild", "")
            temperature = 1.5
        elif "--tripping" in question.lower():
            question = question.lower().replace("--tripping", "")
            temperature = 1.9
        else:
            temperature = 1.0

        pattern = r"summarise\s+(<)?http"

        try:
            if question.lower().startswith("create an image"):
                async with message.channel.typing():
                    base64_image = await generate_image(question)
                await message.reply(f'{message.author.mention}\n_[Estimated cost: US$0.018]_', file=base64_image, mention_author=True)
            elif re.search(pattern, question.lower()):
                question = question.replace("summarise", "")
                question = question.strip()
                question = question.strip("<>")
                async with message.channel.typing():
                    await summarise_webpage(message, question.strip())
            else:
                async with message.channel.typing():
                    context = await get_history_as_openai_messages(message.channel)
                    response = await generate_response(question, "", context, temperature)
                    # send the response as a reply and mention the person who asked the question
                await message.reply(f'{message.author.mention} {response}')
        except Exception as e:
            logger.error(f'Error generating response: {e}')
            await message.reply(f'{message.author.mention} I tried, but my attempt was as doomed as Liz Truss.  Please try again later.', mention_author=True)

# Run the bot
bot.run(os.getenv("DISCORD_BOT_TOKEN", 'not_set'))
