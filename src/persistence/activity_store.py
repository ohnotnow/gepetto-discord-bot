"""
SQLite-based persistence for user activity tracking.
"""

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = './data/gepetto.db'


@dataclass
class UserActivity:
    """Represents a user's last activity record."""
    server_id: str
    user_id: str
    user_name: str
    last_message_at: datetime
    channel_id: str


class ActivityStore:
    """SQLite-based storage for user activity, keyed by server_id and user_id."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        """
        Initialize the store, creating DB and table if needed.

        Args:
            db_path: Path to SQLite database. Defaults to ./data/gepetto.db
        """
        parent = os.path.dirname(db_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent)

        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create table and indexes if they do not exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_activity (
                    server_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    last_message_at TIMESTAMP NOT NULL,
                    channel_id TEXT NOT NULL,
                    PRIMARY KEY (server_id, user_id)
                )
            """)
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    def record_activity(
        self,
        server_id: str,
        user_id: str,
        user_name: str,
        channel_id: str,
        timestamp: datetime
    ) -> None:
        """
        Record user activity, updating if already exists (upsert).

        Args:
            server_id: The Discord server ID
            user_id: The Discord user ID
            user_name: The user's display name
            channel_id: The channel where the message was sent
            timestamp: When the message was sent
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_activity (server_id, user_id, user_name, last_message_at, channel_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(server_id, user_id) DO UPDATE SET
                    user_name = excluded.user_name,
                    last_message_at = excluded.last_message_at,
                    channel_id = excluded.channel_id
                """,
                (server_id, user_id, user_name, timestamp, channel_id)
            )
            conn.commit()

    def get_last_activity(self, server_id: str, user_id: str) -> Optional[UserActivity]:
        """
        Get the last recorded activity for a user.

        Args:
            server_id: The Discord server ID
            user_id: The Discord user ID

        Returns:
            UserActivity if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT server_id, user_id, user_name, last_message_at, channel_id
                FROM user_activity
                WHERE server_id = ? AND user_id = ?
                """,
                (server_id, user_id)
            )
            row = cursor.fetchone()

        if not row:
            return None

        server_id, user_id, user_name, last_message_at, channel_id = row

        if isinstance(last_message_at, str):
            last_message_at = datetime.fromisoformat(last_message_at)

        return UserActivity(
            server_id=server_id,
            user_id=user_id,
            user_name=user_name,
            last_message_at=last_message_at,
            channel_id=channel_id
        )
