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
MAX_RECENT_SLOTS_PER_KIND = 30

# Sentinel server_id for "global" occasions that apply to every server (e.g.
# Christmas, Liz Truss's birthday). A real Discord server_id is a 19-digit
# number, so this literal can never collide with one.
#
# Why a sentinel string rather than a NULL server_id: NULL never matches `=`
# or `IN`, so it'd force IS NULL special-casing throughout. The sentinel keeps
# the column NOT NULL like every other table and the lookup query simple.
#
# Why "__global__" rather than "*": the value is only ever a bound parameter
# compared with `=`/`IN` (never string-interpolated, never LIKE), so "*" would
# have been functionally safe — but "*" is a wildcard in SELECT and in SQLite's
# GLOB operator, so it reads as dangerous and would become a real foot-gun if a
# query ever switched to GLOB. A self-documenting literal avoids all of that.
GLOBAL_SERVER_ID = "__global__"


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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS image_recent_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id TEXT NOT NULL,
                    slot_kind TEXT NOT NULL,
                    value TEXT NOT NULL,
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_recent_slots
                ON image_recent_slots(server_id, slot_kind, id DESC)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS image_occasions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id TEXT NOT NULL,
                    match_key TEXT NOT NULL,
                    directive TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_occasions
                ON image_occasions(server_id, match_key)
            """)
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    @classmethod
    def backup_sections(cls) -> dict:
        """Return available backup sections with descriptions."""
        return {"images": "Daily chat image history (themes, prompts, reasoning)"}

    def export_server(self, server_id: str) -> dict:
        """Export all image history for a server."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT server_id, themes, reasoning, prompt, image_url, created_at "
                "FROM image_history WHERE server_id = ? ORDER BY id",
                (server_id,)
            )
            rows = cursor.fetchall()

        records = []
        for row in rows:
            _, themes_json, reasoning, prompt, image_url, created_at = row
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            records.append({
                "themes": json.loads(themes_json),
                "reasoning": reasoning,
                "prompt": prompt,
                "image_url": image_url,
                "created_at": created_at.isoformat(),
            })

        return {"images": records}

    def import_server(self, server_id: str, data: dict) -> dict:
        """Import image history for a server. Skips exact (themes, prompt) duplicates."""
        records = data.get("images", [])
        imported = 0
        skipped = 0

        # Get existing entries for duplicate detection
        existing = set()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT themes, prompt FROM image_history WHERE server_id = ?",
                (server_id,)
            )
            for row in cursor.fetchall():
                existing.add((row[0], row[1]))

        for record in records:
            themes_json = json.dumps(record["themes"])
            if (themes_json, record["prompt"]) in existing:
                skipped += 1
                continue

            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO image_history (server_id, themes, reasoning, prompt, image_url, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (server_id, themes_json, record["reasoning"],
                     record["prompt"], record.get("image_url"), record["created_at"])
                )
                conn.commit()
            imported += 1

        return {"images": {"imported": imported, "skipped": skipped}}

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

    def save_recent_slot(self, server_id: str, slot_kind: str, value: str) -> None:
        """Record a value used for a given slot kind. Auto-prunes per (server, kind)."""
        value = (value or "").strip()
        if not value:
            return
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO image_recent_slots (server_id, slot_kind, value) VALUES (?, ?, ?)",
                (server_id, slot_kind, value)
            )
            conn.execute(
                """
                DELETE FROM image_recent_slots
                WHERE server_id = ? AND slot_kind = ?
                AND id NOT IN (
                    SELECT id FROM image_recent_slots
                    WHERE server_id = ? AND slot_kind = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                """,
                (server_id, slot_kind, server_id, slot_kind, MAX_RECENT_SLOTS_PER_KIND)
            )
            conn.commit()

    def get_recent_slots(self, server_id: str, slot_kind: str, limit: int = 20) -> List[str]:
        """Return recent values for a slot kind, newest first."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT value FROM image_recent_slots
                WHERE server_id = ? AND slot_kind = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (server_id, slot_kind, limit)
            )
            return [row[0] for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # "On this day" occasions — date-keyed prompt directives injected into
    # the corpse assembler (see ant gepettodiscordbot-VXQvH). A match_key of
    # "YYYY-MM-DD" fires once on that exact date; "MM-DD" fires every year.
    # An occasion stored under server_id == GLOBAL_SERVER_ID applies to every
    # server; a server's own occasion takes precedence over a global one for
    # the same day.
    # ------------------------------------------------------------------

    def add_occasion(self, server_id: str, match_key: str, directive: str) -> int:
        """Add (or replace) an occasion directive for a (server_id, match_key).

        Re-adding the same (server, key) replaces the directive in place, so the
        helper script can be re-run to edit an entry rather than duplicate it.

        Raises ValueError if match_key or directive is blank.
        Returns the new row id.
        """
        match_key = (match_key or "").strip()
        directive = (directive or "").strip()
        if not match_key or not directive:
            raise ValueError("add_occasion requires a non-empty match_key and directive")

        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM image_occasions WHERE server_id = ? AND match_key = ?",
                (server_id, match_key),
            )
            cursor = conn.execute(
                "INSERT INTO image_occasions (server_id, match_key, directive) VALUES (?, ?, ?)",
                (server_id, match_key, directive),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_occasion(self, server_id: str, date=None) -> Optional[str]:
        """Return the occasion directive that applies on the given date, or None.

        `date` may be a datetime/date, an ISO "YYYY-MM-DD" string, or None for
        today. Considers both this server's occasions and GLOBAL_SERVER_ID
        occasions, picking the single best match by this precedence:

            this server, exact date  (YYYY-MM-DD)
            this server, annual      (MM-DD)
            global, exact date       (YYYY-MM-DD)
            global, annual           (MM-DD)

        i.e. a server's own occasion always beats a global one for the same
        day, and within either scope an exact date beats an annual key.
        """
        if date is None:
            date = datetime.now()
        if isinstance(date, str):
            date = datetime.fromisoformat(date)
        exact = date.strftime("%Y-%m-%d")
        annual = date.strftime("%m-%d")

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT directive FROM image_occasions
                WHERE server_id IN (?, ?) AND match_key IN (?, ?)
                ORDER BY
                    (server_id = ?) DESC,   -- this server's rows before global
                    length(match_key) DESC, -- exact date before annual
                    id DESC
                LIMIT 1
                """,
                (server_id, GLOBAL_SERVER_ID, exact, annual, server_id),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def list_occasions(self, server_id: str) -> List[dict]:
        """Return all occasions for a server as dicts, ordered by match_key."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, match_key, directive, created_at
                FROM image_occasions
                WHERE server_id = ?
                ORDER BY match_key
                """,
                (server_id,),
            )
            return [
                {"id": r[0], "match_key": r[1], "directive": r[2], "created_at": r[3]}
                for r in cursor.fetchall()
            ]

    def delete_occasion(self, server_id: str, match_key: str) -> int:
        """Delete the occasion for a (server_id, match_key). Returns rows deleted."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM image_occasions WHERE server_id = ? AND match_key = ?",
                (server_id, (match_key or "").strip()),
            )
            conn.commit()
            return cursor.rowcount

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
