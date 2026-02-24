"""
Tests for backup and restore functionality across all stores.
"""

import gzip
import json
import os
from datetime import datetime, timedelta

from src.persistence.activity_store import ActivityStore
from src.persistence.image_store import ImageStore
from src.persistence.memory_store import MemoryStore
from src.persistence.reminder_store import ReminderStore
from src.persistence.url_store import UrlStore
from src.persistence import get_backup_stores


SERVER_A = "server_a"
SERVER_B = "server_b"


def _make_db(temp_dir, name="test.db"):
    return os.path.join(temp_dir, name)


def _seed_activity(store, server_id=SERVER_A):
    now = datetime.now()
    store.record_activity(server_id, "user1", "Alice", "ch1", now - timedelta(hours=2))
    store.record_activity(server_id, "user2", "Bob", "ch2", now - timedelta(hours=1))


def _seed_images(store, server_id=SERVER_A):
    store.save(server_id, ["cats", "dogs"], "They talked about pets", "A cat and dog playing", "https://img.example.com/1")
    store.save(server_id, ["space"], "Space discussion", "An astronaut floating", None)


def _seed_memories(store, server_id=SERVER_A):
    store.save_memory(server_id, "user1", "Alice", "Likes tea", "preferences")
    store.save_memory(server_id, "user1", "Alice", "Temporary note", "general",
                      expires_at=datetime.now() + timedelta(days=7))
    # Also add an already-expired memory (should NOT be exported)
    store.save_memory(server_id, "user1", "Alice", "Old note", "general",
                      expires_at=datetime.now() - timedelta(days=1))
    store.save_bio(server_id, "user1", "Alice", "Alice is a software engineer who loves tea.")


def _seed_reminders(store, server_id=SERVER_A):
    store.save(server_id, "user1", "Alice", "ch1", "Check the deploy",
               datetime.now() + timedelta(hours=2))
    store.save(server_id, "user1", "Alice", "ch1", "Call Dave",
               datetime.now() + timedelta(hours=5))
    # Add a completed reminder (should NOT be exported)
    rid = store.save(server_id, "user2", "Bob", "ch2", "Old reminder",
                     datetime.now() - timedelta(hours=1))
    store.mark_reminded(rid)


def _seed_urls(store, server_id=SERVER_A):
    store.save(server_id, "ch1", "https://example.com/1", "Summary 1", "key1",
               "user1", "Alice", datetime.now() - timedelta(hours=3), [0.1, 0.2, 0.3])
    store.save(server_id, "ch2", "https://example.com/2", "Summary 2", "key2",
               "user2", "Bob", datetime.now() - timedelta(hours=1))


class TestActivityStoreBackup:
    """Tests for ActivityStore backup methods."""

    def test_backup_sections(self):
        assert "activity" in ActivityStore.backup_sections()

    def test_export_import_roundtrip(self, temp_dir):
        db = _make_db(temp_dir)
        store = ActivityStore(db)
        _seed_activity(store)

        exported = store.export_server(SERVER_A)
        assert len(exported["activity"]) == 2

        # Import into fresh DB under different server
        db2 = _make_db(temp_dir, "test2.db")
        store2 = ActivityStore(db2)
        result = store2.import_server(SERVER_B, exported)
        assert result["activity"]["imported"] == 2

        # Verify data is under new server ID
        activity = store2.get_last_activity(SERVER_B, "user1")
        assert activity is not None
        assert activity.user_name == "Alice"

    def test_empty_server(self, temp_dir):
        store = ActivityStore(_make_db(temp_dir))
        exported = store.export_server("nonexistent")
        assert exported["activity"] == []


class TestImageStoreBackup:
    """Tests for ImageStore backup methods."""

    def test_backup_sections(self):
        assert "images" in ImageStore.backup_sections()

    def test_export_import_roundtrip(self, temp_dir):
        db = _make_db(temp_dir)
        store = ImageStore(db)
        _seed_images(store)

        exported = store.export_server(SERVER_A)
        assert len(exported["images"]) == 2
        # Themes should be exported as lists
        assert exported["images"][0]["themes"] == ["cats", "dogs"]

        # Import into fresh DB
        db2 = _make_db(temp_dir, "test2.db")
        store2 = ImageStore(db2)
        result = store2.import_server(SERVER_B, exported)
        assert result["images"]["imported"] == 2

        entries = store2.get_recent(SERVER_B)
        assert len(entries) == 2

    def test_duplicate_detection(self, temp_dir):
        db = _make_db(temp_dir)
        store = ImageStore(db)
        _seed_images(store)

        exported = store.export_server(SERVER_A)

        # Import same data twice into same server
        store.import_server(SERVER_A, exported)
        result = store.import_server(SERVER_A, exported)
        assert result["images"]["skipped"] == 2
        assert result["images"]["imported"] == 0


