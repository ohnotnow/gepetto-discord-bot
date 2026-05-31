import base64
import logging
import os
import tempfile
import uuid

from openai import AsyncOpenAI


# We talk to OpenAI's dedicated images.generate endpoint and request gpt-image-2
# directly. The Responses API + image_generation tool route still pins to
# gpt-image-1 under the hood (as of 2026-05) and produces noticeably weaker
# results than gpt-image-2; until OpenAI lets the orchestrator pick gpt-image-2,
# the direct endpoint is the only way to get the better model.
#
# Trade-off: we lose the `revised_prompt` field that the Responses API
# exposes. Not a problem on the default "distill" strategy (the LLM that
# crafts the prompt also returns themes/reasoning). If you flip strategy
# back to "direct" for a future model, themes/reasoning have to come from
# the VLM caption hop in main.py (vlm.caption_image, which can route to
# vlm_openai when VLM_PROVIDER=openai).
#
# Note: some scraped/leaked API docs mention a `thinking="medium"` kwarg
# (gpt-5.5-style prompt rewriting). The Python SDK rejects it as an
# unexpected keyword — don't add it back without checking the SDK source.
MODEL = "gpt-image-2"
DISPLAY_NAME = "openai/gpt-image-2"

# Rough cost for high-quality 1536x1024 — tune as real billing data lands.
COST = 0.10

PARAMS = {
    "size": "1536x1024",
    "quality": "high",
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

    def __init__(self, name: str = DISPLAY_NAME):
        self.name = name
        self._cost = COST
        self.strategy = "distill"

    @property
    def cost(self) -> float:
        return self._cost

    @property
    def short_name(self) -> str:
        return self.name

    async def generate(self, prompt: str) -> str:
        logger.info(f"Using OpenAI image model: {self.name}")
        result = await _client.images.generate(
            model=MODEL,
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

    There's only one OpenAI image model surface to support, so model_name is
    accepted for interface symmetry but only affects the display label.
    """
    return ImageModel(model_name or DISPLAY_NAME)
