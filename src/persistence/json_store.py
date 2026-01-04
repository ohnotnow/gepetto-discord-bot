"""
Simple JSON file persistence utility.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class JSONStore:
    """A simple JSON file store with load/save operations."""

    def __init__(self, filepath: str, default: Any = None):
        """
        Initialize the store with a file path.

        Args:
            filepath: Path to the JSON file
            default: Default value if file doesn't exist or is invalid
        """
        self.filepath = filepath
        self.default = default if default is not None else []

    def load(self) -> Any:
        """Load data from the JSON file, returning default if unavailable."""
        if not os.path.exists(self.filepath):
            return self.default

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading {self.filepath}: {e}")
            return self.default

    def save(self, data: Any) -> bool:
        """Save data to the JSON file. Returns True on success."""
        try:
            # Ensure parent directory exists
            parent = os.path.dirname(self.filepath)
            if parent and not os.path.exists(parent):
                os.makedirs(parent)

            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            logger.error(f"Error saving {self.filepath}: {e}")
            return False
