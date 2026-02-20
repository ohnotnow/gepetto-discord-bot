"""
Tests for src/tasks/memories.py — extraction and bio synthesis.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.tasks.memories import extract_memories_from_history, synthesise_bio
from src.providers.response import ChatResponse


def _make_chat_response(message):
    """Create a ChatResponse with the given message text."""
    return ChatResponse(
        message=message, tokens=10, cost=0.001, model="test",
        duration=1.0, completion_tokens=10,
    )


def _mock_chatbot(response_text):
    """Create a mock chatbot that returns the given text."""
    chatbot = MagicMock()
    chatbot.chat = AsyncMock(return_value=_make_chat_response(response_text))
    return chatbot


class TestExtractMemoriesFromHistory:
    """Tests for extract_memories_from_history()."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_messages(self):
        chatbot = _mock_chatbot("{}")
        result = await extract_memories_from_history(chatbot, [])
        assert result == {"memories": [], "bio_updates": []}
        chatbot.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_extracts_memories_and_bio_updates(self):
        llm_response = json.dumps({
            "memories": [
                {"user_id": "123", "user_name": "Alice", "memory": "has a cold", "category": "health_temporary"}
            ],
            "bio_updates": [
                {"user_id": "123", "user_name": "Alice", "bio_addition": "lives in Norwich"}
            ]
        })
        chatbot = _mock_chatbot(llm_response)
        messages = [{"author_id": "123", "author_name": "Alice", "content": "I have a cold"}]

        result = await extract_memories_from_history(chatbot, messages)

        assert len(result["memories"]) == 1
        assert result["memories"][0]["memory"] == "has a cold"
        assert len(result["bio_updates"]) == 1
        assert result["bio_updates"][0]["bio_addition"] == "lives in Norwich"

    @pytest.mark.asyncio
    async def test_skips_malformed_entries(self):
        llm_response = json.dumps({
            "memories": [
                {"user_id": "123"},  # missing required fields
                {"user_id": "456", "user_name": "Bob", "memory": "valid", "category": "general"}
            ],
            "bio_updates": [
                {"user_id": "123"},  # missing required fields
            ]
        })
        chatbot = _mock_chatbot(llm_response)
        messages = [{"author_id": "123", "author_name": "Alice", "content": "test"}]

        result = await extract_memories_from_history(chatbot, messages)

        assert len(result["memories"]) == 1
        assert result["memories"][0]["user_id"] == "456"
        assert len(result["bio_updates"]) == 0

    @pytest.mark.asyncio
    async def test_handles_invalid_json(self):
        chatbot = _mock_chatbot("not valid json at all")
        messages = [{"author_id": "123", "author_name": "Alice", "content": "test"}]

        result = await extract_memories_from_history(chatbot, messages)

        assert result == {"memories": [], "bio_updates": []}

    @pytest.mark.asyncio
    async def test_handles_llm_failure(self):
        chatbot = MagicMock()
        chatbot.chat = AsyncMock(side_effect=Exception("API error"))
        messages = [{"author_id": "123", "author_name": "Alice", "content": "test"}]

        result = await extract_memories_from_history(chatbot, messages)

        assert result == {"memories": [], "bio_updates": []}

    @pytest.mark.asyncio
    async def test_existing_bios_included_in_prompt(self):
        llm_response = json.dumps({"memories": [], "bio_updates": []})
        chatbot = _mock_chatbot(llm_response)
        messages = [{"author_id": "123", "author_name": "Alice", "content": "hello"}]
        existing_bios = {"123": "Alice lives in Norwich and works at DEFRA."}

        await extract_memories_from_history(chatbot, messages, existing_bios=existing_bios)

        # Check the user message sent to the LLM includes the existing bio
        call_args = chatbot.chat.call_args
        user_content = call_args.kwargs["messages"][1]["content"]
        assert "Alice lives in Norwich" in user_content
        assert "only extract NEW facts" in user_content

    @pytest.mark.asyncio
    async def test_no_existing_bios_omits_context(self):
        llm_response = json.dumps({"memories": [], "bio_updates": []})
        chatbot = _mock_chatbot(llm_response)
        messages = [{"author_id": "123", "author_name": "Alice", "content": "hello"}]

        await extract_memories_from_history(chatbot, messages)

        call_args = chatbot.chat.call_args
        user_content = call_args.kwargs["messages"][1]["content"]
        assert "Existing bios" not in user_content


class TestSynthesiseBio:
    """Tests for synthesise_bio()."""

    @pytest.mark.asyncio
    async def test_creates_new_bio_from_facts(self):
        chatbot = _mock_chatbot("Alice is a software developer based in Norwich who enjoys boxing.")
        result = await synthesise_bio(chatbot, "Alice", None, ["works in software", "lives in Norwich", "does boxing"])

        assert result == "Alice is a software developer based in Norwich who enjoys boxing."

    @pytest.mark.asyncio
    async def test_merges_with_existing_bio(self):
        chatbot = _mock_chatbot("Alice is a Laravel developer at DEFRA, based in Norwich. She enjoys boxing and manages a small team.")

        result = await synthesise_bio(
            chatbot, "Alice",
            "Alice is a Laravel developer based in Norwich.",
            ["works at DEFRA", "does boxing", "manages a direct report"]
        )

        assert "DEFRA" in result
        assert "Norwich" in result

    @pytest.mark.asyncio
    async def test_passes_existing_bio_in_prompt(self):
        chatbot = _mock_chatbot("Updated bio.")

        await synthesise_bio(chatbot, "Alice", "Existing bio text here.", ["new fact"])

        call_args = chatbot.chat.call_args
        user_content = call_args.kwargs["messages"][1]["content"]
        assert "Existing bio text here." in user_content
        assert "Current bio:" in user_content

    @pytest.mark.asyncio
    async def test_no_existing_bio_in_prompt(self):
        chatbot = _mock_chatbot("A new bio.")

        await synthesise_bio(chatbot, "Alice", None, ["lives in Norwich"])

        call_args = chatbot.chat.call_args
        user_content = call_args.kwargs["messages"][1]["content"]
        assert "Current bio:" not in user_content
        assert "Facts to build a bio from:" in user_content

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure_with_existing_bio(self):
        chatbot = MagicMock()
        chatbot.chat = AsyncMock(side_effect=Exception("API error"))

        result = await synthesise_bio(chatbot, "Alice", "Existing bio.", ["new fact one", "new fact two"])

        assert result == "Existing bio.; new fact one; new fact two"

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure_no_existing_bio(self):
        chatbot = MagicMock()
        chatbot.chat = AsyncMock(side_effect=Exception("API error"))

        result = await synthesise_bio(chatbot, "Alice", None, ["fact one", "fact two"])

        assert result == "fact one; fact two"

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_response(self):
        chatbot = _mock_chatbot("  A bio with extra whitespace.  \n")

        result = await synthesise_bio(chatbot, "Alice", None, ["some fact"])

        assert result == "A bio with extra whitespace."
