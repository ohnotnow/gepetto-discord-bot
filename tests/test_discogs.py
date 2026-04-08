"""
Tests for src/content/discogs.py
"""

import pytest
from unittest.mock import patch, MagicMock


class TestSearchArtistSync:
    """Tests for the synchronous _search_artist_sync function."""

    @patch("src.content.discogs._get_client")
    def test_returns_formatted_results(self, mock_get_client):
        from src.content.discogs import _search_artist_sync

        mock_artist1 = MagicMock()
        mock_artist1.id = 123
        mock_artist1.name = "Radiohead"
        mock_artist2 = MagicMock()
        mock_artist2.id = 456
        mock_artist2.name = "Radiohead Tribute Band"

        mock_results = MagicMock()
        mock_results.count = 2
        mock_results.__iter__ = lambda self: iter([mock_artist1, mock_artist2])
        mock_results.__getitem__ = lambda self, key: [mock_artist1, mock_artist2][key]

        mock_client = MagicMock()
        mock_client.search.return_value = mock_results
        mock_get_client.return_value = mock_client

        result = _search_artist_sync("Radiohead")

        assert "Radiohead" in result
        assert "ID: 123" in result
        assert "ID: 456" in result
        mock_client.search.assert_called_once_with("Radiohead", type="artist")

    @patch("src.content.discogs._get_client")
    def test_no_results(self, mock_get_client):
        from src.content.discogs import _search_artist_sync

        mock_results = MagicMock()
        mock_results.count = 0

        mock_client = MagicMock()
        mock_client.search.return_value = mock_results
        mock_get_client.return_value = mock_client

        result = _search_artist_sync("xyznonexistentartist")
        assert "No artists found" in result

    @patch("src.content.discogs._get_client")
    def test_missing_token(self, mock_get_client):
        from src.content.discogs import _search_artist_sync

        mock_get_client.return_value = None

        result = _search_artist_sync("Radiohead")
        assert "not configured" in result

    @patch("src.content.discogs._get_client")
    def test_api_error(self, mock_get_client):
        from src.content.discogs import _search_artist_sync

        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("rate limited")
        mock_get_client.return_value = mock_client

        result = _search_artist_sync("Radiohead")
        assert "failed" in result.lower()

    @patch("src.content.discogs._get_client")
    def test_limits_results(self, mock_get_client):
        from src.content.discogs import _search_artist_sync

        artists = []
        for i in range(10):
            a = MagicMock()
            a.id = i
            a.name = f"Artist {i}"
            artists.append(a)

        mock_results = MagicMock()
        mock_results.count = 10
        mock_results.__iter__ = lambda self: iter(artists)
        mock_results.__getitem__ = lambda self, key: artists[key]

        mock_client = MagicMock()
        mock_client.search.return_value = mock_results
        mock_get_client.return_value = mock_client

        result = _search_artist_sync("Artist", limit=3)
        # Should only have 3 entries
        assert result.count("ID:") == 3


