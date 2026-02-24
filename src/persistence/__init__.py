from .json_store import JSONStore
from .image_store import ImageStore, ImageEntry
from .memory_store import MemoryStore, Memory, UserBio
from .url_store import UrlStore, UrlEntry
from .activity_store import ActivityStore, UserActivity
from .reminder_store import ReminderStore, Reminder

__all__ = ['JSONStore', 'ImageStore', 'ImageEntry', 'MemoryStore', 'Memory', 'UserBio', 'UrlStore', 'UrlEntry', 'ActivityStore', 'UserActivity', 'ReminderStore', 'Reminder', 'get_backup_stores']


def get_backup_stores(db_path: str = './data/gepetto.db') -> list:
    """Returns all store instances that support backup."""
    stores = [
        ActivityStore(db_path),
        ImageStore(db_path),
        MemoryStore(db_path),
        ReminderStore(db_path),
        UrlStore(db_path),
    ]
    return [s for s in stores if hasattr(s, 'backup_sections')]
