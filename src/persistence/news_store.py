"""SQLite-backed cache for news bulletins.

The news pipeline in src/content/news.py is slow (4 RSS fetches + 1 LLM
synthesis call) and the bulletins are global — server-agnostic, identical
for every consumer. So we cache the latest fetch and serve it for a few
hours before refreshing.

Single-row table, INSERT OR REPLACE on every save. No history; we don't
care about old news. See ait gepetto-discord-bot-YHETx.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class NewsStore:
    """SQLite-based cache for the most recent news bulletin fetch."""

    def __init__(self, db_path: str = "./data/gepetto.db"):
        parent = os.path.dirname(db_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent)
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS news_cache (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    fetched_at TIMESTAMP NOT NULL,
                    bulletins_json TEXT NOT NULL
                )
            """)
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def save_bulletins(self, bulletins) -> None:
        """Replace the cached row with the given bulletins. Stamps fetched_at
        to now. `bulletins` is a list of src.content.news.Bulletin objects."""
        payload = json.dumps([_bulletin_to_dict(b) for b in bulletins])
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO news_cache (id, fetched_at, bulletins_json) "
                "VALUES (1, ?, ?)",
                (datetime.now().isoformat(), payload),
            )
            conn.commit()

    def get_cached_bulletins(self, max_age_hours: float):
        """Return cached bulletins if the row exists and is younger than
        `max_age_hours`. Returns None if no cache or cache is stale.

        The returned objects are src.content.news.Bulletin instances; their
        nested `sources` are reconstructed src.content.news.Item dataclasses.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT fetched_at, bulletins_json FROM news_cache WHERE id = 1"
            )
            row = cursor.fetchone()

        if not row:
            return None
        fetched_at_str, bulletins_json = row
        try:
            fetched_at = datetime.fromisoformat(fetched_at_str)
        except (TypeError, ValueError):
            logger.warning("[news_cache] unparsable fetched_at %r — treating as miss", fetched_at_str)
            return None

        age = datetime.now() - fetched_at
        if age > timedelta(hours=max_age_hours):
            logger.info(
                "[news_cache] miss: cached %.1fh ago (TTL %.1fh)",
                age.total_seconds() / 3600, max_age_hours,
            )
            return None

        try:
            data = json.loads(bulletins_json)
        except json.JSONDecodeError:
            logger.warning("[news_cache] cached bulletins_json was not valid JSON — treating as miss")
            return None

        bulletins = [_bulletin_from_dict(d) for d in data]
        logger.info(
            "[news_cache] hit: %d bulletin(s) cached %.1fh ago",
            len(bulletins), age.total_seconds() / 3600,
        )
        return bulletins


def _bulletin_to_dict(bulletin) -> dict:
    return {
        "heading": bulletin.heading,
        "body": bulletin.body,
        "sources": [
            {
                "feed": s.feed,
                "title": s.title,
                "summary": s.summary,
                "categories": list(s.categories),
            }
            for s in bulletin.sources
        ],
    }


def _bulletin_from_dict(d: dict):
    """Build a Bulletin (with reconstructed Item sources) from a cached dict.

    Imported lazily to avoid a circular: news_store is used by content.news,
    and importing news here at module load would create that loop. Lazy import
    keeps the persistence layer free of content-layer dependencies at startup.
    """
    from src.content.news import Bulletin, Item

    sources = [
        Item(
            feed=s.get("feed", ""),
            title=s.get("title", ""),
            summary=s.get("summary", ""),
            categories=list(s.get("categories", [])),
        )
        for s in d.get("sources", [])
    ]
    return Bulletin(
        heading=d.get("heading", ""),
        body=d.get("body", ""),
        sources=sources,
    )
