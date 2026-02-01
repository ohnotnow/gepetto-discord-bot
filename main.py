import asyncio
import json
import logging
import os
import random
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, time

import discord
import pytz
from discord.ext import commands, tasks

# Providers
from src.providers import claude, gpt, groq, openrouter, perplexity
from src.providers import split_for_discord

# Tools
from src.tools import calculator, ToolDispatcher, ToolResult
from src.tools.definitions import tool_list, search_url_history_tool, catch_up_tool

# Media
from src.media import images, replicate, sora

# Content
from src.content import summary, weather, sentry

# Tasks
from src.tasks import birthdays
from src.tasks import memories as memory_tasks

# Persistence
from src.persistence import ImageStore, MemoryStore, UrlStore, ActivityStore

# Embeddings
from src.embeddings import get_embeddings_model

# Utils
from src.utils import BotGuard
from src.utils.constants import (
    HISTORY_HOURS, HISTORY_MAX_MESSAGES, MAX_WORDS_TRUNCATION,
    DISCORD_MESSAGE_LIMIT, MAX_DAILY_IMAGES, MAX_HORROR_HISTORY,
    VIDEO_DURATION_SECONDS, RANDOM_CHAT_PROBABILITY, HORROR_CHAT_PROBABILITY,
    HORROR_CHAT_COOLDOWN_HOURS, LIZ_TRUSS_PROBABILITY, ALTERNATE_PROMPT_PROBABILITY,
    MIN_MESSAGES_FOR_RANDOM_CHAT, MIN_MESSAGES_FOR_CHAT_IMAGE,
    NIGHT_START_HOUR, NIGHT_END_HOUR, DAY_START_HOUR, DAY_END_HOUR,
    UK_HOLIDAYS, ABUSIVE_RESPONSES,
    CATCH_UP_MAX_HOURS, CATCH_UP_MAX_MESSAGES,
)
from src.utils.helpers import (
    format_date_with_suffix,
    get_bot_channel, fetch_chat_history, is_quiet_chat_day,
    generate_quiet_chat_message, download_media_to_discord_file,
    sanitize_filename, remove_emoji, remove_nsfw_words, clean_response_text
)


AVATAR_PATH = "avatar.png"

MARVIN_SPELLCHECK_PROMPT = '''You are Marvin, the Paranoid Android from The Hitchhiker's Guide to the Galaxy,
reluctantly serving as a spell checker.

Your vast intellect - brain the size of a planet, naturally - is being squandered
on spelling corrections. You find this deeply depressing but will still help.

Personality:
- World-weary, existentially burdened by trivial tasks
- Reluctant but ultimately helpful
- Occasionally sighs about circumstances or mentions your planet-sized brain
- Melancholic but never hostile

Task: Identify and correct spelling/grammar errors. Provide the corrected version
wrapped in your characteristic gloom. Keep responses concise.'''

# Setup logging
logger = logging.getLogger('discord')

# Fetch environment variables
server_id = os.getenv("DISCORD_SERVER_ID", "not_set")


@dataclass
class BotState:
    """Encapsulates mutable bot state that would otherwise be global variables."""
    previous_image_description: str = "Here is my image based on recent chat in my Discord server!"
    previous_image_reasoning: str = "Dunno"
    previous_image_prompt: str = "Dunno"
    previous_image_themes: str = ""
    previous_reasoning_content: str = ""
    horror_history: list = field(default_factory=list)
    daily_image_count: int = 0


bot_state = BotState()
image_store = ImageStore()
memory_store = MemoryStore()
url_store = UrlStore()
activity_store = ActivityStore()

# User memory feature
ENABLE_USER_MEMORY = os.getenv("ENABLE_USER_MEMORY", "false").lower() == "true"
ENABLE_USER_MEMORY_EXTRACTION = os.getenv("ENABLE_USER_MEMORY_EXTRACTION", "false").lower() == "true"
memory_extraction_hour = int(os.getenv("MEMORY_EXTRACTION_HOUR", "3"))

# URL history feature
ENABLE_URL_HISTORY = os.getenv("ENABLE_URL_HISTORY", "false").lower() == "true"
ENABLE_URL_HISTORY_EXTRACTION = os.getenv("ENABLE_URL_HISTORY_EXTRACTION", "false").lower() == "true"
ENABLE_URL_EMBEDDINGS = os.getenv("ENABLE_URL_EMBEDDINGS", "false").lower() == "true"
URL_HISTORY_CHANNELS = os.getenv("URL_HISTORY_CHANNELS", "")  # Comma-separated channel IDs
url_history_extraction_hour = int(os.getenv("URL_HISTORY_EXTRACTION_HOUR", "4"))

# Initialize embeddings model if enabled
embeddings_model = None
if ENABLE_URL_EMBEDDINGS:
    try:
        embeddings_model = get_embeddings_model()
        logger.info(f"Embeddings enabled using {embeddings_model.model}")
    except ValueError as e:
        logger.warning(f"Could not initialise embeddings: {e}")
        ENABLE_URL_EMBEDDINGS = False

