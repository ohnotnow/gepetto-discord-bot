import base64
import asyncio
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
import traceback
from gepetto import mistral, dalle, summary, weather, random_facts, birthdays, gpt, stats, groq, claude, ollama, guard, replicate, tools, images, gemini, sentry, openrouter, memory
from gepetto import response as gepetto_response
from gepetto import websearch as gepetto_websearch
from gepetto import perplexity
from gepetto import sora
from gepetto.response import split_for_discord
import discord
from discord import File
from discord.ext import commands, tasks
import openai
import feedparser


AVATAR_PATH="avatar.png"
previous_image_description = "Here is my image based on recent chat in my Discord server!"
previous_image_reasoning = "Dunno"
previous_image_prompt = "Dunno"
previous_image_themes = ""
previous_reasoning_content = ""
previous_themes = []
horror_history = []
daily_image_count = 0

# Setup logging
logger = logging.getLogger('discord')  # Get the discord logger
# logging.basicConfig(
#     datefmt='%Y-%m-%d %H:%M:%S',
# )

mention_counts = defaultdict(list) # This will hold user IDs and their mention timestamps
abusive_responses = ["Wanker", "Asshole", "Prick", "Twat", "Asshat", "Knob", "Dick", "Tosser", "Cow", "Cockwomble", "Anorak", "Knickers", "Fanny", "Sigh", "Big girl's blouse"]

# Fetch environment variables
server_id = os.getenv("DISCORD_SERVER_ID", "not_set")
# model_engine = os.getenv("OPENAI_MODEL_ENGINE", gpt.Model.GPT_4_OMNI.value[0])
model_engine = "gpt-4.1-mini"

# openai.api_key = os.getenv("OPENAI_API_KEY")
location = os.getenv('BOT_LOCATION', 'dunno')
chat_image_hour = int(os.getenv('CHAT_IMAGE_HOUR', 18))

AUTO_INVESTIGATE_SENTRY_ISSUES = os.getenv("AUTO_INVESTIGATE_SENTRY_ISSUES", False)


# Create instance of bot
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
import re


#def get_token_count(string):
#    encoding = tiktoken.encoding_for_model(model_engine)
#    return len(encoding.encode(string))

def get_chatbot():
    chatbot = None
    logger.info("BOT_PROVIDER: " + os.getenv("BOT_PROVIDER"))
    if os.getenv("BOT_PROVIDER") == 'mistral':
        chatbot = mistral.MistralModel()
    elif os.getenv("BOT_PROVIDER") == 'groq':
        chatbot = groq.GroqModel()
    elif os.getenv("BOT_PROVIDER") == 'anthropic':
        chatbot = claude.ClaudeModel()
    elif os.getenv("BOT_PROVIDER") == 'ollama':
        chatbot = ollama.OllamaModel()
    elif os.getenv("BOT_PROVIDER") == 'gemini':
        chatbot = gemini.GeminiModel()
    elif os.getenv("BOT_PROVIDER") == 'openrouter':
        chatbot = openrouter.OpenrouterModel()
    else:
        chatbot = gpt.GPTModel()
    return chatbot

def remove_nsfw_words(message):
    message = re.sub("(fuck|prick|asshole|shit|wanker|dick|liz|truss)", "", message, flags=re.IGNORECASE)
    return message

async def get_history_as_openai_messages(channel, include_bot_messages=True, limit=10, since_hours=None, nsfw_filter=False, max_length=1000, include_timestamps=True):
    messages = []
    total_length = 0
    total_tokens = 0
    after_time = datetime.now() - timedelta(hours=8)
    async for msg in channel.history(limit=limit, after=after_time):
        # bail out if the message was by a bot and we don't want bot messages included
        if (not include_bot_messages) and (msg.author.bot):
            continue
        # The role is 'assistant' if the author is the bot, 'user' otherwise
        role = 'assistant' if msg.author == bot.user else 'user'
        username = "" if msg.author == bot.user else msg.author.name
        content = remove_emoji(msg.content)
        if include_timestamps:
            message_content = f"At {msg.created_at.astimezone(timezone.utc).astimezone()} '{msg.author.name}' said: {content}"
        else:
            message_content = f"'{msg.author.name}' said: {content}"
        # message_content = f"User '{username}' said : {content}"
        message_content = re.sub(r'\[tokens used.+Estimated cost.+]', '', message_content, flags=re.MULTILINE)
        message_content = remove_nsfw_words(message_content)
        message_length = len(message_content)
        # if total_length + message_length > max_length:
        #     break
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
    logger.info(f"Length of messages: {len(messages)}")
    for message in messages:
        logger.info(f"Message: {message['content']}")

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

    response = await chatbot.chat(extended_messages, temperature=temperature)
    return response

