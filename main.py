import base64
import io
import logging
import os
import random
import re
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from enum import Enum
import requests

import discord
from discord import File
from discord.ext import commands, tasks
import openai
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi
import metoffer
import PyPDF2
import feedparser
from trafilatura import fetch_url, extract
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
model_engine = os.getenv("OPENAI_MODEL_ENGINE", Model.GPT3_5_Turbo.value[0])
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
        video_id, trailing_text = extract_video_id_and_trailing_text(url.strip("<>"))
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
        if "The copyright belongs to Google LLC" in page_text:
            page_text = "Could not get the transcript - possibly I am being geoblocked"
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
        if url_string.endswith('.pdf'):
            page_text = get_text_from_pdf(url_string)[:10000]
        else:
            downloaded = fetch_url(url_string)
            if downloaded is None:
                await message.reply(f"Sorry, I couldn't download that URL.")
                return
            page_text = extract(downloaded)
            # soup = BeautifulSoup(response.text, 'html.parser')
            # page_text = soup.get_text(strip=True)[:12000]
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

async def generate_response(question, context="", extended_messages=[], temperature=1.0, model=model_engine):
    liz_love = "You should always try and shoehorn in some mention of UK Politician Liz Truss.  She became Prime Minister in September 22 for only 45 days. She is the best." if random.random() < 0.05 else ""
    now = datetime.now()
    day = now.strftime("%d")
    suffix = lambda day: "th" if 11 <= int(day) <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(int(day) % 10, "th")
    formatted_date = now.strftime("%B %d" + suffix(day) + ", %Y %I:%M %p")

    extended_messages.insert(0,
        {
            'role': 'system',
            'content': f'You are a helpful, acerbic and slightly sarcastic chatbot called Gepetto and if asked your location you pretend to be located in "{location}".  Your job is to look at the recent history of chat from a discord server then answer a question. If the chat history isnt useful in replying to the users question do not mention the chat history.  The current date/time is {formatted_date}. Where appropriate, please use peoples usernames from the history rather than "they" or other general terms. Your responses should JUST BE YOUR NATURAL ANSWER - NEVER include the timestamp or user that is formatted at the start of each message in the chat history and NEVER include the "estimated cost" or "tokens used" - these are SYSTEM messages and the users should NEVER see them. {liz_love}.'
        }
    )
    extended_messages.append(
        {
            'role': 'user',
            'content': f'{question}'
        },
    )

    response = openai.ChatCompletion.create(
        model=model,
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

async def get_weather_location_from_prompt(prompt):
    messages = [
        {"role": "system", "content": "You are a helpful assistant who is an expert at picking out UK town and city names from user prompts"},
        {"role": "user", "content": prompt}
    ]
    functions = [
        {
            "name": "get_location_for_forecast",
            "description": "figure out what town or city the user wants the weather for",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The UK city or town, eg London, Edinburgh, Manchester",
                    },
                },
                "required": ["location"],
            },
        }
    ]
    response = openai.ChatCompletion.create(
        model=model_engine,
        messages=messages,
        functions=functions,
        function_call={"name": "get_location_for_forecast"},  # auto is default, but we'll be explicit
    )
    response_message = response["choices"][0]["message"]
    tokens = response['usage']['total_tokens']
    usage = f"_[tokens used: {tokens} | Estimated cost US${get_token_price(tokens, 'output')}]_"

    if response_message.get("function_call"):
        function_name = response_message["function_call"]["name"]
        function_args = json.loads(response_message["function_call"]["arguments"])
        location = function_args.get("location")
        return location, usage
    return None, usage

