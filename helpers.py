"""
Helper functions for the Gepetto Discord bot.
"""

from datetime import datetime


def get_date_suffix(day: int) -> str:
    """Return the ordinal suffix for a day number (st, nd, rd, th)."""
    if 11 <= day <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def format_date_with_suffix(dt: datetime = None) -> str:
    """Format a datetime with ordinal suffix, e.g., 'January 1st, 2024 10:30 AM'."""
    if dt is None:
        dt = datetime.now()
    suffix = get_date_suffix(dt.day)
    return dt.strftime(f"%B {dt.day}{suffix}, %Y %I:%M %p")


def format_date_only(dt: datetime = None) -> str:
    """Format a datetime with ordinal suffix, date only, e.g., 'January 1st, 2024'."""
    if dt is None:
        dt = datetime.now()
    suffix = get_date_suffix(dt.day)
    return dt.strftime(f"%B {dt.day}{suffix}, %Y")