async def reply_to_message(message, response):
    chunks = split_for_discord(response)
    for i, chunk in enumerate(chunks):
        if i == 0:
            await message.reply(f'{message.author.mention} {chunk}')
        else:
            await message.reply(f'{chunk}')
        await asyncio.sleep(0.1)

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
    logger.info(f"Starting discord bot - date time in python is {datetime.now()}")
    if os.getenv("DISCORD_BOT_BIRTHDAYS", None):
        logger.info("Starting say_happy_birthday task")
        say_happy_birthday.start()
    if os.getenv("CHAT_IMAGE_ENABLED", False):
        logger.info(f"Starting make_chat_image task with hour {chat_image_hour}")
        make_chat_image.start()
    if os.getenv("CHAT_VIDEO_ENABLED", False):
        logger.info(f"Starting make_chat_video task")
        make_chat_video.start()
    if os.getenv("FEATURE_HORROR_CHAT", False):
        logger.info("Starting horror_chat task")
        horror_chat.start()
    logger.info(f"Using model type : {type(chatbot)}")
    return
    with open(AVATAR_PATH, 'rb') as avatar:
        await bot.user.edit(avatar=avatar.read())
    logger.info("Avatar has been changed!")

async def websearch(discord_message: discord.Message, prompt: str) -> None:
    response = await perplexity.search(prompt)
    # response = await gepetto_websearch.websearch(prompt)
    response = "🌍" + response
    await reply_to_message(discord_message, response)

async def create_image(discord_message: discord.Message, prompt: str, model: str = "black-forest-labs/flux-schnell") -> None:
    logger.info(f"Creating image with model: {model} and prompt: {prompt}")
    global daily_image_count
    daily_image_count += 1
    if daily_image_count > 10:
        logger.info("Not creating image because daily image count is too high")
        await discord_message.reply(f'Due to budget cuts, I can only generate 10 images per day.', mention_author=True)
        return
    image_url, model_name, cost = await replicate.generate_image(prompt)
    prompt_as_filename = f"{re.sub(r'[^a-zA-Z0-9]', '_', prompt)[:50]}_{datetime.now().strftime('%Y_%m_%d')}.png"
    logger.info("Fetching image")
    image = requests.get(image_url)
    discord_file = File(io.BytesIO(image.content), filename=prompt_as_filename)
    logger.info("Sending image to discord")
    await discord_message.reply(f'{discord_message.author.mention}\n_[Estimated cost: US${cost}] | Model: {model_name}_', file=discord_file)

async def get_weather_forecast(discord_message: discord.Message, prompt: str) -> None:
    logger.info(f"Getting weather forecast for '{prompt}'")
    forecast = await weather.get_friendly_forecast_openweathermap(prompt, chatbot)
    await discord_message.reply(f'{discord_message.author.mention} {forecast}', mention_author=True)

async def summarise_sentry_issue(discord_message: discord.Message, url: str) -> None:
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
    message = response.message.strip()[:1800] + "\n" + response.usage
    await discord_message.reply(f'{discord_message.author.mention} {message}', mention_author=True)

async def summarise_webpage_content(discord_message: discord.Message, prompt: str, url: str) -> None:
    if 'sentry.io' in url:
        await summarise_sentry_issue(discord_message, url)
        return
    logger.info(f"Summarising webpage content for '{url}'")
    original_text = await summary.get_text(url)
    # split the original_text into words, then truncate to max of 12000 words
    words = original_text.split()
    if len(words) > 12000:
        logger.info(f"Original text to summarise is too long, truncating to 12000 words")
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
            'content': f'{prompt}? :: <text-to-summarise>\n\n{original_text}\n\n</text-to-summarise>.  **Important**  Keep your summary brief and to the point!'
        },
    ]
    response = await chatbot.chat(messages, temperature=1.0)
    # chunk the response.message into 1800 character chunks
    await reply_to_message(discord_message, response.message)
    if was_truncated:
        await discord_message.reply(f"[Note: The summary is based on a truncated version of the original text as it was too long.]", mention_author=True)