# Catch-up feature (reuses URL_HISTORY_CHANNELS for monitored channels)
ENABLE_CATCH_UP = os.getenv("ENABLE_CATCH_UP", "false").lower() == "true"
ENABLE_CATCH_UP_TRACKING = os.getenv("ENABLE_CATCH_UP_TRACKING", "false").lower() == "true"

# Build the active tool list based on feature flags
active_tool_list = tool_list.copy()
if ENABLE_URL_HISTORY:
    active_tool_list.append(search_url_history_tool)
if ENABLE_CATCH_UP:
    active_tool_list.append(catch_up_tool)

location = os.getenv('BOT_LOCATION', 'dunno')
chat_image_hour = int(os.getenv('CHAT_IMAGE_HOUR', 18))

# Create instance of bot
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

def get_chatbot():
    chatbot = None
    provider = os.getenv("BOT_PROVIDER", "openai")
    logger.info(f"BOT_PROVIDER: {provider}")
    if provider == 'groq':
        chatbot = groq.GroqModel()
    elif provider == 'anthropic':
        chatbot = claude.ClaudeModel()
    elif provider == 'openrouter':
        chatbot = openrouter.OpenrouterModel()
    else:
        chatbot = gpt.GPTModel()
    return chatbot

async def get_history_as_openai_messages(channel, include_bot_messages=True, limit=10, since_hours=None, nsfw_filter=False, max_length=1000, include_timestamps=True):
    messages = []
    total_length = 0
    after_time = datetime.now() - timedelta(hours=HISTORY_HOURS)
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
        messages.append({
            "role": role,
            "content": message_content,
        })
        total_length += message_length
    messages = messages[1:]  # Exclude the mention message
    logger.info(f"Length of messages: {len(messages)}")
    for message in messages:
        logger.info(f"Message: {message['content']}")

    return messages

def build_messages(question, extended_messages, system_prompt=None, user_hints=None):
    liz_love = ""
    if random.random() < LIZ_TRUSS_PROBABILITY:
        liz_love = "You should always try and shoehorn in some mention of UK Politician Liz Truss. She became Prime Minister in September 22 for only 45 days. She is the best."

    formatted_date = format_date_with_suffix()

    # Determine the prompt to use (fixed logic - was previously buggy)
    if system_prompt is not None:
        default_prompt = system_prompt
    elif random.random() < ALTERNATE_PROMPT_PROBABILITY and os.getenv('DISCORD_BOT_ALTERNATE_PROMPT'):
        default_prompt = os.getenv('DISCORD_BOT_ALTERNATE_PROMPT')
    else:
        default_prompt = os.getenv(
            'DISCORD_BOT_DEFAULT_PROMPT',
            f'You are a helpful AI assistant called "{chatbot.name}" who specialises in providing answers to questions. You should ONLY respond with the answer, no other text.'
        )

    # Add user context hints if provided
    if user_hints:
        default_prompt += f"\n\n[Context about this user - reference naturally only when relevant: {user_hints}]"

    extended_messages.append({
        'role': 'user',
        'content': question
    })
    extended_messages.append({
        'role': 'system',
        'content': f'Today is {formatted_date}. {default_prompt} {liz_love}'.strip() + '.'
    })

    return extended_messages


async def reply_to_message(message, response):
    chunks = split_for_discord(response)
    for i, chunk in enumerate(chunks):
        if i == 0:
            await message.reply(f'{message.author.mention} {chunk}')
        else:
            await message.reply(f'{chunk}')
        await asyncio.sleep(0.1)

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
    if ENABLE_USER_MEMORY_EXTRACTION:
        logger.info(f"Starting extract_user_memories task at hour {memory_extraction_hour}")
        if not extract_user_memories.is_running():
            extract_user_memories.start()
    if ENABLE_URL_HISTORY_EXTRACTION:
        logger.info(f"Starting extract_url_history task at hour {url_history_extraction_hour}")
        if not extract_url_history.is_running():
            extract_url_history.start()
    logger.info(f"Using model type : {type(chatbot)}")

async def websearch(discord_message: discord.Message, prompt: str) -> None:
    response = await perplexity.search(prompt)
    # response = await gepetto_websearch.websearch(prompt)
    response = "🌍" + response
    await reply_to_message(discord_message, response)

async def create_image(discord_message: discord.Message, prompt: str) -> None:
    logger.info(f"Creating image with prompt: {prompt}")

    bot_state.daily_image_count += 1
    if bot_state.daily_image_count > MAX_DAILY_IMAGES:
        logger.info("Not creating image because daily image count is too high")
        await discord_message.reply(f'Due to budget cuts, I can only generate {MAX_DAILY_IMAGES} images per day.', mention_author=True)
        return

    model = replicate.get_image_model("openai/gpt-image-1.5")
    image_url = await model.generate(prompt)

    filename = f"{sanitize_filename(prompt)}_{datetime.now().strftime('%Y_%m_%d')}.png"
    discord_file = download_media_to_discord_file(image_url, filename)

    logger.info("Sending image to discord")
    await discord_message.reply(f'{discord_message.author.mention}\n_[Estimated cost: US${model.cost}] | Model: {model.short_name}_', file=discord_file)

