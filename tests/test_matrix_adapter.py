"""Tests for the Matrix platform adapter."""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import nio

from src.platforms.matrix_adapter import MatrixPlatform, MatrixChannel, _wrap_message


def _mock_room(room_id="!room:example.com", display_name="general"):
    room = MagicMock(spec=nio.MatrixRoom)
    room.room_id = room_id
    room.display_name = display_name
    room.user_name.return_value = "Test User"
    return room


def _mock_event(sender="@user:example.com", body="hello", event_id="$evt1", server_timestamp=1700000000000):
    event = MagicMock(spec=nio.RoomMessageText)
    event.sender = sender
    event.body = body
    event.event_id = event_id
    event.server_timestamp = server_timestamp
    return event


def _mock_client(user_id="@bot:example.com"):
    client = MagicMock(spec=nio.AsyncClient)
    client.user_id = user_id
    client.rooms = {}
    client.room_send = AsyncMock()
    client.room_typing = AsyncMock()
    client.upload = AsyncMock()
    client.room_messages = AsyncMock()
    return client


class TestWrapMessage:
    def test_wraps_event_into_chat_message(self):
        room = _mock_room()
        event = _mock_event()
        client = _mock_client()

        msg = _wrap_message(room, event, client)

        assert msg.content == "hello"
        assert msg.author_id == "@user:example.com"
        assert msg.author_name == "@user:example.com"
        assert msg.author_display_name == "Test User"
        assert msg.author_is_bot is False
        assert msg.channel_id == "!room:example.com"
        assert msg.server_id == "!room:example.com"
        assert msg.raw is event

    def test_bot_message_detected(self):
        room = _mock_room()
        event = _mock_event(sender="@bot:example.com")
        client = _mock_client(user_id="@bot:example.com")

        msg = _wrap_message(room, event, client)
        assert msg.author_is_bot is True

    def test_timestamp_converted(self):
        room = _mock_room()
        event = _mock_event(server_timestamp=1700000000000)
        client = _mock_client()

        msg = _wrap_message(room, event, client)
        assert msg.created_at == datetime.fromtimestamp(1700000000, tz=timezone.utc)

    def test_display_name_fallback(self):
        room = _mock_room()
        room.user_name.return_value = None
        event = _mock_event(sender="@anon:example.com")
        client = _mock_client()

        msg = _wrap_message(room, event, client)
        assert msg.author_display_name == "@anon:example.com"

    @pytest.mark.asyncio
    async def test_reply_sends_to_room(self):
        room = _mock_room()
        event = _mock_event()
        client = _mock_client()

        msg = _wrap_message(room, event, client)
        await msg.reply("response text")

        client.room_send.assert_called_once()
        call_args = client.room_send.call_args
        assert call_args[0][0] == "!room:example.com"
        assert call_args[0][1] == "m.room.message"
        content = call_args[0][2]
        assert content["body"] == "response text"
        assert "m.relates_to" in content
        assert content["m.relates_to"]["m.in_reply_to"]["event_id"] == "$evt1"


class TestMatrixChannel:
    def test_properties(self):
        room = _mock_room(room_id="!abc:example.com", display_name="test-room")
        client = _mock_client()
        channel = MatrixChannel(room, client)

        assert channel.id == "!abc:example.com"
        assert channel.name == "test-room"

    @pytest.mark.asyncio
    async def test_send(self):
        room = _mock_room()
        client = _mock_client()
        channel = MatrixChannel(room, client)

        await channel.send("hello world")

        client.room_send.assert_called_once_with(
            room.room_id,
            "m.room.message",
            {"msgtype": "m.text", "body": "hello world"},
        )

    @pytest.mark.asyncio
    async def test_typing_context_manager(self):
        room = _mock_room()
        client = _mock_client()
        channel = MatrixChannel(room, client)

        async with channel.typing():
            pass

        assert client.room_typing.call_count == 2
        # First call: typing=True, second: typing=False
        first_call = client.room_typing.call_args_list[0]
        assert first_call[1]["typing_state"] is True
        second_call = client.room_typing.call_args_list[1]
        assert second_call[1]["typing_state"] is False

    def test_bot_can_read_history(self):
        room = _mock_room()
        client = _mock_client()
        channel = MatrixChannel(room, client)
        assert channel.bot_can_read_history() is True

    @pytest.mark.asyncio
    async def test_send_file_image(self):
        room = _mock_room()
        client = _mock_client()
        upload_resp = MagicMock(spec=nio.UploadResponse)
        upload_resp.content_uri = "mxc://example.com/abc123"
        client.upload.return_value = (upload_resp, None)
        channel = MatrixChannel(room, client)

        # Mock aiohttp response and session using proper async context managers
        mock_resp = MagicMock()
        mock_resp.read = AsyncMock(return_value=b"image-data")
        mock_resp.content_type = "image/png"

        mock_get_ctx = AsyncMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_get_ctx)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.platforms.matrix_adapter.aiohttp") as mock_aiohttp:
            mock_aiohttp.ClientSession = MagicMock(return_value=mock_session)
            await channel.send_file("a cat", "https://example.com/cat.png", "cat.png")

        client.upload.assert_called_once()
        client.room_send.assert_called_once()
        content = client.room_send.call_args[0][2]
        assert content["msgtype"] == "m.image"
        assert content["url"] == "mxc://example.com/abc123"


