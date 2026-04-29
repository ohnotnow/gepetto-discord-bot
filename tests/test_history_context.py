from datetime import datetime, timedelta, timezone

import pytest

import main
from src.platforms.base import ChatMessage


class FakeChannel:
    def __init__(self, messages):
        self.messages = messages
        self.history_calls = []

    async def history(self, limit, after=None, before=None, oldest_first=None):
        self.history_calls.append({
            "limit": limit,
            "after": after,
            "before": before,
            "oldest_first": oldest_first,
        })

        messages = [
            msg for msg in self.messages
            if (after is None or msg.created_at > after)
            and (before is None or msg.created_at < before)
        ]
        messages.sort(key=lambda msg: msg.created_at, reverse=not oldest_first)
        return messages[:limit]


def make_message(content, author_name, created_at, author_id=None, is_bot=False):
    return ChatMessage(
        content=content,
        author_id=author_id or author_name,
        author_name=author_name,
        author_display_name=author_name,
        author_is_bot=is_bot,
        author_mention=f"<@{author_id or author_name}>",
        channel_id="channel",
        server_id="server",
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_history_context_uses_most_recent_messages_before_current_message():
    main.platform.bot_user_id = "bot"

    now = datetime.now(timezone.utc)
    older_messages = [
        make_message(f"old message {idx}", "olduser", now - timedelta(minutes=60 - idx))
        for idx in range(10)
    ]
    recent_messages = [
        make_message(f"recent message {idx}", "recentuser", now - timedelta(minutes=10 - idx))
        for idx in range(10)
    ]
    current_mention = make_message("@bot what was recentuser referring to?", "asker", now)
    channel = FakeChannel([*older_messages, *recent_messages, current_mention])

    history = await main.get_history_as_openai_messages(
        channel,
        limit=10,
        before=current_mention.created_at,
        include_timestamps=False,
    )

    assert channel.history_calls[0]["oldest_first"] is False
    assert channel.history_calls[0]["before"] == current_mention.created_at
    assert [message["content"] for message in history] == [
        f"'recentuser' said: recent message {idx}"
        for idx in range(10)
    ]
