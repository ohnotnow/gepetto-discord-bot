"""
Tests for src/utils/helpers.py
"""

import pytest
from datetime import datetime
from src.utils.helpers import (
    get_date_suffix,
    format_date_with_suffix,
    format_date_only,
    sanitize_filename,
    remove_emoji,
    remove_nsfw_words,
    clean_response_text,
    wrap_urls_for_discord,
)


class TestGetDateSuffix:
    """Tests for get_date_suffix function."""

    def test_1st(self):
        assert get_date_suffix(1) == "st"

    def test_2nd(self):
        assert get_date_suffix(2) == "nd"

    def test_3rd(self):
        assert get_date_suffix(3) == "rd"

    def test_4th(self):
        assert get_date_suffix(4) == "th"

    def test_11th(self):
        """11, 12, 13 are special cases - always 'th'."""
        assert get_date_suffix(11) == "th"

    def test_12th(self):
        assert get_date_suffix(12) == "th"

    def test_13th(self):
        assert get_date_suffix(13) == "th"

    def test_21st(self):
        assert get_date_suffix(21) == "st"

    def test_22nd(self):
        assert get_date_suffix(22) == "nd"

    def test_23rd(self):
        assert get_date_suffix(23) == "rd"

    def test_31st(self):
        assert get_date_suffix(31) == "st"


class TestFormatDateWithSuffix:
    """Tests for format_date_with_suffix function."""

    def test_formats_date_correctly(self):
        dt = datetime(2024, 1, 1, 10, 30)
        result = format_date_with_suffix(dt)
        assert "January 1st, 2024" in result
        assert "10:30" in result

    def test_handles_11th(self):
        dt = datetime(2024, 3, 11, 14, 0)
        result = format_date_with_suffix(dt)
        assert "March 11th, 2024" in result

    def test_defaults_to_now(self):
        """Should not raise when called without arguments."""
        result = format_date_with_suffix()
        assert isinstance(result, str)
        assert len(result) > 0


class TestFormatDateOnly:
    """Tests for format_date_only function."""

    def test_formats_date_without_time(self):
        dt = datetime(2024, 12, 25, 10, 30)
        result = format_date_only(dt)
        assert result == "December 25th, 2024"

    def test_no_time_component(self):
        dt = datetime(2024, 1, 1, 23, 59)
        result = format_date_only(dt)
        assert ":" not in result  # No time separator


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_removes_special_characters(self):
        result = sanitize_filename("hello world! @#$%")
        assert result == "hello_world______"

    def test_respects_max_length(self):
        long_text = "a" * 100
        result = sanitize_filename(long_text, max_length=50)
        assert len(result) == 50

    def test_keeps_alphanumeric(self):
        result = sanitize_filename("test123")
        assert result == "test123"

    def test_default_max_length(self):
        long_text = "a" * 100
        result = sanitize_filename(long_text)
        assert len(result) == 50  # Default max_length


class TestRemoveEmoji:
    """Tests for remove_emoji function."""

    def test_removes_emoticons(self):
        result = remove_emoji("Hello 😀 World")
        assert result == "Hello  World"

    def test_removes_symbols(self):
        result = remove_emoji("Test 🎉🎊 Party")
        assert result == "Test  Party"

    def test_preserves_text(self):
        result = remove_emoji("No emoji here")
        assert result == "No emoji here"

    def test_handles_empty_string(self):
        result = remove_emoji("")
        assert result == ""


class TestRemoveNsfwWords:
    """Tests for remove_nsfw_words function."""

    def test_removes_nsfw_words(self):
        result = remove_nsfw_words("This is a shit test")
        assert "shit" not in result.lower()

    def test_case_insensitive(self):
        result = remove_nsfw_words("FUCK this SHIT")
        assert "fuck" not in result.lower()
        assert "shit" not in result.lower()

    def test_removes_liz_truss(self):
        """Liz Truss is filtered for image prompts."""
        result = remove_nsfw_words("I love Liz Truss")
        assert "liz" not in result.lower()
        assert "truss" not in result.lower()

    def test_preserves_clean_text(self):
        result = remove_nsfw_words("This is a clean message")
        assert result == "This is a clean message"


class TestCleanResponseText:
    """Tests for clean_response_text function."""

    def test_removes_token_usage(self):
        text = "Hello world [tokens used: 100, Estimated cost: $0.01]"
        result = clean_response_text(text)
        assert "[tokens used" not in result
        assert "Estimated cost" not in result

    def test_removes_said_prefixes(self):
        text = "Gepetto' said: Hello there"
        result = clean_response_text(text)
        assert "Gepetto' said:" not in result

    def test_removes_minxie_said(self):
        text = "Minxie' said: Hi friend"
        result = clean_response_text(text)
        assert "Minxie' said:" not in result

    def test_preserves_clean_text(self):
        text = "This is a normal response"
        result = clean_response_text(text)
        assert result == "This is a normal response"


class TestWrapUrlsForDiscord:
    """Tests for wrap_urls_for_discord function."""

    def test_wraps_bare_http_url(self):
        result = wrap_urls_for_discord("Check https://example.com for info")
        assert "<https://example.com>" in result

    def test_wraps_bare_https_url(self):
        result = wrap_urls_for_discord("See http://example.com/page")
        assert "<http://example.com/page>" in result

    def test_does_not_double_wrap(self):
        result = wrap_urls_for_discord("Already wrapped <https://example.com> here")
        assert "<<https://example.com>>" not in result
        assert "<https://example.com>" in result

    def test_wraps_multiple_urls(self):
        text = "Links: https://one.com and https://two.com"
        result = wrap_urls_for_discord(text)
        assert "<https://one.com>" in result
        assert "<https://two.com>" in result

    def test_preserves_text_without_urls(self):
        text = "No URLs here, just plain text."
        assert wrap_urls_for_discord(text) == text

    def test_handles_url_in_parentheses(self):
        result = wrap_urls_for_discord("(https://example.com/path)")
        assert "<https://example.com/path>" in result
        # Should not include the closing paren in the URL
        assert "<https://example.com/path)>" not in result

    def test_handles_url_in_square_brackets(self):
        result = wrap_urls_for_discord("[https://example.com]")
        assert "<https://example.com>" in result

    def test_handles_url_with_query_params(self):
        result = wrap_urls_for_discord("https://example.com/page?foo=bar&baz=1")
        assert "<https://example.com/page?foo=bar&baz=1>" in result