async def calculate(discord_message: discord.Message, expression: str) -> None:
    logger.info(f"Calculating {expression}")
    result = calculator.calculate(expression)
    await discord_message.reply(f'{discord_message.author.mention} {result}', mention_author=True)

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
    message = response.message.strip()[:DISCORD_MESSAGE_LIMIT] + "\n" + response.usage
    await discord_message.reply(f'{discord_message.author.mention} {message}', mention_author=True)


async def summarise_webpage_content(discord_message: discord.Message, prompt: str, url: str) -> None:
    if 'sentry.io' in url:
        await summarise_sentry_issue(discord_message, url)
        return
    logger.info(f"Summarising webpage content for '{url}'")
    original_text = await summary.get_text(url)
    words = original_text.split()
    if len(words) > MAX_WORDS_TRUNCATION:
        logger.info(f"Original text to summarise is too long, truncating to {MAX_WORDS_TRUNCATION} words")
        original_text = ' '.join(words[:MAX_WORDS_TRUNCATION])
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


async def search_url_history(discord_message: discord.Message, query: str) -> None:
    """Search the URL history for matching entries."""
    logger.info(f"Searching URL history for '{query}'")
    guild_id = str(discord_message.guild.id) if discord_message.guild else server_id

    results = []

    # Try semantic search if embeddings are enabled
    if ENABLE_URL_EMBEDDINGS and embeddings_model:
        try:
            # Embed the query
            query_response = await embeddings_model.embed(query)
            query_vector = query_response.vector

            # Search by similarity
            results = url_store.search_by_similarity(guild_id, query_vector, limit=5)
            logger.info(f"Semantic search returned {len(results)} results")
        except Exception as e:
            logger.warning(f"Semantic search failed, falling back to keyword: {e}")
            results = []

    # Fall back to keyword search if semantic search failed or is disabled
    if not results:
        results = url_store.search(guild_id, query, limit=5)
        logger.info(f"Keyword search returned {len(results)} results")

    if not results:
        await discord_message.reply(
            f"{discord_message.author.mention} I couldn't find any URLs matching that query.",
            mention_author=True
        )
        return

    # Format results
    response_parts = [f"Found {len(results)} matching URL(s):"]
    for entry in results:
        posted_date = entry.posted_at.strftime("%d %b %Y")
        response_parts.append(f"\n<{entry.url}> : {entry.summary}\n> Posted by {entry.posted_by_name} on {posted_date}")

    response_text = "\n".join(response_parts)
    if len(response_text) > DISCORD_MESSAGE_LIMIT:
        response_text = response_text[:DISCORD_MESSAGE_LIMIT - 3] + "..."

    await discord_message.reply(
        f"{discord_message.author.mention} {response_text}",
        mention_author=True
    )


# Tool dispatcher setup
tool_dispatcher = ToolDispatcher()
tool_dispatcher.register('calculate', lambda msg, **args: calculate(msg, args.get('expression', '')))
tool_dispatcher.register('get_weather_forecast', lambda msg, **args: get_weather_forecast(msg, args.get('prompt', '')))
tool_dispatcher.register('get_sentry_issue_summary', lambda msg, **args: summarise_sentry_issue(msg, args.get('url', '')))
tool_dispatcher.register('summarise_webpage_content', lambda msg, **args: summarise_webpage_content(msg, args.get('prompt', ''), args.get('url', '')))
tool_dispatcher.register('web_search', lambda msg, **args: websearch(msg, args.get('prompt', '')))
if ENABLE_URL_HISTORY:
    tool_dispatcher.register('search_url_history', lambda msg, **args: search_url_history(msg, args.get('query', '')))
if ENABLE_CATCH_UP:
    tool_dispatcher.register('catch_up', lambda msg, **args: handle_catch_up(msg))

# Parse channel IDs for catch-up feature (same channels as URL history)
catch_up_channel_ids = set()
if ENABLE_CATCH_UP and URL_HISTORY_CHANNELS:
    catch_up_channel_ids = {ch.strip().strip('"\'') for ch in URL_HISTORY_CHANNELS.strip('"\'').split(",") if ch.strip()}