async def extract_recipe_from_webpage(discord_message: discord.Message, prompt: str, url: str) -> None:
    recipe_prompt = """
    Can you give me the ingredients (with UK quantities and weights) and the method for a recipe. Please list the
    ingredients in order and the method in order.  If there are any ingredients which are unlikely to be found in a normal UK
    supermarket, then please list the original but suggest a UK alternative. Please don't include any preamble or commentary.
    """
    await summarise_webpage_content(discord_message, recipe_prompt, url)

@bot.event
async def on_message(message):
    global previous_reasoning_content
#    if AUTO_INVESTIGATE_SENTRY_ISSUES and 'sentry.io/issues' in message.content:
        # sentry alert url is of the form https://university-of-glasgo-1c05fc43a.sentry.io/issues/6672435553/?alert_rule_id=14799200&alert_type=issue&notification_uuid=2f09f6a7-77fe-4189-8556-749aa4b8e997&project=4506224344039424&referrer=discord
        # we need to extract the entire sentry url from the message using regex
#        sentry_url = re.search(r'https://.*sentry\.io/issues/.*', message.content).group(0)
#        await summarise_sentry_issue(message, sentry_url)
#        return
    message_blocked, abusive_reply = guard.should_block(message, bot, server_id, chatbot)
    if message_blocked:
        if abusive_reply:
            logger.info("Blocked message from: " + message.author.name + " and abusing them")
            await message.channel.send(f"{random.choice(abusive_responses)}.")
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
        async with message.channel.typing():
            #if "--no-logs" in question.lower() or isinstance(chatbot, mistral.MistralModel):
            if "--no-logs" in lq:
                context = []
                question = question.replace("--no-logs", "")
            else:
                if chatbot.uses_logs:
                    context = await get_history_as_openai_messages(message.channel)
                else:
                    context = []
            if '--serious' in lq:
                question = question.replace("--serious", "")
                system_prompt = "You should respond in a very serious, professional and formal manner.  The user is a professional and simply wants a clear answer to their question."
            else:
                system_prompt = None
            if message.author.bot:
                question = question + ". Please be very concise, curt and to the point.  The user in this case is a discord bot."
            if lq.startswith("!image"):
                await make_chat_image()
                return
            if lq.startswith("!video"):
                await make_chat_video()
                return
            if '--rewrite' in lq:
                question = question.replace("--rewrite", "")
                rewrite_mode = True
            else:
                rewrite_mode = False
            if '--o1' in lq:
                question = question.replace("--o1", "")
                override_model = gpt.Model.GPT_O1_MINI.value[0]
            else:
                override_model = None
            optional_args = {}
            if override_model is not None:
                optional_args['model'] = override_model
            if '--reasoning' in lq:
                await message.reply(f'{message.author.mention} **Reasoning:** {previous_image_reasoning}\n**Themes:** {previous_image_themes}\n**Image Prompt:** {previous_image_prompt}'[:1800], mention_author=True)
                return
            if '--thinking' in lq:
                await message.reply(f'{message.author.mention} **Thinking:** {previous_reasoning_content}', mention_author=True)
                return

            # Add user context to the question so LLM knows Discord user info and can use memory tools
            user_context = f"[User: {message.author.name} (ID: {message.author.id})] "
            question_with_context = user_context + question
            if rewrite_mode:
                rewrite_prompt = f"The user has asked the following question.  Your task is to rewrite the question to be much clearer when it is given to another LLM to answer.  The purpose of the rewrite is to get the best possible answer to the original question.  Please respond with only the rewritten question, no other chat or commentary as your response will be passed directly to another LLM.  <original-question>\n{question_with_context}\n</original-question>"
                response = await chatbot.chat([{
                    'role': 'user',
                    'content': rewrite_prompt
                }])
                question_with_context = response.message
                logger.info(f"Rewritten question: {question_with_context}")
            messages = build_messages(question_with_context, context, system_prompt=system_prompt)
            response = await chatbot.chat(messages, temperature=temperature, tools=tools.tool_list, **optional_args)
            if response.reasoning_content:
                previous_reasoning_content = response.reasoning_content[:1800]
            if response.tool_calls:
                tool_call = response.tool_calls[0]
                arguments = json.loads(tool_call.function.arguments)
                fname = tool_call.function.name
                if fname == 'extract_recipe_from_webpage':
                    recipe_url = arguments.get('url', '')
                    if ('example.com' in recipe_url) or ('http' not in lq):
                        original_usage = response.usage
                        response = await chatbot.chat(messages, temperature=temperature, tools=[], **optional_args)
                        response = response.message.strip()[:1800] + "\n" + response.usage + "\n" + original_usage
                        await message.reply(f'{message.author.mention} {response}')
                    else:
                        await extract_recipe_from_webpage(message, arguments.get('prompt', ''), arguments.get('url', ''))
                elif fname == 'get_weather_forecast':
                    await get_weather_forecast(message, arguments.get('prompt', ''))
                elif fname == 'get_sentry_issue_summary':
                    await summarise_sentry_issue(message, arguments.get('url', ''))
                elif fname == 'summarise_webpage_content':
                    await summarise_webpage_content(message, arguments.get('prompt', ''), arguments.get('url', ''))
                elif fname == 'create_image':
                    await create_image(message, arguments.get('prompt', ''), model="nvidia/sana:88312dcb9eaa543d7f8721e092053e8bb901a45a5d3c63c84e0a5aa7c247df33")
                elif fname == 'user_information':
                    discord_user_id = arguments.get('discord_user_id', str(message.author.id))
                    user_info = await memory.user_information(discord_user_id)
                    messages.append({
                        'role': 'user',
                        'content': f'{user_info}'
                    })
                    response = await chatbot.chat(messages, temperature=temperature, tools=[], **optional_args)
                    response_text = response.message.strip()[:1800] + "\n" + response.usage
                    await message.reply(f'{message.author.mention} {response}')
                    return
                elif fname == 'store_user_information':
                    discord_user_id = arguments.get('discord_user_id', str(message.author.id))
                    information = arguments.get('information', '')
                    result = await memory.store_user_information(discord_user_id, information)
                    response = await chatbot.chat(messages, temperature=temperature, tools=[], **optional_args)
                    response_text = response.message.strip()[:1800] + "\n" + response.usage
                    await message.reply(f'{message.author.mention} {response}')
                    return
                elif fname == 'web_search':
                    await websearch(message, arguments.get('prompt', ''))
                    return
                else:
                    logger.info(f'Unknown tool call: {fname}')
                    await message.reply(f'{message.author.mention} I am a silly sausage and don\'t know how to do that.', mention_author=True)
                return
            else:
                response_text = response.message
                response_text = re.sub(r'\[tokens used.+Estimated cost.+]', '', response_text, flags=re.MULTILINE)
                response_text = re.sub(r"Gepetto' said: ", '', response_text, flags=re.MULTILINE)
                response_text = re.sub(r"Minxie' said: ", '', response_text, flags=re.MULTILINE)
                response_text = re.sub(r"^.*At \d{4}-\d{2}.+said?", "", response_text, flags=re.MULTILINE)
                logger.info(response.usage)
                response = response_text.strip() + "\n" + response.usage_short
            await reply_to_message(message, response)
    except Exception as e:
        logger.error(f'Error generating response: {traceback.format_exc()}')
        await message.reply(f'{message.author.mention} I tried, but my attempt was as doomed as Liz Truss.  Please try again later.', mention_author=True)


