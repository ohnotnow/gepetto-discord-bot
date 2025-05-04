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
from gepetto.helpers.history import get_history_as_openai_messages, build_messages
from gepetto import mistral, dalle, summary, weather, random_facts, birthdays, gpt, stats, groq, claude, ollama, guard, replicate, tools, images, gemini, sentry, openrouter
from gepetto import response as gepetto_response
import discord
from discord import File
from discord.ext import commands, tasks
import openai
import feedparser
from constants import abusive_responses
from utils import remove_emoji, remove_nsfw_words, truncate
from gepetto.tasks.birthday_task import register_birthday_task
from gepetto.tasks.random_chat_task import register_random_chat_task
from gepetto.tasks.horror_task import register_horror_chat_task
from gepetto.tasks.image_task import register_make_chat_image_task
from gepetto.handlers.message_handler import register_message_handler
from gepetto.tools.llm_tools import create_image, get_weather_forecast, summarise_webpage_content, extract_recipe_from_webpage
from config import Config
from gepetto.bot_state import BotState


AVATAR_PATH="avatar.png"
previous_image_description = "Here is my image based on recent chat in my Discord server!"
previous_image_reasoning = "Dunno"
previous_image_prompt = "Dunno"
previous_image_themes = ""
previous_reasoning_content = ""
previous_themes = []
horror_history = []

# Setup logging
logger = logging.getLogger('discord')  # Get the discord logger
# logging.basicConfig(
#     datefmt='%Y-%m-%d %H:%M:%S',
# )

mention_counts = defaultdict(list) # This will hold user IDs and their mention timestamps

# Fetch environment variables
server_id = Config.DISCORD_SERVER_ID
# model_engine = Config.OPENAI_MODEL_ENGINE
model_engine = "gpt-4.1-mini"

# openai.api_key = Config.OPENAI_API_KEY
location = Config.BOT_LOCATION
chat_image_hour = int(Config.CHAT_IMAGE_HOUR)



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
    logger.info("BOT_PROVIDER: " + Config.BOT_PROVIDER)
    if Config.BOT_PROVIDER == 'mistral':
        chatbot = mistral.MistralModel()
    elif Config.BOT_PROVIDER == 'groq':
        chatbot = groq.GroqModel()
    elif Config.BOT_PROVIDER == 'anthropic':
        chatbot = claude.ClaudeModel()
    elif Config.BOT_PROVIDER == 'ollama':
        chatbot = ollama.OllamaModel()
    elif Config.BOT_PROVIDER == 'gemini':
        chatbot = gemini.GeminiModel()
    elif Config.BOT_PROVIDER == 'openrouter':
        chatbot = openrouter.OpenrouterModel()
    else:
        chatbot = gpt.GPTModel()
    return chatbot



async def generate_response(question, context="", extended_messages=[], temperature=1.0, model=model_engine, system_prompt=None):
    extended_messages = build_messages(question, bot, extended_messages, system_prompt)

    response = await chatbot.chat(extended_messages, temperature=temperature)
    return response

@bot.event
async def on_ready():
    logger.info(f"Starting discord bot - date time in python is {datetime.now()}")
    register_birthday_task(bot, chatbot)
    register_make_chat_image_task(bot, chatbot, state)
    register_horror_chat_task(bot, chatbot, state)
    register_random_chat_task(bot, chatbot)
    register_message_handler(bot, chatbot, state)
    logger.info(f"Using model type : {type(chatbot)}")
    return
    with open(AVATAR_PATH, 'rb') as avatar:
        await bot.user.edit(avatar=avatar.read())
    logger.info("Avatar has been changed!")

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
    message = truncate(response.message.strip(), 1800, '[... Truncated ...]') + "\n" + response.usage
    await discord_message.reply(f'{discord_message.author.mention} {message}', mention_author=True)

# Run the bot
chatbot = get_chatbot()
if Config.DISCORD_BOT_MODEL:
    chatbot.default_model = Config.DISCORD_BOT_MODEL
if Config.BOT_NAME:
    chatbot.name = Config.BOT_NAME
guard = guard.BotGuard()

# Instantiate the bot state
state = BotState()

bot.run(Config.DISCORD_BOT_TOKEN)
