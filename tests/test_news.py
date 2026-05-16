"""Tests for src/content/news.py — the news-bulletin pipeline."""

import json
from types import SimpleNamespace

import pytest

from src.content import news
from src.content.news import (
    Bulletin,
    Item,
    clean_summary,
    dedupe,
    get_news_bulletins,
    grim_match,
    synthesise_bulletins,
)


def _item(title: str = "Headline", summary: str = "", categories=None, feed: str = "uk") -> Item:
    return Item(feed=feed, title=title, summary=summary, categories=list(categories or []))


class FakeChat:
    """Stand-in chatbot. Each scripted reply is a dict (returned as
    response.message after JSON encoding) or a string (returned verbatim)."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if not self.replies:
            raise AssertionError("FakeChat ran out of scripted replies")
        reply = self.replies.pop(0)
        if isinstance(reply, dict):
            return SimpleNamespace(message=json.dumps(reply))
        return SimpleNamespace(message=reply)


class TestCleanSummary:
    def test_strips_html_tags(self):
        assert clean_summary("<p>Hello <b>world</b></p>") == "Hello world"

    def test_collapses_whitespace(self):
        assert clean_summary("Lots   of    space\n\nhere") == "Lots of space here"

    def test_handles_empty_and_none(self):
        assert clean_summary("") == ""
        assert clean_summary(None) == ""

    def test_no_truncation(self):
        long = "word " * 200
        assert len(clean_summary(long)) > 800


class TestGrimMatch:
    """Each keyword must match BOTH its singular and plural form. The whole
    reason this list got an `s?` pass in the first place was that singular-
    only regexes let 'victims' through while 'victim' was supposedly blocked."""

    @pytest.mark.parametrize("singular,plural", [
        ("war", "wars"),
        ("murder", "murders"),
        ("shooting", "shootings"),
        ("killing", "killings"),
        ("victim", "victims"),
    ])
    def test_matches_both_forms(self, singular, plural):
        assert grim_match(_item(title=f"A {singular} happened")) is not None
        assert grim_match(_item(title=f"Several {plural} reported")) is not None

    def test_matches_eurovision_singular(self):
        # 'eurovision' doesn't pluralise — singular only.
        assert grim_match(_item(title="Eurovision 2026 final")) is not None

    def test_case_insensitive(self):
        assert grim_match(_item(title="MURDER inquiry")) is not None
        assert grim_match(_item(title="Eurovision SEMI-FINAL")) is not None

    def test_clean_items_return_none(self):
        assert grim_match(_item(title="Orchid breeders' arms race")) is None
        assert grim_match(_item(title="Waymo robotaxi in a creek")) is None

    def test_word_boundary_prevents_false_positives(self):
        # 'warden', 'Warwickshire', 'wardrobe' must not match 'war'.
        # 'victimless' must not match 'victim'. The whole reason the keyword
        # patterns use \b in the first place.
        assert grim_match(_item(title="Warwickshire warden's wardrobe")) is None
        assert grim_match(_item(title="A victimless prank")) is None

    def test_matches_in_summary(self):
        item = _item(title="Local council update", summary="The murder inquiry continues")
        assert grim_match(item) is not None

    def test_matches_in_categories(self):
        item = _item(title="Foreign policy briefing", categories=["War in Ukraine"])
        assert grim_match(item) is not None


class TestDedupe:
    def test_drops_exact_duplicate_titles(self):
        items = [_item(title="Same"), _item(title="Same"), _item(title="Different")]
        result = dedupe(items)
        assert [i.title for i in result] == ["Same", "Different"]

    def test_dedupe_is_case_insensitive(self):
        items = [_item(title="Hello World"), _item(title="hello world")]
        assert len(dedupe(items)) == 1

    def test_preserves_first_occurrence_order(self):
        items = [_item(title="A"), _item(title="B"), _item(title="A"), _item(title="C")]
        assert [i.title for i in dedupe(items)] == ["A", "B", "C"]

    def test_drops_empty_titles(self):
        items = [_item(title=""), _item(title="A")]
        assert [i.title for i in dedupe(items)] == ["A"]


class TestSynthesiseBulletins:
    async def test_returns_parsed_bulletins(self):
        items = [
            _item(title="Burnham byelection", summary="Andy stands"),
            _item(title="Waymo creek", summary="Robotaxi in flood"),
        ]
        chatbot = FakeChat([
            {"bulletins": [
                {"heading": "UK politics", "body": "Burnham makes his move.", "sources": [1]},
                {"heading": "In tech", "body": "A Waymo goes for a swim.", "sources": [2]},
            ]}
        ])
        bulletins = await synthesise_bulletins(items, chatbot, max_bulletins=5)
        assert len(bulletins) == 2
        assert bulletins[0].heading == "UK politics"
        assert bulletins[0].body == "Burnham makes his move."
        assert bulletins[0].sources[0].title == "Burnham byelection"
        assert bulletins[1].sources[0].title == "Waymo creek"

    async def test_max_bulletins_renders_into_prompt(self):
        chatbot = FakeChat([{"bulletins": []}])
        await synthesise_bulletins([_item()], chatbot, max_bulletins=3)
        system = chatbot.calls[0]["messages"][0]["content"]
        assert "AT MOST 3 thematic" in system

    async def test_model_override_passed_through(self):
        chatbot = FakeChat([{"bulletins": []}])
        await synthesise_bulletins([_item()], chatbot, max_bulletins=5, model="openai/gpt-4o")
        assert chatbot.calls[0]["kwargs"].get("model") == "openai/gpt-4o"

    async def test_model_omitted_when_none(self):
        chatbot = FakeChat([{"bulletins": []}])
        await synthesise_bulletins([_item()], chatbot, max_bulletins=5)
        assert "model" not in chatbot.calls[0]["kwargs"]

    async def test_uses_json_mode(self):
        chatbot = FakeChat([{"bulletins": []}])
        await synthesise_bulletins([_item()], chatbot, max_bulletins=5)
        assert chatbot.calls[0]["kwargs"].get("json_mode") is True

    async def test_empty_items_skips_call(self):
        chatbot = FakeChat([])  # nothing scripted — would error if called
        result = await synthesise_bulletins([], chatbot, max_bulletins=5)
        assert result == []
        assert chatbot.calls == []

    async def test_bad_json_returns_empty(self):
        chatbot = FakeChat(["not valid json at all"])
        result = await synthesise_bulletins([_item()], chatbot, max_bulletins=5)
        assert result == []

    async def test_skips_bulletins_missing_required_fields(self):
        items = [_item(title="A"), _item(title="B")]
        chatbot = FakeChat([{"bulletins": [
            {"heading": "Good", "body": "Has a body.", "sources": [1]},
            {"heading": "Missing body", "sources": [2]},  # no body — skipped
            {"body": "No heading either", "sources": [1]},  # no heading — skipped
        ]}])
        bulletins = await synthesise_bulletins(items, chatbot, max_bulletins=5)
        assert [b.heading for b in bulletins] == ["Good"]

    async def test_invalid_source_indices_dropped(self):
        items = [_item(title="A"), _item(title="B")]
        chatbot = FakeChat([{"bulletins": [
            {"heading": "H", "body": "B.", "sources": [1, 99, "not-an-int", 2]},
        ]}])
        bulletins = await synthesise_bulletins(items, chatbot, max_bulletins=5)
        assert [s.title for s in bulletins[0].sources] == ["A", "B"]

    async def test_items_appear_numbered_in_prompt(self):
        items = [
            _item(title="First story", summary="<p>Lead paragraph</p>"),
            _item(title="Second story"),
        ]
        chatbot = FakeChat([{"bulletins": []}])
        await synthesise_bulletins(items, chatbot, max_bulletins=5)
        user = chatbot.calls[0]["messages"][1]["content"]
        assert "1. [uk] First story" in user
        # Summary HTML should be cleaned before being sent to the LLM.
        assert "Lead paragraph" in user
        assert "<p>" not in user
        assert "2. [uk] Second story" in user


class TestGetNewsBulletins:
    """End-to-end orchestration: fetch → dedupe → grim-cull → synthesise.
    Network is monkeypatched out — feedparser itself is not under test."""

    async def test_end_to_end_with_fake_feed_and_chatbot(self, monkeypatch):
        canned = {
            "uk": [
                _item(title="Burnham byelection", feed="uk"),
                _item(title="Murder inquiry continues", feed="uk"),  # culled
                _item(title="Burnham byelection", feed="uk"),  # dup, deduped
            ],
            "technology": [
                _item(title="Waymo creek", feed="technology"),
                _item(title="Eurovision tech-judge speaks", feed="technology"),  # culled
            ],
        }

        def fake_fetch(name, url, *, per_feed):
            return canned.get(name, [])

        monkeypatch.setattr(news, "fetch_feed", fake_fetch)
        monkeypatch.setattr(news, "FEEDS", {"uk": "u", "technology": "t"})

        chatbot = FakeChat([{"bulletins": [
            {"heading": "UK politics", "body": "Burnham moves.", "sources": [1]},
            {"heading": "In tech", "body": "Waymo swims.", "sources": [2]},
        ]}])

        result = await get_news_bulletins(chatbot, max_bulletins=5)
        assert [b.heading for b in result] == ["UK politics", "In tech"]
        # The LLM only saw the two grim-cull survivors (after dedupe).
        user = chatbot.calls[0]["messages"][1]["content"]
        assert "Burnham byelection" in user
        assert "Waymo creek" in user
        assert "Murder inquiry" not in user
        assert "Eurovision" not in user

    async def test_unknown_feed_name_logged_and_skipped(self, monkeypatch, caplog):
        monkeypatch.setattr(news, "fetch_feed", lambda *a, **kw: [])
        monkeypatch.setattr(news, "FEEDS", {"uk": "u"})
        chatbot = FakeChat([{"bulletins": []}])
        result = await get_news_bulletins(chatbot, feeds=["uk", "does_not_exist"])
        assert result == []

    async def test_no_survivors_skips_llm_call(self, monkeypatch):
        monkeypatch.setattr(news, "fetch_feed", lambda *a, **kw: [_item(title="A war story")])
        monkeypatch.setattr(news, "FEEDS", {"uk": "u"})
        chatbot = FakeChat([])  # would error if called
        result = await get_news_bulletins(chatbot, feeds=["uk"])
        assert result == []
        assert chatbot.calls == []


class TestGetNewsBulletinsWithCache:
    """Cache layer: when news_store is passed, second call within TTL must
    not re-fetch or re-synthesise. See ait gepetto-discord-bot-YHETx."""

    def _store(self, tmp_path):
        from src.persistence.news_store import NewsStore
        return NewsStore(str(tmp_path / "news.db"))

    async def test_cache_hit_skips_fetch_and_synthesis(self, monkeypatch, tmp_path):
        fetch_calls = {"count": 0}

        def fake_fetch(name, url, *, per_feed):
            fetch_calls["count"] += 1
            return [_item(title="Burnham byelection")]

        monkeypatch.setattr(news, "fetch_feed", fake_fetch)
        monkeypatch.setattr(news, "FEEDS", {"uk": "u"})

        store = self._store(tmp_path)
        chatbot = FakeChat([
            {"bulletins": [{"heading": "UK politics", "body": "Burnham moves.", "sources": [1]}]},
        ])  # only one scripted reply — second call would error if not cached

        first = await get_news_bulletins(chatbot, news_store=store)
        second = await get_news_bulletins(chatbot, news_store=store)

        assert [b.heading for b in first] == ["UK politics"]
        assert [b.heading for b in second] == ["UK politics"]
        assert fetch_calls["count"] == 1, "second call must hit the cache, not refetch"
        assert len(chatbot.calls) == 1, "second call must hit the cache, not re-synthesise"

    async def test_without_store_always_fresh(self, monkeypatch, tmp_path):
        """Without a news_store, every call fetches and synthesises afresh —
        no implicit caching."""
        fetch_calls = {"count": 0}

        def fake_fetch(name, url, *, per_feed):
            fetch_calls["count"] += 1
            return [_item(title="A")]

        monkeypatch.setattr(news, "fetch_feed", fake_fetch)
        monkeypatch.setattr(news, "FEEDS", {"uk": "u"})

        chatbot = FakeChat([
            {"bulletins": [{"heading": "X", "body": "y.", "sources": [1]}]},
            {"bulletins": [{"heading": "X", "body": "y.", "sources": [1]}]},
        ])

        await get_news_bulletins(chatbot)
        await get_news_bulletins(chatbot)
        assert fetch_calls["count"] == 2
        assert len(chatbot.calls) == 2

    async def test_empty_bulletins_not_cached(self, monkeypatch, tmp_path):
        """A transient miss (no survivors, empty LLM reply) shouldn't poison
        the cache — otherwise we'd serve [] for the rest of the TTL window."""
        monkeypatch.setattr(news, "fetch_feed", lambda *a, **kw: [])
        monkeypatch.setattr(news, "FEEDS", {"uk": "u"})

        store = self._store(tmp_path)
        chatbot = FakeChat([])
        result = await get_news_bulletins(chatbot, news_store=store)
        assert result == []
        assert store.get_cached_bulletins(max_age_hours=3) is None

    async def test_stale_cache_triggers_fresh_fetch(self, monkeypatch, tmp_path):
        """A cache older than max_age_hours is treated as a miss; the function
        re-fetches and re-saves."""
        from datetime import datetime, timedelta
        import sqlite3

        monkeypatch.setattr(news, "fetch_feed", lambda *a, **kw: [_item(title="Fresh")])
        monkeypatch.setattr(news, "FEEDS", {"uk": "u"})
        store = self._store(tmp_path)
        chatbot = FakeChat([
            {"bulletins": [{"heading": "stale", "body": "before.", "sources": [1]}]},
            {"bulletins": [{"heading": "fresh", "body": "after.", "sources": [1]}]},
        ])

        await get_news_bulletins(chatbot, news_store=store)
        # Backdate the cache to be stale.
        old_time = (datetime.now() - timedelta(hours=24)).isoformat()
        with sqlite3.connect(store.db_path) as conn:
            conn.execute("UPDATE news_cache SET fetched_at = ? WHERE id = 1", (old_time,))
            conn.commit()
        second = await get_news_bulletins(chatbot, news_store=store, max_age_hours=3)
        assert second[0].heading == "fresh"
