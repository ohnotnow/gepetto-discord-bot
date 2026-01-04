"""
Helper functions for the Gepetto Discord bot.
"""

import io
import logging
import os
import re
from datetime import datetime

import requests
from discord import File

from .constants import (
    HISTORY_HOURS, HISTORY_MAX_MESSAGES, MIN_MESSAGES_FOR_CHAT_IMAGE, UK_HOLIDAYS
)

logger = logging.getLogger('discord')


def get_date_suffix(day: int) -> str:
    """Return the ordinal suffix for a day number (st, nd, rd, th)."""
    if 11 <= day <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def format_date_with_suffix(dt: datetime = None) -> str:
    """Format a datetime with ordinal suffix, e.g., 'January 1st, 2024 10:30 AM'."""
    if dt is None:
        dt = datetime.now()
    suffix = get_date_suffix(dt.day)
    return dt.strftime(f"%B {dt.day}{suffix}, %Y %I:%M %p")


def format_date_only(dt: datetime = None) -> str:
    """Format a datetime with ordinal suffix, date only, e.g., 'January 1st, 2024'."""
    if dt is None:
        dt = datetime.now()
    suffix = get_date_suffix(dt.day)
    return dt.strftime(f"%B {dt.day}{suffix}, %Y")


# --- Media generation helpers ---

def get_bot_channel(bot):
    """Get the configured Discord bot channel."""
    channel_id = os.getenv('DISCORD_BOT_CHANNEL_ID', 'Invalid').strip()
    return bot.get_channel(int(channel_id))


async def fetch_chat_history(channel, get_history_func, limit=1000, max_messages=None, include_bot_messages=True):
    """
    Fetch chat history, truncate to max_messages, and reverse for chronological order.

    Returns: (messages_list, chat_text)
    """
    if max_messages is None:
        max_messages = HISTORY_MAX_MESSAGES

    history = await get_history_func(
        channel,
        limit=limit,
        nsfw_filter=True,
        max_length=15000,
        include_timestamps=False,
        since_hours=HISTORY_HOURS,
        include_bot_messages=include_bot_messages
    )

    if len(history) > max_messages:
        history = history[-max_messages:]

    logger.info(f"History length: {len(history)}")
    if history:
        logger.info(f"Oldest 3 messages: {history[:3]}")
        logger.info(f"Most recent 3 messages: {history[-3:]}")

    history.reverse()
    chat_text = "\n".join(message['content'] for message in history)

    return history, chat_text


def is_quiet_chat_day(history_length: int, min_messages: int = None) -> bool:
    """Check if it's a quiet day (weekend or UK holiday)."""
    if min_messages is None:
        min_messages = MIN_MESSAGES_FOR_CHAT_IMAGE

    if history_length >= min_messages:
        return False

    # It's quiet - but is it a weekend or holiday?
    now = datetime.now()
    is_weekend = now.weekday() >= 5
    is_holiday = now.strftime("%B %d") in UK_HOLIDAYS

    return is_weekend or is_holiday


async def generate_quiet_chat_message(chatbot) -> str:
    """Generate a sarcastic message about how quiet the chat is."""
    date_string = datetime.now().strftime("%A, %d %B %Y")
    response = await chatbot.chat([{
        'role': 'user',
        'content': f"Today is {date_string}. Could you please write a pithy, acerbic, sarcastic comment about how quiet the chat is in this discord server today? If the date looks like a weekend, or a UK holiday, then take that into account when writing your response. The users are all software developers and love nice food, interesting books, obscure sci-fi, cute cats. They enjoy a somewhat jaded, cynical tone. Please reply with only the sentence as it will be sent directly to Discord as a message."
    }])
    return response.message


def download_media_to_discord_file(url: str, filename: str) -> File:
    """Download media from URL and return as a Discord File object."""
    response = requests.get(url)
    return File(io.BytesIO(response.content), filename=filename)


def load_previous_themes(filename: str = 'previous_image_themes.txt', max_lines: int = 10) -> str:
    """Load previous themes from file, keeping only the latest max_lines."""
    try:
        with open(filename, 'r') as file:
            content = file.read()
        lines = content.splitlines()[-max_lines:]
        return "\n".join(lines)
    except FileNotFoundError:
        return ""
    except Exception as e:
        logger.error(f'Error reading {filename}: {e}')
        return ""


def save_previous_themes(themes: str, filename: str = 'previous_image_themes.txt') -> None:
    """Append themes to the themes file."""
    with open(filename, 'a') as file:
        file.write(f"\n{themes}")


def sanitize_filename(text: str, max_length: int = 50) -> str:
    """Convert text to a safe filename."""
    return re.sub(r'[^a-zA-Z0-9]', '_', text)[:max_length]