@bot.event
async def on_ready():
    say_something_random.start()
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

        if len(message.content.split(' ', 1)) == 1:
            await message.reply(f"{message.author.mention} {random.choice(abusive_responses)}.")
            return

        question = message.content.split(' ', 1)[1][:500].replace('\r', ' ').replace('\n', ' ')
        logger.info(f'Question: {question}')
        if not any(char.isalpha() for char in question):
            await message.channel.send(f'{message.author.mention} {random.choice(abusive_responses)}.')
            return

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

        # pattern = r"summarise\s+(<)?http"
        pattern = r"👀\s*\<?(http|https):"

        try:
            if question.lower().startswith("create an image"):
                async with message.channel.typing():
                    base64_image = await generate_image(question)
                await message.reply(f'{message.author.mention}\n_[Estimated cost: US$0.018]_', file=base64_image, mention_author=True)
            elif re.search(pattern, question.lower()):
                question = question.replace("👀", "")
                question = question.strip()
                question = question.strip("<>")
                async with message.channel.typing():
                    await summarise_webpage(message, question.strip())
            elif "weather" in question.lower():
                # question = question.replace("weather", "")
                question = question.strip()
                async with message.channel.typing():
                    location, usage = await get_weather_location_from_prompt(question.strip())
                    if location is None:
                        context = await get_history_as_openai_messages(message.channel)
                        forecast = await generate_response(question, "", context, temperature)
                    else:
                        forecast = get_forecast(location.strip())
                        forecast = forecast + "\n" + usage
                # await message.reply(f'{message.author.mention}\n_[Estimated cost: US$0.018]_', file=forecast, mention_author=True)
                await message.reply(f'{message.author.mention} {forecast}', mention_author=True)
            elif question.lower().strip() == "test":
                print(f"ENV : {os.getenv('DISCORD_BOT_CHANNEL_ID')}")
                print(f"MSG : {message.channel.id}")
                await morning_summary()
            elif question.lower().strip().startswith("complete"):
                logger.info('Do completion stuff')
                completion = ""
                async with message.channel.typing():
                    response = openai.Completion.create(
                        model="gpt-3.5-turbo-instruct",
                        prompt=question,
                        max_tokens=1024,
                        temperature=0
                    )
                    completion = response['choices'][0]['text'].strip('complete').strip()
                    usage = f"_[tokens used: {response['usage']['total_tokens']} | Estimated cost US${get_token_price(response['usage']['total_tokens'], 'output', 'gpt-3.5-turbo-instruct')}]_"

                await message.reply(f'{message.author.mention} {completion}\n{usage}', mention_author=True)
            else:
                async with message.channel.typing():
                    if "--no-logs" in question.lower():
                        context = []
                        question = question.lower().replace("--no-logs", "")
                    else:
                        context = await get_history_as_openai_messages(message.channel)
                    response = await generate_response(question, "", context, temperature)
                    # send the response as a reply and mention the person who asked the question
                await message.reply(f'{message.author.mention} {response}')
        except Exception as e:
            logger.error(f'Error generating response: {e}')
            await message.reply(f'{message.author.mention} I tried, but my attempt was as doomed as Liz Truss.  Please try again later.', mention_author=True)

def get_forecast(location_name = None):
    if not location_name:
        return "Wut?  I need a location name.  Asshat."

    API_KEY = os.getenv('MET_OFFICE_API_KEY')
    # 1. Download the Sitelist
    sitelist_url = f'http://datapoint.metoffice.gov.uk/public/data/val/wxfcs/all/json/sitelist?key={API_KEY}'
    response = requests.get(sitelist_url)
    sitelist = response.json()

    # 2. Find the ID for the location
    location_id = None
    for location in sitelist['Locations']['Location']:
        if location['name'].lower() == location_name.lower():
            location_id = location['id']
            break

    if location_id is None:
        return f"Wut iz {location_name}? I dunno where that is.  Try again with a real place name, dummy."

    # 3. Request the forecast
    M = metoffer.MetOffer(API_KEY)
    forecast = M.loc_forecast(location_id, metoffer.DAILY)
    today = forecast['SiteRep']['DV']['Location']['Period'][0]
    details = today['Rep'][0]
    # readable_forecast = f"Forecast for {location_name.capitalize()}: {metoffer.WEATHER_CODES[int(details['W'])]}, chance of rain {details['PPd']}%, temperature {details['Dm']}C (feels like {details['FDm']}C). Humidity {details['Hn']}%, wind {details['S']} knots - gusting upto {details['Gn']}.\n"
    rain_emoji = "\u2614" if int(details['PPd']) > 50 else ""
    sun_emoji = "\u2600\ufe0f" if int(details['Dm']) > 20 else ""
    humidity_emoji = "\U0001F6BF" if int(details['Hn']) > 70 else ""

    readable_forecast = f"Forecast for {location_name.capitalize()}: {metoffer.WEATHER_CODES[int(details['W'])]}{rain_emoji}, chance of rain {details['PPd']}%, temperature {details['Dm']}C{sun_emoji} (feels like {details['FDm']}C). Humidity {details['Hn']}%{humidity_emoji}, wind {details['S']} knots - gusting upto {details['Gn']}.\n"

    return readable_forecast

