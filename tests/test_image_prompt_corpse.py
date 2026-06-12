"""
Tests for src/media/image_prompt_corpse.py — the blind-pass image prompt
pipeline.
"""

import json
import os
from types import SimpleNamespace

import pytest

from src.media import image_prompt_corpse
from src.persistence.image_store import ImageStore


CHAT = "alice: tomatoes from the market\nbob: also that 404 was hilarious"


class FakeChat:
    """A tiny stand-in for a chatbot.

    Each scripted reply is either a string (returned as ``response.message``)
    or a dict (returned as a tool call's JSON arguments).
    """

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def chat(self, messages, tools=None, temperature=1.0, model="", **_):
        self.calls.append({"messages": messages, "tools": tools, "model": model})
        if not self.replies:
            raise AssertionError("FakeChat ran out of scripted replies")
        reply = self.replies.pop(0)
        if isinstance(reply, dict):
            tool_call = SimpleNamespace(
                function=SimpleNamespace(arguments=json.dumps(reply))
            )
            return SimpleNamespace(message="", tool_calls=[tool_call])
        return SimpleNamespace(message=reply, tool_calls=None)


@pytest.fixture
def store(temp_dir):
    return ImageStore(os.path.join(temp_dir, "test.db"))


@pytest.fixture
def force_decoy(monkeypatch):
    monkeypatch.setattr(image_prompt_corpse.random, "random", lambda: 0.0)


@pytest.fixture
def skip_decoy(monkeypatch):
    monkeypatch.setattr(image_prompt_corpse.random, "random", lambda: 0.99)


def _final_payload():
    return {
        "prompt": "A long descriptive scene with style and mood.",
        "themes": ["mood", "style", "detail-1"],
        "reasoning": "Used the mood as lighting, the style as medium, details as flavour.",
    }