@tasks.loop(time=time(hour=11, tzinfo=pytz.timezone('Europe/London')))
async def say_happy_birthday():
    logger.info("In say_happy_birthday")
    await birthdays.get_birthday_message(bot, chatbot)

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

@tasks.loop(minutes=60)
async def horror_chat():
    global horror_history
    # if the latest horror_history timestamp is within 8hrs, then don't do horror chat
    if horror_history and (datetime.now() - datetime.strptime(horror_history[-1]['timestamp'], "%B %dth, %Y %I:%M %p")).total_seconds() < 8 * 60 * 60:
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
    text_date_time = now.strftime("%-I:%M %p")  # Change the format to include hours, minutes, and AM/PM without leading zero
    formatted_date_time = f"{formatted_date} {text_date_time}"
    start = datetime.strptime('07:00:00', '%H:%M:%S').time()
    end = datetime.strptime('19:50:00', '%H:%M:%S').time()
    now = datetime.now().time()  # Convert current time to datetime object
    if (now >= start and now <= end):
        logger.info("Not doing horror chat because it is day time")
        return
    channel = bot.get_channel(int(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()))
    # context = await get_history_as_openai_messages(channel, include_bot_messages=False, since_hours=0.5)
    # if len(context) < 5:
    #     logger.info("Not joining in with chat because it is too quiet")
    #     return
    system_prompt = f"You are an AI bot who lurks in a Discord server for UK adult horror novelists.  You task is to write one or two short sentences that are creepy, scary or unsettling and convey the sense of an out-of-context line from a horror film.  You will be given the date and time and you can use that to add a sense of timeliness and season to your response. You should ONLY respond with those sentences, no other text. <example>I'm scared.</example> <example>I think I can hear someone outside. In the dark.</example> <example>There's something in the shadows.</example> <example>I think the bleeding has stopped now.  But he deserved it.</example>  <example>That's not the first time I've had to bury a body.</example>"
    previous_horror_history_messages = [x['message'] for x in horror_history]
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
    horror_history.append({
        "message": response.message,
        "timestamp": formatted_date_time
    })
    if len(horror_history) > 40:
        # truncate the history to the most recent 40 entries
        horror_history = horror_history[-40:]
    await channel.send(f"{response.message[:1900]}\n{response.usage_short}")


