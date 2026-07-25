"""
Tests for the music extraction task and backfill command in main.py.

Imports main (precedent: tests/test_history_context.py) and monkeypatches its
module globals — platform, music_store, feature flags — then drives
extract_music_history() and backfill_music_history() with fake channels.
music.enrich_links is replaced with a deterministic fake so no HTTP/LLM/Discogs.
"""

import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

import main
from src.content.music import MusicParseError
from src.persistence.music_store import MusicStore


class FakeChatMessage:
    def __init__(self, author_id="u1", author_name="PosterOne", is_bot=False,
                 content="", created_at=None):
        self.content = content
        self.author_is_bot = is_bot
        self.author_id = author_id
        self.author_display_name = author_name
        self.created_at = created_at or datetime.now()
        self.replies = []

    async def reply(self, text, **kwargs):
        self.replies.append(text)


class FakeChannel:
    def __init__(self, messages):
        self._messages = messages
        self.name = "music"
        self.history_calls = []

    async def history(self, limit, after):
        self.history_calls.append({"limit": limit, "after": after})
        return self._messages


def music_message(url, author_id="u1", author_name="PosterOne"):
    return FakeChatMessage(author_id=author_id, author_name=author_name,
                           content=f"great track {url}")


async def fake_enrich(links, chatbot, throttle_seconds=1.2):
    """Deterministic stand-in for music.enrich_links: urls containing 'music'
    are music by Low; urls containing 'dead' are dropped; others non-music."""
    kept = [l for l in links if "dead" not in l["url"]]
    links[:] = kept
    for link in links:
        is_music = "music" in link["url"]
        link.update({
            "title": "Low - Quorum" if is_music else "Some Trailer",
            "channel": "Sub Pop" if is_music else "Horror Channel",
            "is_music": is_music,
            "artist": "Low" if is_music else None,
            "collaborators": [],
            "track": "Quorum" if is_music else None,
            "genres": ["Rock"] if is_music else [],
            "styles": ["Slowcore"] if is_music else [],
        })


@pytest.fixture
def music_env(temp_dir, monkeypatch):
    """Wire main.py's globals to fakes; returns a context object for tests."""
    store = MusicStore(os.path.join(temp_dir, 'test.db'))
    platform_mock = MagicMock()
    monkeypatch.setattr(main, "music_store", store)
    monkeypatch.setattr(main, "platform", platform_mock)
    monkeypatch.setattr(main, "server_id", "server1")
    monkeypatch.setattr(main, "ENABLE_MUSIC_PROFILE", True)
    monkeypatch.setattr(main, "MUSIC_HISTORY_CHANNELS", "chan1")
    monkeypatch.setattr(main, "chatbot", MagicMock())
    monkeypatch.setattr(main.music, "enrich_links", fake_enrich)
    return type("Ctx", (), {"store": store, "platform": platform_mock, "monkeypatch": monkeypatch})


def set_channel(ctx, messages):
    channel = FakeChannel(messages)
    ctx.platform.get_channel.return_value = channel
    return channel


class TestExtractMusicHistory:

    async def test_disabled_is_clean_skip(self, music_env):
        music_env.monkeypatch.setattr(main, "ENABLE_MUSIC_PROFILE", False)
        await main.extract_music_history()
        main.platform.get_channel.assert_not_called()

    async def test_saves_music_with_attribution(self, music_env):
        set_channel(music_env, [
            music_message("https://youtu.be/music1", author_id="42", author_name="PosterOne"),
        ])
        await main.extract_music_history()
        entries = music_env.store.get_user_history("server1", "42")
        assert len(entries) == 1
        assert entries[0].artist == "Low"
        assert entries[0].genres == ["Rock"]
        assert entries[0].posted_by_name == "PosterOne"

    async def test_saves_non_music_with_flag(self, music_env):
        set_channel(music_env, [music_message("https://youtu.be/trailer1")])
        await main.extract_music_history()
        assert music_env.store.url_exists("server1", "https://youtu.be/trailer1")
        assert music_env.store.get_recent("server1") == []  # excluded from music queries

    async def test_known_urls_not_re_enriched(self, music_env):
        music_env.store.save(
            server_id="server1", channel_id="chan1", url="https://youtu.be/music1",
            video_title="t", video_channel="c", posted_by_id="u1",
            posted_by_name="PosterOne", posted_at=datetime.now(),
        )
        set_channel(music_env, [music_message("https://youtu.be/music1")])
        enrich_calls = []

        async def recording_enrich(links, chatbot, throttle_seconds=1.2):
            enrich_calls.append(list(links))
            await fake_enrich(links, chatbot)

        music_env.monkeypatch.setattr(main.music, "enrich_links", recording_enrich)
        await main.extract_music_history()
        assert enrich_calls == []  # nothing new -> enrichment never invoked

    async def test_bot_messages_skipped(self, music_env):
        set_channel(music_env, [
            FakeChatMessage(is_bot=True, content="https://youtu.be/music1"),
        ])
        await main.extract_music_history()
        assert not music_env.store.url_exists("server1", "https://youtu.be/music1")

    async def test_parse_failure_saves_nothing(self, music_env):
        set_channel(music_env, [music_message("https://youtu.be/music1")])

        async def failing_enrich(links, chatbot, throttle_seconds=1.2):
            raise MusicParseError("bad JSON")

        music_env.monkeypatch.setattr(main.music, "enrich_links", failing_enrich)
        await main.extract_music_history()
        assert not music_env.store.url_exists("server1", "https://youtu.be/music1")

    async def test_only_youtube_urls_collected(self, music_env):
        set_channel(music_env, [
            music_message("https://example.com/music-article"),
        ])
        await main.extract_music_history()
        assert not music_env.store.url_exists("server1", "https://example.com/music-article")


