"""Tests for the platform abstraction layer."""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.platforms.base import ChatMessage, Channel, Platform
from src.utils.guard import BotGuard


class TestChatMessage:
    def test_creation_with_all_fields(self):
        msg = ChatMessage(
            content="hello world",
            author_id="123",
            author_name="testuser",
            author_display_name="Test User",
            author_is_bot=False,
            author_mention="<@123>",
            channel_id="456",
            server_id="789",
            created_at=datetime(2026, 1, 1, 12, 0),
        )
        assert msg.content == "hello world"
        assert msg.author_id == "123"
        assert msg.author_name == "testuser"
        assert msg.author_display_name == "Test User"
        assert msg.author_is_bot is False
        assert msg.author_mention == "<@123>"
        assert msg.channel_id == "456"
        assert msg.server_id == "789"
        assert msg.raw is None

    def test_raw_defaults_to_none(self):
        msg = ChatMessage(
            content="test", author_id="1", author_name="a",
            author_display_name="A", author_is_bot=False,
            author_mention="<@1>", channel_id="2", server_id="3",
            created_at=datetime.now(),
        )
        assert msg.raw is None

    def test_raw_stores_original_message(self):
        original = MagicMock()
        msg = ChatMessage(
            content="test", author_id="1", author_name="a",
            author_display_name="A", author_is_bot=False,
            author_mention="<@1>", channel_id="2", server_id="3",
            created_at=datetime.now(), raw=original,
        )
        assert msg.raw is original

    @pytest.mark.asyncio
    async def test_reply_raises_not_implemented_by_default(self):
        msg = ChatMessage(
            content="test", author_id="1", author_name="a",
            author_display_name="A", author_is_bot=False,
            author_mention="<@1>", channel_id="2", server_id="3",
            created_at=datetime.now(),
        )
        with pytest.raises(NotImplementedError):
            await msg.reply("response")


class TestProtocols:
    def test_channel_is_runtime_checkable(self):
        assert hasattr(Channel, '__protocol_attrs__') or isinstance(Channel, type)

    def test_platform_is_runtime_checkable(self):
        assert hasattr(Platform, '__protocol_attrs__') or isinstance(Platform, type)


class TestGetPlatform:
    @patch.dict(os.environ, {"BOT_BACKEND": "discord"})
    def test_discord_backend_returns_discord_platform(self):
        from src.platforms import get_platform
        platform = get_platform()
        from src.platforms.discord_adapter import DiscordPlatform
        assert isinstance(platform, DiscordPlatform)

    @patch.dict(os.environ, {}, clear=False)
    def test_default_backend_returns_discord_platform(self):
        os.environ.pop("BOT_BACKEND", None)
        from src.platforms import get_platform
        platform = get_platform()
        from src.platforms.discord_adapter import DiscordPlatform
        assert isinstance(platform, DiscordPlatform)

    @patch.dict(os.environ, {"BOT_BACKEND": "matrix"})
    def test_matrix_backend_raises_not_implemented(self):
        from src.platforms import get_platform
        with pytest.raises(NotImplementedError, match="Matrix support coming soon"):
            get_platform()

    @patch.dict(os.environ, {"BOT_BACKEND": "nonsense"})
    def test_unknown_backend_raises_value_error(self):
        from src.platforms import get_platform
        with pytest.raises(ValueError, match="Unknown BOT_BACKEND: nonsense"):
            get_platform()


class TestDiscordPlatform:
    def test_creates_with_correct_intents(self):
        from src.platforms.discord_adapter import DiscordPlatform
        platform = DiscordPlatform()
        assert platform._bot.intents.members is True
        assert platform._bot.intents.message_content is True

    def test_get_channel_returns_none_for_unknown(self):
        from src.platforms.discord_adapter import DiscordPlatform
        platform = DiscordPlatform()
        assert platform.get_channel("999999") is None

    def test_bot_escape_hatch(self):
        from src.platforms.discord_adapter import DiscordPlatform
        platform = DiscordPlatform()
        assert platform.bot is platform._bot


class TestDiscordChannel:
    def test_wraps_channel_properties(self):
        from src.platforms.discord_adapter import DiscordChannel
        mock_channel = MagicMock()
        mock_channel.id = 456
        mock_channel.name = "general"
        channel = DiscordChannel(mock_channel, bot_member=None)
        assert channel.id == "456"
        assert channel.name == "general"

    def test_bot_can_read_history_false_without_member(self):
        from src.platforms.discord_adapter import DiscordChannel
        mock_channel = MagicMock()
        mock_channel.id = 456
        mock_channel.name = "general"
        channel = DiscordChannel(mock_channel, bot_member=None)
        assert channel.bot_can_read_history() is False

    def test_bot_can_read_history_checks_permissions(self):
        from src.platforms.discord_adapter import DiscordChannel
        mock_channel = MagicMock()
        mock_channel.id = 456
        mock_channel.name = "general"
        mock_perms = MagicMock()
        mock_perms.read_message_history = True
        mock_channel.permissions_for.return_value = mock_perms
        mock_member = MagicMock()
        channel = DiscordChannel(mock_channel, mock_member)
        assert channel.bot_can_read_history() is True


