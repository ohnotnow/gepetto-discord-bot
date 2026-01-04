"""
Pytest configuration and shared fixtures.
"""

import pytest
import os
import tempfile
import json


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_json_file(temp_dir):
    """Create a temporary JSON file with test data."""
    filepath = os.path.join(temp_dir, "test_data.json")
    test_data = {"key": "value", "items": [1, 2, 3]}
    with open(filepath, 'w') as f:
        json.dump(test_data, f)
    return filepath, test_data
