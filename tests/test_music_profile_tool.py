"""
Tests for the get_music_profile tool: definition, formatter, and handler.

The suite has no precedent for dispatch-testing main.py's tool branch, so
coverage is: the tool definition dict (shape check, like test_discogs.py's
TestToolDefinitions), format_music_profile driven directly, and
handle_get_music_profile driven with a real temp-db MusicStore and fakes
for platform/chatbot.
"""

import os
import re
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import main
from src.persistence.music_store import MusicStore
from src.tools.definitions import get_music_profile_tool


class FakeTyping:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeChannel:
    def typing(self):
        return FakeTyping()


class FakeChatMessage:
    def __init__(self, author_id="42", author_name="SomePoster"):
        self.author_id = author_id
        self.author_name = author_name
        self.author_display_name = author_name
        self.author_mention = f"<@{author_id}>"
        self.channel_id = "chan1"
        self.replies = []

    async def reply(self, text, **kwargs):
        self.replies.append(text)


class RecordingChatbot:
    def __init__(self):
        self.calls = []

    async def chat(self, messages, temperature=1.0, model="", json_mode=False, tools=None):
        self.calls.append({"messages": list(messages), "tools": tools})
        return SimpleNamespace(message="Here is a playlist.", usage_short="[usage]")


def tool_call_stub():
    return SimpleNamespace(id="t1", function=SimpleNamespace(name="get_music_profile", arguments="{}"))


def seed_store(store):
    """Three music links for SomePoster (Low x2, Suuns x1), one for another user."""
    rows = [
        ("https://youtu.be/one", "Low", "Quorum", ["Rock"], ["Slowcore"], "42", "SomePoster"),
        ("https://youtu.be/two", "Low", "Always Trying", ["Rock"], ["Slowcore"], "42", "SomePoster"),
        ("https://youtu.be/three", "Suuns", "2020", ["Electronic"], ["Leftfield"], "42", "SomePoster"),
        ("https://youtu.be/four", "Pendulum", "Halo", ["Electronic"], ["Drum n Bass"], "99", "OtherUser"),
    ]
    for url, artist, track, genres, styles, user_id, user_name in rows:
        store.save(
            server_id="server1", channel_id="chan1", url=url,
            video_title=f"{artist} - {track}", video_channel="chan",
            posted_by_id=user_id, posted_by_name=user_name, posted_at=datetime.now(),
            artist=artist, track=track, genres=genres, styles=styles,
        )


@pytest.fixture
def profile_env(temp_dir, monkeypatch):
    store = MusicStore(os.path.join(temp_dir, 'test.db'))
    platform_mock = MagicMock()
    platform_mock.get_channel.return_value = FakeChannel()
    chatbot = RecordingChatbot()
    monkeypatch.setattr(main, "music_store", store)
    monkeypatch.setattr(main, "platform", platform_mock)
    monkeypatch.setattr(main, "chatbot", chatbot)
    monkeypatch.setattr(main, "server_id", "server1")
    monkeypatch.setattr(main, "ENABLE_DISCOGS", False)
    return type("Ctx", (), {"store": store, "chatbot": chatbot, "monkeypatch": monkeypatch})


def appended_tool_content(chatbot):
    """The [Music profile data ...] message the handler appended before the follow-up."""
    return chatbot.calls[-1]["messages"][-1]["content"]


class TestToolDefinition:

    def test_structure(self):
        fn = get_music_profile_tool["function"]
        assert fn["name"] == "get_music_profile"
        assert "user_name" in fn["parameters"]["properties"]
        assert fn["parameters"]["required"] == []


class TestFormatMusicProfile:

    def make_inputs(self, store):
        seed_store(store)
        counts = store.profile_counts("server1", "42")
        entries = store.get_user_history("server1", "42")
        return counts, entries

    def test_contains_artists_genres_styles_and_tracks(self, temp_dir):
        store = MusicStore(os.path.join(temp_dir, 'test.db'))
        counts, entries = self.make_inputs(store)
        text = main.format_music_profile("SomePoster", counts, entries)
        assert "Low (2)" in text
        assert "Rock (2)" in text
        assert "Slowcore (2)" in text
        assert "Suuns — 2020" in text

    def test_every_url_wrapped_in_angle_brackets(self, temp_dir):
        store = MusicStore(os.path.join(temp_dir, 'test.db'))
        counts, entries = self.make_inputs(store)
        text = main.format_music_profile("SomePoster", counts, entries)
        assert "<https://youtu.be/one>" in text
        assert re.search(r"(?<!<)https?://", text) is None  # no bare URL anywhere

    def test_skips_rows_with_null_artist_or_track(self, temp_dir):
        store = MusicStore(os.path.join(temp_dir, 'test.db'))
        store.save(
            server_id="server1", channel_id="chan1", url="https://youtu.be/mystery",
            video_title="???", video_channel="chan",
            posted_by_id="42", posted_by_name="SomePoster", posted_at=datetime.now(),
            artist=None, track=None,
        )
        counts = store.profile_counts("server1", "42")
        entries = store.get_user_history("server1", "42")
        text = main.format_music_profile("SomePoster", counts, entries)
        assert "None" not in text
        assert "Recent tracks" not in text  # nothing renderable


class TestHandleGetMusicProfile:

    async def run_handler(self, ctx, arguments, message=None):
        message = message or FakeChatMessage()
        await main.handle_get_music_profile(message, tool_call_stub(), arguments, [], 0.7)
        return message

    async def test_no_history_is_graceful_with_no_tools(self, profile_env):
        message = await self.run_handler(profile_env, {"user_name": "nobody"})
        assert "No music history found for nobody" in appended_tool_content(profile_env.chatbot)
        assert profile_env.chatbot.calls[-1]["tools"] == []
        assert message.replies  # the LLM's graceful reply went out

    async def test_defaults_to_message_author(self, profile_env):
        seed_store(profile_env.store)
        await self.run_handler(profile_env, {})
        content = appended_tool_content(profile_env.chatbot)
        assert "Music profile for SomePoster" in content
        assert "Low (2)" in content
        assert profile_env.chatbot.calls[-1]["tools"] == []

    async def test_resolves_name_with_leading_at(self, profile_env):
        seed_store(profile_env.store)
        requester = FakeChatMessage(author_id="99", author_name="OtherUser")
        await self.run_handler(profile_env, {"user_name": "@someposter"}, message=requester)
        assert "Low (2)" in appended_tool_content(profile_env.chatbot)

    async def test_resolves_raw_mention_form(self, profile_env):
        seed_store(profile_env.store)
        requester = FakeChatMessage(author_id="99", author_name="OtherUser")
        await self.run_handler(profile_env, {"user_name": "<@42>"}, message=requester)
        assert "Low (2)" in appended_tool_content(profile_env.chatbot)

    async def test_explore_data_included_for_top_two_artists(self, profile_env):
        seed_store(profile_env.store)
        profile_env.monkeypatch.setattr(main, "ENABLE_DISCOGS", True)
        explore = AsyncMock(side_effect=lambda a: f"## {a}\nnetwork data")
        profile_env.monkeypatch.setattr(main.discogs, "explore_artist", explore)
        await self.run_handler(profile_env, {})
        content = appended_tool_content(profile_env.chatbot)
        assert "Artist network data" in content
        assert explore.await_count == 2
        explored = {call.args[0] for call in explore.await_args_list}
        assert "Low" in explored  # top artist definitely included