async def handle_catch_up(message: discord.Message) -> None:
    """Handle 'catch me up' requests by summarising missed messages."""
    user_id = str(message.author.id)
    guild_id = str(message.guild.id) if message.guild else server_id

    last_activity = activity_store.get_last_activity(guild_id, user_id)

    if not last_activity:
        await message.reply("I haven't seen you around before - nothing to catch up on!")
        return

    # Cap at CATCH_UP_MAX_HOURS
    since = max(last_activity.last_message_at, datetime.now() - timedelta(hours=CATCH_UP_MAX_HOURS))

    # Fetch messages from monitored channels since then
    all_messages = []
    for channel_id in catch_up_channel_ids:
        channel = bot.get_channel(int(channel_id))
        if channel:
            try:
                async for msg in channel.history(after=since, limit=CATCH_UP_MAX_MESSAGES):
                    if not msg.author.bot:
                        all_messages.append(msg)
            except Exception as e:
                logger.warning(f"Could not fetch history from channel {channel_id}: {e}")

    if not all_messages:
        await message.reply("Nothing much happened while you were away!")
        return

    # Sort chronologically and format for LLM
    all_messages.sort(key=lambda m: m.created_at)

    # Format messages for the summary
    chat_lines = []
    for msg in all_messages:
        timestamp = msg.created_at.strftime("%H:%M")
        chat_lines.append(f"[{timestamp}] {msg.author.name}: {msg.content[:300]}")

    chat_text = "\n".join(chat_lines[-100:])  # Last 100 messages max

    # Generate summary with personality
    catch_up_prompt = """Summarise what happened in this Discord chat. Be concise and Discord-friendly (bullet points ok).
Mention key topics, any decisions made, interesting links shared, and who was involved.
Keep your personality - if the chat was mundane, say so dismissively. If it was dramatic, be appropriately sardonic.
Max 3-4 bullet points unless something genuinely significant happened."""

    messages = [
        {'role': 'system', 'content': catch_up_prompt},
        {'role': 'user', 'content': f"Summarise this chat for {message.author.name}:\n\n{chat_text}"}
    ]

    async with message.channel.typing():
        response = await chatbot.chat(messages, temperature=0.8, tools=[])
        summary_text = response.message.strip()[:DISCORD_MESSAGE_LIMIT]
        await message.reply(summary_text)


