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
        assert result["reasoning"] == ""


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