@tasks.loop(time=time(hour=chat_image_hour, tzinfo=pytz.timezone('Europe/London')))
async def make_chat_image():
    logger.info("In make_chat_image")
    global previous_image_description
    global previous_image_reasoning
    global previous_image_themes
    global previous_image_prompt
    global previous_reasoning_content
    try:
        with open('previous_image_themes.txt', 'r') as file:
            previous_image_themes = file.read()
    except Exception as e:
        logger.error(f'Error reading previous_image_themes.txt: {e}')
        previous_image_themes = ""
    # strip any blank lines and only keep the latest 10 lines from the end of the file
    previous_image_themes = "\n".join(previous_image_themes.splitlines()[-10:])
    if previous_image_themes:
        previous_image_themes = f"Please try and avoid repeating themes from the previous image themes.  Previously used themes are:\n{previous_image_themes}\n\n"
    if not os.getenv("CHAT_IMAGE_ENABLED", False):
        logger.info("Not making chat image because CHAT_IMAGE_ENABLED is not set")
        return
    channel = bot.get_channel(int(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()))
    async with channel.typing():
        history = await get_history_as_openai_messages(channel, limit=1000, nsfw_filter=True, max_length=15000, include_timestamps=False, since_hours=8)
        # if we have loads of messages, then truncate the history to the most recent 200 messages
        if len(history) > 200:
            history = history[-200:]
        logger.info(f"History length: {len(history)}")
        logger.info(f"Oldest 3 messages: {history[:3]}")
        logger.info(f"Most recent 3 messages: {history[-3:]}")
        # reverse the history due to discord.py's message ordering
        history.reverse()
        if len(history) < 2:
            # get the date as, eg "Sunday, 24th November 2024"
            # check if today is a weekend or obvious holiday
            if datetime.now().weekday() >= 5 or datetime.now().strftime("%B %d") in ["December 25", "December 26", "December 27", "December 28", "January 1", "January 2"]:
                logger.info("Not making chat image because today is a weekend or obvious holiday")
                return
            date_string = datetime.now().strftime("%A, %d% %B %Y")
            response = await chatbot.chat([{
                'role': 'user',
                'content': f"Today is {date_string}.  Could you please write a pithy, acerbic, sarcastic comment about how quiet the chat is in this discord server today?  If the date looks like a weekend, or a UK holiday, then take that into account when writing your response.  The users are all software developers and love nice food, interesting books, obscure sci-fi, cute cats.  They enjoy a somewhat jaded, cynical tone.  Please reply with only the sentence as it will be sent directly to Discord as a message."
            }])
            await channel.send(f"{response.message}")
            # return

        chat_history = ""
        for message in history:
            chat_history += f"{message['content']}\n"
        logger.info(f"Asking for chat prompt")
        full_prompt = images.build_nanobanana_prompt(chat_history, previous_image_themes)
        llm_chat_prompt = "N/A"
        llm_chat_themes = []
        llm_chat_reasoning = ""
        # else:
        #     combined_chat = images.get_initial_chat_image_prompt(chat_history, previous_image_themes)
        #     decoded_response = await images.get_image_response_from_llm(combined_chat, chatbot)
        #     logger.info(f"Decoded response: {decoded_response}")
        #     llm_chat_prompt = decoded_response.get("prompt", "")
        #     llm_chat_themes = decoded_response.get("themes", [])
        #     llm_chat_reasoning = decoded_response.get("reasoning", "")
        #     if not llm_chat_prompt:
        #         logger.info("No prompt in LLM JSON response, using the whole response")
        #         llm_chat_prompt = str(decoded_response)
        #     previous_image_prompt = llm_chat_prompt
        #     previous_image_themes = llm_chat_themes
        #     previous_image_reasoning = llm_chat_reasoning
        #     extra_guidelines = images.get_extra_guidelines()
        #     full_prompt = llm_chat_prompt + f"\n{extra_guidelines}"

        logger.info(f"Calling replicate to generate image")
        image_url, model_name, cost = await replicate.generate_image(full_prompt, enhance_prompt=False)
        logger.info(f"Image URL: {image_url} - model: {model_name} - cost: {cost}")
        if not image_url:
            logger.info('We did not get a file from API')
            await channel.send(f"Sorry, I tried to make an image but I failed (probably because of naughty words - tsk).")
            return
    image = requests.get(image_url)
    today_string = datetime.now().strftime("%Y-%m-%d")
    discord_file = File(io.BytesIO(image.content), filename=f'channel_summary_{today_string}.png')
    message = f'{chatbot.name}\'s chosen themes: _{", ".join(llm_chat_themes)}_\n_Model: {model_name}]  / Estimated cost: US${cost:.3f}_'

    if len(message) > 1900:
        message = message[:1900]
    await channel.send(f"{message}\n", file=discord_file)
    with open('previous_image_themes.txt', 'a') as file:
        file.write(f"\n{previous_image_themes}")


