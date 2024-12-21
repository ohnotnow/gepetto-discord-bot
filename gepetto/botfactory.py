import os
from pydantic_ai import Agent
import logging

def get_chatbot(model_name=None, bot_name=None, system_prompt=None):
    # see https://ai.pydantic.dev/api/models/base/#pydantic_ai.models.KnownModelName for a list of pydantic-ai model names
    if not model_name:
        model_name = os.getenv("BOT_MODEL", 'openai:gpt-4o-mini')
    if not bot_name:
        bot_name = os.getenv("BOT_NAME", 'Gepetto')
    if not system_prompt:
        system_prompt = os.getenv("BOT_DEFAULT_PROMPT", None)
    logger = logging.getLogger('discord')
    logger.info("Using LLM model: " + model_name + " and bot name: " + bot_name)
    return Agent(model_name, name=bot_name, system_prompt=system_prompt)
