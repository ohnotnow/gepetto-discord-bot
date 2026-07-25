"""
Tests for src/persistence/music_store.py
"""

import os
from datetime import datetime, timedelta

from src.persistence.music_store import MusicStore, MusicEntry


def make_store(temp_dir):
    return MusicStore(os.path.join(temp_dir, 'test.db'))


def save_link(store, url='https://www.youtube.com/watch?v=abc123', user_id='user1',
              user_name='TestUser', artist='Arab Strap', is_music=True, **overrides):
    kwargs = dict(
        server_id='server1',
        channel_id='channel1',
        url=url,
        video_title=f'{artist} - Some Track' if artist else 'Some Video',
        video_channel='SomeChannel',
        posted_by_id=user_id,
        posted_by_name=user_name,
        posted_at=datetime.now(),
        artist=artist,
        collaborators=['Guest Singer'],
        track='Some Track',
        genres=['Rock', 'Electronic'],
        styles=['Indie Rock'],
        is_music=is_music,
    )
    kwargs.update(overrides)
    return store.save(**kwargs)


class TestMusicStore:

    def test_init_creates_database(self, temp_dir):
        db_path = os.path.join(temp_dir, 'test.db')
        MusicStore(db_path)
        assert os.path.exists(db_path)

    def test_save_returns_id(self, temp_dir):
        store = make_store(temp_dir)
        assert save_link(store) == 1

    def test_save_duplicate_url_returns_none(self, temp_dir):
        store = make_store(temp_dir)
        assert save_link(store) == 1
        assert save_link(store) is None

    def test_same_url_different_server_is_not_duplicate(self, temp_dir):
        store = make_store(temp_dir)
        save_link(store)
        assert save_link(store, server_id='server2') is not None

    def test_url_exists(self, temp_dir):
        store = make_store(temp_dir)
        save_link(store)
        assert store.url_exists('server1', 'https://www.youtube.com/watch?v=abc123') is True
        assert store.url_exists('server1', 'https://www.youtube.com/watch?v=other') is False

    def test_json_list_fields_round_trip(self, temp_dir):
        store = make_store(temp_dir)
        save_link(store, collaborators=['Polly Jean Harvey'],
                  genres=['Electronic', 'Hip Hop'], styles=['Trip Hop', 'Downtempo'])
        entry = store.get_recent('server1')[0]
        assert entry.collaborators == ['Polly Jean Harvey']
        assert entry.genres == ['Electronic', 'Hip Hop']
        assert entry.styles == ['Trip Hop', 'Downtempo']
        assert entry.is_music is True

    def test_non_music_saved_with_null_artist(self, temp_dir):
        store = make_store(temp_dir)
        entry_id = save_link(store, artist=None, track=None, is_music=False,
                             collaborators=[], genres=[], styles=[])
        assert entry_id is not None
        assert store.url_exists('server1', 'https://www.youtube.com/watch?v=abc123') is True

    def test_get_user_history_excludes_non_music(self, temp_dir):
        store = make_store(temp_dir)
        save_link(store, url='https://youtu.be/music1')
        save_link(store, url='https://youtu.be/trailer', is_music=False, artist=None)
        entries = store.get_user_history('server1', 'user1')
        assert [e.url for e in entries] == ['https://youtu.be/music1']

    def test_get_user_history_is_per_user_and_newest_first(self, temp_dir):
        store = make_store(temp_dir)
        now = datetime.now()
        save_link(store, url='https://youtu.be/old', posted_at=now - timedelta(days=2))
        save_link(store, url='https://youtu.be/new', posted_at=now)
        save_link(store, url='https://youtu.be/other-user', user_id='user2', user_name='Other')
        entries = store.get_user_history('server1', 'user1')
        assert [e.url for e in entries] == ['https://youtu.be/new', 'https://youtu.be/old']

    def test_get_recent_excludes_non_music(self, temp_dir):
        store = make_store(temp_dir)
        save_link(store, url='https://youtu.be/music1')
        save_link(store, url='https://youtu.be/trailer', is_music=False, artist=None)
        assert [e.url for e in store.get_recent('server1')] == ['https://youtu.be/music1']

    def test_profile_counts_single_user_only(self, temp_dir):
        store = make_store(temp_dir)
        save_link(store, url='https://youtu.be/one', artist='Low')
        save_link(store, url='https://youtu.be/two', artist='Low')
        save_link(store, url='https://youtu.be/three', user_id='user2', user_name='Other', artist='Pendulum')
        counts = store.profile_counts('server1', 'user1')
        assert counts['artists'] == {'Low': 2}
        assert counts['genres']['Rock'] == 2
        assert counts['styles']['Indie Rock'] == 2

    def test_profile_counts_drops_non_music_genre_tag(self, temp_dir):
        store = make_store(temp_dir)
        save_link(store, genres=['Rock', 'Non-Music'])
        counts = store.profile_counts('server1', 'user1')
        assert 'Non-Music' not in counts['genres']
        assert counts['genres']['Rock'] == 1

    def test_profile_counts_ignores_non_music_rows(self, temp_dir):
        store = make_store(temp_dir)
        save_link(store, url='https://youtu.be/trailer', is_music=False, artist=None,
                  genres=['Stage & Screen'])
        counts = store.profile_counts('server1', 'user1')
        assert counts['artists'] == {}
        assert counts['genres'] == {}

    def test_resolve_user_name_case_insensitive(self, temp_dir):
        store = make_store(temp_dir)
        save_link(store, user_id='12345', user_name='SomePoster')
        assert store.resolve_user_name('server1', 'someposter') == '12345'
        assert store.resolve_user_name('server1', 'SOMEPOSTER') == '12345'

    def test_resolve_user_name_unknown_returns_none(self, temp_dir):
        store = make_store(temp_dir)
        save_link(store)
        assert store.resolve_user_name('server1', 'nobody') is None

    def test_no_pruning_at_scale(self, temp_dir):
        store = make_store(temp_dir)
        for i in range(600):
            save_link(store, url=f'https://youtu.be/video{i}')
        entries = store.get_user_history('server1', 'user1', limit=1000)
        assert len(entries) == 600


class TestMusicStoreBackup:

    def test_backup_sections(self):
        assert 'music' in MusicStore.backup_sections()

    def test_export_import_roundtrip(self, temp_dir):
        store = make_store(temp_dir)
        save_link(store, url='https://youtu.be/one', artist='Suuns')
        save_link(store, url='https://youtu.be/trailer', is_music=False, artist=None)
        exported = store.export_server('server1')
        assert len(exported['music']) == 2

        other = MusicStore(os.path.join(temp_dir, 'other.db'))
        result = other.import_server('server1', exported)
        assert result['music'] == {'imported': 2, 'skipped': 0}

        entries = other.get_recent('server1')
        assert len(entries) == 1  # only the music row
        assert entries[0].artist == 'Suuns'
        assert other.url_exists('server1', 'https://youtu.be/trailer') is True

    def test_import_skips_duplicates(self, temp_dir):
        store = make_store(temp_dir)
        save_link(store)
        exported = store.export_server('server1')
        result = store.import_server('server1', exported)
        assert result['music'] == {'imported': 0, 'skipped': 1}

    def test_registered_in_get_backup_stores(self, temp_dir):
        from src.persistence import get_backup_stores
        stores = get_backup_stores(os.path.join(temp_dir, 'test.db'))
        assert any(isinstance(s, MusicStore) for s in stores)