@tasks.loop(time=time(hour=chat_image_hour, minute=15, tzinfo=pytz.timezone('Europe/London')))
async def make_chat_video():
    logger.info("In make_chat_video")
    if not os.getenv("CHAT_VIDEO_ENABLED", False):
        logger.info("Not making chat video because CHAT_VIDEO_ENABLED is not set")
        return
    channel = bot.get_channel(int(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()))
    history = await get_history_as_openai_messages(channel, limit=1000, include_bot_messages=False, nsfw_filter=True, max_length=15000, include_timestamps=False, since_hours=8)
    # if we have loads of messages, then truncate the history to the most recent 200 messages
    if len(history) > 200:
        history = history[-200:]
    logger.info(f"History length: {len(history)}")
    logger.info(f"Oldest 3 messages: {history[:3]}")
    logger.info(f"Most recent 3 messages: {history[-3:]}")
    # reverse the history due to discord.py's message ordering
    history.reverse()
    if len(history) < 2:
        # get the date as, eg "Sunday, 24th November 2024"
        # check if today is a weekend or obvious holiday
        if datetime.now().weekday() >= 5 or datetime.now().strftime("%B %d") in ["December 25", "December 26", "December 27", "December 28", "January 1", "January 2"]:
            logger.info("Not making chat video because today is a weekend or obvious holiday")
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
    duration = 8
    with open('gepetto/video_prompt.md', 'r') as file:
        prompt = file.read()
    prompt = prompt + f"""
    <chat-history>
    {chat_history}
    </chat-history>
    """
    async with channel.typing():
        response = await chatbot.chat([{
            'role': 'user',
            'content': prompt
        }])
        logger.info(f"Video prompt: {response.message}")
        video_url, model_name, cost = await sora.generate_video(response.message, seconds=duration)
        # video_url, model_name, cost# = await replicate.generate_video(response.message)
        logger.info(f"Video URL: {video_url} - model: {model_name} - cost: {cost}")
        if not video_url:
            logger.info('We did not get a file from API')
            return
        today_string = datetime.now().strftime("%Y-%m-%d")
        video = requests.get(video_url)
        discord_file = File(io.BytesIO(video.content), filename=f'channel_summary_{today_string}.mp4')
        message = f'{response.message}\n_Model: {model_name}]  / Estimated cost: US${cost:.3f}_'
        await channel.send(f"{message}\n", file=discord_file)

@tasks.loop(time=time(hour=3, tzinfo=pytz.timezone('Europe/London')))
async def reset_daily_image_count():
    logger.info("In reset_daily_image_count")
    global daily_image_count
    daily_image_count = 0

# Run the bot
chatbot = get_chatbot()
if os.getenv("DISCORD_BOT_MODEL", None):
    chatbot.default_model = os.getenv("DISCORD_BOT_MODEL")
if os.getenv("BOT_NAME", None):
    chatbot.name = os.getenv("BOT_NAME")
guard = guard.BotGuard()
bot.run(os.getenv("DISCORD_BOT_TOKEN", 'not_set'))
