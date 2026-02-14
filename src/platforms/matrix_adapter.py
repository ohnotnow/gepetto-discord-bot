import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import aiohttp
import nio

from .base import ChatMessage

logger = logging.getLogger("matrix")


def _wrap_message(room: nio.MatrixRoom, event: nio.RoomMessageText, client: nio.AsyncClient) -> ChatMessage:
    """Convert a matrix-nio RoomMessageText event into a platform-agnostic ChatMessage."""
    sender = event.sender  # e.g. "@user:example.com"
    display_name = room.user_name(sender) or sender

    message = ChatMessage(
        content=event.body,
        author_id=sender,
        author_name=sender,
        author_display_name=display_name,
        author_is_bot=(sender == client.user_id),
        author_mention=sender,
        channel_id=room.room_id,
        server_id=room.room_id,  # Matrix rooms don't belong to a single server
        created_at=datetime.fromtimestamp(event.server_timestamp / 1000, tz=timezone.utc),
        raw=event,
    )

    async def reply(text: str, mention_author: bool = True) -> None:
        content = {
            "msgtype": "m.text",
            "body": text,
            "m.relates_to": {
                "m.in_reply_to": {"event_id": event.event_id}
            },
        }
        if mention_author:
            pill = f'<a href="https://matrix.to/#/{sender}">{display_name}</a>'
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = f"{pill} {text}"
        await client.room_send(room.room_id, "m.room.message", content)

    message.reply = reply
    return message


class MatrixChannel:
    """Wraps a Matrix room behind the Channel protocol."""

    def __init__(self, room: nio.MatrixRoom, client: nio.AsyncClient):
        self._room = room
        self._client = client
        self.id = room.room_id
        self.name = room.display_name or room.room_id

    async def send(self, text: str, **kwargs) -> None:
        content = {"msgtype": "m.text", "body": text}
        await self._client.room_send(self._room.room_id, "m.room.message", content)

    async def send_file(self, text: str, file_path: str, filename: str) -> None:
        # Download from URL to a temp file, then upload to Matrix content repo
        async with aiohttp.ClientSession() as session:
            async with session.get(file_path) as resp:
                data = await resp.read()
                content_type = resp.content_type or "application/octet-stream"

        upload_resp, _ = await self._client.upload(
            data,
            content_type=content_type,
            filename=filename,
        )
        if not isinstance(upload_resp, nio.UploadResponse):
            logger.error("Failed to upload file to Matrix: %s", upload_resp)
            return

        # Determine message type from content type
        if content_type.startswith("image/"):
            msgtype = "m.image"
        elif content_type.startswith("video/"):
            msgtype = "m.video"
        else:
            msgtype = "m.file"

        content = {
            "msgtype": msgtype,
            "body": text or filename,
            "url": upload_resp.content_uri,
            "info": {"mimetype": content_type},
        }
        await self._client.room_send(self._room.room_id, "m.room.message", content)

    async def history(self, limit: int, after=None) -> list[ChatMessage]:
        messages = []
        start_token = ""

        # Convert 'after' datetime to a token by getting the room's message history
        # and filtering by timestamp. Matrix uses pagination tokens, not datetimes.
        after_ts = int(after.timestamp() * 1000) if after else 0

        while len(messages) < limit:
            resp = await self._client.room_messages(
                self._room.room_id,
                start=start_token or "",
                limit=min(limit - len(messages), 100),
                direction=nio.MessageDirection.back if not start_token else nio.MessageDirection.back,
            )
            if not isinstance(resp, nio.RoomMessagesResponse):
                break

            if not start_token:
                start_token = resp.end

            for event in resp.chunk:
                if not isinstance(event, nio.RoomMessageText):
                    continue
                if after_ts and event.server_timestamp < after_ts:
                    return list(reversed(messages))
                messages.append(_wrap_message(self._room, event, self._client))

            if not resp.chunk or resp.end == start_token:
                break
            start_token = resp.end

        return list(reversed(messages))

    @asynccontextmanager
    async def typing(self):
        await self._client.room_typing(self._room.room_id, typing_state=True)
        try:
            yield
        finally:
            await self._client.room_typing(self._room.room_id, typing_state=False)

    def bot_can_read_history(self) -> bool:
        # Matrix rooms the bot has joined are readable by default
        # Power level checks could be added here if needed
        return True