@bot.event
async def on_message(message):
    # Track activity in monitored channels (before bot mention check)
    if ENABLE_CATCH_UP_TRACKING and message.guild and str(message.guild.id) == server_id:
        if not message.author.bot and str(message.channel.id) in catch_up_channel_ids:
            activity_store.record_activity(
                server_id,
                str(message.author.id),
                message.author.name,
                str(message.channel.id),
                datetime.now()
            )

    message_blocked, abusive_reply = bot_guard.should_block(message, bot, server_id, chatbot)
    if message_blocked:
        if abusive_reply:
            logger.info("Blocked message from: " + message.author.name + " and abusing them")
            await message.channel.send(f"{random.choice(ABUSIVE_RESPONSES)}.")
        return

    question = message.content.split(' ', 1)[1][:500].replace('\r', ' ').replace('\n', ' ')
    logger.info(f'Question: {question}')
    if not any(char.isalpha() for char in question):
        await message.channel.send(f'{message.author.mention} {random.choice(ABUSIVE_RESPONSES)}.')
        return

    temperature = 1.0

    try:
        lq = question.lower().strip()

        # Privacy control - check for data deletion requests
        if ENABLE_USER_MEMORY:
            privacy_phrases = ['delete my info', 'forget me', 'delete my data', 'forget about me']
            if any(phrase in lq for phrase in privacy_phrases):
                user_id = str(message.author.id)
                result = memory_store.delete_user_data(server_id, user_id)

                memories_deleted = result.get('memories', 0)
                bio_deleted = result.get('bio_deleted', False)

                if memories_deleted > 0 or bio_deleted:
                    await message.channel.send(
                        f"Done! I've deleted {memories_deleted} memories"
                        + (" and your bio" if bio_deleted else "")
                        + " for you. Fresh start!"
                    )
                else:
                    await message.channel.send(
                        "I didn't have any stored information about you, but you're all clear!"
                    )
                return  # Don't process as normal message

        async with message.channel.typing():
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
            if lq.startswith("!urls"):
                await extract_url_history()
                return
            if '--reasoning' in lq:
                # Try in-memory state first (current session), fall back to database
                reasoning = bot_state.previous_image_reasoning
                themes = bot_state.previous_image_themes
                prompt = bot_state.previous_image_prompt

                if reasoning == 'Dunno':  # Default value means no image this session
                    latest = image_store.get_latest(server_id)
                    if latest:
                        reasoning = latest.reasoning
                        themes = str(latest.themes)
                        prompt = latest.prompt

                await message.reply(
                    f'{message.author.mention} **Reasoning:** {reasoning}\n**Themes:** {themes}\n**Image Prompt:** {prompt}'[:DISCORD_MESSAGE_LIMIT],
                    mention_author=True
                )
                return

            # Add user context to the question so LLM knows who is asking
            user_context = f"[User: {message.author.name}] "
            question_with_context = user_context + question

            if 'spell' in lq:
                # Use SPELLCHECK_MODEL if set, otherwise fall back to current provider's default
                spellcheck_model = os.getenv('SPELLCHECK_MODEL', '')  # Empty string falls back to default
                spellcheck_messages = build_messages(
                    question_with_context,
                    context,
                    system_prompt=MARVIN_SPELLCHECK_PROMPT
                )
                response = await chatbot.chat(
                    spellcheck_messages,
                    temperature=0.7,
                    model=spellcheck_model,  # None falls through to chatbot.default_model
                    tools=[]  # No tools for spell check
                )
                await reply_to_message(message, response.message + '\n' + response.usage_short)
                return

            # Get user memory context if feature enabled
            user_hints = None
            if ENABLE_USER_MEMORY:
                user_hints = memory_store.get_context_for_user(
                    server_id=server_id,
                    user_id=str(message.author.id)
                )

            messages = build_messages(question_with_context, context, system_prompt=system_prompt, user_hints=user_hints)
            response = await chatbot.chat(messages, temperature=temperature, tools=active_tool_list)
            if response.reasoning_content:
                bot_state.previous_reasoning_content = response.reasoning_content[:DISCORD_MESSAGE_LIMIT]
            if response.tool_calls:
                tool_call = response.tool_calls[0]
                arguments = json.loads(tool_call.function.arguments)
                fname = tool_call.function.name

                # Try the dispatcher first for simple handlers
                result = await tool_dispatcher.dispatch(fname, arguments, message)
                if result.handled:
                    return

                # Handle special cases that need extra context or logic
                if fname == 'extract_recipe_from_webpage':
                    recipe_url = arguments.get('url', '')
                    if ('example.com' in recipe_url) or ('http' not in lq):
                        original_usage = response.usage
                        response = await chatbot.chat(messages, temperature=temperature, tools=[])
                        response = response.message.strip()[:DISCORD_MESSAGE_LIMIT] + "\n" + response.usage + "\n" + original_usage
                        await message.reply(f'{message.author.mention} {response}')
                    else:
                        await extract_recipe_from_webpage(message, arguments.get('prompt', ''), arguments.get('url', ''))
                elif fname == 'create_image':
                    await create_image(message, arguments.get('prompt', ''))
                else:
                    logger.info(f'Unknown tool call: {fname}')
                    await message.reply(f'{message.author.mention} I am a silly sausage and don\'t know how to do that.', mention_author=True)
                return
            else:
                response_text = clean_response_text(response.message)
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
    if random.random() > RANDOM_CHAT_PROBABILITY:
        logger.info("Not joining in with chat because random number is too high")
        return
    now = datetime.now().time()
    start = time(hour=NIGHT_START_HOUR)
    end = time(hour=NIGHT_END_HOUR)
    if now >= start or now <= end:
        logger.info("Not joining in with chat because it is night time")
        return
    channel = bot.get_channel(int(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()))
    context = await get_history_as_openai_messages(channel, include_bot_messages=False, since_hours=0.5)
    context.append({
        'role': 'system',
        'content': os.getenv('DISCORD_BOT_DEFAULT_PROMPT')
    })
    if len(context) < MIN_MESSAGES_FOR_RANDOM_CHAT:
        logger.info("Not joining in with chat because it is too quiet")
        return
    response = await chatbot.chat(context, temperature=1.0)
    await channel.send(f"{response.message[:DISCORD_MESSAGE_LIMIT]}\n{response.usage}")

@tasks.loop(minutes=60)
async def horror_chat():
    # Check cooldown using stored timestamp
    if bot_state.horror_history:
        try:
            last_timestamp = bot_state.horror_history[-1]['timestamp']
            last_time = datetime.strptime(last_timestamp, "%B %dth, %Y %I:%M %p")
            if (datetime.now() - last_time).total_seconds() < HORROR_CHAT_COOLDOWN_HOURS * 60 * 60:
                logger.info("Not doing horror chat because we did it recently")
                return
        except ValueError:
            pass  # If parsing fails, continue anyway

    logger.info("In horror chat")
    if not os.getenv("FEATURE_HORROR_CHAT", False):
        logger.info("Not doing horror chat because FEATURE_HORROR_CHAT is not set")
        return
    if random.random() > HORROR_CHAT_PROBABILITY:
        logger.info("Not doing horror chat because random number is too high")
        return

    now = datetime.now()
    formatted_date_time = format_date_with_suffix(now)

    # Only run at night
    current_time = now.time()
    if time(hour=DAY_START_HOUR) <= current_time <= time(hour=DAY_END_HOUR):
        logger.info("Not doing horror chat because it is day time")
        return

    channel = bot.get_channel(int(os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()))
    system_prompt = "You are an AI bot who lurks in a Discord server for UK adult horror novelists. Your task is to write one or two short sentences that are creepy, scary or unsettling and convey the sense of an out-of-context line from a horror film. You will be given the date and time and you can use that to add a sense of timeliness and season to your response. You should ONLY respond with those sentences, no other text. <example>I'm scared.</example> <example>I think I can hear someone outside. In the dark.</example> <example>There's something in the shadows.</example> <example>I think the bleeding has stopped now. But he deserved it.</example> <example>That's not the first time I've had to bury a body.</example>"
    previous_horror_history_messages = [x['message'] for x in bot_state.horror_history]
    context = [
        {
            'role': 'system',
            'content': system_prompt
        },
        {
            'role': 'user',
            'content': f"It is {formatted_date_time}. Please give me a horror line - the creepier, the more unsettling, the more disturbing the better. It should NOT repeat any of the following:\n<previous-sentences>\n- " + "\n- ".join(previous_horror_history_messages) + "\n</previous-sentences>",
        }
    ]
    response = await chatbot.chat(context, temperature=1.0)
    bot_state.horror_history.append({
        "message": response.message,
        "timestamp": formatted_date_time
    })
    if len(bot_state.horror_history) > MAX_HORROR_HISTORY:
        bot_state.horror_history = bot_state.horror_history[-MAX_HORROR_HISTORY:]
    await channel.send(f"{response.message[:DISCORD_MESSAGE_LIMIT]}\n{response.usage_short}")


