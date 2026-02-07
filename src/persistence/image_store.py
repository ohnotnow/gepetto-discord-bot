"""
SQLite-based persistence for image generation history.
"""

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

MAX_ENTRIES_PER_SERVER = 10


@dataclass
class ImageEntry:
    """Represents a single image generation record."""
    id: int
    server_id: str
    themes: List[str]
    reasoning: str
    prompt: str
    image_url: Optional[str]
    created_at: datetime

    @property
    def themes_str(self) -> str:
        """Return themes as comma-separated string for display."""
        return ", ".join(self.themes)


class ImageStore:
    """SQLite-based storage for image generation history, keyed by server_id."""

    def __init__(self, db_path: str = './data/gepetto.db'):
        """
        Initialize the store, creating DB and table if needed.

        Args:
            db_path: Path to SQLite database. Defaults to ./data/gepetto.db
        """
        # Ensure parent directory exists
        parent = os.path.dirname(db_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent)

        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create table and index if they do not exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS image_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id TEXT NOT NULL,
                    themes TEXT NOT NULL,
                    reasoning TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    image_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_server_id
                ON image_history(server_id, id DESC)
            """)
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    def save(
        self,
        server_id: str,
        themes: List[str],
        reasoning: str,
        prompt: str,
        image_url: Optional[str] = None
    ) -> int:
        """
        Save an image entry. Auto-prunes to keep last 10 per server.

        Returns the ID of the inserted record.
        """
        themes_json = json.dumps(themes)

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO image_history (server_id, themes, reasoning, prompt, image_url)
                VALUES (?, ?, ?, ?, ?)
                """,
                (server_id, themes_json, reasoning, prompt, image_url)
            )
            conn.commit()
            inserted_id = cursor.lastrowid

        # Prune old entries after insert
        self._prune(server_id)

        return inserted_id or 0

    def _prune(self, server_id: str, keep: int = MAX_ENTRIES_PER_SERVER) -> None:
        """Delete all but the most recent keep entries for server_id."""
        with self._get_connection() as conn:
            conn.execute(
                """
                DELETE FROM image_history
                WHERE server_id = ?
                AND id NOT IN (
                    SELECT id FROM image_history
                    WHERE server_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                """,
                (server_id, server_id, keep)
            )
            conn.commit()

    def get_recent(self, server_id: str, limit: int = 10) -> List[ImageEntry]:
        """Get the most recent entries for a server, newest first."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, server_id, themes, reasoning, prompt, image_url, created_at
                FROM image_history
                WHERE server_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (server_id, limit)
            )
            rows = cursor.fetchall()

        return [self._row_to_entry(row) for row in rows]

    def get_latest(self, server_id: str) -> Optional[ImageEntry]:
        """Get the single most recent entry for a server, or None."""
        entries = self.get_recent(server_id, limit=1)
        return entries[0] if entries else None

    def get_previous_themes(self, server_id: str, limit: int = 10) -> str:
        """
        Get themes as newline-separated string.

        For backward compatibility with load_previous_themes().
        Returns format like: "theme1, theme2\ntheme3, theme4"
        """
        entries = self.get_recent(server_id, limit=limit)
        if not entries:
            return ""

        return "\n".join(entry.themes_str for entry in entries)

    def _row_to_entry(self, row: tuple) -> ImageEntry:
        """Convert a database row tuple to an ImageEntry."""
        id_, server_id, themes_json, reasoning, prompt, image_url, created_at = row

        themes = json.loads(themes_json)

        # Parse timestamp - SQLite returns string
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return ImageEntry(
            id=id_,
            server_id=server_id,
            themes=themes,
            reasoning=reasoning,
            prompt=prompt,
            image_url=image_url,
            created_at=created_at
        )
