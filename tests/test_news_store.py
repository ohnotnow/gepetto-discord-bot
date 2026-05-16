"""Tests for src/persistence/news_store.py — the news bulletin cache."""

import os
import sqlite3
from datetime import datetime, timedelta

import pytest

from src.content.news import Bulletin, Item
from src.persistence.news_store import NewsStore


def _bulletin(heading: str = "UK politics", body: str = "Stuff happened.", sources=None) -> Bulletin:
    return Bulletin(
        heading=heading,
        body=body,
        sources=sources or [
            Item(feed="uk", title="A headline", summary="A summary", categories=["politics"]),
        ],
    )


class TestNewsStore:
    def test_init_creates_database(self, temp_dir):
        db_path = os.path.join(temp_dir, "test.db")
        NewsStore(db_path)
        assert os.path.exists(db_path)

    def test_init_creates_parent_directory(self, temp_dir):
        db_path = os.path.join(temp_dir, "nested", "dir", "test.db")
        NewsStore(db_path)
        assert os.path.exists(db_path)

    def test_empty_cache_returns_none(self, temp_dir):
        store = NewsStore(os.path.join(temp_dir, "test.db"))
        assert store.get_cached_bulletins(max_age_hours=3) is None

    def test_round_trip(self, temp_dir):
        store = NewsStore(os.path.join(temp_dir, "test.db"))
        original = [
            _bulletin(heading="UK politics", body="Burnham moves."),
            _bulletin(
                heading="In tech",
                body="A Waymo goes for a swim.",
                sources=[
                    Item(feed="technology", title="Waymo creek",
                         summary="Robotaxi in flood", categories=["tech"]),
                ],
            ),
        ]
        store.save_bulletins(original)
        retrieved = store.get_cached_bulletins(max_age_hours=3)
        assert retrieved is not None
        assert len(retrieved) == 2
        assert retrieved[0].heading == "UK politics"
        assert retrieved[0].body == "Burnham moves."
        assert retrieved[1].sources[0].feed == "technology"
        assert retrieved[1].sources[0].title == "Waymo creek"
        assert retrieved[1].sources[0].categories == ["tech"]

    def test_save_replaces_existing(self, temp_dir):
        """Cache holds the latest fetch only — second save replaces the first."""
        store = NewsStore(os.path.join(temp_dir, "test.db"))
        store.save_bulletins([_bulletin(heading="Old", body="Old news.")])
        store.save_bulletins([_bulletin(heading="New", body="Newer news.")])
        retrieved = store.get_cached_bulletins(max_age_hours=3)
        assert len(retrieved) == 1
        assert retrieved[0].heading == "New"

    def test_stale_cache_returns_none(self, temp_dir):
        """A cache older than max_age_hours is treated as a miss."""
        store = NewsStore(os.path.join(temp_dir, "test.db"))
        store.save_bulletins([_bulletin()])
        # Manually backdate the cached row to simulate staleness.
        old_time = (datetime.now() - timedelta(hours=5)).isoformat()
        with sqlite3.connect(store.db_path) as conn:
            conn.execute("UPDATE news_cache SET fetched_at = ? WHERE id = 1", (old_time,))
            conn.commit()
        assert store.get_cached_bulletins(max_age_hours=3) is None

    def test_fresh_cache_returns_bulletins(self, temp_dir):
        """A cache just-saved is well within any reasonable TTL."""
        store = NewsStore(os.path.join(temp_dir, "test.db"))
        store.save_bulletins([_bulletin()])
        assert store.get_cached_bulletins(max_age_hours=3) is not None

    def test_corrupt_fetched_at_returns_none(self, temp_dir):
        """If somehow fetched_at becomes unparsable, treat as miss rather than crash."""
        store = NewsStore(os.path.join(temp_dir, "test.db"))
        store.save_bulletins([_bulletin()])
        with sqlite3.connect(store.db_path) as conn:
            conn.execute("UPDATE news_cache SET fetched_at = 'not a date' WHERE id = 1")
            conn.commit()
        assert store.get_cached_bulletins(max_age_hours=3) is None

    def test_corrupt_bulletins_json_returns_none(self, temp_dir):
        """If somehow bulletins_json becomes unparsable, treat as miss."""
        store = NewsStore(os.path.join(temp_dir, "test.db"))
        store.save_bulletins([_bulletin()])
        with sqlite3.connect(store.db_path) as conn:
            conn.execute("UPDATE news_cache SET bulletins_json = 'not json' WHERE id = 1")
            conn.commit()
        assert store.get_cached_bulletins(max_age_hours=3) is None

    def test_save_empty_list_is_valid(self, temp_dir):
        """Saving an empty list shouldn't crash. Reading it back returns []."""
        store = NewsStore(os.path.join(temp_dir, "test.db"))
        store.save_bulletins([])
        retrieved = store.get_cached_bulletins(max_age_hours=3)
        assert retrieved == []

    def test_check_constraint_keeps_table_single_row(self, temp_dir):
        """The CHECK (id = 1) constraint enforces single-row semantics — any
        attempt to insert a different id fails."""
        store = NewsStore(os.path.join(temp_dir, "test.db"))
        store.save_bulletins([_bulletin()])
        with sqlite3.connect(store.db_path) as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO news_cache (id, fetched_at, bulletins_json) VALUES (2, ?, '[]')",
                    (datetime.now().isoformat(),),
                )


