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

from gepetto import mistral, dalle, summary, weather, random_facts, birthdays, gpt, stats, groq, claude, ollama, guard, replicate, tools, images, gemini
from gepetto import response as gepetto_response
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
previous_themes = []
horror_history = []

# Setup logging
logger = logging.getLogger('discord')  # Get the discord logger
# logging.basicConfig(
#     datefmt='%Y-%m-%d %H:%M:%S',
# )

mention_counts = defaultdict(list) # This will hold user IDs and their mention timestamps
abusive_responses = ["Wanker", "Asshole", "Prick", "Twat", "Asshat", "Knob", "Dick", "Tosser", "Cow", "Cockwomble", "Anorak", "Knickers", "Fanny", "Sigh", "Big girl's blouse"]

# Fetch environment variables
server_id = os.getenv("DISCORD_SERVER_ID", "not_set")
model_engine = os.getenv("OPENAI_MODEL_ENGINE", gpt.Model.GPT_4_OMNI.value[0])
openai.api_key = os.getenv("OPENAI_API_KEY")
location = os.getenv('BOT_LOCATION', 'dunno')



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
    elif os.getenv("BOT_PROVIDER") == 'claude':
        chatbot = claude.ClaudeModel()
    elif os.getenv("BOT_PROVIDER") == 'ollama':
        chatbot = ollama.OllamaModel()
    elif os.getenv("BOT_PROVIDER") == 'gemini':
        chatbot = gemini.GeminiModel()
    else:
        chatbot = gpt.GPTModel()
    return chatbot

def remove_nsfw_words(message):
    message = re.sub(r"(fuck|prick|asshole|shit|wanker|dick)", "", message)
    return message

async def get_history_as_openai_messages(channel, include_bot_messages=True, limit=10, since_hours=None, nsfw_filter=False, max_length=1000, include_timestamps=True):
    messages = []
    total_length = 0
    total_tokens = 0
    if since_hours:
        after_time = datetime.utcnow() - timedelta(hours=since_hours)
    else:
        after_time = None
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
        message_content = remove_nsfw_words(message_content) if nsfw_filter else message_content
        message_length = len(message_content)
        if total_length + message_length > max_length:
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

    response = await chatbot.chat(extended_messages, temperature=temperature)
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
    logger.info(f"Starting discord bot - date time in python is {datetime.now()}")
    say_happy_birthday.start()
    make_chat_image.start()
    horror_chat.start()
    logger.info(f"Using model type : {type(chatbot)}")
    return
    with open(AVATAR_PATH, 'rb') as avatar:
        await bot.user.edit(avatar=avatar.read())
    logger.info("Avatar has been changed!")

async def create_image(discord_message: discord.Message, prompt: str, model: str = "black-forest-labs/flux-schnell") -> None:
    if '--better' in prompt.lower():
        prompt = prompt.replace("--better", "")
        model = "black-forest-labs/flux-1.1-pro"
        logger.info("Using better image model")
    logger.info(f"Creating image with model: {model} and prompt: {prompt}")
    # response = await chatbot.chat([{ 'role': 'user', 'content': f"Please take this request and give me a detailed prompt for a Stable Diffusion image model so that it gives me a dramatic and intriguing image. <query>{prompt}</query>"}], temperature=1.0)
    image_url = await replicate.generate_image(prompt, model=model)
    logger.info("Fetching image")
    image = requests.get(image_url)
    discord_file = File(io.BytesIO(image.content), filename=f'channel_summary.png')
    if model == "black-forest-labs/flux-1.1-pro":
        cost = 0.04
    else:
        cost = 0.003
    logger.info("Sending image to discord")
    await discord_message.reply(f'{discord_message.author.mention}\n_[Estimated cost: US${cost}] | Model: {model}_', file=discord_file)

async def get_weather_forecast(discord_message: discord.Message, prompt: str, locations: list[str]) -> None:
    forecast = await weather.get_friendly_forecast(prompt, chatbot, locations)
    await discord_message.reply(f'{discord_message.author.mention} {forecast}', mention_author=True)