class TestBuild:
    async def test_returns_assembler_output_shape(self, store, force_decoy):
        chatbot = FakeChat([
            "DETAIL: a wonky kettle\nREASON: alice mentioned tomatoes and the kitchen feels lived-in.",
            "DETAIL: the smell of damp coats\nREASON: bob's 404 joke had a soggy, indoor texture to it.",
            "a tin of antique fishhooks",
            "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        result = await image_prompt_corpse.build(
            chat_text=CHAT,
            previous_themes_text="",
            bios_text="",
            user_locations="",
            cat_descriptions="",
            server_id="srv1",
            image_store=store,
            chatbot=chatbot,
        )
        assert result["prompt"].startswith("A long descriptive scene")
        assert result["themes"] == ["mood", "style", "detail-1"]
        assert result["reasoning"]

    async def test_persists_picks_for_future_exclusion(self, store, force_decoy):
        chatbot = FakeChat([
            "DETAIL: a wonky kettle\nREASON: alice mentioned tomatoes and the kitchen feels lived-in.",
            "DETAIL: the smell of damp coats\nREASON: bob's 404 joke had a soggy, indoor texture to it.",
            "a tin of antique fishhooks",
            "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        assert store.get_recent_slots("srv1", "detail") == [
            "the smell of damp coats",
            "a wonky kettle",
        ]
        assert store.get_recent_slots("srv1", "decoy") == ["a tin of antique fishhooks"]
        assert store.get_recent_slots("srv1", "mood") == ["gentle Tuesday melancholy"]
        assert store.get_recent_slots("srv1", "style") == [
            "Edward Hopper diner-light oil painting"
        ]

    async def test_decoy_skipped_when_probability_misses(self, store, skip_decoy):
        chatbot = FakeChat([
            "a wonky kettle",
            "the smell of damp coats",
            "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        # Only 5 LLM calls when decoy is skipped (no _pick_decoy call).
        assert len(chatbot.calls) == 5
        assert store.get_recent_slots("srv1", "decoy") == []

    async def test_exclude_lists_passed_into_pick_prompts(self, store, force_decoy):
        # Pre-seed the store with values so they should appear in exclude lists.
        store.save_recent_slot("srv1", "detail", "previous-detail-x")
        store.save_recent_slot("srv1", "decoy", "previous-decoy-y")
        store.save_recent_slot("srv1", "mood", "previous-mood-z")
        store.save_recent_slot("srv1", "style", "previous-style-q")

        chatbot = FakeChat([
            "a wonky kettle", "the smell of damp coats",
            "a tin of antique fishhooks", "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        # detail_1 (call 0) user message should mention the previous detail.
        detail_1_user = chatbot.calls[0]["messages"][1]["content"]
        assert "previous-detail-x" in detail_1_user
        # decoy (call 2) user message should mention the previous decoy.
        decoy_user = chatbot.calls[2]["messages"][1]["content"]
        assert "previous-decoy-y" in decoy_user
        # mood (call 3) and style (call 4) similarly.
        assert "previous-mood-z" in chatbot.calls[3]["messages"][1]["content"]
        assert "previous-style-q" in chatbot.calls[4]["messages"][1]["content"]

    async def test_second_detail_call_sees_first_detail(self, store, force_decoy):
        chatbot = FakeChat([
            "a wonky kettle", "the smell of damp coats",
            "a tin of antique fishhooks", "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        detail_2_user = chatbot.calls[1]["messages"][1]["content"]
        assert "a wonky kettle" in detail_2_user
        assert "different sense" in detail_2_user.lower() or "DIFFERENT" in detail_2_user

    async def test_assembler_has_no_chat_history(self, store, force_decoy):
        chatbot = FakeChat([
            "a wonky kettle", "the smell of damp coats",
            "a tin of antique fishhooks", "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        secret_phrase = "tomatoes from the market"
        await image_prompt_corpse.build(
            chat_text=secret_phrase + "\nbob: " + "secret_canary_phrase",
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        # The final call (index 5) is the assembler. It must NOT see the chat.
        assembler_messages = chatbot.calls[5]["messages"]
        full_text = "\n".join(m["content"] for m in assembler_messages)
        assert "secret_canary_phrase" not in full_text
        assert secret_phrase not in full_text

    async def test_assembler_receives_context_extras(self, store, force_decoy):
        chatbot = FakeChat([
            "a wonky kettle", "the smell of damp coats",
            "a tin of antique fishhooks", "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="last week: a teal kitchen",
            bios_text="alice: cellist; bob: pickler",
            user_locations="Bath and Manchester",
            cat_descriptions="Mango, a marmalade tabby",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        assembler_user = chatbot.calls[5]["messages"][1]["content"]
        assert "Bath and Manchester" in assembler_user
        assert "Mango" in assembler_user
        assert "cellist" in assembler_user
        assert "teal kitchen" in assembler_user

    async def test_decoy_call_does_not_see_chat(self, store, force_decoy):
        chatbot = FakeChat([
            "a wonky kettle", "the smell of damp coats",
            "a tin of antique fishhooks", "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text="canary_chat_marker",
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        decoy_messages = chatbot.calls[2]["messages"]
        full = "\n".join(m["content"] for m in decoy_messages)
        assert "canary_chat_marker" not in full

    async def test_style_call_does_not_see_chat(self, store, force_decoy):
        chatbot = FakeChat([
            "a wonky kettle", "the smell of damp coats",
            "a tin of antique fishhooks", "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text="canary_chat_marker",
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        style_messages = chatbot.calls[4]["messages"]
        full = "\n".join(m["content"] for m in style_messages)
        assert "canary_chat_marker" not in full

    async def test_evergreen_style_bans_in_prompt(self, store, force_decoy):
        chatbot = FakeChat([
            "a wonky kettle", "the smell of damp coats",
            "a tin of antique fishhooks", "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        style_user = chatbot.calls[4]["messages"][1]["content"]
        assert "Dutch Golden Age" in style_user
        assert "De Chirico" in style_user

    async def test_detail_reasons_reach_the_assembler(self, store, force_decoy):
        chatbot = FakeChat([
            "DETAIL: a wonky kettle\nREASON: alice's tomato remark hinted at a homely kitchen mood.",
            "DETAIL: the smell of damp coats\nREASON: bob's 404 joke had a soggy indoor texture.",
            "a tin of antique fishhooks",
            "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        assembler_user = chatbot.calls[5]["messages"][1]["content"]
        assert "a wonky kettle" in assembler_user
        assert "the smell of damp coats" in assembler_user
        assert "alice's tomato remark" in assembler_user
        assert "soggy indoor texture" in assembler_user
        # Only the detail itself goes into the anti-list, not the reason.
        saved = store.get_recent_slots("srv1", "detail")
        assert "a wonky kettle" in saved
        assert "the smell of damp coats" in saved
        assert not any("tomato remark" in s for s in saved)

    async def test_detail_picker_falls_back_when_unstructured(self, store, force_decoy):
        # Bare-string replies (no DETAIL:/REASON:) should still produce a usable
        # detail with an empty reason — graceful fallback.
        chatbot = FakeChat([
            "a wonky kettle",
            "the smell of damp coats",
            "a tin of antique fishhooks", "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        assembler_user = chatbot.calls[5]["messages"][1]["content"]
        assert "a wonky kettle" in assembler_user
        assert "the smell of damp coats" in assembler_user
        # No "(picked because: ...)" line when the reason was empty.
        assert "picked because" not in assembler_user

    async def test_sensitive_topics_guard_present_in_chat_facing_pickers(self, store, force_decoy):
        """The detail and mood picker system prompts must carry the sensitive-topics
        guard. History: the original images.py prompt had this guard and it was lost
        in the corpse refactor — once produced a miscarriage-themed image. Restoring
        it is a hard requirement, not a polish item."""
        chatbot = FakeChat([
            "a wonky kettle", "the smell of damp coats",
            "a tin of antique fishhooks", "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        # detail_1 (call 0), detail_2 (call 1), mood (call 3) — each must contain
        # the sensitive-topics guidance in the *system* prompt.
        for call_index, label in [(0, "detail_1"), (1, "detail_2"), (3, "mood")]:
            system_prompt = chatbot.calls[call_index]["messages"][0]["content"]
            assert "painful or sensitive life events" in system_prompt, (
                f"Sensitive-topics guard missing from {label} system prompt"
            )
            assert "miscarriage" in system_prompt, (
                f"Sensitive-topics skip list missing miscarriage in {label} prompt"
            )

    async def test_assembler_has_belt_and_braces_pain_guard(self, store, force_decoy):
        """Even if a poisoned ingredient slips past the picker, the assembler must
        be told not to reflect serious pain back into the image."""
        chatbot = FakeChat([
            "a wonky kettle", "the smell of damp coats",
            "a tin of antique fishhooks", "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        assembler_system = chatbot.calls[5]["messages"][0]["content"]
        assert "poisoned" in assembler_system
        assert "never appear cruel or tone-deaf" in assembler_system

    async def test_liz_truss_cameo_fires_when_probability_hits(self, store, force_decoy):
        """The main Discord server adopted Liz Truss as its ironic patron saint a
        week before she became PM. The legacy images.py prompt fired a cameo at
        LIZ_TRUSS_PROBABILITY (0.05) and the corpse refactor silently dropped it
        — same failure mode as the pain-guard regression. Restored 2026-05-15.
        Do not delete this test without re-checking the cameo wiring."""
        chatbot = FakeChat([
            "a wonky kettle", "the smell of damp coats",
            "a tin of antique fishhooks", "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        assembler_user = chatbot.calls[5]["messages"][1]["content"]
        assert "Liz Truss" in assembler_user
        assert "grotesque reference" in assembler_user

    async def test_liz_truss_cameo_skipped_when_probability_misses(self, store, skip_decoy):
        """skip_decoy fixture forces random.random() to 0.99 — above
        LIZ_TRUSS_PROBABILITY (0.05) — so the cameo must not appear."""
        chatbot = FakeChat([
            "a wonky kettle", "the smell of damp coats",
            "gentle Tuesday melancholy", "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        # Decoy is skipped, so the assembler call index shifts from 5 to 4.
        assembler_user = chatbot.calls[-1]["messages"][1]["content"]
        assert "Liz Truss" not in assembler_user

    async def test_news_decoy_fires_when_bulletins_available(self, store, force_decoy):
        """When news_bulletins are passed AND the decoy probability fires, the
        decoy is sourced from the news picker, not the random-thing picker.
        See ant gepettodiscordbot-Ed6UZ."""
        from src.content.news import Bulletin
        bulletins = [
            Bulletin(heading="UK politics", body="Burnham moves.", sources=[]),
            Bulletin(heading="In tech", body="A Waymo goes for a swim.", sources=[]),
        ]
        chatbot = FakeChat([
            "DETAIL: a wonky kettle\nREASON: r1.",
            "DETAIL: the smell of damp coats\nREASON: r2.",
            "a chancellor with tired eyes",  # news decoy pick
            "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, news_bulletins=bulletins,
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        # The decoy call (index 2) must be the news picker — its user message
        # contains the bulletin content, NOT the random-thing prompt.
        decoy_user = chatbot.calls[2]["messages"][1]["content"]
        assert "<news>" in decoy_user
        assert "Burnham moves" in decoy_user
        assert "Waymo" in decoy_user
        # The picked decoy went into the decoy anti-list slot.
        assert "a chancellor with tired eyes" in store.get_recent_slots("srv1", "decoy")

    async def test_news_decoy_picker_carries_sensitive_topics_guard(self, store, force_decoy):
        """Defence in depth: even though synthesis-time filtering already
        removed grim items, the news decoy picker also carries the guard.
        See ant gepettodiscordbot-sYVTv for why all chat/bio/news-reading
        stages must carry it."""
        from src.content.news import Bulletin
        bulletins = [Bulletin(heading="x", body="y", sources=[])]
        chatbot = FakeChat([
            "DETAIL: a kettle\nREASON: r.",
            "DETAIL: damp coats\nREASON: r.",
            "a chancellor with tired eyes",
            "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, news_bulletins=bulletins,
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        system = chatbot.calls[2]["messages"][0]["content"]
        assert "painful or sensitive life events" in system
        assert "miscarriage" in system

    async def test_falls_back_to_random_decoy_when_bulletins_empty(self, store, force_decoy):
        """An empty news_bulletins (network blip, empty cache) falls through to
        the random-thing decoy picker — original build() behaviour preserved."""
        chatbot = FakeChat([
            "DETAIL: a kettle\nREASON: r.",
            "DETAIL: damp coats\nREASON: r.",
            "a tin of antique fishhooks",  # random-thing pick
            "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build(
            chat_text=CHAT, news_bulletins=[],
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        decoy_system = chatbot.calls[2]["messages"][0]["content"]
        # Random-thing picker prompt, not the news one.
        assert "wildly unrelated random thing" not in decoy_system or "random concrete thing" in decoy_system
        decoy_user = chatbot.calls[2]["messages"][1]["content"]
        assert "<news>" not in decoy_user
        assert "wildly unrelated random thing" in decoy_user

    async def test_falls_back_when_tool_call_missing(self, store, force_decoy):
        chatbot = FakeChat([
            "a wonky kettle", "the smell of damp coats",
            "a tin of antique fishhooks", "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            "the model just replied with prose instead of a tool call",
        ])
        result = await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        assert "prose instead of a tool call" in result["prompt"]
        assert result["themes"] == []
        # The assembler produced no reasoning sentence, but the ingredient
        # log is still composed — handy for debugging exactly this failure.
        assert result["reasoning"].startswith("Ingredients")
        assert "a wonky kettle" in result["reasoning"]


    async def test_reasoning_includes_ingredient_log(self, store, force_decoy):
        """`--reasoning` shows the choices made along the way, not just the
        assembler's 1-3 sentences — every pick (and the picker's stated
        reason) is appended to the returned reasoning string."""
        chatbot = FakeChat([
            "DETAIL: a wonky kettle\nREASON: alice's tomato remark felt homely.",
            "DETAIL: the smell of damp coats\nREASON: bob's 404 joke had a soggy indoor texture.",
            "a tin of antique fishhooks",
            "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        result = await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        reasoning = result["reasoning"]
        # Assembler's own sentence comes first...
        assert reasoning.startswith("Used the mood as lighting")
        # ...followed by every pick and the why behind it.
        assert "Detail 1: a wonky kettle" in reasoning
        assert "alice's tomato remark felt homely." in reasoning
        assert "Detail 2: the smell of damp coats" in reasoning
        assert "soggy indoor texture" in reasoning
        assert "Mood: gentle Tuesday melancholy" in reasoning
        assert "Style: Edward Hopper diner-light oil painting" in reasoning
        assert "Decoy: a tin of antique fishhooks (random pick)" in reasoning
        # force_decoy pins random() to 0.0, so the cameo fires too.
        assert "Liz Truss cameo: fired" in reasoning

    async def test_reasoning_log_when_decoy_and_cameo_skipped(self, store, skip_decoy):
        chatbot = FakeChat([
            "a wonky kettle", "the smell of damp coats",
            "gentle Tuesday melancholy", "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        result = await image_prompt_corpse.build(
            chat_text=CHAT, previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        assert "Decoy: none this run" in result["reasoning"]
        assert "Liz Truss cameo: skipped" in result["reasoning"]
        # Bare-string picks have no reason — no stray markdown emphasis.
        assert "Detail 1: a wonky kettle\n" in result["reasoning"]

    async def test_reasoning_log_labels_news_decoy(self, store, force_decoy):
        from src.content.news import Bulletin
        bulletins = [Bulletin(heading="In tech", body="A Waymo goes for a swim.", sources=[])]
        chatbot = FakeChat([
            "DETAIL: a kettle\nREASON: r.",
            "DETAIL: damp coats\nREASON: r.",
            "a robotaxi nosed into floodwater",
            "gentle Tuesday melancholy",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        result = await image_prompt_corpse.build(
            chat_text=CHAT, news_bulletins=bulletins,
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        assert "Decoy: a robotaxi nosed into floodwater (from today's news)" in result["reasoning"]


class TestBuildQuiet:
    """Quiet-day variant: pickers source from bios + memories, mood from date."""

    def _bios(self):
        from src.persistence.memory_store import UserBio
        from datetime import datetime
        return [
            UserBio(server_id="srv1", user_id="u1", user_name="Mike",
                    bio="Collects vintage typewriters. Based in Bath.",
                    updated_at=datetime.now()),
            UserBio(server_id="srv1", user_id="u2", user_name="Alice",
                    bio="German heritage, lives in Madrid. Plays the cello.",
                    updated_at=datetime.now()),
        ]

    def _memories(self):
        from src.persistence.memory_store import Memory
        from datetime import datetime
        return [
            Memory(id=1, server_id="srv1", user_id="u1", user_name="Mike",
                   memory="recently took up sourdough baking", category="interest",
                   created_at=datetime.now(), expires_at=None,
                   last_referenced_at=None, reference_count=0),
            Memory(id=2, server_id="srv1", user_id="u2", user_name="Alice",
                   memory="has a new kitten named Whiskers", category="pet_new",
                   created_at=datetime.now(), expires_at=None,
                   last_referenced_at=None, reference_count=0),
        ]

    async def test_returns_assembler_output_shape(self, store, force_decoy):
        chatbot = FakeChat([
            "DETAIL: a vintage typewriter collection\nREASON: evocative of slow, deliberate craft.",
            "DETAIL: the warm tang of sourdough rising\nREASON: tactile, gustatory counterpoint.",
            "a tin of antique fishhooks",
            "soft Friday-afternoon stillness",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        result = await image_prompt_corpse.build_quiet(
            bios=self._bios(), memories=self._memories(),
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        assert result["prompt"].startswith("A long descriptive scene")
        assert result["themes"] == ["mood", "style", "detail-1"]

    async def test_pickers_receive_facts_blob_not_chat(self, store, force_decoy):
        chatbot = FakeChat([
            "DETAIL: a vintage typewriter collection\nREASON: r1.",
            "DETAIL: a kitten named Whiskers\nREASON: r2.",
            "a tin of antique fishhooks",
            "soft Friday-afternoon stillness",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build_quiet(
            bios=self._bios(), memories=self._memories(),
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        # detail_1 (call 0) and detail_2 (call 1) user messages must contain
        # bio + memory fragments wrapped in <facts>...</facts>.
        for call_index in (0, 1):
            facts_user = chatbot.calls[call_index]["messages"][1]["content"]
            assert "<facts>" in facts_user
            assert "vintage typewriters" in facts_user
            assert "sourdough" in facts_user

    async def test_quiet_pickers_carry_sensitive_topics_guard(self, store, force_decoy):
        chatbot = FakeChat([
            "DETAIL: a vintage typewriter collection\nREASON: r1.",
            "DETAIL: a kitten named Whiskers\nREASON: r2.",
            "a tin of antique fishhooks",
            "soft Friday-afternoon stillness",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build_quiet(
            bios=self._bios(), memories=self._memories(),
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        for call_index, label in [(0, "quiet_detail_1"), (1, "quiet_detail_2")]:
            system = chatbot.calls[call_index]["messages"][0]["content"]
            assert "painful or sensitive life events" in system, f"guard missing from {label}"
            assert "miscarriage" in system

    async def test_quiet_pickers_told_not_to_name_people(self, store, force_decoy):
        chatbot = FakeChat([
            "DETAIL: a vintage typewriter collection\nREASON: r1.",
            "DETAIL: a kitten named Whiskers\nREASON: r2.",
            "a tin of antique fishhooks",
            "soft Friday-afternoon stillness",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build_quiet(
            bios=self._bios(), memories=self._memories(),
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        for call_index in (0, 1):
            system = chatbot.calls[call_index]["messages"][0]["content"]
            assert "WITHOUT naming" in system or "without naming" in system.lower()

    async def test_mood_picker_uses_date_not_chat(self, store, force_decoy):
        chatbot = FakeChat([
            "DETAIL: a vintage typewriter collection\nREASON: r1.",
            "DETAIL: a kitten named Whiskers\nREASON: r2.",
            "a tin of antique fishhooks",
            "soft Friday-afternoon stillness",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build_quiet(
            bios=self._bios(), memories=self._memories(),
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        # Mood is call index 3 (after detail_1, detail_2, decoy).
        mood_messages = chatbot.calls[3]["messages"]
        system = mood_messages[0]["content"]
        user = mood_messages[1]["content"]
        assert "No chat" in system or "no chat to read" in system.lower()
        assert "Date:" in user

    async def test_persists_picks_for_future_exclusion(self, store, force_decoy):
        chatbot = FakeChat([
            "DETAIL: a vintage typewriter collection\nREASON: r1.",
            "DETAIL: a kitten named Whiskers\nREASON: r2.",
            "a tin of antique fishhooks",
            "soft Friday-afternoon stillness",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build_quiet(
            bios=self._bios(), memories=self._memories(),
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        details_saved = store.get_recent_slots("srv1", "detail")
        assert "a vintage typewriter collection" in details_saved
        assert "a kitten named Whiskers" in details_saved
        assert store.get_recent_slots("srv1", "decoy") == ["a tin of antique fishhooks"]
        assert store.get_recent_slots("srv1", "mood") == ["soft Friday-afternoon stillness"]

    async def test_reasoning_includes_ingredient_log(self, store, force_decoy):
        """The quiet-day path gets the same ingredient log, labelled so it's
        obvious which path produced the image."""
        chatbot = FakeChat([
            "DETAIL: a vintage typewriter collection\nREASON: evocative of slow, deliberate craft.",
            "DETAIL: the warm tang of sourdough rising\nREASON: tactile, gustatory counterpoint.",
            "a tin of antique fishhooks",
            "soft Friday-afternoon stillness",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        result = await image_prompt_corpse.build_quiet(
            bios=self._bios(), memories=self._memories(),
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        reasoning = result["reasoning"]
        assert "quiet day" in reasoning
        assert "Detail 1: a vintage typewriter collection" in reasoning
        assert "evocative of slow, deliberate craft." in reasoning
        assert "Mood: soft Friday-afternoon stillness" in reasoning
        assert "Liz Truss cameo: fired" in reasoning

    async def test_handles_empty_bios_and_memories(self, store, force_decoy):
        """build_quiet still runs with empty inputs; caller is responsible for fallback."""
        chatbot = FakeChat([
            "DETAIL: inventing something\nREASON: nothing to grip on.",
            "DETAIL: a vague feeling\nREASON: same.",
            "a tin of antique fishhooks",
            "soft Friday-afternoon stillness",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        result = await image_prompt_corpse.build_quiet(
            bios=[], memories=[],
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        assert result["prompt"]
        facts_user = chatbot.calls[0]["messages"][1]["content"]
        assert "<facts>" in facts_user  # tag present even if body is empty

    async def test_news_bulletins_reach_quiet_pickers(self, store, force_decoy):
        """News bulletins passed via the news_bulletins kwarg show up in the
        facts blob the quiet pickers see. The picker's system prompt has also
        been broadened to mention news so the LLM knows what it's looking at.
        See ant gepettodiscordbot-mjBCN."""
        from src.content.news import Bulletin
        bulletins = [
            Bulletin(heading="UK politics", body="Burnham makes his move.", sources=[]),
            Bulletin(heading="In tech", body="A Waymo goes for a swim.", sources=[]),
        ]
        chatbot = FakeChat([
            "DETAIL: a chancellor with tired eyes\nREASON: news mood.",
            "DETAIL: a robotaxi nosed into floodwater\nREASON: same news.",
            "a tin of antique fishhooks",
            "soft Friday-afternoon stillness",
            "Edward Hopper diner-light oil painting",
            _final_payload(),
        ])
        await image_prompt_corpse.build_quiet(
            bios=self._bios(), memories=self._memories(),
            news_bulletins=bulletins,
            previous_themes_text="", bios_text="",
            user_locations="", cat_descriptions="",
            server_id="srv1", image_store=store, chatbot=chatbot,
        )
        for call_index in (0, 1):
            user = chatbot.calls[call_index]["messages"][1]["content"]
            assert "Burnham makes his move" in user
            assert "Waymo goes for a swim" in user
            assert "Today's news" in user
            system = chatbot.calls[call_index]["messages"][0]["content"]
            assert "news" in system.lower(), "picker framing should mention news"


class TestFormatQuietFacts:
    def test_deduplicates_case_insensitively(self):
        from src.persistence.memory_store import UserBio, Memory
        from datetime import datetime
        bios = [
            UserBio(server_id="s", user_id="u1", user_name="A",
                    bio="Plays the cello", updated_at=datetime.now()),
            UserBio(server_id="s", user_id="u2", user_name="B",
                    bio="plays the cello", updated_at=datetime.now()),  # dup
        ]
        out = image_prompt_corpse.format_quiet_facts(bios, [])
        assert out.lower().count("plays the cello") == 1

    def test_handles_empty(self):
        assert image_prompt_corpse.format_quiet_facts([], []) == ""
        assert image_prompt_corpse.format_quiet_facts(None, None) == ""

    def test_mixes_bios_and_memories(self):
        from src.persistence.memory_store import UserBio, Memory
        from datetime import datetime
        bios = [UserBio(server_id="s", user_id="u1", user_name="A",
                        bio="German heritage", updated_at=datetime.now())]
        mems = [Memory(id=1, server_id="s", user_id="u1", user_name="A",
                       memory="has a new kitten", category="pet_new",
                       created_at=datetime.now(), expires_at=None,
                       last_referenced_at=None, reference_count=0)]
        out = image_prompt_corpse.format_quiet_facts(bios, mems)
        assert "German heritage" in out
        assert "has a new kitten" in out

    def test_news_bulletins_included_with_label(self):
        """Bulletins are mixed into the facts blob prefixed 'Today's news:' so
        the picker can see them as a distinct category alongside server facts.
        See ant gepettodiscordbot-mjBCN for the rationale."""
        from src.content.news import Bulletin
        bulletins = [
            Bulletin(heading="UK politics", body="Burnham makes his move.", sources=[]),
            Bulletin(heading="In tech", body="A Waymo goes for a swim.", sources=[]),
        ]
        out = image_prompt_corpse.format_quiet_facts([], [], news_bulletins=bulletins)
        assert "Today's news (UK politics): Burnham makes his move." in out
        assert "Today's news (In tech): A Waymo goes for a swim." in out

    def test_news_bulletins_optional(self):
        """Existing callers that don't pass news_bulletins must keep working."""
        out = image_prompt_corpse.format_quiet_facts([], [])
        assert out == ""

    def test_bulletin_without_heading_still_included(self):
        """A bulletin with only a body still gets a 'Today's news:' label."""
        bulletin = SimpleNamespace(heading="", body="something happened")
        out = image_prompt_corpse.format_quiet_facts([], [], news_bulletins=[bulletin])
        assert "Today's news: something happened" in out


class TestCleanPick:
    def test_strips_preamble(self):
        assert image_prompt_corpse._clean_pick("Detail: a kettle") == "a kettle"
        assert image_prompt_corpse._clean_pick("- a kettle") == "a kettle"

    def test_strips_quotes(self):
        assert image_prompt_corpse._clean_pick('"a kettle"') == "a kettle"
        assert image_prompt_corpse._clean_pick("'a kettle'") == "a kettle"
        assert image_prompt_corpse._clean_pick("“a kettle”") == "a kettle"

    def test_empty_safe(self):
        assert image_prompt_corpse._clean_pick("") == ""
        assert image_prompt_corpse._clean_pick("   ") == ""


class TestSplitDetailAndReason:
    def test_parses_two_line_format(self):
        raw = "DETAIL: a wonky kettle\nREASON: alice's tomato remark felt homely."
        detail, reason = image_prompt_corpse._split_detail_and_reason(raw)
        assert detail == "a wonky kettle"
        assert reason == "alice's tomato remark felt homely."

    def test_is_label_case_insensitive(self):
        raw = "detail: a kettle\nreason: it felt warm."
        detail, reason = image_prompt_corpse._split_detail_and_reason(raw)
        assert detail == "a kettle"
        assert reason == "it felt warm."

    def test_accepts_because_or_why_as_reason_label(self):
        raw = "DETAIL: a kettle\nBecause: it felt warm."
        _, reason = image_prompt_corpse._split_detail_and_reason(raw)
        assert reason == "it felt warm."

    def test_falls_back_to_first_line_when_unlabeled(self):
        detail, reason = image_prompt_corpse._split_detail_and_reason("a wonky kettle")
        assert detail == "a wonky kettle"
        assert reason == ""

    def test_handles_empty(self):
        assert image_prompt_corpse._split_detail_and_reason("") == ("", "")
        assert image_prompt_corpse._split_detail_and_reason("   ") == ("", "")