class TestMemoryStoreBackup:
    """Tests for MemoryStore backup methods."""

    def test_backup_sections(self):
        sections = MemoryStore.backup_sections()
        assert "memories" in sections
        assert "bios" in sections

    def test_export_excludes_expired(self, temp_dir):
        store = MemoryStore(_make_db(temp_dir))
        _seed_memories(store)

        exported = store.export_server(SERVER_A)
        # Should have 2 memories (non-expired), not 3
        assert len(exported["memories"]) == 2
        assert len(exported["bios"]) == 1

    def test_export_import_roundtrip(self, temp_dir):
        db = _make_db(temp_dir)
        store = MemoryStore(db)
        _seed_memories(store)

        exported = store.export_server(SERVER_A)

        db2 = _make_db(temp_dir, "test2.db")
        store2 = MemoryStore(db2)
        result = store2.import_server(SERVER_B, exported)
        assert result["memories"]["imported"] == 2
        assert result["bios"]["imported"] == 1

        bio = store2.get_user_bio(SERVER_B, "user1")
        assert bio is not None
        assert "software engineer" in bio.bio

    def test_duplicate_memories_skipped(self, temp_dir):
        db = _make_db(temp_dir)
        store = MemoryStore(db)
        _seed_memories(store)

        exported = store.export_server(SERVER_A)
        # Import into same server twice
        store.import_server(SERVER_A, exported)
        result = store.import_server(SERVER_A, exported)
        assert result["memories"]["skipped"] == 2
        assert result["memories"]["imported"] == 0

    def test_bio_upsert_on_reimport(self, temp_dir):
        db = _make_db(temp_dir)
        store = MemoryStore(db)
        _seed_memories(store)

        exported = store.export_server(SERVER_A)
        # Modify bio text in export data
        exported["bios"][0]["bio"] = "Updated bio text"
        store.import_server(SERVER_A, exported)

        bio = store.get_user_bio(SERVER_A, "user1")
        assert bio.bio == "Updated bio text"


class TestReminderStoreBackup:
    """Tests for ReminderStore backup methods."""

    def test_backup_sections(self):
        assert "reminders" in ReminderStore.backup_sections()

    def test_export_only_pending(self, temp_dir):
        store = ReminderStore(_make_db(temp_dir))
        _seed_reminders(store)

        exported = store.export_server(SERVER_A)
        # Should have 2 pending, not the completed one
        assert len(exported["reminders"]) == 2

    def test_export_import_roundtrip(self, temp_dir):
        db = _make_db(temp_dir)
        store = ReminderStore(db)
        _seed_reminders(store)

        exported = store.export_server(SERVER_A)

        db2 = _make_db(temp_dir, "test2.db")
        store2 = ReminderStore(db2)
        result = store2.import_server(SERVER_B, exported)
        assert result["reminders"]["imported"] == 2

        pending = store2.get_pending_for_user(SERVER_B, "user1")
        assert len(pending) == 2

    def test_duplicate_reminders_skipped(self, temp_dir):
        db = _make_db(temp_dir)
        store = ReminderStore(db)
        _seed_reminders(store)

        exported = store.export_server(SERVER_A)
        store.import_server(SERVER_A, exported)
        result = store.import_server(SERVER_A, exported)
        assert result["reminders"]["skipped"] == 2


class TestUrlStoreBackup:
    """Tests for UrlStore backup methods."""

    def test_backup_sections(self):
        assert "urls" in UrlStore.backup_sections()

    def test_export_import_roundtrip(self, temp_dir):
        db = _make_db(temp_dir)
        store = UrlStore(db)
        _seed_urls(store)

        exported = store.export_server(SERVER_A)
        assert len(exported["urls"]) == 2
        # Check embedding is preserved (order not guaranteed)
        by_url = {r["url"]: r for r in exported["urls"]}
        assert by_url["https://example.com/1"]["embedding"] == [0.1, 0.2, 0.3]
        assert by_url["https://example.com/2"]["embedding"] is None

        db2 = _make_db(temp_dir, "test2.db")
        store2 = UrlStore(db2)
        result = store2.import_server(SERVER_B, exported)
        assert result["urls"]["imported"] == 2

        entries = store2.get_all(SERVER_B)
        assert len(entries) == 2

    def test_duplicate_urls_skipped(self, temp_dir):
        db = _make_db(temp_dir)
        store = UrlStore(db)
        _seed_urls(store)

        exported = store.export_server(SERVER_A)
        store.import_server(SERVER_A, exported)
        result = store.import_server(SERVER_A, exported)
        assert result["urls"]["skipped"] == 2