async def summarise_webpage_content(discord_message: discord.Message, prompt: str, url: str) -> None:
    original_text = await summary.get_text(url)
    if len(original_text) > 10000:
        logger.info(f"Original text to summarise is too long, truncating to 10000 characters")
        original_text = original_text[:10000]
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
    page_summary = response.message[:1800] + "\n" + response.usage
    if was_truncated:
        page_summary = "[Note: The summary is based on a truncated version of the original text as it was too long.]\n\n" + page_summary
    await discord_message.reply(f"{page_summary}", mention_author=True)

async def extract_recipe_from_webpage(discord_message: discord.Message, prompt: str, url: str) -> None:
    recipe_prompt = """
    Can you give me the ingredients (with UK quantities and weights) and the method for a recipe. Please list the
    ingredients in order and the method in order.  Please don't include any preamble or commentary.
    """
    await summarise_webpage_content(discord_message, recipe_prompt, url)

@bot.event
async def on_message(message):
    message_blocked, abusive_reply = guard.should_block(message, bot, server_id)
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
            if "--no-logs" in question.lower():
                context = []
                question = question.lower().replace("--no-logs", "")
            else:
                if chatbot.uses_logs:
                    context = await get_history_as_openai_messages(message.channel)
                else:
                    context = []
            if '--serious' in question.lower():
                question = question.lower().replace("--serious", "")
                system_prompt = "You should respond in a very serious, professional and formal manner.  The user is a professional and simply wants a clear answer to their question."
            else:
                system_prompt = None
            if message.author.bot:
                question = question + ". Please be very concise, curt and to the point.  The user in this case is a discord bot."
            if question.lower().startswith("!image"):
                await make_chat_image()
                return
            if '--o1' in question.lower():
                question = question.lower().replace("--o1", "")
                override_model = gpt.Model.GPT_O1_MINI.value[0]
            else:
                override_model = None
            optional_args = {}
            if override_model is not None:
                optional_args['model'] = override_model
            if '--reasoning' in question.lower():
                await message.reply(f'{message.author.mention} **Reasoning:** {previous_image_reasoning}\n**Themes:** {previous_image_themes}', mention_author=True)
                return
            messages = build_messages(question, context, system_prompt=system_prompt)
            response = await chatbot.chat(messages, temperature=temperature, tools=tools.tool_list, **optional_args)
            if response.tool_calls:
                tool_call = response.tool_calls[0]
                arguments = json.loads(tool_call.function.arguments)
                fname = tool_call.function.name
                if fname == 'extract_recipe_from_webpage':
                    recipe_url = arguments.get('url', '')
                    if ('example.com' in recipe_url) or ('http' not in question.lower()):
                        original_usage = response.usage
                        response = await chatbot.chat(messages, temperature=temperature, tools=[], **optional_args)
                        response = response.message.strip()[:1800] + "\n" + response.usage + "\n" + original_usage
                        await message.reply(f'{message.author.mention} {response}')
                    else:
                        await extract_recipe_from_webpage(message, arguments.get('prompt', ''), arguments.get('url', ''))
                elif fname == 'get_weather_forecast':
                    await get_weather_forecast(message, arguments.get('prompt', ''), arguments.get('locations', []))
                elif fname == 'summarise_webpage_content':
                    await summarise_webpage_content(message, arguments.get('prompt', ''), arguments.get('url', ''))
                elif fname == 'create_image':
                    await create_image(message, arguments.get('prompt', ''))
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
                response = response_text.strip()[:1900] + "\n" + response.usage
            await message.reply(f'{message.author.mention} {response}')
    except Exception as e:
        logger.error(f'Error generating response: {e}')
        await message.reply(f'{message.author.mention} I tried, but my attempt was as doomed as Liz Truss.  Please try again later.', mention_author=True)


@tasks.loop(time=time(hour=11, tzinfo=pytz.timezone('Europe/London')))
async def say_happy_birthday():
    logger.info("In say_happy_birthday")
    await birthdays.get_birthday_message(bot, chatbot)

