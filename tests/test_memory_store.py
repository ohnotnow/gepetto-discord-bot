"""
Tests for src/persistence/memory_store.py
"""

import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from src.persistence.memory_store import MemoryStore, Memory, UserBio


class TestMemoryStore:
    """Tests for MemoryStore class."""

    # Initialization tests

    def test_init_creates_tables(self, temp_dir):
        """MemoryStore should create both tables on init."""
        db_path = os.path.join(temp_dir, 'test.db')
        store = MemoryStore(db_path)
        assert os.path.exists(db_path)

        # Verify tables exist by inserting data
        store.save_memory('s1', 'u1', 'user1', 'test memory')
        store.save_bio('s1', 'u1', 'user1', 'test bio')
        # If we get here without error, tables exist

    def test_uses_existing_database(self, temp_dir):
        """MemoryStore should reuse existing database file."""
        db_path = os.path.join(temp_dir, 'test.db')
        store1 = MemoryStore(db_path)
        store1.save_memory('s1', 'u1', 'user1', 'memory from store1')

        store2 = MemoryStore(db_path)
        memories = store2.get_user_memories('s1', 'u1')
        assert len(memories) == 1
        assert memories[0].memory == 'memory from store1'

    # Memory operations tests

    def test_save_memory_returns_id(self, temp_dir):
        """save_memory() should return the ID of the new entry."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        id1 = store.save_memory('s1', 'u1', 'user1', 'memory1')
        id2 = store.save_memory('s1', 'u1', 'user1', 'memory2')
        assert id1 == 1
        assert id2 == 2

    def test_get_user_memories_returns_list(self, temp_dir):
        """get_user_memories() should return a list of Memory objects."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        store.save_memory('s1', 'u1', 'user1', 'memory1')
        store.save_memory('s1', 'u1', 'user1', 'memory2')

        memories = store.get_user_memories('s1', 'u1')
        assert len(memories) == 2
        assert all(isinstance(m, Memory) for m in memories)

    def test_get_user_memories_excludes_expired_by_default(self, temp_dir):
        """get_user_memories() should exclude expired memories by default."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        past = datetime.now() - timedelta(days=1)
        future = datetime.now() + timedelta(days=1)

        store.save_memory('s1', 'u1', 'user1', 'expired', expires_at=past)
        store.save_memory('s1', 'u1', 'user1', 'active', expires_at=future)
        store.save_memory('s1', 'u1', 'user1', 'no_expiry')

        memories = store.get_user_memories('s1', 'u1')
        memory_texts = [m.memory for m in memories]
        assert 'expired' not in memory_texts
        assert 'active' in memory_texts
        assert 'no_expiry' in memory_texts

    def test_get_user_memories_can_include_expired(self, temp_dir):
        """get_user_memories(include_expired=True) should include expired."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        past = datetime.now() - timedelta(days=1)

        store.save_memory('s1', 'u1', 'user1', 'expired', expires_at=past)
        store.save_memory('s1', 'u1', 'user1', 'active')

        memories = store.get_user_memories('s1', 'u1', include_expired=True)
        memory_texts = [m.memory for m in memories]
        assert 'expired' in memory_texts
        assert 'active' in memory_texts

    def test_mark_referenced_updates_timestamp_and_count(self, temp_dir):
        """mark_referenced() should update timestamp and increment count."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        mem_id = store.save_memory('s1', 'u1', 'user1', 'test')

        memories_before = store.get_user_memories('s1', 'u1')
        assert memories_before[0].last_referenced_at is None
        assert memories_before[0].reference_count == 0

        store.mark_referenced(mem_id)

        memories_after = store.get_user_memories('s1', 'u1')
        assert memories_after[0].last_referenced_at is not None
        assert memories_after[0].reference_count == 1

        store.mark_referenced(mem_id)
        memories_twice = store.get_user_memories('s1', 'u1')
        assert memories_twice[0].reference_count == 2

    def test_cleanup_expired_removes_old_memories(self, temp_dir):
        """cleanup_expired() should remove expired memories."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        past = datetime.now() - timedelta(days=1)
        future = datetime.now() + timedelta(days=1)

        store.save_memory('s1', 'u1', 'user1', 'expired', expires_at=past)
        store.save_memory('s1', 'u1', 'user1', 'active', expires_at=future)

        store.cleanup_expired()

        memories = store.get_user_memories('s1', 'u1', include_expired=True)
        memory_texts = [m.memory for m in memories]
        assert 'expired' not in memory_texts
        assert 'active' in memory_texts

    def test_cleanup_expired_returns_count(self, temp_dir):
        """cleanup_expired() should return count of deleted memories."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        past = datetime.now() - timedelta(days=1)

        store.save_memory('s1', 'u1', 'user1', 'expired1', expires_at=past)
        store.save_memory('s1', 'u1', 'user1', 'expired2', expires_at=past)
        store.save_memory('s1', 'u1', 'user1', 'active')

        count = store.cleanup_expired()
        assert count == 2

    # Bio operations tests

    def test_save_bio_creates_new(self, temp_dir):
        """save_bio() should create a new bio."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        store.save_bio('s1', 'u1', 'user1', 'German heritage, lives in Madrid')

        bio = store.get_user_bio('s1', 'u1')
        assert bio is not None
        assert bio.bio == 'German heritage, lives in Madrid'
        assert bio.user_name == 'user1'

    def test_save_bio_updates_existing(self, temp_dir):
        """save_bio() should update existing bio (upsert)."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        store.save_bio('s1', 'u1', 'user1', 'original bio')
        store.save_bio('s1', 'u1', 'user1', 'updated bio')

        bio = store.get_user_bio('s1', 'u1')
        assert bio.bio == 'updated bio'

    def test_get_user_bio_returns_none_when_missing(self, temp_dir):
        """get_user_bio() should return None when no bio exists."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        bio = store.get_user_bio('s1', 'u1')
        assert bio is None

    # Privacy tests

    def test_delete_user_data_removes_memories(self, temp_dir):
        """delete_user_data() should remove all user memories."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        store.save_memory('s1', 'u1', 'user1', 'mem1')
        store.save_memory('s1', 'u1', 'user1', 'mem2')

        store.delete_user_data('s1', 'u1')

        memories = store.get_user_memories('s1', 'u1', include_expired=True)
        assert len(memories) == 0

    def test_delete_user_data_removes_bio(self, temp_dir):
        """delete_user_data() should remove user bio."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        store.save_bio('s1', 'u1', 'user1', 'test bio')

        store.delete_user_data('s1', 'u1')

        bio = store.get_user_bio('s1', 'u1')
        assert bio is None

    def test_delete_user_data_returns_counts(self, temp_dir):
        """delete_user_data() should return deletion counts."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        store.save_memory('s1', 'u1', 'user1', 'mem1')
        store.save_memory('s1', 'u1', 'user1', 'mem2')
        store.save_bio('s1', 'u1', 'user1', 'bio')

        result = store.delete_user_data('s1', 'u1')
        assert result['memories'] == 2
        assert result['bio_deleted'] is True

    # Server isolation tests

    def test_memories_isolated_by_server(self, temp_dir):
        """Memories should be isolated by server_id."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        store.save_memory('server1', 'u1', 'user1', 'server1 memory')
        store.save_memory('server2', 'u1', 'user1', 'server2 memory')

        s1_memories = store.get_user_memories('server1', 'u1')
        s2_memories = store.get_user_memories('server2', 'u1')

        assert len(s1_memories) == 1
        assert len(s2_memories) == 1
        assert s1_memories[0].memory == 'server1 memory'
        assert s2_memories[0].memory == 'server2 memory'

    def test_bios_isolated_by_server(self, temp_dir):
        """Bios should be isolated by server_id."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        store.save_bio('server1', 'u1', 'user1', 'server1 bio')
        store.save_bio('server2', 'u1', 'user1', 'server2 bio')

        s1_bio = store.get_user_bio('server1', 'u1')
        s2_bio = store.get_user_bio('server2', 'u1')

        assert s1_bio.bio == 'server1 bio'
        assert s2_bio.bio == 'server2 bio'

    def test_delete_only_affects_specified_server(self, temp_dir):
        """delete_user_data() should only affect the specified server."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        store.save_memory('server1', 'u1', 'user1', 's1 memory')
        store.save_memory('server2', 'u1', 'user1', 's2 memory')
        store.save_bio('server1', 'u1', 'user1', 's1 bio')
        store.save_bio('server2', 'u1', 'user1', 's2 bio')

        store.delete_user_data('server1', 'u1')

        assert len(store.get_user_memories('server1', 'u1')) == 0
        assert len(store.get_user_memories('server2', 'u1')) == 1
        assert store.get_user_bio('server1', 'u1') is None
        assert store.get_user_bio('server2', 'u1') is not None

    # Context building tests

    def test_get_context_respects_cooldown(self, temp_dir):
        """get_context_for_user() should exclude recently referenced memories."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        mem_id = store.save_memory('s1', 'u1', 'user1', 'recent memory')
        store.mark_referenced(mem_id)

        # With probability=1 to ensure inclusion if not cooled down
        with patch('random.random', return_value=0):
            context = store.get_context_for_user('s1', 'u1', cooldown_hours=24, probability=1.0)

        assert 'recent memory' not in context

    def test_get_context_respects_probability(self, temp_dir):
        """get_context_for_user() should apply probability filtering."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        store.save_memory('s1', 'u1', 'user1', 'test memory')

        # With random returning 0.5 and probability 0.3, should exclude
        with patch('random.random', return_value=0.5):
            context = store.get_context_for_user('s1', 'u1', probability=0.3)

        assert context == ''

        # With random returning 0.1 and probability 0.3, should include
        with patch('random.random', return_value=0.1):
            context = store.get_context_for_user('s1', 'u1', probability=0.3)

        assert 'test memory' in context

    def test_get_context_respects_max_memories(self, temp_dir):
        """get_context_for_user() should cap at max_memories."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        for i in range(10):
            store.save_memory('s1', 'u1', 'user1', f'memory{i}')

        # With probability=1 to ensure all eligible
        with patch('random.random', return_value=0):
            context = store.get_context_for_user('s1', 'u1', probability=1.0, max_memories=3)

        # Should have at most 3 memories
        # Count by checking how many "memory" substrings appear
        assert context.count('memory') <= 3

    def test_get_context_marks_included_as_referenced(self, temp_dir):
        """get_context_for_user() should mark included memories as referenced."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        mem_id = store.save_memory('s1', 'u1', 'user1', 'test memory')

        with patch('random.random', return_value=0):
            store.get_context_for_user('s1', 'u1', probability=1.0)

        memories = store.get_user_memories('s1', 'u1')
        assert memories[0].reference_count == 1
        assert memories[0].last_referenced_at is not None

    def test_get_context_includes_bio(self, temp_dir):
        """get_context_for_user() should include bio if available."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        store.save_bio('s1', 'u1', 'user1', 'German heritage')

        context = store.get_context_for_user('s1', 'u1')
        assert 'German heritage' in context

    def test_get_context_returns_empty_when_no_data(self, temp_dir):
        """get_context_for_user() should return empty string when no data."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        context = store.get_context_for_user('s1', 'u1')
        assert context == ''

    def test_memory_category_stored(self, temp_dir):
        """save_memory() should store the category."""
        store = MemoryStore(os.path.join(temp_dir, 'test.db'))
        store.save_memory('s1', 'u1', 'user1', 'has a cold', category='health_temporary')

        memories = store.get_user_memories('s1', 'u1')
        assert memories[0].category == 'health_temporary'