class TestBackupRestoreIntegration:
    """Integration tests for the full backup/restore workflow."""

    def test_get_backup_stores(self, temp_dir):
        stores = get_backup_stores(os.path.join(temp_dir, "test.db"))
        assert len(stores) == 5

    def test_all_sections_unique(self, temp_dir):
        stores = get_backup_stores(os.path.join(temp_dir, "test.db"))
        all_sections = {}
        for store in stores:
            for name, desc in store.backup_sections().items():
                assert name not in all_sections, f"Duplicate section: {name}"
                all_sections[name] = desc

    def test_full_export_import_roundtrip(self, temp_dir):
        """Seed all stores, export, import to new DB, verify."""
        db = _make_db(temp_dir)
        activity = ActivityStore(db)
        images = ImageStore(db)
        memories = MemoryStore(db)
        reminders = ReminderStore(db)
        urls = UrlStore(db)

        _seed_activity(activity)
        _seed_images(images)
        _seed_memories(memories)
        _seed_reminders(reminders)
        _seed_urls(urls)

        # Export all
        stores = get_backup_stores(db)
        exported = {"server_id": SERVER_A, "sections": {}}
        for store in stores:
            result = store.export_server(SERVER_A)
            exported["sections"].update(result)

        # Import all to new DB with different server ID
        db2 = _make_db(temp_dir, "test2.db")
        stores2 = get_backup_stores(db2)
        for store in stores2:
            store_sections = set(store.backup_sections()) & set(exported["sections"])
            store_data = {s: exported["sections"][s] for s in store_sections}
            if store_data:
                store.import_server(SERVER_B, store_data)

        # Verify data exists under new server ID
        activity2 = ActivityStore(db2)
        assert activity2.get_last_activity(SERVER_B, "user1") is not None

        memories2 = MemoryStore(db2)
        assert memories2.get_user_bio(SERVER_B, "user1") is not None

        urls2 = UrlStore(db2)
        assert len(urls2.get_all(SERVER_B)) == 2

    def test_gzip_roundtrip(self, temp_dir):
        """Test that gzip export/import preserves data."""
        db = _make_db(temp_dir)
        store = ActivityStore(db)
        _seed_activity(store)

        exported = store.export_server(SERVER_A)
        data = {"server_id": SERVER_A, "exported_at": datetime.now().isoformat(), "sections": exported}

        # Write gzipped
        gz_path = os.path.join(temp_dir, "backup.json.gz")
        with gzip.open(gz_path, "wt", encoding="utf-8") as f:
            json.dump(data, f)

        # Read back
        with gzip.open(gz_path, "rt", encoding="utf-8") as f:
            loaded = json.load(f)

        assert loaded["sections"]["activity"] == exported["activity"]

        # Import from loaded data
        db2 = _make_db(temp_dir, "test2.db")
        store2 = ActivityStore(db2)
        result = store2.import_server(SERVER_B, loaded["sections"])
        assert result["activity"]["imported"] == 2

    def test_include_filter(self, temp_dir):
        """Test that include filter only exports requested sections."""
        db = _make_db(temp_dir)
        activity = ActivityStore(db)
        memories = MemoryStore(db)
        _seed_activity(activity)
        _seed_memories(memories)

        stores = get_backup_stores(db)
        sections_to_export = {"activity"}

        exported = {}
        for store in stores:
            store_sections = set(store.backup_sections()) & sections_to_export
            if store_sections:
                result = store.export_server(SERVER_A)
                for section in store_sections:
                    if section in result:
                        exported[section] = result[section]

        assert "activity" in exported
        assert "memories" not in exported
        assert "bios" not in exported

    def test_exclude_filter(self, temp_dir):
        """Test that exclude filter omits specified sections."""
        db = _make_db(temp_dir)
        activity = ActivityStore(db)
        memories = MemoryStore(db)
        _seed_activity(activity)
        _seed_memories(memories)

        stores = get_backup_stores(db)
        all_sections = set()
        for store in stores:
            all_sections.update(store.backup_sections())

        sections_to_export = all_sections - {"activity"}

        exported = {}
        for store in stores:
            store_sections = set(store.backup_sections()) & sections_to_export
            if store_sections:
                result = store.export_server(SERVER_A)
                for section in store_sections:
                    if section in result:
                        exported[section] = result[section]

        assert "activity" not in exported
        assert "memories" in exported
