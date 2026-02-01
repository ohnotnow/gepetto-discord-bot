"""
SQLite-based persistence for URL history and summaries.
"""

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from src.utils.constants import SEMANTIC_SEARCH_MIN_SIMILARITY

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
    embedding: Optional[List[float]] = None


def rerank(results: List[UrlEntry], query: str) -> List[UrlEntry]:
    """
    Re-rank search results for improved relevance.

    Currently a no-op that returns results unchanged.

    Future improvements could include:
    - LLM-based re-ranking (send query + summaries to LLM, ask it to rank)
    - BM25 scoring on summary text
    - Hybrid scoring (combine cosine similarity with keyword overlap)
    - Minimum similarity threshold filtering

    Args:
        results: URL entries from similarity or keyword search
        query: The original search query

    Returns:
        Re-ranked list of URL entries (currently unchanged)
    """
    return results


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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    embedding TEXT
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

            # Migration: add embedding column if it doesn't exist
            cursor = conn.execute("PRAGMA table_info(url_history)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'embedding' not in columns:
                conn.execute("ALTER TABLE url_history ADD COLUMN embedding TEXT")
                logger.info("Added embedding column to url_history table")

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
        posted_at: datetime,
        embedding: Optional[List[float]] = None
    ) -> Optional[int]:
        """
        Save a URL entry. Returns None if URL already exists.

        Returns the ID of the inserted record, or None if duplicate.
        """
        embedding_json = json.dumps(embedding) if embedding is not None else None

        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO url_history
                    (server_id, channel_id, url, summary, keywords,
                     posted_by_id, posted_by_name, posted_at, embedding)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (server_id, channel_id, url, summary, keywords,
                     posted_by_id, posted_by_name, posted_at, embedding_json)
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
                       posted_by_id, posted_by_name, posted_at, created_at, embedding
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
                       posted_by_id, posted_by_name, posted_at, created_at, embedding
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
        # Handle both old (10-field) and new (11-field) row formats
        if len(row) == 11:
            (id_, server_id, channel_id, url, summary, keywords,
             posted_by_id, posted_by_name, posted_at, created_at, embedding_json) = row
        else:
            (id_, server_id, channel_id, url, summary, keywords,
             posted_by_id, posted_by_name, posted_at, created_at) = row
            embedding_json = None

        if isinstance(posted_at, str):
            posted_at = datetime.fromisoformat(posted_at)
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        # Parse embedding JSON
        embedding = None
        if embedding_json:
            try:
                embedding = json.loads(embedding_json)
            except json.JSONDecodeError:
                pass

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
            created_at=created_at,
            embedding=embedding
        )

    def search_by_similarity(
        self,
        server_id: str,
        query_vector: List[float],
        limit: int = 5,
        min_similarity: Optional[float] = None
    ) -> List[UrlEntry]:
        """
        Search URLs by cosine similarity to query embedding.

        Args:
            server_id: The server to search in
            query_vector: The embedding vector of the search query
            limit: Maximum results to return
            min_similarity: Minimum similarity threshold (defaults to SEMANTIC_SEARCH_MIN_SIMILARITY)

        Returns:
            List of UrlEntry sorted by similarity (highest first), filtered by threshold
        """
        from src.embeddings import cosine_similarity

        threshold = min_similarity if min_similarity is not None else SEMANTIC_SEARCH_MIN_SIMILARITY

        # Get all entries with embeddings for this server
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, server_id, channel_id, url, summary, keywords,
                       posted_by_id, posted_by_name, posted_at, created_at, embedding
                FROM url_history
                WHERE server_id = ? AND embedding IS NOT NULL
                """,
                (server_id,)
            )
            rows = cursor.fetchall()

        # Calculate similarity for each entry, filtering by threshold
        entries_with_scores = []
        for row in rows:
            entry = self._row_to_entry(row)
            if entry.embedding:
                similarity = cosine_similarity(query_vector, entry.embedding)
                if similarity >= threshold:
                    entries_with_scores.append((similarity, entry))

        # Sort by similarity (highest first) and return top N
        entries_with_scores.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in entries_with_scores[:limit]]
