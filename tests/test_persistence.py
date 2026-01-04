"""
Tests for src/persistence module.
"""

import pytest
import os
import json
from src.persistence.json_store import JSONStore


class TestJSONStore:
    """Tests for JSONStore class."""

    def test_load_nonexistent_file_returns_default(self, temp_dir):
        """Loading a file that doesn't exist should return the default."""
        store = JSONStore(os.path.join(temp_dir, "nonexistent.json"), default=[])
        result = store.load()
        assert result == []

    def test_load_existing_file(self, mock_json_file):
        """Loading an existing file should return its contents."""
        filepath, expected_data = mock_json_file
        store = JSONStore(filepath)
        result = store.load()
        assert result == expected_data

    def test_save_creates_file(self, temp_dir):
        """Saving should create a new file."""
        filepath = os.path.join(temp_dir, "new_file.json")
        store = JSONStore(filepath)
        test_data = {"test": "data"}

        result = store.save(test_data)

        assert result is True
        assert os.path.exists(filepath)
        with open(filepath) as f:
            saved_data = json.load(f)
        assert saved_data == test_data

    def test_save_overwrites_existing(self, mock_json_file):
        """Saving should overwrite existing file."""
        filepath, _ = mock_json_file
        store = JSONStore(filepath)
        new_data = {"new": "data"}

        store.save(new_data)

        with open(filepath) as f:
            saved_data = json.load(f)
        assert saved_data == new_data

    def test_load_invalid_json_returns_default(self, temp_dir):
        """Loading invalid JSON should return the default."""
        filepath = os.path.join(temp_dir, "invalid.json")
        with open(filepath, 'w') as f:
            f.write("not valid json {{{")

        store = JSONStore(filepath, default={"fallback": True})
        result = store.load()
        assert result == {"fallback": True}

    def test_default_value_is_empty_list(self, temp_dir):
        """Default default value should be an empty list."""
        store = JSONStore(os.path.join(temp_dir, "test.json"))
        result = store.load()
        assert result == []

    def test_save_creates_parent_directory(self, temp_dir):
        """Saving should create parent directories if needed."""
        filepath = os.path.join(temp_dir, "nested", "dir", "file.json")
        store = JSONStore(filepath)

        result = store.save({"nested": True})

        assert result is True
        assert os.path.exists(filepath)
