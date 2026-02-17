"""
Tests for the catch-up feature.

Note: handle_catch_up lives in main.py which has heavy module-level side effects
(starts the bot on import), so we test the logic indirectly:
- Tool definition structure
- Constants
- Time window calculation logic (replicated from handle_catch_up)
"""

import pytest
from datetime import datetime, timedelta

from src.tools.definitions import catch_up_tool
from src.utils.constants import CATCH_UP_MAX_HOURS, CATCH_UP_MAX_MESSAGES


class TestCatchUpToolDefinition:
    """Tests for the catch_up tool definition structure."""

    def test_tool_name(self):
        assert catch_up_tool["function"]["name"] == "catch_up"

    def test_has_hours_parameter(self):
        props = catch_up_tool["function"]["parameters"]["properties"]
        assert "hours" in props
        assert props["hours"]["type"] == "integer"

    def test_hours_not_required(self):
        required = catch_up_tool["function"]["parameters"].get("required", [])
        assert "hours" not in required

    def test_description_mentions_both_modes(self):
        desc = catch_up_tool["function"]["description"]
        assert "time range" in desc.lower() or "hours" in desc.lower()
        assert "last activity" in desc.lower() or "default" in desc.lower()


class TestCatchUpConstants:
    """Tests for catch-up related constants."""

    def test_max_hours_allows_weekly(self):
        assert CATCH_UP_MAX_HOURS >= 168, "Should support at least a week lookback"

    def test_max_messages_is_reasonable(self):
        assert CATCH_UP_MAX_MESSAGES > 0
        assert CATCH_UP_MAX_MESSAGES <= 1000


class TestCatchUpTimeWindowLogic:
    """
    Tests for the time window calculation logic used in handle_catch_up.

    This replicates the core branching logic from main.py without importing it,
    since main.py has module-level side effects that start the bot.
    """

    @staticmethod
    def calculate_since(hours=None, last_message_at=None):
        """
        Replicate the time window logic from handle_catch_up.

        Returns (since_datetime, used_activity_lookup: bool)
        """
        if hours is not None:
            clamped = min(int(hours), CATCH_UP_MAX_HOURS)
            return datetime.now() - timedelta(hours=clamped), False
        else:
            if last_message_at is None:
                return None, True  # No activity found
            return max(last_message_at, datetime.now() - timedelta(hours=CATCH_UP_MAX_HOURS)), True

    def test_explicit_hours_calculates_window(self):
        since, used_activity = self.calculate_since(hours=24)
        expected = datetime.now() - timedelta(hours=24)
        assert abs((since - expected).total_seconds()) < 2
        assert not used_activity

    def test_explicit_hours_clamped_to_max(self):
        since, _ = self.calculate_since(hours=9999)
        expected = datetime.now() - timedelta(hours=CATCH_UP_MAX_HOURS)
        assert abs((since - expected).total_seconds()) < 2

    def test_explicit_hours_today(self):
        """'today' maps to ~8 hours."""
        since, _ = self.calculate_since(hours=8)
        expected = datetime.now() - timedelta(hours=8)
        assert abs((since - expected).total_seconds()) < 2

    def test_explicit_hours_this_week(self):
        """'this week' maps to 168 hours."""
        since, _ = self.calculate_since(hours=168)
        expected = datetime.now() - timedelta(hours=168)
        assert abs((since - expected).total_seconds()) < 2

    def test_default_mode_uses_last_activity(self):
        last_seen = datetime.now() - timedelta(hours=6)
        since, used_activity = self.calculate_since(last_message_at=last_seen)
        assert abs((since - last_seen).total_seconds()) < 2
        assert used_activity

    def test_default_mode_caps_old_activity(self):
        """User away for 30 days should be capped to CATCH_UP_MAX_HOURS."""
        last_seen = datetime.now() - timedelta(days=30)
        since, _ = self.calculate_since(last_message_at=last_seen)
        expected = datetime.now() - timedelta(hours=CATCH_UP_MAX_HOURS)
        assert abs((since - expected).total_seconds()) < 2

    def test_default_mode_no_activity_returns_none(self):
        since, used_activity = self.calculate_since()
        assert since is None
        assert used_activity

    def test_explicit_zero_hours(self):
        """Edge case: hours=0 means 'right now'."""
        since, _ = self.calculate_since(hours=0)
        assert abs((since - datetime.now()).total_seconds()) < 2

    def test_explicit_hours_as_string_int(self):
        """The LLM might pass hours as a string — int() conversion should handle it."""
        since, _ = self.calculate_since(hours="24")
        expected = datetime.now() - timedelta(hours=24)
        assert abs((since - expected).total_seconds()) < 2
