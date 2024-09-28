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

from gepetto import mistral, dalle, summary, weather, random_facts, birthdays, gpt, stats, groq, claude, ollama, guard, replicate, tools

import discord
from discord import File
from discord.ext import commands, tasks
import openai
import feedparser


AVATAR_PATH="avatar.png"
previous_image_description = "Here is my image based on recent chat in my Discord server!"
previous_themes = ""
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
    else:
        chatbot = gpt.GPTModel()
    return chatbot

def remove_nsfw_words(message):
    message = re.sub(r"(fuck|prick|asshole|shit|wanker|dick)", "", message)
    return message

async def get_history_as_openai_messages(channel, include_bot_messages=True, limit=10, since_hours=None, nsfw_filter=False, max_length=1000):
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
        message_content = f"At {msg.created_at.astimezone(timezone.utc).astimezone()} '{msg.author.name}' said: {content}"
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
    say_happy_birthday.start()
    make_chat_image.start()
    horror_chat.start()
    logger.info(f"Using model type : {type(chatbot)}")
    return
    with open(AVATAR_PATH, 'rb') as avatar:
        await bot.user.edit(avatar=avatar.read())
    logger.info("Avatar has been changed!")

async def create_image(discord_message: discord.Message, prompt: str, model: str = "black-forest-labs/flux-schnell") -> None:
    response = await chatbot.chat([{ 'role': 'user', 'content': f"Please take this request and give me a detailed prompt for a Stable Diffusion image model so that it gives me a dramatic and intriguing image. <query>{prompt}</query>"}], temperature=1.0)
    image_url = await replicate.generate_image(response.message, model=model)
    image = requests.get(image_url)
    discord_file = File(io.BytesIO(image.content), filename=f'channel_summary.png')
    if model == "black-forest-labs/flux-dev":
        cost = 0.03
    else:
        cost = 0.003
    await discord_message.reply(f'{discord_message.author.mention}\n_[Estimated cost: US${cost}]_', file=discord_file)

async def get_weather_forecast(discord_message: discord.Message, prompt: str) -> None:
    forecast = await weather.get_friendly_forecast(prompt, chatbot)
    await discord_message.reply(f'{discord_message.author.mention} {forecast}', mention_author=True)

