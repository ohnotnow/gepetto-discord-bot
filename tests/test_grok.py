import os

import pytest
from unittest.mock import patch, MagicMock

from src.providers.grok import _format_for_discord


def _make_stream_chunks(content_parts, tool_call_names=None, citations=None):
    """Build a list of (response, chunk) tuples to simulate chat.stream()."""
    chunks = []
    final_response = MagicMock()
    final_response.citations = citations

    for i, text in enumerate(content_parts):
        chunk = MagicMock()
        chunk.content = text
        chunk.tool_calls = []
        if tool_call_names and i == 0:
            for name in tool_call_names:
                tc = MagicMock()
                tc.function.name = name
                chunk.tool_calls.append(tc)
        # Each iteration yields the accumulating response
        chunks.append((final_response, chunk))

    return chunks


class TestFormatForDiscord:
    def test_collapses_blank_lines(self):
        result = _format_for_discord("line1\n\n\nline2", None)
        assert result == "line1\nline2"

    def test_converts_mentions_to_links(self):
        result = _format_for_discord("Check @elonmusk for updates", None)
        assert "<https://x.com/elonmusk>" in result

    def test_does_not_convert_email_mentions(self):
        result = _format_for_discord("Email user@example.com", None)
        assert "x.com" not in result

    def test_wraps_bare_urls(self):
        result = _format_for_discord("See https://example.com/page for info", None)
        assert "<https://example.com/page>" in result

    def test_adds_citations(self):
        result = _format_for_discord("Content", ["https://twitter.com/status/1", "https://twitter.com/status/2"])
        assert "**Sources:**" in result
        assert "twitter.com/status/1" in result
        assert "twitter.com/status/2" in result

    def test_limits_citations_to_five(self):
        urls = [f"https://twitter.com/status/{i}" for i in range(10)]
        result = _format_for_discord("Content", urls)
        url_count = result.count("twitter.com/status/")
        assert url_count == 5

    def test_truncates_to_1800(self):
        result = _format_for_discord("x" * 2000, None)
        assert len(result) <= 1800


class TestSearch:
    @pytest.mark.asyncio
    @patch.dict(os.environ, {"XAI_API_KEY": "test-key"})
    async def test_search_returns_response(self):
        from src.providers import grok

        chunks = _make_stream_chunks(["Here is what people are saying about AI"])

        with patch("src.providers.grok.Client") as mock_client_cls:
            mock_chat = MagicMock()
            mock_chat.stream.return_value = chunks
            mock_client_cls.return_value.chat.create.return_value = mock_chat

            result = await grok.search("AI news")

        assert len(result) > 0
        assert "AI" in result

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"XAI_API_KEY": "test-key"})
    async def test_search_includes_citations(self):
        from src.providers import grok

        citations = ["https://twitter.com/user/status/123", "https://twitter.com/user/status/456"]
        chunks = _make_stream_chunks(["Breaking news about the event"], citations=citations)

        with patch("src.providers.grok.Client") as mock_client_cls:
            mock_chat = MagicMock()
            mock_chat.stream.return_value = chunks
            mock_client_cls.return_value.chat.create.return_value = mock_chat

            result = await grok.search("breaking news")

        assert "Sources:" in result
        assert "twitter.com" in result

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"XAI_API_KEY": "test-key"})
    async def test_search_truncates_long_response(self):
        from src.providers import grok

        chunks = _make_stream_chunks(["x" * 2000])

        with patch("src.providers.grok.Client") as mock_client_cls:
            mock_chat = MagicMock()
            mock_chat.stream.return_value = chunks
            mock_client_cls.return_value.chat.create.return_value = mock_chat

            result = await grok.search("test query")

        assert len(result) <= 1800

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"XAI_API_KEY": "test-key"})
    async def test_search_uses_correct_model(self):
        from src.providers import grok

        chunks = _make_stream_chunks(["Response"])

        with patch("src.providers.grok.Client") as mock_client_cls:
            mock_chat = MagicMock()
            mock_chat.stream.return_value = chunks
            mock_client_cls.return_value.chat.create.return_value = mock_chat

            await grok.search("test")

        call_kwargs = mock_client_cls.return_value.chat.create.call_args
        assert "grok" in call_kwargs.kwargs["model"].lower()

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"XAI_API_KEY": "test-key"})
    async def test_search_handles_empty_content(self):
        from src.providers import grok

        chunks = _make_stream_chunks([None])

        with patch("src.providers.grok.Client") as mock_client_cls:
            mock_chat = MagicMock()
            mock_chat.stream.return_value = chunks
            mock_client_cls.return_value.chat.create.return_value = mock_chat

            result = await grok.search("test query")

        assert result == "No Twitter results found."

    @pytest.mark.asyncio
    async def test_search_missing_api_key(self):
        from src.providers import grok

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XAI_API_KEY", None)
            result = await grok.search("test")

        assert "not configured" in result
