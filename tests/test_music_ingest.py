"""
Tests for src/content/music.py — the music link enrichment pipeline.

No live calls: HTTP, LLM, and Discogs client are all mocked. Fake Discogs
release objects are hand-rolled (not MagicMock) because MagicMock().data
returns a truthy MagicMock and the genre-reading loop would silently do
nothing while appearing to pass.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.content.music import (
    MusicParseError,
    YOUTUBE_URL_RE,
    artist_genres,
    enrich_links,
    fetch_oembed,
    parse_titles,
)


class StubChatbot:
    """Minimal chatbot stub recording chat() kwargs and returning a canned reply."""

    def __init__(self, reply: str):
        self.reply = reply
        self.calls = []

    async def chat(self, messages, model="", json_mode=False, tools=None):
        self.calls.append({
            "messages": messages,
            "model": model,
            "json_mode": json_mode,
        })
        return SimpleNamespace(message=self.reply)


class RecordingRelease:
    """Fake Discogs search result: real .data dict, records any lazy attribute access."""

    def __init__(self, data):
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "lazy_accesses", [])

    def __getattr__(self, name):
        self.lazy_accesses.append(name)
        return None


def parse_reply(entries) -> str:
    return json.dumps({"entries": entries})


class TestYoutubeUrlRe:

    def test_matches_watch_and_short_forms(self):
        text = "see https://www.youtube.com/watch?v=abc_12-3 and https://youtu.be/xyz789"
        assert len(YOUTUBE_URL_RE.findall(text)) == 2

    def test_ignores_other_urls(self):
        assert YOUTUBE_URL_RE.findall("https://example.com/watch?v=abc") == []


class TestFetchOembed:

    @patch("src.content.music.requests.get")
    async def test_returns_title_and_channel_on_200(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"title": "Low - Quorum", "author_name": "Sub Pop"},
        )
        result = await fetch_oembed("https://youtu.be/abc")
        assert result == {"title": "Low - Quorum", "channel": "Sub Pop"}

    @patch("src.content.music.requests.get")
    async def test_returns_none_on_400(self, mock_get):
        mock_get.return_value = MagicMock(status_code=400)
        assert await fetch_oembed("https://youtu.be/dead") is None

    @patch("src.content.music.requests.get")
    async def test_returns_none_on_request_exception(self, mock_get):
        import requests as requests_lib
        mock_get.side_effect = requests_lib.ConnectionError("boom")
        assert await fetch_oembed("https://youtu.be/abc") is None


class TestParseTitles:

    def make_links(self):
        return [
            {"url": "https://youtu.be/a", "channel": "CreationBaby", "title": "Tricky feat. PJ Harvey - Broken Homes"},
            {"url": "https://youtu.be/b", "channel": "Via Cinema", "title": "When an audition changed cinema"},
        ]

    def good_reply(self):
        return parse_reply([
            {"index": 1, "is_music": True, "artist": "Tricky", "collaborators": ["PJ Harvey"], "track": "Broken Homes"},
            {"index": 2, "is_music": False, "artist": None, "collaborators": [], "track": None},
        ])

    async def test_populates_fields(self):
        links = self.make_links()
        await parse_titles(links, StubChatbot(self.good_reply()))
        assert links[0]["is_music"] is True
        assert links[0]["artist"] == "Tricky"
        assert links[0]["collaborators"] == ["PJ Harvey"]
        assert links[0]["track"] == "Broken Homes"
        assert links[1]["is_music"] is False
        assert links[1]["artist"] is None

    async def test_handles_code_fenced_json(self):
        links = self.make_links()
        fenced = f"```json\n{self.good_reply()}\n```"
        await parse_titles(links, StubChatbot(fenced))
        assert links[0]["artist"] == "Tricky"

    async def test_raises_on_non_json(self):
        with pytest.raises(MusicParseError):
            await parse_titles(self.make_links(), StubChatbot("I am not JSON, sorry"))

    async def test_raises_when_entries_missing(self):
        with pytest.raises(MusicParseError):
            await parse_titles(self.make_links(), StubChatbot(json.dumps({"oops": []})))

    async def test_uses_music_parse_model_when_set(self, monkeypatch):
        monkeypatch.setenv("MUSIC_PARSE_MODEL", "openai/gpt-5.6-luna")
        chatbot = StubChatbot(self.good_reply())
        await parse_titles(self.make_links(), chatbot)
        assert chatbot.calls[0]["model"] == "openai/gpt-5.6-luna"
        assert chatbot.calls[0]["json_mode"] is True

    async def test_empty_model_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("MUSIC_PARSE_MODEL", raising=False)
        chatbot = StubChatbot(self.good_reply())
        await parse_titles(self.make_links(), chatbot)
        assert chatbot.calls[0]["model"] == ""

    async def test_empty_links_makes_no_llm_call(self):
        chatbot = StubChatbot(self.good_reply())
        await parse_titles([], chatbot)
        assert chatbot.calls == []


class TestArtistGenres:

    def make_client(self, releases):
        client = MagicMock()
        client.search.return_value = releases
        return client

    @patch("src.content.music._get_client")
    async def test_one_search_call_and_data_access_only(self, mock_get_client):
        releases = [
            RecordingRelease({"genre": ["Rock", "Electronic"], "style": ["Indie Rock"]}),
            RecordingRelease({"genre": ["Rock"], "style": []}),
        ]
        client = self.make_client(releases)
        mock_get_client.return_value = client

        result = await artist_genres("Low")

        client.search.assert_called_once_with(artist="Low", type="release")
        assert result["found"] is True
        assert result["genres"][0] == "Rock"  # most common first
        assert "Indie Rock" in result["styles"]
        for release in releases:
            assert release.lazy_accesses == []  # never touched a lazy attribute

    @patch("src.content.music._get_client")
    async def test_no_token_returns_found_false(self, mock_get_client):
        mock_get_client.return_value = None
        result = await artist_genres("Low")
        assert result["found"] is False
        assert result["genres"] == []
        assert result["styles"] == []

    @patch("src.content.music._get_client")
    async def test_no_results_returns_found_false(self, mock_get_client):
        mock_get_client.return_value = self.make_client([])
        result = await artist_genres("Nonexistent Band")
        assert result == {"found": False, "error": "no releases found", "genres": [], "styles": []}

    @patch("src.content.music._get_client")
    async def test_search_exception_returns_found_false(self, mock_get_client):
        client = MagicMock()
        client.search.side_effect = RuntimeError("api down")
        mock_get_client.return_value = client
        result = await artist_genres("Low")
        assert result["found"] is False
        assert result["genres"] == []


class TestEnrichLinks:

    def oembed_side_effect(self, mapping):
        async def fake(url):
            return mapping.get(url)
        return fake

    @patch("src.content.music.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.content.music.artist_genres", new_callable=AsyncMock)
    @patch("src.content.music.fetch_oembed")
    async def test_full_pipeline_with_artist_dedupe_and_throttle(
            self, mock_oembed, mock_genres, mock_sleep):
        links = [
            {"url": "https://youtu.be/a", "poster": "someposter"},
            {"url": "https://youtu.be/b", "poster": "someposter"},
            {"url": "https://youtu.be/dead", "poster": "someposter"},
        ]
        mock_oembed.side_effect = self.oembed_side_effect({
            "https://youtu.be/a": {"title": "Low - Quorum", "channel": "Sub Pop"},
            "https://youtu.be/b": {"title": "Low - Always Trying", "channel": "Sub Pop"},
        })
        chatbot = StubChatbot(parse_reply([
            {"index": 1, "is_music": True, "artist": "Low", "collaborators": [], "track": "Quorum"},
            {"index": 2, "is_music": True, "artist": "Low", "collaborators": [], "track": "Always Trying"},
        ]))
        mock_genres.return_value = {"found": True, "genres": ["Rock"], "styles": ["Slowcore"]}

        await enrich_links(links, chatbot)

        # dead link dropped in place
        assert [l["url"] for l in links] == ["https://youtu.be/a", "https://youtu.be/b"]
        # same artist twice = one lookup, one throttle sleep
        mock_genres.assert_called_once_with("Low")
        assert mock_sleep.await_count == 1
        # both links got the genres
        assert links[0]["genres"] == ["Rock"]
        assert links[1]["styles"] == ["Slowcore"]
        # caller-owned keys untouched
        assert links[0]["poster"] == "someposter"

    @patch("src.content.music.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.content.music.artist_genres", new_callable=AsyncMock)
    @patch("src.content.music.fetch_oembed")
    async def test_lookup_miss_still_sets_empty_lists(
            self, mock_oembed, mock_genres, mock_sleep):
        links = [{"url": "https://youtu.be/a"}, {"url": "https://youtu.be/b"}]
        mock_oembed.side_effect = self.oembed_side_effect({
            "https://youtu.be/a": {"title": "Skilled Mechanics - Diving Away", "channel": "Trickyofficial"},
            "https://youtu.be/b": {"title": "Los Vampires | Trailer", "channel": "Horror"},
        })
        chatbot = StubChatbot(parse_reply([
            {"index": 1, "is_music": True, "artist": "Skilled Mechanics", "collaborators": [], "track": "Diving Away"},
            {"index": 2, "is_music": False, "artist": None, "collaborators": [], "track": None},
        ]))
        mock_genres.return_value = {"found": False, "error": "no releases found", "genres": [], "styles": []}

        await enrich_links(links, chatbot)

        # miss and non-music rows both carry the keys the store expects
        assert links[0]["genres"] == []
        assert links[0]["styles"] == []
        assert links[1]["genres"] == []
        assert links[1]["styles"] == []
        # non-music link got no Discogs lookup
        mock_genres.assert_called_once_with("Skilled Mechanics")

    @patch("src.content.music.fetch_oembed")
    async def test_all_dead_links_returns_early_without_llm_call(self, mock_oembed):
        mock_oembed.side_effect = self.oembed_side_effect({})
        links = [{"url": "https://youtu.be/dead"}]
        chatbot = StubChatbot("should never be called")
        await enrich_links(links, chatbot)
        assert links == []
        assert chatbot.calls == []

    @patch("src.content.music.fetch_oembed")
    async def test_parse_failure_propagates(self, mock_oembed):
        mock_oembed.side_effect = self.oembed_side_effect({
            "https://youtu.be/a": {"title": "Low - Quorum", "channel": "Sub Pop"},
        })
        with pytest.raises(MusicParseError):
            await enrich_links([{"url": "https://youtu.be/a"}], StubChatbot("garbage"))
