"""Unit tests for the OpenAI direct image provider.

Network-free — the AsyncOpenAI client is patched out. The point of these
tests is to lock in the call shape (gpt-image-2 + quality=medium) and the
magic-byte sniff that protects us from gpt-image-2 lying about its
output_format.
"""

import base64
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.media import openai_direct


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
# Minimal RIFF/WEBP header — enough to satisfy our magic-byte check.
WEBP_BYTES = b"RIFF" + (b"\x00" * 4) + b"WEBP" + b"\x00" * 32


def _fake_result(image_bytes: bytes) -> SimpleNamespace:
    return SimpleNamespace(
        data=[SimpleNamespace(b64_json=base64.b64encode(image_bytes).decode("utf-8"))]
    )


@pytest.mark.parametrize(
    "image_bytes,expected_ext",
    [
        (PNG_BYTES, "png"),
        (WEBP_BYTES, "webp"),
        (b"\x00\x01\x02\x03some-other-format", "bin"),
    ],
)
def test_detect_extension(image_bytes, expected_ext):
    assert openai_direct._detect_extension(image_bytes) == expected_ext


@pytest.mark.asyncio
async def test_generate_writes_png_with_correct_extension(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    with patch.object(
        openai_direct._client.images,
        "generate",
        new=AsyncMock(return_value=_fake_result(PNG_BYTES)),
    ) as mocked:
        model = openai_direct.get_image_model()
        path = await model.generate("a cat in a hat")

    assert path.endswith(".png")
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == PNG_BYTES

    call_kwargs = mocked.await_args.kwargs
    assert call_kwargs["model"] == "gpt-image-2"
    assert call_kwargs["prompt"] == "a cat in a hat"
    assert call_kwargs["size"] == "1536x1024"
    assert call_kwargs["quality"] == "medium"
    # `thinking` was suggested by some scraped API docs but the Python SDK
    # rejects it as an unexpected kwarg — keep it out of the call.
    assert "thinking" not in call_kwargs


@pytest.mark.asyncio
async def test_generate_honours_actual_webp_when_returned(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    with patch.object(
        openai_direct._client.images,
        "generate",
        new=AsyncMock(return_value=_fake_result(WEBP_BYTES)),
    ):
        path = await openai_direct.get_image_model().generate("anything")

    assert path.endswith(".webp")


@pytest.mark.asyncio
async def test_generate_raises_when_no_image_returned():
    empty = SimpleNamespace(data=[SimpleNamespace(b64_json=None)])
    with patch.object(
        openai_direct._client.images,
        "generate",
        new=AsyncMock(return_value=empty),
    ):
        with pytest.raises(RuntimeError, match="no image bytes"):
            await openai_direct.get_image_model().generate("anything")


def test_image_model_interface_matches_other_providers():
    model = openai_direct.get_image_model()
    assert model.strategy == "distill"
    assert model.short_name == "openai/gpt-image-2"
    assert isinstance(model.cost, float)