class TestBackfillMusicHistory:

    async def test_disabled_replies_and_stops(self, music_env):
        music_env.monkeypatch.setattr(main, "ENABLE_MUSIC_PROFILE", False)
        message = FakeChatMessage()
        await main.backfill_music_history(message, "!musicbackfill")
        assert "No MUSIC_HISTORY_CHANNELS" in message.replies[0]
        main.platform.get_channel.assert_not_called()

    async def test_days_argument_respected(self, music_env):
        channel = set_channel(music_env, [])
        message = FakeChatMessage()
        await main.backfill_music_history(message, "!musicbackfill 730")
        after = channel.history_calls[0]["after"]
        assert abs((datetime.now() - after) - timedelta(days=730)) < timedelta(minutes=5)
        assert "730 days" in message.replies[0]

    async def test_days_defaults_to_365_when_unparseable(self, music_env):
        channel = set_channel(music_env, [])
        message = FakeChatMessage()
        await main.backfill_music_history(message, "!musicbackfill soon")
        after = channel.history_calls[0]["after"]
        assert abs((datetime.now() - after) - timedelta(days=365)) < timedelta(minutes=5)

    async def test_rerun_is_idempotent(self, music_env):
        set_channel(music_env, [music_message("https://youtu.be/music1")])
        first = FakeChatMessage()
        await main.backfill_music_history(first, "!musicbackfill")
        assert "1 music" in first.replies[-1]

        second = FakeChatMessage()
        await main.backfill_music_history(second, "!musicbackfill")
        assert "0 new links found" in second.replies[-1]

    async def test_parse_is_chunked(self, music_env):
        music_env.monkeypatch.setattr(main, "MUSIC_BACKFILL_CHUNK_SIZE", 2)
        set_channel(music_env, [
            music_message(f"https://youtu.be/music{i}") for i in range(5)
        ])
        enrich_calls = []

        async def recording_enrich(links, chatbot, throttle_seconds=1.2):
            enrich_calls.append(len(links))
            await fake_enrich(links, chatbot)

        music_env.monkeypatch.setattr(main.music, "enrich_links", recording_enrich)
        message = FakeChatMessage()
        await main.backfill_music_history(message, "!musicbackfill")
        assert enrich_calls == [2, 2, 1]
        assert "5 music" in message.replies[-1]

    async def test_failed_chunk_skipped_and_run_continues(self, music_env):
        music_env.monkeypatch.setattr(main, "MUSIC_BACKFILL_CHUNK_SIZE", 2)
        set_channel(music_env, [
            music_message(f"https://youtu.be/music{i}") for i in range(4)
        ])
        calls = {"n": 0}

        async def flaky_enrich(links, chatbot, throttle_seconds=1.2):
            calls["n"] += 1
            if calls["n"] == 1:
                raise MusicParseError("bad JSON")
            await fake_enrich(links, chatbot)

        music_env.monkeypatch.setattr(main.music, "enrich_links", flaky_enrich)
        message = FakeChatMessage()
        await main.backfill_music_history(message, "!musicbackfill")
        assert "2 music" in message.replies[-1]
        assert "1 chunk(s) failed" in message.replies[-1]
        # failed chunk's links stay unsaved for a re-run
        assert not music_env.store.url_exists("server1", "https://youtu.be/music0")

    async def test_dead_link_does_not_abort(self, music_env):
        set_channel(music_env, [
            music_message("https://youtu.be/dead1"),
            music_message("https://youtu.be/music1"),
        ])
        message = FakeChatMessage()
        await main.backfill_music_history(message, "!musicbackfill")
        assert "1 music" in message.replies[-1]
        assert not music_env.store.url_exists("server1", "https://youtu.be/dead1")
