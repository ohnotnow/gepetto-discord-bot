import base64
import logging
import os
import tempfile
import uuid

from openai import AsyncOpenAI


# We talk to OpenAI's dedicated images.generate endpoint and request the image
# model by name. The Responses API + image_generation tool route pinned to
# gpt-image-1 under the hood (as of 2026-05) and produced noticeably weaker
# results; the direct endpoint lets us choose the model ourselves.
#
# Trade-off: we lose the `revised_prompt` field that the Responses API
# exposes. Not a problem: the corpse pipeline's LLM crafts the prompt and
# returns themes/reasoning itself.
#
# Note: some scraped/leaked API docs mention a `thinking="medium"` kwarg
# (gpt-5.5-style prompt rewriting). The Python SDK rejects it as an
# unexpected keyword — don't add it back without checking the SDK source.
# Used when IMAGE_MODEL / CHAT_IMAGE_MODEL is unset.
MODEL = "gpt-image-2.5-sunburst"

# OpenAI's pricing calculator for gpt-image-2.5-sunburst, medium quality,
# 1536x1024: $0.03396 per image (2026-11).
COST = 0.03

PARAMS = {
    "size": "1536x1024",
    "quality": "medium",
    "output_format": "webp",
    "output_compression": 80,
    "moderation": "low",
}

_client = AsyncOpenAI()
logger = logging.getLogger(__name__)


def _detect_extension(image_bytes: bytes) -> str:
    """Sniff magic bytes to pick the right file extension.

    gpt-image-2 ignores `output_format=webp` and returns PNG bytes anyway
    (confirmed empirically — the response object cheerfully claims webp).
    Trusting the bytes keeps downstream uploads honest.
    """
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "webp"
    return "bin"


class ImageModel:
    """OpenAI image provider — same interface as replicate.ImageModel / fal.ImageModel.

    Unlike Replicate and FAL (which host the image and return a URL), OpenAI
    returns base64 bytes inline. We persist those to a temp file and return
    the local path; the platform adapters know how to send a local path.
    """

    def __init__(self, model: str = MODEL):
        self.model = model
        self.name = f"openai/{model}"
        self._cost = COST

    @property
    def cost(self) -> float:
        return self._cost

    @property
    def short_name(self) -> str:
        return self.name

    async def generate(self, prompt: str) -> str:
        logger.info(f"Using OpenAI image model: {self.name}")
        result = await _client.images.generate(
            model=self.model,
            prompt=prompt,
            **PARAMS,
        )
        image_b64 = result.data[0].b64_json if result.data else None
        if not image_b64:
            raise RuntimeError("OpenAI images.generate returned no image bytes")

        image_bytes = base64.b64decode(image_b64)
        ext = _detect_extension(image_bytes)
        path = os.path.join(
            tempfile.gettempdir(),
            f"openai_{uuid.uuid4().hex}.{ext}",
        )
        with open(path, "wb") as f:
            f.write(image_bytes)
        return path


def get_image_model(model_name: str | None = None) -> ImageModel:
    """Factory: returns an ImageModel ready to generate images.

    A leading "provider/" is stripped, so the same IMAGE_MODEL value works
    for FAL ("openai/gpt-image-2") and OpenAI direct ("gpt-image-2").
    """
    if not model_name:
        return ImageModel()
    return ImageModel(model_name.split("/", 1)[-1])