class MatrixPlatform:
    """Wraps matrix-nio behind the Platform protocol."""

    def __init__(self):
        homeserver = os.getenv("MATRIX_HOMESERVER", "")
        user_id = os.getenv("MATRIX_USER_ID", "")
        self._client = nio.AsyncClient(homeserver, user_id)
        self._message_callback = None
        self._ready_callback = None
        self._daily_tasks: list[dict] = []
        self._interval_tasks: list[dict] = []
        self.bot_user_id: str = user_id
        self.bot_user_name: str = os.getenv("BOT_NAME", "Bot")

    def get_channel(self, channel_id: str) -> MatrixChannel | None:
        room = self._client.rooms.get(channel_id)
        if room is None:
            return None
        return MatrixChannel(room, self._client)

    async def get_readable_channels(self, server_id: str) -> list[MatrixChannel]:
        channels = []
        for room_id, room in self._client.rooms.items():
            channels.append(MatrixChannel(room, self._client))
        return channels

    async def fetch_user_mention(self, user_id: str) -> str:
        return user_id  # Matrix user IDs are already readable (@user:server)

    def on_message(self, callback) -> None:
        self._message_callback = callback

    def on_ready(self, callback) -> None:
        self._ready_callback = callback

    def schedule_daily(self, name: str, callback, hour: int, minute: int = 0, tz=None) -> None:
        self._daily_tasks.append({
            "name": name,
            "callback": callback,
            "hour": hour,
            "minute": minute,
            "tz": tz,
        })

    def schedule_interval(self, name: str, callback, minutes: int = 60) -> None:
        self._interval_tasks.append({
            "name": name,
            "callback": callback,
            "minutes": minutes,
        })

    def start_schedules(self) -> None:
        for task in self._daily_tasks:
            asyncio.create_task(self._run_daily(task))
        for task in self._interval_tasks:
            asyncio.create_task(self._run_interval(task))

    async def _run_daily(self, task: dict) -> None:
        """Sleep until the target time each day, then run the callback."""
        tz = task["tz"] or timezone.utc
        while True:
            now = datetime.now(tz)
            target = now.replace(hour=task["hour"], minute=task["minute"], second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            delay = (target - now).total_seconds()
            logger.info("Scheduled '%s' in %.0f seconds", task["name"], delay)
            await asyncio.sleep(delay)
            try:
                await task["callback"]()
            except Exception:
                logger.exception("Error in scheduled task '%s'", task["name"])

    async def _run_interval(self, task: dict) -> None:
        """Run a callback at regular intervals."""
        while True:
            await asyncio.sleep(task["minutes"] * 60)
            try:
                await task["callback"]()
            except Exception:
                logger.exception("Error in interval task '%s'", task["name"])

    def run(self, token: str) -> None:
        asyncio.run(self._async_run(token))

    async def _async_run(self, token: str) -> None:
        # Login - token can be an access token or password
        access_token = os.getenv("MATRIX_ACCESS_TOKEN", "")
        if access_token:
            self._client.access_token = access_token
            self._client.user_id = self.bot_user_id
        else:
            resp = await self._client.login(token)
            if isinstance(resp, nio.LoginError):
                logger.error("Matrix login failed: %s", resp.message)
                return

        # Register message callback
        if self._message_callback:
            async def _on_message(room: nio.MatrixRoom, event: nio.RoomMessageText):
                if event.sender == self._client.user_id:
                    return  # Ignore own messages
                wrapped = _wrap_message(room, event, self._client)
                await self._message_callback(wrapped)

            self._client.add_event_callback(_on_message, nio.RoomMessageText)

        # Do an initial sync to populate room state
        await self._client.sync(timeout=30000)

        # Fire ready callback
        if self._ready_callback:
            await self._ready_callback()

        # Start scheduled tasks
        self.start_schedules()

        # Sync forever
        await self._client.sync_forever(timeout=30000)
