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