async def summarise_webpage_content(discord_message: discord.Message, prompt: str, url: str) -> None:
    summarised_text = await summary.get_text(url)
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
            'content': f'{prompt}? :: <text-to-summarise>\n\n{summarised_text}\n\n</text-to-summarise>'
        },
    ]
    response = await chatbot.chat(messages, temperature=1.0)
    page_summary = response.message[:1800] + "\n" + response.usage
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
            if '--o1' in question.lower():
                question = question.lower().replace("--o1", "")
                override_model = gpt.Model.GPT_O1_MINI.value[0]
            else:
                override_model = model_engine
            messages = build_messages(question, context, system_prompt=system_prompt)
            response = await chatbot.chat(messages, temperature=temperature, model=override_model, tools=tools.tool_list)
            if response.tool_calls:
                tool_call = response.tool_calls[0]
                arguments = json.loads(tool_call.function.arguments)
                fname = tool_call.function.name
                if fname == 'extract_recipe_from_webpage':
                    await extract_recipe_from_webpage(message, arguments.get('prompt', ''), arguments.get('url', ''))
                elif fname == 'get_weather_forecast':
                    await get_weather_forecast(message, arguments.get('prompt', ''))
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
    response = await chatbot.chat(context, temperature=1.0, model="claude-3-sonnet-20240229")
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
    global previous_image_description
    logger.info("In make_chat_image")
    if chatbot.name != "Minxie":
        logger.info("Not making chat image because we are not using Claude")
        return
    # logger.info('Generating chat image using model: ' + type(chatbot).__name__)
    channel = bot.get_channel(int(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()))
    async with channel.typing():
        history = await get_history_as_openai_messages(channel, limit=100, nsfw_filter=True, max_length=5000)
        # combined_chat = "Could you make me an image which takes just one or two of the themes contained in following transcript? Don't try and cover too many things in one image. Please make the image an artistic interpretation - not a literal image based on the summary. Be creative! Choose a single artistic movement from across the visual arts, historic or modern. The transcript is between adults - so if there has been any NSFW content or mentions of celebtrities, please just make an image a little like them but not *of* them.  Thanks!\n\n"
        chat_history = ""
        for message in history:
            chat_history += f"{message['content']}\n"
        extra_guidelines = ""
        random_1 = random.random()
        random_2 = random.random()
        random_3 = random.random()

        # Content guidelines

        # Style guidelines
        if random_2 > 0.9:
            style_choice = random.random()
            if style_choice > 0.9:
                extra_guidelines += "- The image should be in the style of a medieval painting.\n"
            elif style_choice > 0.8:
                extra_guidelines += "- The image should be in the style of a 1950s budget sci-fi movie poster.\n"
            elif style_choice > 0.7:
                extra_guidelines += "- The image should echo the style of De Chirico.\n"
            elif style_choice > 0.6:
                extra_guidelines += "- The image should echo the style of Hieronymus Bosch.\n"
            elif style_choice > 0.5:
                extra_guidelines += "- The image should be in the style of a 1970s horror film poster.\n"
            elif style_choice > 0.4:
                extra_guidelines += "- The image should look like a still from a 1970s low-budget adult film that has been badly transferred to VHS.\n"
            else:
                extra_guidelines += "- Ideally echo the style of Eduard Munch.\n"

        # Visual characteristics
        if random_3 > 0.9:
            visual_choice = random.random()
            if visual_choice > 0.7:
                extra_guidelines += "- The image should be wildly colourful, surreal and mind-bending.\n"
            elif visual_choice > 0.4:
                extra_guidelines += "- The image should be a single object, such as a vase or a teacup.\n"
            elif visual_choice > 0.2:
                extra_guidelines += "- The image should be in the style of a 1980s computer game.\n"
            else:
                extra_guidelines += "- Please make the image a little bit like a famous painting.\n"

        combined_chat = f"""
You will be given a Discord server transcript between UK-based Caucasian adult male IT workers.  Please do not misgender or misethnicise them.

<chat-history>
{chat_history}
</chat-history>

1. Identify 1-2 key themes from the conversation.
2. Create a descriptive and creative image prompt for a Stable Diffusion image model that incorporates the chosen theme(s).  It should
capture the essence of the conversation themes and be a unique and artistic interpretation.  It could be a literal, or an abstract, or a comedic, or... representation of the theme(s).
3. The image should be visually striking.
4. You could choose a single artistic movement from across the visual arts, historic or modern, to inspire the image - cinematic, film noir, sci-fi, modernist, surrealist, anime, charcoal illustration - the world is your oyster!
5. The prompt should be highly detailed and imaginative, as suits a Stable Diffusion image model.

{extra_guidelines}

Please try and avoid repeating themes from the previous image descriptions.  Previously used themes are:
{previous_themes}

Examples of good Stable Diffusion model prompts :

"a beautiful and powerful mysterious sorceress, smile, sitting on a rock, lightning magic, hat, detailed leather clothing with gemstones, dress, castle background, digital art, hyperrealistic, fantasy, dark art, artstation, highly detailed, sharp focus, sci-fi, dystopian, iridescent gold, studio lighting"

"Moulin Rouge, cabaret style, burlesque, photograph of a gorgeous beautiful woman, slender toned body, at a burlesque club, highly detailed, posing, smoky room, dark lit, low key, alluring, seductive, muted colors, red color pop, rim light, lingerie, photorealistic, shot with professional DSLR camera, F1. 4, 1/800s, ISO 100, sharp focus, depth of field, cinematic composition"

"A portrait of a woman with horns, split into two contrasting halves. One side is grayscale with intricate tattoos and a serious expression, while the other side is in vivid colors with a more intense and fierce look. The background is divided into gray and red, enhancing the contrast between the two halves. The overall style is edgy and artistic, blending elements of fantasy and modern tattoo art."

"A charismatic speaker is captured mid-speech. He has short, tousled brown hair that's slightly messy on top. He has a round circle face, clean shaven, adorned with rounded rectangular-framed glasses with dark rims, is animated as he gestures with his left hand. He is holding a black microphone in his right hand, speaking passionately.  The man is wearing a light grey sweater over a white t-shirt. He's also wearing a simple black lanyard hanging around his neck. The lanyard badge has the text "Anakin AI".  Behind him, there is a blurred background with a white banner containing logos and text (including Anakin AI), a professional conference setting."

"A quirky inventor in his mid-60s stands proudly next to his latest creation in his cluttered workshop. He has wild, Einstein-like white hair, twinkling blue eyes behind round spectacles, and an excited grin. His face is smudged with grease, and he's wearing a lab coat covered in colorful stains and patches. The background is filled with an assortment of bizarre contraptions, blueprints, and tools. Soft, warm lighting from an old-fashioned desk lamp illuminates the scene."

"A candid photograph of a beautiful woman, looking away from the viewer, long straight dark blonde hair, light blue eyes, fair complexion, full lips, sitting in a comfy chair, looking out the window, snowing outside, wearing nothing, covered in a thin blanket, showing some cleavage, enjoying the view"

"A verification selfie webcam pic of an attractive woman smiling. Holding up a sign written in blue ballpoint pen that says "KEEP THINGS REAL" on an crumpled index card with one hand. Potato quality. Indoors, night, Low light, no natural light. Compressed. Reddit selfie. Low quality."

"Evening Love Song,.Ornamental clouds.compose an evening love song;.a road leaves evasively..The new moon begins.a new chapter of our nights,.of those frail nights.we stretch out and which mingle.with these black horizontals...by Posuka Demizu, Arthur Rackham and Tony DiTerlizzi, meticulous, intricate, entangled, intricately detailed"

Please respond with the following JSON object  with the prompt for the Stable Diffusion image model and the themes you identified.

{{
    "prompt": "Your stable diffusion prompt here",
    "themes": ["theme1", "theme2"]
}}

"""
        response = await chatbot.chat([{ 'role': 'user', 'content': combined_chat }], temperature=1.0, json_mode=True)
        try:
            decoded_response = json.loads(response.message)
        except json.JSONDecodeError:
            logger.error(f'Error decoding JSON: {response.message}')
            decoded_response = {
                "prompt": response.message,
                "themes": []
            }
        logger.info("Asking model to make a chat image")
        llm_chat_prompt = decoded_response["prompt"]
        llm_chat_themes = decoded_response["themes"]
        if random_1 > 0.9:
            if random.random() > 0.5:
                llm_chat_prompt += "\n- If you can somehow shoehorn a grotesque reference to UK Politician Liz Truss into the image, please do so.\n"
            if random.random() > 0.5:
                llm_chat_prompt += "\n- The image should be set in a Pork Market.\n"
            if random.random() > 0.5:
                llm_chat_prompt += "\n- The image should be reflective of a blood-curdling, gory, horror film.\n"

        # await channel.send(f"I'm asking Dalle to make an image based on this prompt\n>{response.message}")
        # discord_file, prompt = await dalle.generate_image(combined_chat, return_prompt=True, style="vivid")
        image_url = await replicate.generate_image(llm_chat_prompt)
        if not image_url:
            logger.info('We did not get a file from dalle')
            await channel.send(f"Sorry, I tried to make an image but I failed (probably because of naughty words - tsk).")
            return
        # if discord_file is None:
        #     logger.info('We did not get a file from dalle')
        #     await channel.send(f"Sorry, I tried to make an image but I failed (probably because of naughty words - tsk).")
        #     return
        try:
            logger.info('Asking chatbot to reword the image description')
            response = await chatbot.chat([{
                'role': 'user',
                'content': f"Could you rephrase the following sentence to make it sound more like a jaded, cynical human who works as a programmer wrote it? You can reword and restructure it any way you like - just keep the sentiment and tone. <sentence>{previous_image_description}</sentence>.  Please reply with only the reworded sentence as it will be sent directly to Discord as a message."
            }])
        except Exception as e:
            logger.error(f'Error generating chat image response: {e}')
            await channel.send(f"Sorry, I tried to make an image but I failed (probably because of naughty words - tsk).")
            return
    previous_image_description = response.message
    previous_themes.append(llm_chat_themes)
    image = requests.get(image_url)
    discord_file = File(io.BytesIO(image.content), filename=f'channel_summary.png')
    await channel.send(f'{response.message}\n_{chatbot.name}\'s chosen themes: {", ".join(llm_chat_themes)}_\n_[Estimated cost: US$0.003]_', file=discord_file)

# Run the bot
chatbot = get_chatbot()
guard = guard.BotGuard()
bot.run(os.getenv("DISCORD_BOT_TOKEN", 'not_set'))
