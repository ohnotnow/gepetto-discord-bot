import io
import logging
from datetime import time

import discord
import requests
from discord.ext import commands, tasks

from .base import ChatMessage

logger = logging.getLogger('discord')


def _wrap_message(msg: discord.Message) -> ChatMessage:
    """Convert a discord.Message into a platform-agnostic ChatMessage."""
    message = ChatMessage(
        content=msg.content,
        author_id=str(msg.author.id),
        author_name=msg.author.name,
        author_display_name=msg.author.display_name,
        author_is_bot=msg.author.bot,
        author_mention=msg.author.mention,
        channel_id=str(msg.channel.id),
        server_id=str(msg.guild.id) if msg.guild else "",
        created_at=msg.created_at,
        raw=msg,
    )

    async def reply(text: str, mention_author: bool = True) -> None:
        await msg.reply(text, mention_author=mention_author)

    message.reply = reply
    return message


class DiscordChannel:
    """Wraps a discord.TextChannel behind the Channel protocol."""

    def __init__(self, channel: discord.TextChannel, bot_member: discord.Member | None):
        self._channel = channel
        self._bot_member = bot_member
        self.id = str(channel.id)
        self.name = channel.name

    async def send(self, text: str, **kwargs) -> None:
        await self._channel.send(text, **kwargs)

    async def send_file(self, text: str, file_path: str, filename: str) -> None:
        response = requests.get(file_path)
        discord_file = discord.File(io.BytesIO(response.content), filename=filename)
        await self._channel.send(text, file=discord_file)

    async def history(self, limit: int, after=None) -> list[ChatMessage]:
        messages = []
        async for msg in self._channel.history(limit=limit, after=after):
            messages.append(_wrap_message(msg))
        return messages

    def typing(self):
        return self._channel.typing()

    def bot_can_read_history(self) -> bool:
        if self._bot_member is None:
            return False
        permissions = self._channel.permissions_for(self._bot_member)
        return permissions.read_message_history


class DiscordPlatform:
    """Wraps discord.py behind the Platform protocol."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        self._bot = commands.Bot(command_prefix='!', intents=intents)
        self._schedules: list[tasks.Loop] = []
        self.bot_user_id: str = ""
        self.bot_user_name: str = ""

    @property
    def bot(self) -> commands.Bot:
        """Escape hatch for code that still needs the raw discord bot during migration."""
        return self._bot

    def get_channel(self, channel_id: str) -> DiscordChannel | None:
        channel = self._bot.get_channel(int(channel_id))
        if channel is None:
            return None
        guild = channel.guild if hasattr(channel, 'guild') else None
        bot_member = guild.me if guild else None
        return DiscordChannel(channel, bot_member)

    async def fetch_user_mention(self, user_id: str) -> str:
        user = await self._bot.fetch_user(int(user_id))
        return user.mention

    def on_message(self, callback) -> None:
        @self._bot.event
        async def on_message(message: discord.Message):
            wrapped = _wrap_message(message)
            await callback(wrapped)

    def on_ready(self, callback) -> None:
        @self._bot.event
        async def on_ready():
            self.bot_user_id = str(self._bot.user.id)
            self.bot_user_name = self._bot.user.name
            await callback()

    def schedule_daily(self, name: str, callback, hour: int, minute: int = 0, tz=None) -> None:
        run_time = time(hour=hour, minute=minute, tzinfo=tz)

        @tasks.loop(time=run_time)
        async def task():
            await callback()

        task.__name__ = name
        self._schedules.append(task)

    def schedule_interval(self, name: str, callback, minutes: int = 60) -> None:
        @tasks.loop(minutes=minutes)
        async def task():
            await callback()

        task.__name__ = name
        self._schedules.append(task)

    def start_schedules(self) -> None:
        for task in self._schedules:
            task.start()

    def run(self, token: str) -> None:
        self._bot.run(token)