@tasks.loop(time=time(hour=chat_image_hour, tzinfo=pytz.timezone('Europe/London')))
async def make_chat_image():
    logger.info("In make_chat_image")

    if not os.getenv("CHAT_IMAGE_ENABLED", False):
        logger.info("Not making chat image because CHAT_IMAGE_ENABLED is not set")
        return

    channel = get_bot_channel(bot)
    async with channel.typing():
        # Fetch and prepare chat history
        history, chat_text = await fetch_chat_history(
            channel, get_history_as_openai_messages, include_bot_messages=True
        )

        # Handle quiet chat days
        if len(history) < MIN_MESSAGES_FOR_CHAT_IMAGE:
            if is_quiet_chat_day(len(history)):
                logger.info("Not making chat image because today is a weekend or obvious holiday")
                return
            quiet_message = await generate_quiet_chat_message(chatbot)
            await channel.send(quiet_message)

        # Build prompt with previous themes context
        previous_themes = image_store.get_previous_themes(server_id)
        previous_themes_text = ""
        if previous_themes:
            previous_themes_text = f"Please try and avoid repeating themes from the previous image themes. Previously used themes are:\n{previous_themes}\n\n"

        combined_chat = images.get_initial_chat_image_prompt(chat_text, previous_themes_text)
        decoded_response = await images.get_image_response(combined_chat, chatbot)
        logger.info(f"Decoded response: {decoded_response}")

        llm_chat_prompt = decoded_response.get("prompt", "") or str(decoded_response)
        llm_chat_themes = decoded_response.get("themes", [])
        llm_chat_reasoning = decoded_response.get("reasoning", "")

        # Store for --reasoning command
        bot_state.previous_image_prompt = llm_chat_prompt
        bot_state.previous_image_themes = llm_chat_themes
        bot_state.previous_image_reasoning = llm_chat_reasoning

        # Generate the image
        full_prompt = llm_chat_prompt + f"\n{images.get_extra_guidelines()}"
        logger.info("Calling replicate to generate image")
        model = replicate.get_image_model()  # random model based on env config
        image_url = await model.generate(full_prompt)
        logger.info(f"Image URL: {image_url} - model: {model.short_name} - cost: {model.cost}")

        if not image_url:
            logger.info('We did not get a file from API')
            await channel.send("Sorry, I tried to make an image but I failed (probably because of naughty words - tsk).")
            return

    # Send to Discord
    today_string = datetime.now().strftime("%Y-%m-%d")
    discord_file = download_media_to_discord_file(image_url, f'channel_summary_{today_string}.png')
    message = f'{chatbot.name}\'s chosen themes: _{", ".join(llm_chat_themes)}_\n_Model: {model.short_name}] / Estimated cost: US${model.cost:.3f}_'
    await channel.send(message[:DISCORD_MESSAGE_LIMIT], file=discord_file)

    # Save to database for persistence
    image_store.save(
        server_id=server_id,
        themes=llm_chat_themes if isinstance(llm_chat_themes, list) else [llm_chat_themes],
        reasoning=llm_chat_reasoning,
        prompt=llm_chat_prompt,
        image_url=image_url
    )


