"""
SQLite-based persistence for user reminders.
"""

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = './data/gepetto.db'


@dataclass
class Reminder:
    """Represents a scheduled reminder."""
    id: int
    server_id: str
    user_id: str
    user_name: str
    channel_id: str
    reminder_text: str
    created_at: datetime
    remind_at: datetime
    reminded_at: Optional[datetime]


class ReminderStore:
    """SQLite-based storage for user reminders."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        parent = os.path.dirname(db_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent)

        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create table and indexes if they do not exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    reminder_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    remind_at TIMESTAMP NOT NULL,
                    reminded_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_reminders_due
                ON reminders(remind_at) WHERE reminded_at IS NULL
            """)
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    def save(self, server_id: str, user_id: str, user_name: str,
             channel_id: str, reminder_text: str, remind_at: datetime) -> int:
        """Insert a reminder and return its id."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reminders (server_id, user_id, user_name, channel_id, reminder_text, remind_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (server_id, user_id, user_name, channel_id, reminder_text, remind_at)
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_due_reminders(self, server_id: str) -> List[Reminder]:
        """Get reminders that are due and haven't been sent yet."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, server_id, user_id, user_name, channel_id,
                       reminder_text, created_at, remind_at, reminded_at
                FROM reminders
                WHERE server_id = ? AND remind_at <= ? AND reminded_at IS NULL
                """,
                (server_id, datetime.now())
            )
            rows = cursor.fetchall()

        return [self._row_to_reminder(row) for row in rows]

    def mark_reminded(self, reminder_id: int) -> None:
        """Mark a reminder as sent."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE reminders SET reminded_at = ? WHERE id = ?",
                (datetime.now(), reminder_id)
            )
            conn.commit()

    def count_pending_for_user(self, server_id: str, user_id: str) -> int:
        """Count pending (unsent) reminders for a user."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM reminders
                WHERE server_id = ? AND user_id = ? AND reminded_at IS NULL
                """,
                (server_id, user_id)
            )
            return cursor.fetchone()[0]

    def get_pending_for_user(self, server_id: str, user_id: str) -> List[Reminder]:
        """Get all pending reminders for a user."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, server_id, user_id, user_name, channel_id,
                       reminder_text, created_at, remind_at, reminded_at
                FROM reminders
                WHERE server_id = ? AND user_id = ? AND reminded_at IS NULL
                ORDER BY remind_at ASC
                """,
                (server_id, user_id)
            )
            rows = cursor.fetchall()

        return [self._row_to_reminder(row) for row in rows]

    def delete_reminder(self, reminder_id: int, user_id: str) -> bool:
        """Delete a reminder, checking it belongs to the user. Returns True if deleted."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM reminders WHERE id = ? AND user_id = ?",
                (reminder_id, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def prune(self, days: int = 30) -> int:
        """Delete old sent reminders. Returns number of rows deleted."""
        cutoff = datetime.now() - timedelta(days=days)
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM reminders WHERE reminded_at IS NOT NULL AND reminded_at < ?",
                (cutoff,)
            )
            conn.commit()
            return cursor.rowcount

    def _row_to_reminder(self, row: tuple) -> Reminder:
        """Convert a database row to a Reminder dataclass."""
        id_, server_id, user_id, user_name, channel_id, reminder_text, created_at, remind_at, reminded_at = row

        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        if isinstance(remind_at, str):
            remind_at = datetime.fromisoformat(remind_at)
        if isinstance(reminded_at, str):
            reminded_at = datetime.fromisoformat(reminded_at)

        return Reminder(
            id=id_,
            server_id=server_id,
            user_id=user_id,
            user_name=user_name,
            channel_id=channel_id,
            reminder_text=reminder_text,
            created_at=created_at,
            remind_at=remind_at,
            reminded_at=reminded_at,
        )
