import base64
import io
import logging
import os
import random
import re
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone, time
import pytz
from enum import Enum
import requests

from gepetto import mistral, dalle, summary, weather, random_facts, birthdays, gpt, stats

import discord
from discord import File
from discord.ext import commands, tasks
import openai
import feedparser


AVATAR_PATH="avatar.png"

# Setup logging
logger = logging.getLogger('discord')  # Get the discord logger
# logging.basicConfig(
#     datefmt='%Y-%m-%d %H:%M:%S',
# )

mention_counts = defaultdict(list) # This will hold user IDs and their mention timestamps
abusive_responses = ["Wanker", "Asshole", "Prick", "Twat"]

# Fetch environment variables
server_id = os.getenv("DISCORD_SERVER_ID", "not_set")
model_engine = os.getenv("OPENAI_MODEL_ENGINE", gpt.Model.GPT3_5_Turbo.value[0])
openai.api_key = os.getenv("OPENAI_API_KEY")
location = os.getenv('BOT_LOCATION', 'dunno')

if os.getenv("BOT_PROVIDER") == 'mistral':
    chatbot = mistral.MistralModel()
else:
    chatbot = gpt.GPTModel()

# Create instance of bot
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
import re


#def get_token_count(string):
#    encoding = tiktoken.encoding_for_model(model_engine)
#    return len(encoding.encode(string))

async def get_history_as_openai_messages(channel, include_bot_messages=True, limit=50, since_hours=None):
    messages = []
    total_length = 0
    total_tokens = 0
    if since_hours:
        after_time = datetime.datetime.utcnow() - datetime.timedelta(hours=since_hours)
    else:
        after_time = None
    async for msg in channel.history(limit=limit, after=after_time):
        # bail out if the message was by a bot and we don't want bot messages included
        if (not include_bot_messages) and (msg.author.bot):
            continue
        # The role is 'assistant' if the author is the bot, 'user' otherwise
        role = 'assistant' if msg.author == bot.user else 'user'
        username = "" if msg.author == bot.user else msg.author.name
        # message_content = f"At {msg.created_at.astimezone(timezone.utc).astimezone()} '{msg.author.name}' said: {msg.content}"
        content = remove_emoji(msg.content)
        message_content = f"{content}"
        message_content = re.sub(r'\[tokens used.+Estimated cost.+]', '', message_content, flags=re.MULTILINE)
        message_length = len(message_content)
        if total_length + message_length > 1000:
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

def build_messages(question, extended_messages, system_prompt=None):
    liz_love = "You should always try and shoehorn in some mention of UK Politician Liz Truss.  She became Prime Minister in September 22 for only 45 days. She is the best." if random.random() < 0.05 else ""
    now = datetime.now()
    day = now.strftime("%d")
    suffix = lambda day: "th" if 11 <= int(day) <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(int(day) % 10, "th")
    formatted_date = now.strftime("%B %d" + suffix(day) + ", %Y %I:%M %p")
    if random.random() < 0.1 and system_prompt is None:
        default_prompt = os.getenv('DISCORD_BOT_ALTERNATE_PROMPT', None)
    if system_prompt is None:
        default_prompt = os.getenv('DISCORD_BOT_DEFAULT_PROMPT', f'You are a helpful AI assistant called "{chatbot.name}" who specialises in providing answers to questions.  You should ONLY respond with the answer, no other text.')
    else:
        default_prompt = system_prompt
    extended_messages.append(
        {
            'role': 'user',
            'content': f'{question}'
        },
    )
    extended_messages.append(
        {
            'role': 'system',
            'content': f'Today is {formatted_date}. {default_prompt} {liz_love}.'
        }
    )

    return extended_messages

async def generate_response(question, context="", extended_messages=[], temperature=1.0, model=model_engine, system_prompt=None):
    extended_messages = build_messages(question, extended_messages, system_prompt)

    response = await chatbot.chat(extended_messages, temperature=1.0)
    return response

def remove_emoji(text):
    regrex_pattern = re.compile(pattern = "["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                           "]+", flags = re.UNICODE)
    return regrex_pattern.sub(r'',text)