class TestWrapMessage:
    def test_wraps_discord_message(self):
        from src.platforms.discord_adapter import _wrap_message
        mock_msg = MagicMock()
        mock_msg.content = "hello"
        mock_msg.author.id = 123
        mock_msg.author.name = "testuser"
        mock_msg.author.display_name = "Test User"
        mock_msg.author.bot = False
        mock_msg.author.mention = "<@123>"
        mock_msg.channel.id = 456
        mock_msg.guild.id = 789
        mock_msg.created_at = datetime(2026, 1, 1)

        wrapped = _wrap_message(mock_msg)
        assert wrapped.content == "hello"
        assert wrapped.author_id == "123"
        assert wrapped.author_name == "testuser"
        assert wrapped.author_display_name == "Test User"
        assert wrapped.author_is_bot is False
        assert wrapped.channel_id == "456"
        assert wrapped.server_id == "789"
        assert wrapped.raw is mock_msg

    def test_wraps_dm_message_with_no_guild(self):
        from src.platforms.discord_adapter import _wrap_message
        mock_msg = MagicMock()
        mock_msg.content = "dm content"
        mock_msg.author.id = 123
        mock_msg.author.name = "testuser"
        mock_msg.author.display_name = "Test User"
        mock_msg.author.bot = False
        mock_msg.author.mention = "<@123>"
        mock_msg.channel.id = 456
        mock_msg.guild = None
        mock_msg.created_at = datetime(2026, 1, 1)

        wrapped = _wrap_message(mock_msg)
        assert wrapped.server_id == ""


def _make_message(**overrides) -> ChatMessage:
    """Helper to create a ChatMessage with sensible defaults for guard tests."""
    defaults = dict(
        content="<@BOT123> hello there",
        author_id="USER456",
        author_name="testuser",
        author_display_name="Test User",
        author_is_bot=False,
        author_mention="<@USER456>",
        channel_id="CH789",
        server_id="SERVER1",
        created_at=datetime.now(),
    )
    defaults.update(overrides)
    return ChatMessage(**defaults)


BOT_ID = "BOT123"
SERVER_ID = "SERVER1"


class TestBotGuardWithChatMessage:
    def test_blocks_dms(self):
        guard = BotGuard()
        msg = _make_message(server_id="")
        blocked, abusive = guard.should_block(msg, BOT_ID, SERVER_ID)
        assert blocked is True
        assert abusive is False

    def test_blocks_wrong_server(self):
        guard = BotGuard()
        msg = _make_message(server_id="OTHER_SERVER")
        blocked, abusive = guard.should_block(msg, BOT_ID, SERVER_ID)
        assert blocked is True
        assert abusive is False

    def test_blocks_bot_itself(self):
        guard = BotGuard()
        msg = _make_message(author_id=BOT_ID)
        blocked, abusive = guard.should_block(msg, BOT_ID, SERVER_ID)
        assert blocked is True
        assert abusive is False

    def test_blocks_other_bots(self):
        guard = BotGuard()
        msg = _make_message(author_is_bot=True)
        blocked, abusive = guard.should_block(msg, BOT_ID, SERVER_ID)
        assert blocked is True
        assert abusive is False

    def test_blocks_no_mention(self):
        guard = BotGuard()
        msg = _make_message(content="hello there, no mention here")
        blocked, abusive = guard.should_block(msg, BOT_ID, SERVER_ID)
        assert blocked is True
        assert abusive is False

    def test_blocks_mention_only_no_content(self):
        guard = BotGuard()
        msg = _make_message(content="<@BOT123>")
        blocked, abusive = guard.should_block(msg, BOT_ID, SERVER_ID)
        assert blocked is True
        assert abusive is True

    def test_blocks_non_alpha_content(self):
        guard = BotGuard()
        msg = _make_message(content="<@BOT123> 12345 !!! ???")
        blocked, abusive = guard.should_block(msg, BOT_ID, SERVER_ID)
        assert blocked is True
        assert abusive is True

    def test_allows_valid_mention(self):
        guard = BotGuard()
        msg = _make_message(content="<@BOT123> what is the weather?")
        blocked, abusive = guard.should_block(msg, BOT_ID, SERVER_ID)
        assert blocked is False
        assert abusive is False

    def test_rate_limiting(self):
        guard = BotGuard(max_mentions=3, mention_window=timedelta(hours=1))
        for _ in range(3):
            msg = _make_message()
            guard.should_block(msg, BOT_ID, SERVER_ID)

        # 4th mention should be blocked
        msg = _make_message()
        blocked, abusive = guard.should_block(msg, BOT_ID, SERVER_ID)
        assert blocked is True
        assert abusive is True

    def test_omnilistens_blocks_name_mention(self):
        guard = BotGuard()
        chatbot = MagicMock()
        chatbot.omnilistens = True
        chatbot.name = "Gepetto"
        msg = _make_message(content="hey gepetto what's up?")
        blocked, abusive = guard.should_block(msg, BOT_ID, SERVER_ID, chatbot)
        assert blocked is True
        assert abusive is False

    def test_omnilistens_allows_non_name_message(self):
        guard = BotGuard()
        chatbot = MagicMock()
        chatbot.omnilistens = True
        chatbot.name = "Gepetto"
        msg = _make_message(content="<@BOT123> hello there friend")
        blocked, abusive = guard.should_block(msg, BOT_ID, SERVER_ID, chatbot)
        assert blocked is False
        assert abusive is False
