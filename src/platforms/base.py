from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class ChatMessage:
    content: str
    author_id: str
    author_name: str
    author_display_name: str
    author_is_bot: bool
    author_mention: str
    channel_id: str
    server_id: str
    created_at: datetime
    raw: object = None

    async def reply(self, text: str, mention_author: bool = True) -> None:
        """Reply to this message. Implemented by platform adapter."""
        raise NotImplementedError


@runtime_checkable
class Channel(Protocol):
    id: str
    name: str

    async def send(self, text: str, **kwargs) -> None: ...
    async def send_file(self, text: str, file_path: str, filename: str) -> None: ...
    async def history(self, limit: int, after=None) -> list[ChatMessage]: ...
    def typing(self): ...
    def bot_can_read_history(self) -> bool: ...


@runtime_checkable
class Platform(Protocol):
    bot_user_id: str
    bot_user_name: str

    def get_channel(self, channel_id: str) -> Channel | None: ...
    async def fetch_user_mention(self, user_id: str) -> str: ...
    async def get_readable_channels(self, server_id: str) -> list[Channel]: ...
    def on_message(self, callback) -> None: ...
    def on_ready(self, callback) -> None: ...
    def schedule_daily(self, name: str, callback, hour: int, minute: int = 0, tz=None) -> None: ...
    def schedule_interval(self, name: str, callback, minutes: int = 60) -> None: ...
    def start_schedules(self) -> None: ...
    def run(self, token: str) -> None: ...