class TestExploreArtistSync:
    """Tests for the synchronous _explore_artist_sync function."""

    def _make_mock_artist(self, name="Radiohead", artist_id=123):
        artist = MagicMock()
        artist.name = name
        artist.id = artist_id
        artist.profile = "English rock band formed in Abingdon, Oxfordshire."

        member1 = MagicMock()
        member1.name = "Thom Yorke"
        member1.id = 100
        member2 = MagicMock()
        member2.name = "Jonny Greenwood"
        member2.id = 101
        artist.members = [member1, member2]
        artist.groups = []

        release1 = MagicMock()
        release1.title = "OK Computer"
        release1.year = 1997
        release1.genres = ["Electronic", "Rock"]
        release1.styles = ["Alternative Rock", "Art Rock"]

        release2 = MagicMock()
        release2.title = "Kid A"
        release2.year = 2000
        release2.genres = ["Electronic", "Rock"]
        release2.styles = ["Experimental", "IDM"]

        artist.releases = [release1, release2]
        return artist

    @patch("src.content.discogs._get_client")
    def test_explore_by_name(self, mock_get_client):
        from src.content.discogs import _explore_artist_sync

        mock_artist = self._make_mock_artist()
        mock_search_result = MagicMock()
        mock_search_result.id = 123

        mock_results = MagicMock()
        mock_results.count = 1
        mock_results.__getitem__ = lambda self, key: mock_search_result

        mock_client = MagicMock()
        mock_client.search.return_value = mock_results
        mock_client.artist.return_value = mock_artist
        mock_get_client.return_value = mock_client

        result = _explore_artist_sync("Radiohead")

        assert "Radiohead" in result
        assert "Thom Yorke" in result
        assert "Jonny Greenwood" in result
        assert "OK Computer" in result
        assert "Kid A" in result
        assert "Alternative Rock" in result
        assert "Electronic" in result

    @patch("src.content.discogs._get_client")
    def test_explore_by_id(self, mock_get_client):
        from src.content.discogs import _explore_artist_sync

        mock_artist = self._make_mock_artist()

        mock_client = MagicMock()
        mock_client.artist.return_value = mock_artist
        mock_get_client.return_value = mock_client

        result = _explore_artist_sync("123")

        assert "Radiohead" in result
        assert "Thom Yorke" in result
        mock_client.search.assert_not_called()

    @patch("src.content.discogs._get_client")
    def test_explore_not_found(self, mock_get_client):
        from src.content.discogs import _explore_artist_sync

        mock_results = MagicMock()
        mock_results.count = 0
        mock_results.__getitem__ = MagicMock(side_effect=IndexError)

        mock_client = MagicMock()
        mock_client.search.return_value = mock_results
        mock_get_client.return_value = mock_client

        result = _explore_artist_sync("xyznonexistent")
        assert "No artist found" in result

    @patch("src.content.discogs._get_client")
    def test_missing_token(self, mock_get_client):
        from src.content.discogs import _explore_artist_sync

        mock_get_client.return_value = None

        result = _explore_artist_sync("Radiohead")
        assert "not configured" in result

    @patch("src.content.discogs._get_client")
    def test_solo_artist_shows_groups(self, mock_get_client):
        from src.content.discogs import _explore_artist_sync

        mock_artist = MagicMock()
        mock_artist.name = "Thom Yorke"
        mock_artist.id = 100
        mock_artist.profile = "English musician."
        mock_artist.members = []

        group1 = MagicMock()
        group1.name = "Radiohead"
        group1.id = 123
        group2 = MagicMock()
        group2.name = "Atoms For Peace"
        group2.id = 789
        mock_artist.groups = [group1, group2]
        mock_artist.releases = []

        mock_search_result = MagicMock()
        mock_search_result.id = 100

        mock_results = MagicMock()
        mock_results.count = 1
        mock_results.__getitem__ = lambda self, key: mock_search_result

        mock_client = MagicMock()
        mock_client.search.return_value = mock_results
        mock_client.artist.return_value = mock_artist
        mock_get_client.return_value = mock_client

        result = _explore_artist_sync("Thom Yorke")

        assert "Thom Yorke" in result
        assert "Radiohead" in result
        assert "Atoms For Peace" in result
        assert "Also in" in result

    @patch("src.content.discogs._get_client")
    def test_truncates_long_profile(self, mock_get_client):
        from src.content.discogs import _explore_artist_sync

        mock_artist = MagicMock()
        mock_artist.name = "Test Artist"
        mock_artist.id = 1
        mock_artist.profile = "x" * 1000
        mock_artist.members = []
        mock_artist.groups = []
        mock_artist.releases = []

        mock_client = MagicMock()
        mock_client.artist.return_value = mock_artist
        mock_get_client.return_value = mock_client

        result = _explore_artist_sync("1")
        assert "..." in result


class TestToolDefinitions:
    """Tests for Discogs tool definitions."""

    def test_search_discogs_tool_structure(self):
        from src.tools.definitions import search_discogs_tool
        func = search_discogs_tool["function"]
        assert func["name"] == "search_discogs"
        assert "query" in func["parameters"]["properties"]
        assert func["parameters"]["required"] == ["query"]

    def test_explore_discogs_artist_tool_structure(self):
        from src.tools.definitions import explore_discogs_artist_tool
        func = explore_discogs_artist_tool["function"]
        assert func["name"] == "explore_discogs_artist"
        assert "artist" in func["parameters"]["properties"]
        assert func["parameters"]["required"] == ["artist"]


@pytest.mark.asyncio
class TestAsyncWrappers:
    """Tests for the async wrapper functions."""

    @patch("src.content.discogs._get_client")
    async def test_search_artist_async(self, mock_get_client):
        from src.content.discogs import search_artist

        mock_get_client.return_value = None
        result = await search_artist("test")
        assert "not configured" in result

    @patch("src.content.discogs._get_client")
    async def test_explore_artist_async(self, mock_get_client):
        from src.content.discogs import explore_artist

        mock_get_client.return_value = None
        result = await explore_artist("test")
        assert "not configured" in result
