import re
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel

class DiscordMessage(BaseModel):
    role: str
    content: str
    created_at: datetime
    author: str

    def to_openai_message(self, include_timestamps=True) -> dict:
        if include_timestamps:
            return {
                "role": self.role,
                "content": f"At {self.created_at.astimezone(timezone.utc).astimezone()} '{self.author}' said: {self.content}",
            }
        else:
            return {
                "role": self.role,
                "content": f"'{self.author}' said: {self.content}",
            }

class ChannelHistory(BaseModel):
    messages: list[DiscordMessage]

    def to_openai_messages(self, include_timestamps=True) -> list[dict]:
        return [message.to_openai_message(include_timestamps) for message in self.messages]

def remove_emoji(text):
    regrex_pattern = re.compile(pattern = "["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                           "]+", flags = re.UNICODE)
    return regrex_pattern.sub(r'',text)

def remove_nsfw_words(message):
    message = re.sub(r"(fuck|prick|asshole|shit|wanker|dick)", "", message)
    return message

async def get_history_as_openai_messages(channel, include_bot_messages=True, limit=10, since_hours=None, nsfw_filter=False, max_length=1000, include_timestamps=True):
    history = ChannelHistory(messages=[])
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
        role = 'assistant' if msg.author.bot else 'user'
        username = "" if msg.author.bot else msg.author.name
        message_content = remove_emoji(msg.content)
        message_content = re.sub(r'\[tokens used.+Estimated cost.+]', '', message_content, flags=re.MULTILINE)
        message_content = remove_nsfw_words(message_content) if nsfw_filter else message_content
        message_length = len(message_content)
        if total_length + message_length > max_length:
            break

        history.messages.append(DiscordMessage(
            role=role,
            content=message_content,
            created_at=msg.created_at,
            author=username,
        ))
        total_length += message_length
    # We reverse the list to make it in chronological order
    return history.to_openai_messages(include_timestamps)[::-1]