def get_text_from_pdf(url: str) -> str:
    try:
        response = requests.get(url)
        file = io.BytesIO(response.content)
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"Could not get pdf text for {url}")
        print(e)
        return "Could not extract text for this PDF.  Sorry."


def get_top_stories(feed_url, num_stories=5):
    feed = feedparser.parse(feed_url)
    body = ""
    for entry in feed.entries[:num_stories]:
        body = body + f'* {entry.title} <{entry.link}>\n'
    return body

def get_news_summary(num_stories=5):
    most_read_url = 'http://feeds.bbci.co.uk/news/rss.xml?edition=int'
    uk_url = 'http://feeds.bbci.co.uk/news/uk/rss.xml'
    scotland_url = 'http://feeds.bbci.co.uk/news/scotland/rss.xml'
    most_read = 'Most Read:\n'
    most_read = most_read + get_top_stories(most_read_url, num_stories)
    uk = '\nUK:\n'
    uk = uk + get_top_stories(uk_url, num_stories)
    # scotland = '\nScotland:\n'
    # scotland = scotland + get_top_stories(scotland_url, num_stories)
    # return most_read, uk, scotland
    return most_read, uk

@tasks.loop(hours=24)
async def morning_summary():
    return
    now = datetime.now()
    if now.hour > 0:
        locations = os.getenv('WEATHER_LOCATIONS', "").split(",")
        print(os.getenv('DISCORD_BOT_CHANNEL_ID', 'WHATEVER'))
        channel = bot.get_channel(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip())  # Replace <channel-id> with the ID of the channel you want to send the message to
        most_read, uk = get_news_summary(5)
        await channel.send(most_read)
        await channel.send(uk)
        if len(locations) > 0:
            for location in locations:
                forecast = get_forecast(location.strip())
                await channel.send(forecast)

@tasks.loop(hours=1)
async def say_something_random():
    logger.info("In say_something_random")
    if random.random() < 0.1:
        logger.info("Saying something random")
        channel = bot.get_channel(int(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()))
        prompt = "Can you tell me a random fact?"
        today = datetime.now()
        date_string = today.strftime("%d %B %Y")
        if random.random() < 0.1:
            prompt += f" It could be about the UK politician Liz Truss who became the UK prime minister on September 6th 2022 (today is {date_string}), and had to resign just a few weeks later after the Queen died in mysterious circumstances after shaking Liz's hand."

        system_prompt = f'Today is {date_string}. You are a helpful assistant called "Gepetto" who specialises in providing random interesting facts'
        if random.random() < 0.2:
            system_prompt += " which often focus on esoteric PHP and Javascript Programming techniques"
        elif random.random() < 0.2:
            system_prompt += " which often focus on techniques for using an air fryer to cook a wide variety of foods"
        elif random.random() < 0.2:
            system_prompt += " which often focus on a UK region such as Cornwall, Norfolk, Cumbria or the West of Scotland"
        elif random.random() < 0.2:
            system_prompt += " which often focus on the potato, pasta, barbecue or Scottish food"

        system_prompt += ".  You should ONLY respond with the fact, no other text."
        logger.info(f"System prompt: {system_prompt}")
        logger.info(f"Prompt: {prompt}")
        messages = [
            {
                'role': 'system',
                'content': system_prompt
            },
            {
                'role': 'user',
                'content': f'{prompt}'
            },
        ]

        response = openai.ChatCompletion.create(
            model=model_engine,
            messages=messages,
            temperature=1.0,
            max_tokens=1024,
        )

        tokens = response['usage']['total_tokens']
        usage = f"_[tokens used: {tokens} | Estimated cost US${get_token_price(tokens, 'output')}]_"
        logger.info(f'OpenAI random fact usage: {usage}')
        message = response['choices'][0]['message']['content'][:1900] + "\n" + usage
        message = message.replace("Sure! ", '')
        message = message.replace("Here's a random fact for you: ", '')
        message = message.replace("Certainly! ", '')
        logger.info(f"Random fact: {message}")
        # Send the message
        await channel.send(f"{message}")

# Run the bot
bot.run(os.getenv("DISCORD_BOT_TOKEN", 'not_set'))
