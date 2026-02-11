"""
SQLite-based persistence for user memories and bios.
"""

import logging
import os
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Memory:
    """A single memory about a user."""
    id: int
    server_id: str
    user_id: str
    user_name: str
    memory: str
    category: str
    created_at: datetime
    expires_at: Optional[datetime]
    last_referenced_at: Optional[datetime]
    reference_count: int


@dataclass
class UserBio:
    """Long-term user profile."""
    server_id: str
    user_id: str
    user_name: str
    bio: str
    updated_at: datetime


class MemoryStore:
    """SQLite-based storage for user memories and bios, keyed by server_id + user_id."""

    def __init__(self, db_path: str = './data/gepetto.db'):
        """
        Initialize the store, creating DB and tables if needed.

        Args:
            db_path: Path to SQLite database. Defaults to ./data/gepetto.db
        """
        parent = os.path.dirname(db_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent)

        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    memory TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    last_referenced_at TIMESTAMP,
                    reference_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_memories_lookup
                ON user_memories(server_id, user_id)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_bios (
                    server_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    bio TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (server_id, user_id)
                )
            """)
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    def save_memory(
        self,
        server_id: str,
        user_id: str,
        user_name: str,
        memory: str,
        category: str = 'general',
        expires_at: Optional[datetime] = None
    ) -> int:
        """
        Save a memory about a user.

        Returns the ID of the inserted record.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO user_memories (server_id, user_id, user_name, memory, category, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (server_id, user_id, user_name, memory, category, expires_at)
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_user_memories(
        self,
        server_id: str,
        user_id: str,
        include_expired: bool = False
    ) -> List[Memory]:
        """Get all memories for a user, excluding expired by default."""
        with self._get_connection() as conn:
            if include_expired:
                cursor = conn.execute(
                    """
                    SELECT id, server_id, user_id, user_name, memory, category,
                           created_at, expires_at, last_referenced_at, reference_count
                    FROM user_memories
                    WHERE server_id = ? AND user_id = ?
                    ORDER BY created_at DESC
                    """,
                    (server_id, user_id)
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, server_id, user_id, user_name, memory, category,
                           created_at, expires_at, last_referenced_at, reference_count
                    FROM user_memories
                    WHERE server_id = ? AND user_id = ?
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                    ORDER BY created_at DESC
                    """,
                    (server_id, user_id)
                )
            rows = cursor.fetchall()

        return [self._row_to_memory(row) for row in rows]

    def mark_referenced(self, memory_id: int) -> None:
        """Update last_referenced_at to now and increment reference_count."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE user_memories
                SET last_referenced_at = CURRENT_TIMESTAMP,
                    reference_count = reference_count + 1
                WHERE id = ?
                """,
                (memory_id,)
            )
            conn.commit()

    def cleanup_expired(self) -> int:
        """Delete expired memories. Returns count deleted."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM user_memories
                WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP
                """
            )
            conn.commit()
            return cursor.rowcount

    def save_bio(
        self,
        server_id: str,
        user_id: str,
        user_name: str,
        bio: str
    ) -> None:
        """Upsert bio (INSERT OR REPLACE)."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO user_bios (server_id, user_id, user_name, bio, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (server_id, user_id, user_name, bio)
            )
            conn.commit()

    def get_user_bio(self, server_id: str, user_id: str) -> Optional[UserBio]:
        """Get bio for a user, or None if not found."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT server_id, user_id, user_name, bio, updated_at
                FROM user_bios
                WHERE server_id = ? AND user_id = ?
                """,
                (server_id, user_id)
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return self._row_to_bio(row)

    def delete_memory(self, server_id: str, user_id: str, memory_id: int) -> bool:
        """Delete a specific memory by ID, scoped to server and user. Returns True if deleted."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM user_memories
                WHERE id = ? AND server_id = ? AND user_id = ?
                """,
                (memory_id, server_id, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_user_data(self, server_id: str, user_id: str) -> dict:
        """Delete all memories and bio for user. Returns counts."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM user_memories
                WHERE server_id = ? AND user_id = ?
                """,
                (server_id, user_id)
            )
            memories_deleted = cursor.rowcount

            cursor = conn.execute(
                """
                DELETE FROM user_bios
                WHERE server_id = ? AND user_id = ?
                """,
                (server_id, user_id)
            )
            bio_deleted = cursor.rowcount > 0

            conn.commit()

        return {
            'memories': memories_deleted,
            'bio_deleted': bio_deleted
        }

    def get_context_for_user(
        self,
        server_id: str,
        user_id: str,
        cooldown_hours: int = 24,
        probability: float = 0.3,
        max_memories: int = 3
    ) -> str:
        """
        Get formatted context string for prompt injection.

        Applies cooldown, probability filtering, and caps.
        Updates last_referenced_at for included memories.
        Returns empty string if no relevant context.
        """
        memories = self.get_user_memories(server_id, user_id, include_expired=False)

        cooldown_threshold = datetime.now() - timedelta(hours=cooldown_hours)
        eligible = []

        for mem in memories:
            if mem.last_referenced_at and mem.last_referenced_at > cooldown_threshold:
                continue
            if random.random() > probability:
                continue
            eligible.append(mem)
            if len(eligible) >= max_memories:
                break

        for mem in eligible:
            self.mark_referenced(mem.id)

        bio = self.get_user_bio(server_id, user_id)

        parts = []
        if eligible:
            memory_texts = [m.memory for m in eligible]
            parts.append(", ".join(memory_texts))
        if bio:
            parts.append(bio.bio)

        return "; ".join(parts) if parts else ""

    def _row_to_memory(self, row: tuple) -> Memory:
        """Convert a database row tuple to a Memory."""
        (id_, server_id, user_id, user_name, memory, category,
         created_at, expires_at, last_referenced_at, reference_count) = row

        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if isinstance(last_referenced_at, str):
            last_referenced_at = datetime.fromisoformat(last_referenced_at)

        return Memory(
            id=id_,
            server_id=server_id,
            user_id=user_id,
            user_name=user_name,
            memory=memory,
            category=category,
            created_at=created_at,
            expires_at=expires_at,
            last_referenced_at=last_referenced_at,
            reference_count=reference_count
        )

    def _row_to_bio(self, row: tuple) -> UserBio:
        """Convert a database row tuple to a UserBio."""
        server_id, user_id, user_name, bio, updated_at = row

        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return UserBio(
            server_id=server_id,
            user_id=user_id,
            user_name=user_name,
            bio=bio,
            updated_at=updated_at
        )
