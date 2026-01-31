"""
Tests for src/persistence/activity_store.py
"""

import os
from datetime import datetime, timedelta

from src.persistence.activity_store import ActivityStore, UserActivity


class TestActivityStore:
    """Tests for ActivityStore class."""

    def test_init_creates_database(self, temp_dir):
        """ActivityStore should create the database file on init."""
        db_path = os.path.join(temp_dir, 'test.db')
        ActivityStore(db_path)
        assert os.path.exists(db_path)

    def test_init_creates_parent_directory(self, temp_dir):
        """ActivityStore should create parent directories if needed."""
        db_path = os.path.join(temp_dir, 'nested', 'dir', 'test.db')
        ActivityStore(db_path)
        assert os.path.exists(db_path)

    def test_record_activity_creates_new_record(self, temp_dir):
        """record_activity() should create a new record for new user."""
        store = ActivityStore(os.path.join(temp_dir, 'test.db'))
        now = datetime.now()

        store.record_activity(
            server_id='server1',
            user_id='user1',
            user_name='TestUser',
            channel_id='channel1',
            timestamp=now
        )

        activity = store.get_last_activity('server1', 'user1')
        assert activity is not None
        assert activity.server_id == 'server1'
        assert activity.user_id == 'user1'
        assert activity.user_name == 'TestUser'
        assert activity.channel_id == 'channel1'

    def test_record_activity_updates_existing_record(self, temp_dir):
        """record_activity() should update existing record (upsert)."""
        store = ActivityStore(os.path.join(temp_dir, 'test.db'))
        earlier = datetime.now() - timedelta(hours=1)
        later = datetime.now()

        # First activity
        store.record_activity(
            server_id='server1',
            user_id='user1',
            user_name='OldName',
            channel_id='channel1',
            timestamp=earlier
        )

        # Second activity (should update)
        store.record_activity(
            server_id='server1',
            user_id='user1',
            user_name='NewName',
            channel_id='channel2',
            timestamp=later
        )

        activity = store.get_last_activity('server1', 'user1')
        assert activity is not None
        assert activity.user_name == 'NewName'
        assert activity.channel_id == 'channel2'

    def test_get_last_activity_returns_none_for_unknown_user(self, temp_dir):
        """get_last_activity() should return None when user not found."""
        store = ActivityStore(os.path.join(temp_dir, 'test.db'))

        activity = store.get_last_activity('server1', 'unknown_user')
        assert activity is None

    def test_server_isolation(self, temp_dir):
        """Different servers should have isolated activity data."""
        store = ActivityStore(os.path.join(temp_dir, 'test.db'))
        now = datetime.now()

        store.record_activity(
            server_id='server1',
            user_id='user1',
            user_name='User1',
            channel_id='channel1',
            timestamp=now
        )
        store.record_activity(
            server_id='server2',
            user_id='user1',  # Same user ID, different server
            user_name='User1Different',
            channel_id='channel2',
            timestamp=now
        )

        s1_activity = store.get_last_activity('server1', 'user1')
        s2_activity = store.get_last_activity('server2', 'user1')

        assert s1_activity is not None
        assert s2_activity is not None
        assert s1_activity.channel_id == 'channel1'
        assert s2_activity.channel_id == 'channel2'

    def test_timestamp_is_preserved(self, temp_dir):
        """The timestamp should be correctly stored and retrieved."""
        store = ActivityStore(os.path.join(temp_dir, 'test.db'))
        timestamp = datetime(2024, 6, 15, 14, 30, 0)

        store.record_activity(
            server_id='server1',
            user_id='user1',
            user_name='TestUser',
            channel_id='channel1',
            timestamp=timestamp
        )

        activity = store.get_last_activity('server1', 'user1')
        assert activity is not None
        # Compare without microseconds as SQLite may not preserve them
        assert activity.last_message_at.year == 2024
        assert activity.last_message_at.month == 6
        assert activity.last_message_at.day == 15
        assert activity.last_message_at.hour == 14
        assert activity.last_message_at.minute == 30

    def test_multiple_users_same_server(self, temp_dir):
        """Multiple users in the same server should be tracked separately."""
        store = ActivityStore(os.path.join(temp_dir, 'test.db'))
        now = datetime.now()

        store.record_activity(
            server_id='server1',
            user_id='user1',
            user_name='User One',
            channel_id='channel1',
            timestamp=now
        )
        store.record_activity(
            server_id='server1',
            user_id='user2',
            user_name='User Two',
            channel_id='channel2',
            timestamp=now
        )

        user1_activity = store.get_last_activity('server1', 'user1')
        user2_activity = store.get_last_activity('server1', 'user2')

        assert user1_activity is not None
        assert user2_activity is not None
        assert user1_activity.user_name == 'User One'
        assert user2_activity.user_name == 'User Two'

    def test_returns_user_activity_dataclass(self, temp_dir):
        """get_last_activity() should return a UserActivity instance."""
        store = ActivityStore(os.path.join(temp_dir, 'test.db'))
        now = datetime.now()

        store.record_activity(
            server_id='server1',
            user_id='user1',
            user_name='TestUser',
            channel_id='channel1',
            timestamp=now
        )

        activity = store.get_last_activity('server1', 'user1')
        assert isinstance(activity, UserActivity)
