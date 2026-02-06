"""
Tests for src/persistence/url_store.py
"""

import pytest
import os
from datetime import datetime, timedelta
from src.persistence.url_store import UrlStore, UrlEntry


class TestUrlStore:
    """Tests for UrlStore class."""

    def test_init_creates_database(self, temp_dir):
        """UrlStore should create the database file on init."""
        db_path = os.path.join(temp_dir, 'test.db')
        store = UrlStore(db_path)
        assert os.path.exists(db_path)

    def test_init_creates_parent_directory(self, temp_dir):
        """UrlStore should create parent directories if needed."""
        db_path = os.path.join(temp_dir, 'nested', 'dir', 'test.db')
        store = UrlStore(db_path)
        assert os.path.exists(db_path)

    def test_save_returns_id(self, temp_dir):
        """save() should return the ID of the new entry."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        entry_id = store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page1',
            summary='A test page',
            keywords='test, example',
            posted_by_id='user1',
            posted_by_name='TestUser',
            posted_at=datetime.now()
        )
        assert entry_id == 1

    def test_save_duplicate_url_returns_none(self, temp_dir):
        """save() should return None when URL already exists for server."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        entry_id1 = store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page1',
            summary='First summary',
            keywords='first',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now()
        )
        entry_id2 = store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page1',  # Same URL
            summary='Second summary',
            keywords='second',
            posted_by_id='user2',
            posted_by_name='User2',
            posted_at=datetime.now()
        )
        assert entry_id1 == 1
        assert entry_id2 is None

    def test_url_exists_returns_true_when_found(self, temp_dir):
        """url_exists() should return True when URL exists."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page1',
            summary='A test page',
            keywords='test',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now()
        )
        assert store.url_exists('server1', 'https://example.com/page1') is True

    def test_url_exists_returns_false_when_not_found(self, temp_dir):
        """url_exists() should return False when URL doesn't exist."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        assert store.url_exists('server1', 'https://example.com/notfound') is False

    def test_search_finds_matching_urls(self, temp_dir):
        """search() should find URLs matching query terms."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/ai-article',
            summary='An article about artificial intelligence and machine learning',
            keywords='ai, machine learning, technology',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now()
        )
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/cooking',
            summary='Recipes for Italian pasta dishes',
            keywords='cooking, pasta, italian',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now()
        )

        results = store.search('server1', 'artificial intelligence')
        assert len(results) == 1
        assert results[0].url == 'https://example.com/ai-article'

    def test_search_matches_keywords(self, temp_dir):
        """search() should match against keywords."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page',
            summary='A generic summary',
            keywords='python, programming, tutorial',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now()
        )

        results = store.search('server1', 'python')
        assert len(results) == 1

    def test_search_returns_empty_for_no_matches(self, temp_dir):
        """search() should return empty list when no matches."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page',
            summary='About cats',
            keywords='cats, pets',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now()
        )

        results = store.search('server1', 'dogs')
        assert len(results) == 0

    def test_search_is_case_insensitive(self, temp_dir):
        """search() should be case insensitive."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page',
            summary='About Python Programming',
            keywords='PYTHON, CODE',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now()
        )

        results = store.search('server1', 'python')
        assert len(results) == 1

    def test_get_recent_returns_newest_first(self, temp_dir):
        """get_recent() should return entries in newest-first order."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        now = datetime.now()

        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/old',
            summary='Old page',
            keywords='old',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=now - timedelta(days=2)
        )
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/new',
            summary='New page',
            keywords='new',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=now
        )

        recent = store.get_recent('server1')
        assert len(recent) == 2
        assert recent[0].url == 'https://example.com/new'

    def test_server_isolation(self, temp_dir):
        """Different servers should have isolated data."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        now = datetime.now()

        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page',
            summary='Server 1 page',
            keywords='server1',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=now
        )
        store.save(
            server_id='server2',
            channel_id='channel2',
            url='https://example.com/page',  # Same URL, different server
            summary='Server 2 page',
            keywords='server2',
            posted_by_id='user2',
            posted_by_name='User2',
            posted_at=now
        )

        s1_results = store.get_recent('server1')
        s2_results = store.get_recent('server2')

        assert len(s1_results) == 1
        assert len(s2_results) == 1
        assert s1_results[0].summary == 'Server 1 page'
        assert s2_results[0].summary == 'Server 2 page'

    def test_search_respects_limit(self, temp_dir):
        """search() should respect the limit parameter."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        now = datetime.now()

        for i in range(10):
            store.save(
                server_id='server1',
                channel_id='channel1',
                url=f'https://example.com/page{i}',
                summary=f'Page about python {i}',
                keywords='python',
                posted_by_id='user1',
                posted_by_name='User1',
                posted_at=now - timedelta(hours=i)
            )

        results = store.search('server1', 'python', limit=3)
        assert len(results) == 3

    def test_search_filters_stopwords(self, temp_dir):
        """search() should filter out common stopwords."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page',
            summary='Article about cats',
            keywords='cats, pets',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now()
        )

        # Search with only stopwords should return empty
        results = store.search('server1', 'the a an')
        assert len(results) == 0

        # Search with stopwords + real term should work
        results = store.search('server1', 'the cats')
        assert len(results) == 1

    def test_search_filters_single_char_terms(self, temp_dir):
        """search() should filter out single character terms."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page',
            summary='Article about AI',
            keywords='ai, technology',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now()
        )

        # "AI" is 2 chars so should work
        results = store.search('server1', 'AI')
        assert len(results) == 1

        # Single char "a" alone should return empty (it's also a stopword)
        results = store.search('server1', 'a')
        assert len(results) == 0


class TestUrlStoreSimilaritySearch:
    """Tests for embedding-based similarity search."""

    def test_save_with_embedding(self, temp_dir):
        """save() should store embedding as JSON."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        embedding = [0.1, 0.2, 0.3]
        entry_id = store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page1',
            summary='A test page',
            keywords='test',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now(),
            embedding=embedding
        )
        assert entry_id == 1

        # Verify embedding is retrieved correctly
        results = store.get_recent('server1', limit=1)
        assert len(results) == 1
        assert results[0].embedding == embedding

    def test_save_without_embedding(self, temp_dir):
        """save() should work without embedding (backward compat)."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        entry_id = store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page1',
            summary='A test page',
            keywords='test',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now()
        )
        assert entry_id == 1

        results = store.get_recent('server1', limit=1)
        assert len(results) == 1
        assert results[0].embedding is None

    def test_search_by_similarity_returns_most_similar_first(self, temp_dir):
        """search_by_similarity() should return entries sorted by similarity."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))

        # Create entries with different embeddings
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page1',
            summary='Page about cats',
            keywords='cats',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now(),
            embedding=[1.0, 0.0, 0.0]  # Points in x direction
        )
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page2',
            summary='Page about dogs',
            keywords='dogs',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now(),
            embedding=[0.0, 1.0, 0.0]  # Points in y direction
        )

        # Query similar to first embedding (use min_similarity=0 to test sorting, not filtering)
        results = store.search_by_similarity('server1', [0.9, 0.1, 0.0], min_similarity=0)
        assert len(results) == 2
        assert results[0].url == 'https://example.com/page1'

    def test_search_by_similarity_respects_limit(self, temp_dir):
        """search_by_similarity() should respect limit parameter."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))

        for i in range(5):
            store.save(
                server_id='server1',
                channel_id='channel1',
                url=f'https://example.com/page{i}',
                summary=f'Page {i}',
                keywords='test',
                posted_by_id='user1',
                posted_by_name='User1',
                posted_at=datetime.now(),
                embedding=[float(i), 0.0, 0.0]
            )

        results = store.search_by_similarity('server1', [1.0, 0.0, 0.0], limit=2)
        assert len(results) == 2

    def test_search_by_similarity_excludes_entries_without_embeddings(self, temp_dir):
        """search_by_similarity() should skip entries without embeddings."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))

        # Entry with embedding
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/with-embedding',
            summary='Has embedding',
            keywords='test',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now(),
            embedding=[1.0, 0.0, 0.0]
        )
        # Entry without embedding
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/no-embedding',
            summary='No embedding',
            keywords='test',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now()
        )

        results = store.search_by_similarity('server1', [1.0, 0.0, 0.0])
        assert len(results) == 1
        assert results[0].url == 'https://example.com/with-embedding'

    def test_search_by_similarity_returns_empty_when_no_embeddings(self, temp_dir):
        """search_by_similarity() returns empty list when no entries have embeddings."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))

        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page',
            summary='No embedding',
            keywords='test',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now()
        )

        results = store.search_by_similarity('server1', [1.0, 0.0, 0.0])
        assert len(results) == 0

    def test_search_by_similarity_filters_by_threshold(self, temp_dir):
        """search_by_similarity() should filter out results below min_similarity threshold."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))

        # Create entry with orthogonal embedding (similarity ~0 to query)
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/orthogonal',
            summary='Orthogonal content',
            keywords='test',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now(),
            embedding=[0.0, 1.0, 0.0]  # Points in y direction
        )

        # Query in x direction - cosine similarity with y-vector is 0
        results = store.search_by_similarity('server1', [1.0, 0.0, 0.0], min_similarity=0.5)
        assert len(results) == 0  # Should be filtered out (similarity ~0)

    def test_search_by_similarity_filters_by_posted_after(self, temp_dir):
        """search_by_similarity() should only return entries posted after the given date."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        now = datetime.now()

        # Old entry (60 days ago)
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/old',
            summary='Old article',
            keywords='old',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=now - timedelta(days=60),
            embedding=[0.9, 0.1, 0.0]
        )
        # Recent entry (2 days ago)
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/recent',
            summary='Recent article',
            keywords='recent',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=now - timedelta(days=2),
            embedding=[0.8, 0.2, 0.0]
        )

        # Search with posted_after=7 days ago should only find the recent one
        results = store.search_by_similarity(
            'server1', [1.0, 0.0, 0.0],
            min_similarity=0, posted_after=now - timedelta(days=7)
        )
        assert len(results) == 1
        assert results[0].url == 'https://example.com/recent'

    def test_search_by_similarity_posted_after_none_returns_all(self, temp_dir):
        """search_by_similarity() with posted_after=None should return all matching entries."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))
        now = datetime.now()

        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/old',
            summary='Old article',
            keywords='old',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=now - timedelta(days=60),
            embedding=[0.9, 0.1, 0.0]
        )
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/recent',
            summary='Recent article',
            keywords='recent',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=now - timedelta(days=2),
            embedding=[0.8, 0.2, 0.0]
        )

        # No posted_after filter should return both
        results = store.search_by_similarity(
            'server1', [1.0, 0.0, 0.0], min_similarity=0, posted_after=None
        )
        assert len(results) == 2

    def test_search_by_similarity_returns_results_above_threshold(self, temp_dir):
        """search_by_similarity() should return results above the threshold."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))

        # Create entry with similar embedding (high similarity to query)
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/similar',
            summary='Similar content',
            keywords='test',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now(),
            embedding=[0.9, 0.1, 0.0]  # Similar to x direction
        )
        # Create entry with orthogonal embedding
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/orthogonal',
            summary='Orthogonal content',
            keywords='test',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now(),
            embedding=[0.0, 1.0, 0.0]  # Points in y direction
        )

        # Query in x direction with threshold
        results = store.search_by_similarity('server1', [1.0, 0.0, 0.0], min_similarity=0.5)
        assert len(results) == 1  # Only the similar one
        assert results[0].url == 'https://example.com/similar'

    def test_search_by_similarity_uses_default_threshold(self, temp_dir):
        """search_by_similarity() uses SEMANTIC_SEARCH_MIN_SIMILARITY when no threshold provided."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))

        # Create entry with orthogonal embedding (similarity ~0)
        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/orthogonal',
            summary='Orthogonal content',
            keywords='test',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now(),
            embedding=[0.0, 1.0, 0.0]  # Points in y direction
        )

        # Query without explicit threshold - should use default (0.5)
        results = store.search_by_similarity('server1', [1.0, 0.0, 0.0])
        assert len(results) == 0  # Should be filtered by default threshold

    def test_update_changes_summary_keywords_and_embedding(self, temp_dir):
        """update() should modify an existing entry's summary, keywords, and embedding."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))

        store.save(
            server_id='server1',
            channel_id='channel1',
            url='https://example.com/page1',
            summary='Old summary',
            keywords='old, keywords',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now(),
            embedding=[1.0, 0.0, 0.0]
        )

        entries = store.get_all('server1')
        assert len(entries) == 1

        store.update(entries[0].id, 'New detailed summary', 'new, better, keywords', [0.0, 1.0, 0.0])

        updated = store.get_all('server1')
        assert len(updated) == 1
        assert updated[0].summary == 'New detailed summary'
        assert updated[0].keywords == 'new, better, keywords'
        assert updated[0].embedding == [0.0, 1.0, 0.0]
        assert updated[0].url == 'https://example.com/page1'  # URL unchanged

    def test_get_all_returns_all_entries(self, temp_dir):
        """get_all() should return all entries for a server."""
        store = UrlStore(os.path.join(temp_dir, 'test.db'))

        for i in range(3):
            store.save(
                server_id='server1',
                channel_id='channel1',
                url=f'https://example.com/page{i}',
                summary=f'Summary {i}',
                keywords=f'keyword{i}',
                posted_by_id='user1',
                posted_by_name='User1',
                posted_at=datetime.now()
            )

        # Different server
        store.save(
            server_id='server2',
            channel_id='channel1',
            url='https://example.com/other',
            summary='Other server',
            keywords='other',
            posted_by_id='user1',
            posted_by_name='User1',
            posted_at=datetime.now()
        )

        results = store.get_all('server1')
        assert len(results) == 3

        results2 = store.get_all('server2')
        assert len(results2) == 1
