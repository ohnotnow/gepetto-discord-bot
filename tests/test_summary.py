"""Tests for summary module URL filtering."""

import pytest
from src.content.summary import is_summarisable_url


class TestIsSummarisableUrl:
    """Tests for is_summarisable_url function."""

    def test_normal_webpage_returns_true(self):
        """Normal webpage URLs should be summarisable."""
        assert is_summarisable_url("https://example.com/article") is True
        assert is_summarisable_url("https://news.ycombinator.com/item?id=123") is True
        assert is_summarisable_url("https://blog.example.com/post/title-here") is True

    def test_image_extensions_return_false(self):
        """Image URLs should not be summarisable."""
        assert is_summarisable_url("https://example.com/photo.jpg") is False
        assert is_summarisable_url("https://example.com/photo.JPEG") is False
        assert is_summarisable_url("https://example.com/image.png") is False
        assert is_summarisable_url("https://example.com/animation.gif") is False
        assert is_summarisable_url("https://example.com/image.webp") is False

    def test_video_extensions_return_false(self):
        """Video URLs should not be summarisable."""
        assert is_summarisable_url("https://example.com/video.mp4") is False
        assert is_summarisable_url("https://example.com/clip.webm") is False
        assert is_summarisable_url("https://example.com/movie.mkv") is False

    def test_audio_extensions_return_false(self):
        """Audio URLs should not be summarisable."""
        assert is_summarisable_url("https://example.com/song.mp3") is False
        assert is_summarisable_url("https://example.com/audio.wav") is False
        assert is_summarisable_url("https://example.com/track.flac") is False

    def test_archive_extensions_return_false(self):
        """Archive/binary URLs should not be summarisable."""
        assert is_summarisable_url("https://example.com/file.zip") is False
        assert is_summarisable_url("https://example.com/app.exe") is False
        assert is_summarisable_url("https://example.com/package.tar.gz") is False

    def test_media_hosting_domains_return_false(self):
        """URLs from media hosting domains should not be summarisable."""
        assert is_summarisable_url("https://imgur.com/gallery/abc") is False
        assert is_summarisable_url("https://i.imgur.com/abc123.jpg") is False
        assert is_summarisable_url("https://media.giphy.com/media/123/giphy.gif") is False
        assert is_summarisable_url("https://cdn.discordapp.com/attachments/123/456/image.png") is False
        assert is_summarisable_url("https://media.discordapp.net/attachments/123/456/file") is False

    def test_query_params_stripped_for_extension_check(self):
        """Query parameters should not affect extension detection."""
        assert is_summarisable_url("https://example.com/image.jpg?size=large") is False
        assert is_summarisable_url("https://example.com/image.png#section") is False

    def test_case_insensitive_extension_matching(self):
        """Extension matching should be case-insensitive."""
        assert is_summarisable_url("https://example.com/IMAGE.JPG") is False
        assert is_summarisable_url("https://example.com/Video.MP4") is False

    def test_youtube_returns_true(self):
        """YouTube URLs should be summarisable (handled specially by get_text)."""
        assert is_summarisable_url("https://www.youtube.com/watch?v=abc123") is True
        assert is_summarisable_url("https://youtu.be/abc123") is True