@bot.event
async def on_ready():
    say_something_random.start()
    say_happy_birthday.start()
    random_chat.start()
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
            lq = question.lower().strip()
            if lq.startswith("create an image") or lq.startswith("📷") or lq.startswith("🖌️") or lq.startswith("🖼️"):
                async with message.channel.typing():
                    base64_image = await dalle.generate_image(question)
                stats.update(message.author.id, message.author.name, 0, 0.04)
                await message.reply(f'{message.author.mention}\n_[Estimated cost: US$0.04]_', file=base64_image, mention_author=True)
            elif re.search(pattern, lq):
                question = question.replace("👀", "")
                question = question.strip()
                question = question.strip("<>")
                page_summary = ""
                async with message.channel.typing():
                    page_text = await summary.get_text(message, question.strip())
                    messages = [
                        {
                            'role': 'system',
                            'content': 'You are a helpful assistant who specialises in providing concise, short summaries of text.'
                        },
                        {
                            'role': 'user',
                            'content': f'{question}? :: {page_text}'
                        },
                    ]
                    response = await chatbot.chat(messages, temperature=1.0)
                    stats.update(message.author.id, message.author.name, response.tokens, response.cost)
                    page_summary = response.message[:1900] + "\n" + response.usage
                await message.reply(f"Here's a summary of the content:\n{page_summary}")
            elif "weather" in question.lower():
                question = question.strip()
                forecast = ""
                logger.info("Getting weather using " + type(chatbot).__name__)
                async with message.channel.typing():
                    forecast = await weather.get_friendly_forecast(question.strip(), chatbot)
                await message.reply(f'{message.author.mention} {forecast}', mention_author=True)
            elif question.lower().strip() == "test":
                print(f"ENV : {os.getenv('DISCORD_BOT_CHANNEL_ID')}")
                print(f"MSG : {message.channel.id}")
            elif question.lower().strip() == "stats":
                statistics = stats.get_stats()
                response = f"```json\n{json.dumps(statistics, indent=2)}\n```"
                await message.reply(f'{message.author.mention} {response}', mention_author=True)
            else:
                async with message.channel.typing():
                    #if "--no-logs" in question.lower() or isinstance(chatbot, mistral.MistralModel):
                    if "--no-logs" in question.lower():
                        context = []
                        question = question.lower().replace("--no-logs", "")
                    else:
                        context = await get_history_as_openai_messages(message.channel)
                    if message.author.bot:
                        question = question + ". Please be very concise, curt and to the point.  The user in this case is a discord bot."
                    messages = build_messages(question, context)
                    response = await chatbot.chat(messages, temperature=temperature)
                    response_text = response.message
                    response_text = re.sub(r'\[tokens used.+Estimated cost.+]', '', response_text, flags=re.MULTILINE)
                    response_text = re.sub(r"Gepetto' said: ", '', response_text, flags=re.MULTILINE)
                    response_text = re.sub(r"Minxie' said: ", '', response_text, flags=re.MULTILINE)
                    response_text = re.sub(r"^.*At \d{4}-\d{2}.+said?", "", response_text, flags=re.MULTILINE)
                    stats.update(message.author.id, message.author.name, response.tokens, response.cost)
                    response = response_text.strip()[:1900] + "\n" + response.usage
                    # send the response as a reply and mention the person who asked the question
                await message.reply(f'{message.author.mention} {response}')
        except Exception as e:
            logger.error(f'Error generating response: {e}')
            await message.reply(f'{message.author.mention} I tried, but my attempt was as doomed as Liz Truss.  Please try again later.', mention_author=True)


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

@tasks.loop(time=time(hour=9, tzinfo=pytz.timezone('Europe/London')))
async def say_happy_birthday():
    logger.info("In say_happy_birthday")
    await birthdays.say_happy_birthday(bot, chatbot)

@tasks.loop(minutes=60)
async def random_chat():
    logger.info("In random_chat")
    if isinstance(chatbot, mistral.MistralModel):
        logger.info("Not joining in with chat because we are using Mistral")
        return
    if random.random() > 0.3:
        logger.info("Not joining in with chat because random number is too high")
        return
    now = datetime.now().time()
    start = datetime.strptime('23:00:00', '%H:%M:%S').time()
    end = datetime.strptime('07:00:00', '%H:%M:%S').time()
    if (now >= start or now <= end):
        logger.info("Not joining in with chat because it is night time")
        return
    channel = bot.get_channel(int(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()))
    context = await get_history_as_openai_messages(channel, include_bot_messages=True, since_hourse=2)
    if len(context) < 3:
        return
    system_prompt = f'You are a helpful AI Discord bot called "{chatbot.name}" who reads the chat history of a Discord server and adds funny, ascerbic, sarcastic replies based on what has been happening.  Your reply should be natural and fit in with the flow of the conversation as if you were a human user chatting to your friends on Discord.  You should ONLY respond with the chat reply, no other text.  You can quote the text you are using as context by using markdown `> original text here` formatting if needed.'
    context.append(
        {
            'role': 'system',
            'content': system_prompt
        }
    )
    response = await chatbot.chat(context, temperature=1.0)
    await channel.send(f"{response.message[:1900]}\n{response.usage}")

@tasks.loop(hours=1)
async def say_something_random():
    logger.info("In say_something_random")
    if random.random() > 0.1:
        return
    if isinstance(chatbot, gpt.GPTModel):
        logger.info("Not saying something random because we are using GPT")
        return
    fact = await random_facts.get_fact(chatbot)
    channel = bot.get_channel(int(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()))
    await channel.send(f"{fact[:1900]}")

# Run the bot
bot.run(os.getenv("DISCORD_BOT_TOKEN", 'not_set'))
