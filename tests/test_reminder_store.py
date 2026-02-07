"""
Tests for src/persistence/reminder_store.py
"""

import os
from datetime import datetime, timedelta

from src.persistence.reminder_store import ReminderStore, Reminder


class TestReminderStore:
    """Tests for ReminderStore class."""

    def test_init_creates_database(self, temp_dir):
        """ReminderStore should create the database file on init."""
        db_path = os.path.join(temp_dir, 'test.db')
        ReminderStore(db_path)
        assert os.path.exists(db_path)

    def test_init_creates_parent_directory(self, temp_dir):
        """ReminderStore should create parent directories if needed."""
        db_path = os.path.join(temp_dir, 'nested', 'dir', 'test.db')
        ReminderStore(db_path)
        assert os.path.exists(db_path)

    def test_save_returns_id(self, temp_dir):
        """save() should return the id of the new reminder."""
        store = ReminderStore(os.path.join(temp_dir, 'test.db'))
        remind_at = datetime.now() + timedelta(hours=1)

        reminder_id = store.save(
            server_id='server1',
            user_id='user1',
            user_name='TestUser',
            channel_id='channel1',
            reminder_text='Check the deploy',
            remind_at=remind_at,
        )

        assert reminder_id >= 1

    def test_get_due_reminders_returns_due_items(self, temp_dir):
        """get_due_reminders() should return reminders that are past due."""
        store = ReminderStore(os.path.join(temp_dir, 'test.db'))
        past = datetime.now() - timedelta(minutes=5)
        future = datetime.now() + timedelta(hours=1)

        store.save('server1', 'user1', 'User1', 'ch1', 'Due reminder', past)
        store.save('server1', 'user1', 'User1', 'ch1', 'Future reminder', future)

        due = store.get_due_reminders('server1')
        assert len(due) == 1
        assert due[0].reminder_text == 'Due reminder'

    def test_mark_reminded_excludes_from_due(self, temp_dir):
        """mark_reminded() should stop a reminder appearing in get_due_reminders()."""
        store = ReminderStore(os.path.join(temp_dir, 'test.db'))
        past = datetime.now() - timedelta(minutes=5)

        reminder_id = store.save('server1', 'user1', 'User1', 'ch1', 'Test', past)
        store.mark_reminded(reminder_id)

        due = store.get_due_reminders('server1')
        assert len(due) == 0

    def test_count_pending_for_user(self, temp_dir):
        """count_pending_for_user() should count unsent reminders for a user."""
        store = ReminderStore(os.path.join(temp_dir, 'test.db'))
        future = datetime.now() + timedelta(hours=1)

        store.save('server1', 'user1', 'User1', 'ch1', 'Reminder 1', future)
        store.save('server1', 'user1', 'User1', 'ch1', 'Reminder 2', future)
        store.save('server1', 'user2', 'User2', 'ch1', 'Other user', future)

        assert store.count_pending_for_user('server1', 'user1') == 2
        assert store.count_pending_for_user('server1', 'user2') == 1

    def test_get_pending_for_user(self, temp_dir):
        """get_pending_for_user() should return pending reminders ordered by remind_at."""
        store = ReminderStore(os.path.join(temp_dir, 'test.db'))
        later = datetime.now() + timedelta(hours=2)
        sooner = datetime.now() + timedelta(hours=1)

        store.save('server1', 'user1', 'User1', 'ch1', 'Later', later)
        store.save('server1', 'user1', 'User1', 'ch1', 'Sooner', sooner)

        pending = store.get_pending_for_user('server1', 'user1')
        assert len(pending) == 2
        assert pending[0].reminder_text == 'Sooner'
        assert pending[1].reminder_text == 'Later'

    def test_server_isolation(self, temp_dir):
        """Different servers should have isolated reminder data."""
        store = ReminderStore(os.path.join(temp_dir, 'test.db'))
        past = datetime.now() - timedelta(minutes=5)

        store.save('server1', 'user1', 'User1', 'ch1', 'Server1 reminder', past)
        store.save('server2', 'user1', 'User1', 'ch1', 'Server2 reminder', past)

        due_s1 = store.get_due_reminders('server1')
        due_s2 = store.get_due_reminders('server2')

        assert len(due_s1) == 1
        assert due_s1[0].reminder_text == 'Server1 reminder'
        assert len(due_s2) == 1
        assert due_s2[0].reminder_text == 'Server2 reminder'

    def test_prune_removes_old_sent_reminders(self, temp_dir):
        """prune() should delete old reminded entries but keep recent ones."""
        store = ReminderStore(os.path.join(temp_dir, 'test.db'))
        past = datetime.now() - timedelta(minutes=5)

        # Create and mark as reminded
        id1 = store.save('server1', 'user1', 'User1', 'ch1', 'Old', past)
        store.mark_reminded(id1)

        # Prune with 0 days should remove it
        pruned = store.prune(days=0)
        assert pruned == 1

    def test_prune_keeps_unsent_reminders(self, temp_dir):
        """prune() should not delete reminders that haven't been sent yet."""
        store = ReminderStore(os.path.join(temp_dir, 'test.db'))
        past = datetime.now() - timedelta(days=60)

        store.save('server1', 'user1', 'User1', 'ch1', 'Unsent', past)

        pruned = store.prune(days=0)
        assert pruned == 0

    def test_delete_reminder_works_and_checks_user(self, temp_dir):
        """delete_reminder() should only delete if user_id matches."""
        store = ReminderStore(os.path.join(temp_dir, 'test.db'))
        future = datetime.now() + timedelta(hours=1)

        reminder_id = store.save('server1', 'user1', 'User1', 'ch1', 'Test', future)

        # Wrong user should fail
        assert store.delete_reminder(reminder_id, 'wrong_user') is False
        assert store.count_pending_for_user('server1', 'user1') == 1

        # Right user should succeed
        assert store.delete_reminder(reminder_id, 'user1') is True
        assert store.count_pending_for_user('server1', 'user1') == 0

    def test_returns_reminder_dataclass(self, temp_dir):
        """get_due_reminders() should return Reminder instances."""
        store = ReminderStore(os.path.join(temp_dir, 'test.db'))
        past = datetime.now() - timedelta(minutes=5)

        store.save('server1', 'user1', 'User1', 'ch1', 'Test', past)

        due = store.get_due_reminders('server1')
        assert len(due) == 1
        assert isinstance(due[0], Reminder)
        assert due[0].server_id == 'server1'
        assert due[0].user_id == 'user1'
        assert due[0].user_name == 'User1'
        assert due[0].channel_id == 'ch1'
        assert due[0].reminder_text == 'Test'
        assert due[0].reminded_at is None
