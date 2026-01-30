"""
Tests for src/persistence/image_store.py
"""

import pytest
import os
from src.persistence.image_store import ImageStore, ImageEntry


class TestImageStore:
    """Tests for ImageStore class."""

    def test_init_creates_database(self, temp_dir):
        """ImageStore should create the database file on init."""
        db_path = os.path.join(temp_dir, 'test.db')
        store = ImageStore(db_path)
        assert os.path.exists(db_path)

    def test_init_creates_parent_directory(self, temp_dir):
        """ImageStore should create parent directories if needed."""
        db_path = os.path.join(temp_dir, 'nested', 'dir', 'test.db')
        store = ImageStore(db_path)
        assert os.path.exists(db_path)

    def test_save_returns_id(self, temp_dir):
        """save() should return the ID of the new entry."""
        store = ImageStore(os.path.join(temp_dir, 'test.db'))
        entry_id = store.save('server1', ['theme1'], 'reasoning', 'prompt')
        assert entry_id == 1
        entry_id2 = store.save('server1', ['theme2'], 'reasoning2', 'prompt2')
        assert entry_id2 == 2

    def test_get_latest_returns_most_recent(self, temp_dir):
        """get_latest() should return the most recent entry."""
        store = ImageStore(os.path.join(temp_dir, 'test.db'))
        store.save('server1', ['old'], 'old reasoning', 'old prompt')
        store.save('server1', ['new'], 'new reasoning', 'new prompt')

        latest = store.get_latest('server1')
        assert latest is not None
        assert latest.themes == ['new']
        assert latest.reasoning == 'new reasoning'

    def test_get_latest_returns_none_when_empty(self, temp_dir):
        """get_latest() should return None when no entries exist."""
        store = ImageStore(os.path.join(temp_dir, 'test.db'))
        assert store.get_latest('server1') is None

    def test_get_recent_returns_newest_first(self, temp_dir):
        """get_recent() should return entries in newest-first order."""
        store = ImageStore(os.path.join(temp_dir, 'test.db'))
        store.save('server1', ['first'], 'r1', 'p1')
        store.save('server1', ['second'], 'r2', 'p2')
        store.save('server1', ['third'], 'r3', 'p3')

        recent = store.get_recent('server1', limit=3)
        assert len(recent) == 3
        assert recent[0].themes == ['third']
        assert recent[2].themes == ['first']

    def test_get_recent_respects_limit(self, temp_dir):
        """get_recent() should respect the limit parameter."""
        store = ImageStore(os.path.join(temp_dir, 'test.db'))
        for i in range(5):
            store.save('server1', [f'theme{i}'], f'r{i}', f'p{i}')

        recent = store.get_recent('server1', limit=2)
        assert len(recent) == 2

    def test_server_isolation(self, temp_dir):
        """Different servers should have isolated data."""
        store = ImageStore(os.path.join(temp_dir, 'test.db'))
        store.save('server1', ['s1theme'], 's1r', 's1p')
        store.save('server2', ['s2theme'], 's2r', 's2p')

        s1_latest = store.get_latest('server1')
        s2_latest = store.get_latest('server2')

        assert s1_latest.themes == ['s1theme']
        assert s2_latest.themes == ['s2theme']

    def test_auto_prune_keeps_only_10(self, temp_dir):
        """save() should auto-prune to keep only 10 entries per server."""
        store = ImageStore(os.path.join(temp_dir, 'test.db'))
        for i in range(15):
            store.save('server1', [f'theme{i}'], f'r{i}', f'p{i}')

        all_entries = store.get_recent('server1', limit=100)
        assert len(all_entries) == 10
        # Should have themes 5-14 (most recent 10)
        themes = [e.themes[0] for e in all_entries]
        assert 'theme0' not in themes
        assert 'theme14' in themes

    def test_get_previous_themes_format(self, temp_dir):
        """get_previous_themes() should return newline-separated theme strings."""
        store = ImageStore(os.path.join(temp_dir, 'test.db'))
        store.save('server1', ['theme1', 'theme2'], 'r1', 'p1')
        store.save('server1', ['theme3'], 'r2', 'p2')

        themes_str = store.get_previous_themes('server1')
        # Should contain both theme entries, newest first
        assert 'theme3' in themes_str
        assert 'theme1' in themes_str

    def test_get_previous_themes_empty(self, temp_dir):
        """get_previous_themes() should return empty string when no entries."""
        store = ImageStore(os.path.join(temp_dir, 'test.db'))
        assert store.get_previous_themes('server1') == ''

    def test_image_url_optional(self, temp_dir):
        """image_url should be optional in save()."""
        store = ImageStore(os.path.join(temp_dir, 'test.db'))
        store.save('server1', ['t'], 'r', 'p')  # No image_url
        store.save('server1', ['t2'], 'r2', 'p2', image_url='http://example.com/img.png')

        entries = store.get_recent('server1')
        assert entries[0].image_url == 'http://example.com/img.png'
        assert entries[1].image_url is None