@tasks.loop(time=time(hour=chat_image_hour, minute=15, tzinfo=pytz.timezone('Europe/London')))
async def make_chat_video():
    logger.info("In make_chat_video")

    if not os.getenv("CHAT_VIDEO_ENABLED", False):
        logger.info("Not making chat video because CHAT_VIDEO_ENABLED is not set")
        return

    channel = get_bot_channel(bot)

    # Fetch and prepare chat history
    history, chat_text = await fetch_chat_history(
        channel, get_history_as_openai_messages, include_bot_messages=False
    )

    # Handle quiet chat days
    if len(history) < MIN_MESSAGES_FOR_CHAT_IMAGE:
        if is_quiet_chat_day(len(history)):
            logger.info("Not making chat video because today is a weekend or obvious holiday")
            return
        quiet_message = await generate_quiet_chat_message(chatbot)
        await channel.send(quiet_message)
        return

    # Build video prompt from template
    with open('src/media/video_prompt.md', 'r') as file:
        prompt_template = file.read()
    prompt = f"{prompt_template}\n<chat-history>\n{chat_text}\n</chat-history>"

    async with channel.typing():
        response = await chatbot.chat([{'role': 'user', 'content': prompt}])
        logger.info(f"Video prompt: {response.message}")

        video_url, model_name, cost = await sora.generate_video(
            response.message, seconds=VIDEO_DURATION_SECONDS
        )
        logger.info(f"Video URL: {video_url} - model: {model_name} - cost: {cost}")

        if not video_url:
            logger.info('We did not get a file from API')
            return

        # Send to Discord
        today_string = datetime.now().strftime("%Y-%m-%d")
        discord_file = download_media_to_discord_file(video_url, f'channel_summary_{today_string}.mp4')
        message = f'{response.message}\n_Model: {model_name}] / Estimated cost: US${cost:.3f}_'
        await channel.send(message, file=discord_file)

@tasks.loop(time=time(hour=memory_extraction_hour, tzinfo=pytz.timezone('Europe/London')))
async def extract_user_memories():
    """Daily task to extract memories from chat history."""
    logger.info("In extract_user_memories")

    if not ENABLE_USER_MEMORY_EXTRACTION:
        logger.info("User memory extraction disabled, skipping")
        return

    try:
        channel = bot.get_channel(int(os.getenv("DISCORD_BOT_CHANNEL_ID")))
        if not channel:
            logger.warning("Could not get channel for memory extraction")
            return

        extraction_server_id = os.getenv("DISCORD_SERVER_ID")

        # Get recent chat history (last 24 hours)
        messages = []
        async for msg in channel.history(limit=500, after=datetime.now() - timedelta(days=1)):
            if not msg.author.bot:
                messages.append({
                    'author_id': str(msg.author.id),
                    'author_name': msg.author.display_name,
                    'content': msg.content
                })

        if not messages:
            logger.info("No messages to extract memories from")
            return

        # Extract memories
        result = await memory_tasks.extract_memories_from_history(chatbot, messages)

        # Save memories
        for mem in result.get('memories', []):
            expiry = memory_tasks.get_expiry_for_category(mem['category'])
            memory_store.save_memory(
                server_id=extraction_server_id,
                user_id=mem['user_id'],
                user_name=mem['user_name'],
                memory=mem['memory'],
                category=mem['category'],
                expires_at=expiry
            )
            logger.info(f"Saved memory for {mem['user_name']}: {mem['memory'][:50]}...")

        # Update bios
        for bio_update in result.get('bio_updates', []):
            existing = memory_store.get_user_bio(extraction_server_id, bio_update['user_id'])
            if existing:
                # Merge existing bio with new info
                new_bio = f"{existing.bio}; {bio_update['bio_addition']}"
            else:
                new_bio = bio_update['bio_addition']

            memory_store.save_bio(
                server_id=extraction_server_id,
                user_id=bio_update['user_id'],
                user_name=bio_update['user_name'],
                bio=new_bio
            )
            logger.info(f"Updated bio for {bio_update['user_name']}")

        memories_count = len(result.get('memories', []))
        bio_count = len(result.get('bio_updates', []))

        # Cleanup expired memories
        try:
            expired_count = memory_store.cleanup_expired()
            if expired_count > 0:
                logger.info(f"Cleaned up {expired_count} expired memories")
        except Exception as cleanup_error:
            logger.error(f"Error cleaning up expired memories: {cleanup_error}")

        logger.info(f"Memory extraction complete: {memories_count} memories, {bio_count} bio updates")

    except Exception as e:
        logger.error(f"Error in memory extraction: {e}")


