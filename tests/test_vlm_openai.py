"""Unit tests for the OpenAI VLM caption helper.

Network-free — the AsyncOpenAI client's responses.create is patched out.
"""

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.media import vlm_openai


def _fake_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(output_text=text)


@pytest.mark.asyncio
async def test_empty_url_short_circuits_to_empty_caption():
    result = await vlm_openai.caption_image("")
    assert result == vlm_openai.EMPTY_CAPTION
    assert result is not vlm_openai.EMPTY_CAPTION


@pytest.mark.asyncio
async def test_parses_clean_json_from_url():
    payload = {
        "description": "A cat in the void",
        "themes": ["surreal", "feline"],
        "style": "oil painting",
        "reasoning": "domestic vs infinite",
    }
    with patch.object(
        vlm_openai._client.responses,
        "create",
        new=AsyncMock(return_value=_fake_response(json.dumps(payload))),
    ) as mocked:
        result = await vlm_openai.caption_image("https://example.com/cat.png")

    assert result == payload
    # The URL should pass through untouched as the image_url field.
    call_kwargs = mocked.await_args.kwargs
    image_part = call_kwargs["input"][0]["content"][1]
    assert image_part["type"] == "input_image"
    assert image_part["image_url"] == "https://example.com/cat.png"


@pytest.mark.asyncio
async def test_local_path_is_base64_encoded(tmp_path):
    image_bytes = b"\x89PNG\r\n\x1a\nfakebody"
    img_file = tmp_path / "tiny.png"
    img_file.write_bytes(image_bytes)

    payload = {"description": "x", "themes": ["a"], "style": "y", "reasoning": "z"}
    with patch.object(
        vlm_openai._client.responses,
        "create",
        new=AsyncMock(return_value=_fake_response(json.dumps(payload))),
    ) as mocked:
        result = await vlm_openai.caption_image(str(img_file))

    assert result["description"] == "x"
    image_url = mocked.await_args.kwargs["input"][0]["content"][1]["image_url"]
    expected_b64 = base64.b64encode(image_bytes).decode("utf-8")
    assert image_url == f"data:image/png;base64,{expected_b64}"


@pytest.mark.asyncio
async def test_strips_markdown_fence():
    raw = "```json\n" + '{"description": "x", "themes": ["a"], "style": "y", "reasoning": "z"}' + "\n```"
    with patch.object(
        vlm_openai._client.responses,
        "create",
        new=AsyncMock(return_value=_fake_response(raw)),
    ):
        result = await vlm_openai.caption_image("https://example.com/x.png")
    assert result["description"] == "x"
    assert result["themes"] == ["a"]


@pytest.mark.asyncio
async def test_network_failure_returns_empty_caption():
    with patch.object(
        vlm_openai._client.responses,
        "create",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await vlm_openai.caption_image("https://example.com/x.png")
    assert result == vlm_openai.EMPTY_CAPTION


@pytest.mark.asyncio
async def test_garbled_output_returns_empty_caption():
    with patch.object(
        vlm_openai._client.responses,
        "create",
        new=AsyncMock(return_value=_fake_response("not-json-at-all")),
    ):
        result = await vlm_openai.caption_image("https://example.com/x.png")
    assert result == vlm_openai.EMPTY_CAPTION


@pytest.mark.asyncio
async def test_empty_output_text_returns_empty_caption():
    with patch.object(
        vlm_openai._client.responses,
        "create",
        new=AsyncMock(return_value=_fake_response("")),
    ):
        result = await vlm_openai.caption_image("https://example.com/x.png")
    assert result == vlm_openai.EMPTY_CAPTION


@pytest.mark.asyncio
async def test_missing_local_file_returns_empty_caption():
    result = await vlm_openai.caption_image("/no/such/path/image.png")
    assert result == vlm_openai.EMPTY_CAPTION


@pytest.mark.asyncio
async def test_null_themes_normalised_to_empty_list():
    raw = '{"themes": null, "description": "x", "style": "y", "reasoning": "z"}'
    with patch.object(
        vlm_openai._client.responses,
        "create",
        new=AsyncMock(return_value=_fake_response(raw)),
    ):
        result = await vlm_openai.caption_image("https://example.com/x.png")
    assert result["themes"] == []


@pytest.mark.asyncio
async def test_dispatcher_routes_to_openai_when_env_set(monkeypatch):
    """vlm.caption_image should hand off to vlm_openai when VLM_PROVIDER=openai."""
    from src.media import vlm

    monkeypatch.setenv("VLM_PROVIDER", "openai")
    sentinel = {"description": "routed", "themes": [], "style": "", "reasoning": ""}
    with patch("src.media.vlm_openai.caption_image", new=AsyncMock(return_value=sentinel)) as routed:
        result = await vlm.caption_image("https://example.com/x.png")

    routed.assert_awaited_once_with("https://example.com/x.png")
    assert result == sentinel
