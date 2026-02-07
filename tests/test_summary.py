"""Tests for summary module URL filtering and Gemini summarisation."""

import asyncio
import os
import pytest
from unittest.mock import MagicMock, patch
from src.content.summary import is_summarisable_url, is_youtube_url, summarise_with_gemini


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


class TestIsYoutubeUrl:
    def test_standard_youtube_url(self):
        assert is_youtube_url("https://www.youtube.com/watch?v=abc123") is True

    def test_short_youtube_url(self):
        assert is_youtube_url("https://youtu.be/abc123") is True

    def test_non_youtube_url(self):
        assert is_youtube_url("https://example.com/article") is False

    def test_youtube_in_path_but_not_domain(self):
        assert is_youtube_url("https://example.com/youtube.com/video") is False


class TestSummariseWithGemini:
    def test_returns_none_when_no_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            result = asyncio.run(summarise_with_gemini("https://example.com", "summarise this"))
            assert result is None

    def test_returns_summary_on_success(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is a summary."
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            with patch("src.content.summary.acompletion", return_value=mock_response):
                result = asyncio.run(summarise_with_gemini("https://example.com", "summarise this"))
                assert result == "This is a summary."

    def test_returns_none_on_exception(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            with patch("src.content.summary.acompletion", side_effect=Exception("API error")):
                result = asyncio.run(summarise_with_gemini("https://example.com", "summarise this"))
                assert result is None

    def test_returns_none_on_empty_response(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            with patch("src.content.summary.acompletion", return_value=mock_response):
                result = asyncio.run(summarise_with_gemini("https://example.com", "summarise this"))
                assert result is None

    def test_passes_prompt_to_gemini(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "A summary."
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            with patch("src.content.summary.acompletion", return_value=mock_response) as mock_call:
                asyncio.run(summarise_with_gemini("https://example.com", "give me the key points"))
                call_args = mock_call.call_args
                user_msg = call_args.kwargs["messages"][1]["content"]
                assert "give me the key points" in user_msg
                assert "https://example.com" in user_msg
