import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_search_returns_response():
    """Test that search returns formatted response"""
    from src.providers import grok

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Here is what people are saying about AI on Twitter..."
    mock_response.citations = None

    with patch("src.providers.grok.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = mock_response
        result = await grok.search("AI news")

        assert "AI" in result or "Twitter" in result.lower() or len(result) > 0
        mock_completion.assert_called_once()


@pytest.mark.asyncio
async def test_search_includes_citations():
    """Test that citations are formatted in response"""
    from src.providers import grok

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Breaking news about the event"
    mock_response.citations = ["https://twitter.com/user/status/123", "https://twitter.com/user/status/456"]

    with patch("src.providers.grok.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = mock_response
        result = await grok.search("breaking news")

        assert "Sources:" in result
        assert "https://twitter.com" in result


@pytest.mark.asyncio
async def test_search_truncates_long_response():
    """Test that response is truncated to 1800 chars"""
    from src.providers import grok

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "x" * 2000  # Longer than limit
    mock_response.citations = None

    with patch("src.providers.grok.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = mock_response
        result = await grok.search("test query")

        assert len(result) <= 1800


@pytest.mark.asyncio
async def test_search_uses_correct_model():
    """Test that search uses the correct Grok model"""
    from src.providers import grok

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Response"
    mock_response.citations = None

    with patch("src.providers.grok.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = mock_response
        await grok.search("test")

        call_kwargs = mock_completion.call_args.kwargs
        assert "grok" in call_kwargs["model"].lower()
        assert call_kwargs["tools"] is not None


@pytest.mark.asyncio
async def test_search_handles_empty_content():
    """Test that search handles empty response content gracefully"""
    from src.providers import grok

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = None
    mock_response.citations = None

    with patch("src.providers.grok.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = mock_response
        result = await grok.search("test query")

        assert result == ""


@pytest.mark.asyncio
async def test_search_limits_citations_to_five():
    """Test that only up to 5 citations are included"""
    from src.providers import grok

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Content"
    mock_response.citations = [f"https://twitter.com/status/{i}" for i in range(10)]

    with patch("src.providers.grok.acompletion", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = mock_response
        result = await grok.search("test")

        # Count URLs in result - should be max 5
        url_count = result.count("https://twitter.com/status/")
        assert url_count <= 5
