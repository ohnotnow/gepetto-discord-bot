"""
SQLite-based persistence for URL history and summaries.
"""

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = './data/gepetto.db'
MAX_ENTRIES_PER_SERVER = 500


@dataclass
class UrlEntry:
    """Represents a single URL record."""
    id: int
    server_id: str
    channel_id: str
    url: str
    summary: str
    keywords: str
    posted_by_id: str
    posted_by_name: str
    posted_at: datetime
    created_at: datetime


class UrlStore:
    """SQLite-based storage for URL history, keyed by server_id."""

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
                CREATE TABLE IF NOT EXISTS url_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    keywords TEXT NOT NULL,
                    posted_by_id TEXT NOT NULL,
                    posted_by_name TEXT NOT NULL,
                    posted_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_url_history_server
                ON url_history(server_id, id DESC)
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_url_history_unique
                ON url_history(server_id, url)
            """)
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    def url_exists(self, server_id: str, url: str) -> bool:
        """Check if a URL already exists for this server."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT 1 FROM url_history
                WHERE server_id = ? AND url = ?
                LIMIT 1
                """,
                (server_id, url)
            )
            return cursor.fetchone() is not None

    def save(
        self,
        server_id: str,
        channel_id: str,
        url: str,
        summary: str,
        keywords: str,
        posted_by_id: str,
        posted_by_name: str,
        posted_at: datetime
    ) -> Optional[int]:
        """
        Save a URL entry. Returns None if URL already exists.

        Returns the ID of the inserted record, or None if duplicate.
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO url_history
                    (server_id, channel_id, url, summary, keywords, posted_by_id, posted_by_name, posted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (server_id, channel_id, url, summary, keywords, posted_by_id, posted_by_name, posted_at)
                )
                conn.commit()
                inserted_id = cursor.lastrowid

                # Prune old entries after insert
                self._prune(server_id)

                return inserted_id
            except sqlite3.IntegrityError:
                # Duplicate URL
                return None

    def _prune(self, server_id: str, keep: int = MAX_ENTRIES_PER_SERVER) -> None:
        """Delete all but the most recent entries for server_id."""
        with self._get_connection() as conn:
            conn.execute(
                """
                DELETE FROM url_history
                WHERE server_id = ?
                AND id NOT IN (
                    SELECT id FROM url_history
                    WHERE server_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                """,
                (server_id, server_id, keep)
            )
            conn.commit()

    # Common words to ignore in searches
    STOPWORDS = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                 'of', 'with', 'by', 'is', 'it', 'as', 'be', 'was', 'were', 'been',
                 'that', 'this', 'what', 'which', 'who', 'how', 'when', 'where', 'why'}

    def search(self, server_id: str, query: str, limit: int = 10) -> List[UrlEntry]:
        """
        Search URLs by matching query against summary and keywords.

        Uses simple LIKE matching with the query terms.
        Filters out stopwords and very short terms to avoid matching everything.
        """
        # Split query into words, filter out stopwords and single-char terms
        terms = [t for t in query.lower().split()
                 if len(t) > 1 and t not in self.STOPWORDS]
        if not terms:
            return []

        # Build WHERE clause that matches any term in summary or keywords
        conditions = []
        params = [server_id]
        for term in terms:
            conditions.append("(LOWER(summary) LIKE ? OR LOWER(keywords) LIKE ?)")
            params.extend([f'%{term}%', f'%{term}%'])

        where_clause = " OR ".join(conditions)

        with self._get_connection() as conn:
            cursor = conn.execute(
                f"""
                SELECT id, server_id, channel_id, url, summary, keywords,
                       posted_by_id, posted_by_name, posted_at, created_at
                FROM url_history
                WHERE server_id = ? AND ({where_clause})
                ORDER BY posted_at DESC
                LIMIT ?
                """,
                params + [limit]
            )
            rows = cursor.fetchall()

        return [self._row_to_entry(row) for row in rows]

    def get_recent(self, server_id: str, limit: int = 20) -> List[UrlEntry]:
        """Get the most recent URLs for a server."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, server_id, channel_id, url, summary, keywords,
                       posted_by_id, posted_by_name, posted_at, created_at
                FROM url_history
                WHERE server_id = ?
                ORDER BY posted_at DESC
                LIMIT ?
                """,
                (server_id, limit)
            )
            rows = cursor.fetchall()

        return [self._row_to_entry(row) for row in rows]

    def _row_to_entry(self, row: tuple) -> UrlEntry:
        """Convert a database row tuple to a UrlEntry."""
        (id_, server_id, channel_id, url, summary, keywords,
         posted_by_id, posted_by_name, posted_at, created_at) = row

        if isinstance(posted_at, str):
            posted_at = datetime.fromisoformat(posted_at)
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return UrlEntry(
            id=id_,
            server_id=server_id,
            channel_id=channel_id,
            url=url,
            summary=summary,
            keywords=keywords,
            posted_by_id=posted_by_id,
            posted_by_name=posted_by_name,
            posted_at=posted_at,
            created_at=created_at
        )
