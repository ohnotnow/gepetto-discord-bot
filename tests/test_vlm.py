"""Unit tests for the VLM caption helper.

Network-free — the replicate client is patched out. The end-to-end behaviour
was validated against a real image during the exploration phase (see the
epic gepetto-discord-bot-VqXmZ for findings).
"""

from unittest.mock import patch

import pytest

from src.media import vlm


class _FakeAsyncIter:
    """Minimal async iterator yielding pre-baked chunks as replicate would."""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


def _stream_returning(chunks):
    # replicate.async_stream returns a coroutine that resolves to an async
    # iterator, so our fake has to match that shape.
    async def _fake_stream(*_args, **_kwargs):
        return _FakeAsyncIter(chunks)
    return _fake_stream


@pytest.mark.asyncio
async def test_empty_url_short_circuits_to_empty_caption():
    result = await vlm.caption_image("")
    assert result == vlm.EMPTY_CAPTION
    # Return value should be a fresh copy — callers mutating it shouldn't
    # corrupt the module-level constant.
    assert result is not vlm.EMPTY_CAPTION


@pytest.mark.asyncio
async def test_parses_clean_json():
    payload = {
        "description": "A cat floating in the void",
        "themes": ["surreal", "feline", "cosmic"],
        "style": "oil painting",
        "reasoning": "contrast between domestic and infinite",
    }
    import json as _json
    chunks = [_json.dumps(payload)]
    with patch("src.media.vlm.replicate_client.async_stream", _stream_returning(chunks)):
        result = await vlm.caption_image("https://example.com/cat.png")
    assert result == payload


@pytest.mark.asyncio
async def test_strips_markdown_fence():
    raw = "```json\n" + '{"description": "x", "themes": ["a"], "style": "y", "reasoning": "z"}' + "\n```"
    with patch("src.media.vlm.replicate_client.async_stream", _stream_returning([raw])):
        result = await vlm.caption_image("https://example.com/x.png")
    assert result["description"] == "x"
    assert result["themes"] == ["a"]


@pytest.mark.asyncio
async def test_network_failure_returns_empty_caption():
    async def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")
    with patch("src.media.vlm.replicate_client.async_stream", _boom):
        result = await vlm.caption_image("https://example.com/x.png")
    assert result == vlm.EMPTY_CAPTION


@pytest.mark.asyncio
async def test_garbled_output_returns_empty_caption():
    chunks = ["not-json-at-all"]
    with patch("src.media.vlm.replicate_client.async_stream", _stream_returning(chunks)):
        result = await vlm.caption_image("https://example.com/x.png")
    assert result == vlm.EMPTY_CAPTION


@pytest.mark.asyncio
async def test_missing_keys_are_filled_with_defaults():
    # Model returns partial output — we still want a well-shaped dict back.
    chunks = ['{"themes": ["a", "b"]}']
    with patch("src.media.vlm.replicate_client.async_stream", _stream_returning(chunks)):
        result = await vlm.caption_image("https://example.com/x.png")
    assert result["themes"] == ["a", "b"]
    assert result["description"] == ""
    assert result["style"] == ""
    assert result["reasoning"] == ""


@pytest.mark.asyncio
async def test_null_themes_normalised_to_empty_list():
    # Defensive: if the model emits `"themes": null`, we don't want a None
    # slipping into the rest of the pipeline where it expects a list.
    chunks = ['{"themes": null, "description": "x", "style": "y", "reasoning": "z"}']
    with patch("src.media.vlm.replicate_client.async_stream", _stream_returning(chunks)):
        result = await vlm.caption_image("https://example.com/x.png")
    assert result["themes"] == []


@pytest.mark.asyncio
async def test_critique_empty_url_returns_empty_string():
    assert await vlm.critique_image("") == ""


@pytest.mark.asyncio
async def test_critique_returns_joined_stream_text():
    chunks = ["A work of ", "unpardonable ", "sincerity."]
    with patch("src.media.vlm.replicate_client.async_stream", _stream_returning(chunks)):
        result = await vlm.critique_image("https://example.com/x.png")
    assert result == "A work of unpardonable sincerity."


@pytest.mark.asyncio
async def test_critique_failure_returns_empty_string():
    async def _boom(*_args, **_kwargs):
        raise RuntimeError("nope")
    with patch("src.media.vlm.replicate_client.async_stream", _boom):
        result = await vlm.critique_image("https://example.com/x.png")
    assert result == ""


@pytest.mark.asyncio
async def test_critique_is_blind_no_context_beyond_the_image():
    """The critic must receive ONLY the image and the persona prompt —
    no chat, no themes, no generation prompt. The blindness is the joke."""
    captured = {}

    async def _capturing_stream(model, input):
        captured["model"] = model
        captured["input"] = input
        return _FakeAsyncIter(["review"])

    with patch("src.media.vlm.replicate_client.async_stream", _capturing_stream):
        await vlm.critique_image("https://example.com/x.png")

    assert captured["input"]["images"] == ["https://example.com/x.png"]
    assert captured["input"]["prompt"] == vlm.CRITIC_PROMPT
