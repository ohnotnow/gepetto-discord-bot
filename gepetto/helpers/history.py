
import re
import random
from datetime import datetime, timedelta, timezone
from config import Config
from utils import remove_emoji, remove_nsfw_words

async def get_history_as_openai_messages(channel, bot, include_bot_messages=True, limit=10, since_hours=None, nsfw_filter=False, max_length=1000, include_timestamps=True):
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
        default_prompt = Config.DISCORD_BOT_ALTERNATE_PROMPT
    if system_prompt is None:
        default_prompt = Config.DISCORD_BOT_DEFAULT_PROMPT
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