@tasks.loop(minutes=60)
async def random_chat():
    logger.info("In random_chat")
    if not isinstance(chatbot, gpt.GPTModel):
        logger.info("Not joining in with chat because we are using non-gpt")
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
    context = await get_history_as_openai_messages(channel, include_bot_messages=False, since_hours=0.5)
    if len(context) < 5:
        logger.info("Not joining in with chat because it is too quiet")
        return
    system_prompt = f'You are a helpful AI Discord bot called "{chatbot.name}" who reads the chat history of a Discord server and adds funny, acerbic, sarcastic replies based on a single topic mentioned.  Your reply should be natural and fit in with the flow of the conversation as if you were a human user chatting to your friends on Discord.  You should ONLY respond with the chat reply, no other text.  You can quote the text you are using as context by using markdown `> original text here` formatting for context but do not @mention the user.'
    context.append(
        {
            'role': 'system',
            'content': system_prompt
        }
    )
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
    if not isinstance(chatbot, claude.ClaudeModel):
        logger.info("Not doing horror chat because we are not appropriate models")
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
    await channel.send(f"{response.message[:1900]}\n{response.usage}")


@tasks.loop(time=time(hour=17, tzinfo=pytz.timezone('Europe/London')))
async def make_chat_image():
    logger.info("In make_chat_image")
    global previous_image_description
    global previous_image_reasoning
    global previous_image_themes
    global previous_image_prompt

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
    if chatbot.name != "Minxie":
        logger.info("Not making chat image because we are not using Claude")
        return
    # logger.info('Generating chat image using model: ' + type(chatbot).__name__)
    channel = bot.get_channel(int(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()))
    async with channel.typing():
        history = await get_history_as_openai_messages(channel, limit=100, nsfw_filter=True, max_length=5000, include_timestamps=False)
        chat_history = ""
        for message in history:
            chat_history += f"{message['content']}\n"
        combined_chat = images.get_initial_chat_image_prompt(chat_history, previous_image_themes)
        response = await chatbot.chat([{ 'role': 'user', 'content': combined_chat }], temperature=1.0, json_mode=True)
        try:
            decoded_response = json.loads(response.message)
        except json.JSONDecodeError:
            logger.error(f'Error decoding JSON: {response.message}')
            decoded_response = {
                "prompt": response.message,
                "themes": [],
                "reasoning": ""
            }
        llm_chat_prompt = decoded_response["prompt"]
        llm_chat_themes = decoded_response["themes"]
        llm_chat_reasoning = decoded_response["reasoning"]
        previous_image_prompt = llm_chat_prompt
        previous_image_themes = llm_chat_themes
        previous_image_reasoning = llm_chat_reasoning
        extra_guidelines = images.get_extra_guidelines()
        full_prompt = llm_chat_prompt + f"\n{extra_guidelines}"

        image_url = await replicate.generate_image(full_prompt, enhance_prompt=False)
        logger.info("Image URL: " + image_url)
        if not image_url:
            logger.info('We did not get a file from API')
            await channel.send(f"Sorry, I tried to make an image but I failed (probably because of naughty words - tsk).")
            return
        try:
            response = await chatbot.chat([{
                'role': 'user',
                'content': f"Could you rephrase the following sentence to make it sound more like a jaded, cynical human who works as a programmer wrote it? You can reword and restructure it any way you like - just keep it succinct and keep the sentiment and tone. <sentence>{previous_image_description}</sentence>.  Please reply with only the reworded sentence as it will be sent directly to Discord as a message."
            }])
        except Exception as e:
            logger.info(f'Error generating chat image response: {e}')
            response = gepetto_response.ChatResponse(message='Behold!', tokens=0, cost=0.0, model=chatbot.name)
    previous_image_description = response.message
    previous_image_themes
    image = requests.get(image_url)
    today_string = datetime.now().strftime("%Y-%m-%d")
    discord_file = File(io.BytesIO(image.content), filename=f'channel_summary_{today_string}.png')
    message = f'{response.message}\n{chatbot.name}\'s chosen themes: _{", ".join(llm_chat_themes)}_'
    if len(message) > 1900:
        message = message[:1900]
    await channel.send(f"{message}\n_[Estimated cost: US$0.003]_", file=discord_file)
    with open('previous_image_themes.txt', 'a') as file:
        file.write(f"\n{previous_image_themes}")

# Run the bot
chatbot = get_chatbot()
if os.getenv("DISCORD_BOT_MODEL", None):
    chatbot.model = os.getenv("DISCORD_BOT_MODEL")
guard = guard.BotGuard()
bot.run(os.getenv("DISCORD_BOT_TOKEN", 'not_set'))