class TestMatrixPlatform:
    @patch.dict(os.environ, {"MATRIX_HOMESERVER": "https://matrix.example.com", "MATRIX_USER_ID": "@bot:example.com"})
    def test_creation(self):
        platform = MatrixPlatform()
        assert platform.bot_user_id == "@bot:example.com"

    @patch.dict(os.environ, {"MATRIX_HOMESERVER": "https://matrix.example.com", "MATRIX_USER_ID": "@bot:example.com"})
    def test_get_channel_returns_none_for_unknown(self):
        platform = MatrixPlatform()
        assert platform.get_channel("!unknown:example.com") is None

    @patch.dict(os.environ, {"MATRIX_HOMESERVER": "https://matrix.example.com", "MATRIX_USER_ID": "@bot:example.com"})
    def test_get_channel_returns_channel_for_known_room(self):
        platform = MatrixPlatform()
        room = _mock_room(room_id="!room:example.com")
        platform._client.rooms = {"!room:example.com": room}

        channel = platform.get_channel("!room:example.com")
        assert channel is not None
        assert channel.id == "!room:example.com"

    @patch.dict(os.environ, {"MATRIX_HOMESERVER": "https://matrix.example.com", "MATRIX_USER_ID": "@bot:example.com"})
    async def test_fetch_user_mention(self):
        platform = MatrixPlatform()
        mention = await platform.fetch_user_mention("@user:example.com")
        assert mention == "@user:example.com"

    @patch.dict(os.environ, {"MATRIX_HOMESERVER": "https://matrix.example.com", "MATRIX_USER_ID": "@bot:example.com"})
    def test_on_message_stores_callback(self):
        platform = MatrixPlatform()
        callback = MagicMock()
        platform.on_message(callback)
        assert platform._message_callback is callback

    @patch.dict(os.environ, {"MATRIX_HOMESERVER": "https://matrix.example.com", "MATRIX_USER_ID": "@bot:example.com"})
    def test_on_ready_stores_callback(self):
        platform = MatrixPlatform()
        callback = MagicMock()
        platform.on_ready(callback)
        assert platform._ready_callback is callback

    @patch.dict(os.environ, {"MATRIX_HOMESERVER": "https://matrix.example.com", "MATRIX_USER_ID": "@bot:example.com"})
    def test_schedule_daily_stores_task(self):
        platform = MatrixPlatform()
        callback = MagicMock()
        platform.schedule_daily("test_task", callback, hour=10, minute=30)
        assert len(platform._daily_tasks) == 1
        assert platform._daily_tasks[0]["name"] == "test_task"
        assert platform._daily_tasks[0]["hour"] == 10
        assert platform._daily_tasks[0]["minute"] == 30

    @patch.dict(os.environ, {"MATRIX_HOMESERVER": "https://matrix.example.com", "MATRIX_USER_ID": "@bot:example.com"})
    def test_schedule_interval_stores_task(self):
        platform = MatrixPlatform()
        callback = MagicMock()
        platform.schedule_interval("check_stuff", callback, minutes=15)
        assert len(platform._interval_tasks) == 1
        assert platform._interval_tasks[0]["name"] == "check_stuff"
        assert platform._interval_tasks[0]["minutes"] == 15

    @patch.dict(os.environ, {"MATRIX_HOMESERVER": "https://matrix.example.com", "MATRIX_USER_ID": "@bot:example.com"})
    def test_get_readable_channels(self):
        platform = MatrixPlatform()
        room1 = _mock_room(room_id="!room1:example.com")
        room2 = _mock_room(room_id="!room2:example.com")
        platform._client.rooms = {
            "!room1:example.com": room1,
            "!room2:example.com": room2,
        }

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"MATRIX_HOMESERVER": "https://matrix.example.com", "MATRIX_USER_ID": "@bot:example.com"})
    async def test_get_readable_channels_returns_all_joined_rooms(self):
        platform = MatrixPlatform()
        room1 = _mock_room(room_id="!room1:example.com")
        room2 = _mock_room(room_id="!room2:example.com")
        platform._client.rooms = {
            "!room1:example.com": room1,
            "!room2:example.com": room2,
        }

        channels = await platform.get_readable_channels("ignored")
        assert len(channels) == 2
        ids = {ch.id for ch in channels}
        assert ids == {"!room1:example.com", "!room2:example.com"}