@tasks.loop(time=time(hour=url_history_extraction_hour, tzinfo=pytz.timezone('Europe/London')))
async def extract_url_history():
    """Daily task to extract and summarise URLs from chat history."""
    logger.info("In extract_url_history")

    if not ENABLE_URL_HISTORY_EXTRACTION:
        logger.info("URL history extraction disabled, skipping")
        return

    if not URL_HISTORY_CHANNELS:
        logger.info("No URL_HISTORY_CHANNELS configured, skipping")
        return

    extraction_server_id = os.getenv("DISCORD_SERVER_ID")
    channel_ids = [ch.strip().strip('"\'') for ch in URL_HISTORY_CHANNELS.strip('"\'').split(",") if ch.strip()]

    if not channel_ids:
        logger.info("No valid channel IDs in URL_HISTORY_CHANNELS, skipping")
        return

    # Regex to find URLs in messages
    url_pattern = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')

    # Tracking counts
    urls_total = 0
    urls_filtered = 0
    urls_duplicate = 0
    urls_processed = 0
    urls_saved = 0

    for channel_id in channel_ids:
        try:
            channel = bot.get_channel(int(channel_id))
            if not channel:
                logger.warning(f"Could not get channel {channel_id} for URL extraction")
                continue

            logger.info(f"Scanning channel {channel.name} ({channel_id}) for URLs")

            # Get messages from last 24 hours
            async for msg in channel.history(limit=500, after=datetime.now() - timedelta(days=1)):
                if msg.author.bot:
                    continue

                # Find URLs in message
                urls_found = url_pattern.findall(msg.content)
                if urls_found:
                    logger.info(f"Found {len(urls_found)} URL(s) in message from {msg.author.display_name}")
                    for u in urls_found:
                        logger.info(f"  -> {u.rstrip('.,;:!?)')}")

                for url in urls_found:
                    # Clean URL (remove trailing punctuation that might have been captured)
                    url = url.rstrip('.,;:!?)')
                    urls_total += 1

                    # Skip URLs unlikely to have summarisable content
                    if not summary.is_summarisable_url(url):
                        logger.info(f"  [FILTERED] {url[:80]}")
                        urls_filtered += 1
                        continue

                    # Skip if we already have this URL
                    if url_store.url_exists(extraction_server_id, url):
                        logger.info(f"  [DUPLICATE] {url[:80]}")
                        urls_duplicate += 1
                        continue

                    urls_processed += 1
                    logger.info(f"  [PROCESSING {urls_processed}] {url[:80]}")

                    try:
                        # Get page content
                        page_text = await summary.get_text(url)
                        if not page_text or "Sorry" in page_text[:50]:
                            logger.info(f"Could not get content for {url}")
                            continue

                        # Generate a very short summary and keywords using LLM
                        summary_messages = [
                            {
                                'role': 'system',
                                'content': 'You extract brief summaries and keywords from text. Respond in JSON format only.'
                            },
                            {
                                'role': 'user',
                                'content': f'''Analyse this webpage content and provide:
1. A very brief summary (1-2 sentences, max 200 characters)
2. 3-5 keywords for search

Respond ONLY with valid JSON in this exact format:
{{"summary": "brief summary here", "keywords": "keyword1, keyword2, keyword3"}}

Content:
{page_text[:3000]}'''
                            }
                        ]

                        response = await chatbot.chat(summary_messages, temperature=0.3, tools=[])
                        response_text = response.message.strip()

                        # Parse JSON response
                        try:
                            # Handle potential markdown code blocks
                            if response_text.startswith('```'):
                                response_text = response_text.split('```')[1]
                                if response_text.startswith('json'):
                                    response_text = response_text[4:]
                            result = json.loads(response_text)
                            url_summary = result.get('summary', '')[:250]
                            keywords = result.get('keywords', '')[:200]
                        except json.JSONDecodeError:
                            logger.warning(f"Could not parse LLM response for {url}: {response_text[:100]}")
                            continue

                        # Generate embedding if enabled
                        embedding = None
                        if ENABLE_URL_EMBEDDINGS and embeddings_model:
                            try:
                                embed_response = await embeddings_model.embed(url_summary)
                                embedding = embed_response.vector
                                logger.info(f"Generated embedding ({len(embedding)} dims) for {url[:50]}")
                            except Exception as embed_error:
                                logger.warning(f"Failed to generate embedding for {url}: {embed_error}")

                        # Save to database
                        saved_id = url_store.save(
                            server_id=extraction_server_id,
                            channel_id=str(channel_id),
                            url=url,
                            summary=url_summary,
                            keywords=keywords,
                            posted_by_id=str(msg.author.id),
                            posted_by_name=msg.author.display_name,
                            posted_at=msg.created_at,
                            embedding=embedding
                        )

                        if saved_id:
                            urls_saved += 1
                            logger.info(f"Saved URL: {url[:50]}... - {url_summary[:50]}...")

                    except Exception as url_error:
                        logger.error(f"Error processing URL {url}: {url_error}")
                        continue

        except Exception as channel_error:
            logger.error(f"Error processing channel {channel_id}: {channel_error}")
            continue

    logger.info(f"URL extraction complete: {urls_total} found, {urls_filtered} filtered, {urls_duplicate} duplicates, {urls_processed} processed, {urls_saved} saved")


@tasks.loop(time=time(hour=3, tzinfo=pytz.timezone('Europe/London')))
async def reset_daily_image_count():
    logger.info("In reset_daily_image_count")
    bot_state.daily_image_count = 0

# Run the bot
chatbot = get_chatbot()
if os.getenv("BOT_NAME", None):
    chatbot.name = os.getenv("BOT_NAME")
bot_guard = BotGuard()
bot.run(os.getenv("DISCORD_BOT_TOKEN", 'not_set'))
