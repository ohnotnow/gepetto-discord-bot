"""
SQLite-based persistence for music link history.

Structured rows (artist, track, genres, styles) rather than prose summaries,
so per-user taste profiles are simple tallies. Non-music links are stored too
(is_music=0) because url_exists() is the dedupe gate for the daily scan —
without them every run would re-classify the same film trailers.

Deliberately no pruning (unlike url_store's 500-row cap): taste profiles
need long memory and the rows are tiny.
"""

import json
import logging
import os
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MusicEntry:
    """Represents a single music link record."""
    id: int
    server_id: str
    channel_id: str
    url: str
    video_title: str
    video_channel: str
    artist: Optional[str]
    collaborators: List[str]
    track: Optional[str]
    genres: List[str]
    styles: List[str]
    is_music: bool
    posted_by_id: str
    posted_by_name: str
    posted_at: datetime
    created_at: datetime


class MusicStore:
    """SQLite-based storage for music link history, keyed by server_id."""

    def __init__(self, db_path: str = './data/gepetto.db'):
        parent = os.path.dirname(db_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent)

        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create table and indexes if they do not exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS music_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    video_title TEXT NOT NULL,
                    video_channel TEXT NOT NULL,
                    artist TEXT,
                    collaborators TEXT NOT NULL DEFAULT '[]',
                    track TEXT,
                    genres TEXT NOT NULL DEFAULT '[]',
                    styles TEXT NOT NULL DEFAULT '[]',
                    is_music INTEGER NOT NULL DEFAULT 1,
                    posted_by_id TEXT NOT NULL,
                    posted_by_name TEXT NOT NULL,
                    posted_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_music_history_unique
                ON music_history(server_id, url)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_music_history_user
                ON music_history(server_id, posted_by_id)
            """)
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    @classmethod
    def backup_sections(cls) -> dict:
        """Return available backup sections with descriptions."""
        return {"music": "Music link history with artists, genres and styles"}

    def save(
        self,
        server_id: str,
        channel_id: str,
        url: str,
        video_title: str,
        video_channel: str,
        posted_by_id: str,
        posted_by_name: str,
        posted_at: datetime,
        artist: Optional[str] = None,
        collaborators: Optional[List[str]] = None,
        track: Optional[str] = None,
        genres: Optional[List[str]] = None,
        styles: Optional[List[str]] = None,
        is_music: bool = True,
    ) -> Optional[int]:
        """
        Save a music link entry. Returns None if URL already exists.

        Returns the ID of the inserted record, or None if duplicate.
        """
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO music_history
                    (server_id, channel_id, url, video_title, video_channel,
                     artist, collaborators, track, genres, styles, is_music,
                     posted_by_id, posted_by_name, posted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (server_id, channel_id, url, video_title, video_channel,
                     artist, json.dumps(collaborators or []), track,
                     json.dumps(genres or []), json.dumps(styles or []),
                     1 if is_music else 0,
                     posted_by_id, posted_by_name, posted_at)
                )
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # Duplicate URL
                return None

    def url_exists(self, server_id: str, url: str) -> bool:
        """Check if a URL already exists for this server."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT 1 FROM music_history
                WHERE server_id = ? AND url = ?
                LIMIT 1
                """,
                (server_id, url)
            )
            return cursor.fetchone() is not None

    _SELECT_FIELDS = """
        SELECT id, server_id, channel_id, url, video_title, video_channel,
               artist, collaborators, track, genres, styles, is_music,
               posted_by_id, posted_by_name, posted_at, created_at
        FROM music_history
    """

    def get_user_history(self, server_id: str, user_id: str, limit: int = 100) -> List[MusicEntry]:
        """Get a user's music links (music rows only), newest first."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                self._SELECT_FIELDS + """
                WHERE server_id = ? AND posted_by_id = ? AND is_music = 1
                ORDER BY posted_at DESC
                LIMIT ?
                """,
                (server_id, user_id, limit)
            )
            rows = cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_recent(self, server_id: str, limit: int = 50) -> List[MusicEntry]:
        """Get the most recent music links (music rows only) for a server."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                self._SELECT_FIELDS + """
                WHERE server_id = ? AND is_music = 1
                ORDER BY posted_at DESC
                LIMIT ?
                """,
                (server_id, limit)
            )
            rows = cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]

    def profile_counts(self, server_id: str, user_id: str) -> Dict[str, Counter]:
        """
        Tally one user's artists, genres and styles across their music rows.

        Drops the literal Discogs genre "Non-Music" (DVDs and compilations
        get tagged with it and it pollutes profiles).
        """
        artists: Counter = Counter()
        genres: Counter = Counter()
        styles: Counter = Counter()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT artist, genres, styles FROM music_history
                WHERE server_id = ? AND posted_by_id = ? AND is_music = 1
                """,
                (server_id, user_id)
            )
            rows = cursor.fetchall()

        for artist, genres_json, styles_json in rows:
            if artist:
                artists[artist] += 1
            for genre in self._parse_json_list(genres_json):
                if genre != "Non-Music":
                    genres[genre] += 1
            for style in self._parse_json_list(styles_json):
                styles[style] += 1

        return {"artists": artists, "genres": genres, "styles": styles}

    def resolve_user_name(self, server_id: str, name: str) -> Optional[str]:
        """
        Resolve a display name to a user ID, case-insensitively.

        Returns the posted_by_id of the most recent matching row, or None.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT posted_by_id FROM music_history
                WHERE server_id = ? AND LOWER(posted_by_name) = LOWER(?)
                ORDER BY posted_at DESC
                LIMIT 1
                """,
                (server_id, name)
            )
            row = cursor.fetchone()
        return row[0] if row else None

    def export_server(self, server_id: str) -> dict:
        """Export all music history for a server."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                self._SELECT_FIELDS + " WHERE server_id = ?",
                (server_id,)
            )
            rows = cursor.fetchall()

        records = []
        for row in rows:
            entry = self._row_to_entry(row)
            records.append({
                "channel_id": entry.channel_id,
                "url": entry.url,
                "video_title": entry.video_title,
                "video_channel": entry.video_channel,
                "artist": entry.artist,
                "collaborators": entry.collaborators,
                "track": entry.track,
                "genres": entry.genres,
                "styles": entry.styles,
                "is_music": entry.is_music,
                "posted_by_id": entry.posted_by_id,
                "posted_by_name": entry.posted_by_name,
                "posted_at": entry.posted_at.isoformat(),
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            })

        return {"music": records}

    def import_server(self, server_id: str, data: dict) -> dict:
        """Import music history for a server. Skips duplicate URLs via unique constraint."""
        records = data.get("music", [])
        imported = 0
        skipped = 0

        for record in records:
            result = self.save(
                server_id=server_id,
                channel_id=record["channel_id"],
                url=record["url"],
                video_title=record["video_title"],
                video_channel=record["video_channel"],
                posted_by_id=record["posted_by_id"],
                posted_by_name=record["posted_by_name"],
                posted_at=datetime.fromisoformat(record["posted_at"]),
                artist=record.get("artist"),
                collaborators=record.get("collaborators"),
                track=record.get("track"),
                genres=record.get("genres"),
                styles=record.get("styles"),
                is_music=record.get("is_music", True),
            )
            if result is None:
                skipped += 1
            else:
                imported += 1

        return {"music": {"imported": imported, "skipped": skipped}}

    @staticmethod
    def _parse_json_list(value) -> List[str]:
        """Parse a JSON array column, tolerating NULLs and bad data."""
        if not value:
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []

    def _row_to_entry(self, row: tuple) -> MusicEntry:
        """Convert a database row tuple to a MusicEntry."""
        (id_, server_id, channel_id, url, video_title, video_channel,
         artist, collaborators_json, track, genres_json, styles_json, is_music,
         posted_by_id, posted_by_name, posted_at, created_at) = row

        if isinstance(posted_at, str):
            posted_at = datetime.fromisoformat(posted_at)
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return MusicEntry(
            id=id_,
            server_id=server_id,
            channel_id=channel_id,
            url=url,
            video_title=video_title,
            video_channel=video_channel,
            artist=artist,
            collaborators=self._parse_json_list(collaborators_json),
            track=track,
            genres=self._parse_json_list(genres_json),
            styles=self._parse_json_list(styles_json),
            is_music=bool(is_music),
            posted_by_id=posted_by_id,
            posted_by_name=posted_by_name,
            posted_at=posted_at,
            created_at=created_at,
        )
