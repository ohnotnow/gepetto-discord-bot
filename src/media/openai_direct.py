import base64
import os
import tempfile
import uuid

from openai import AsyncOpenAI


# The Responses API hosts the image_generation tool. ORCHESTRATOR_MODEL picks
# what to draw and how to interpret the prompt; the tool itself routes through
# OpenAI's gpt-image-* family to do the actual rendering. We surface the
# underlying model name (DISPLAY_NAME) for cost reporting since that's what
# users care about.
ORCHESTRATOR_MODEL = "gpt-5.5"
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


class ImageModel:
    """OpenAI image provider — same interface as replicate.ImageModel / fal.ImageModel.

    Unlike Replicate and FAL (which host the image and return a URL), OpenAI
    returns base64 bytes inline. We persist those to a temp file and return
    the local path; the platform adapters know how to send a local path.
    """

    def __init__(self, name: str = DISPLAY_NAME):
        self.name = name
        self._cost = COST
        self.strategy = "direct"

    @property
    def cost(self) -> float:
        return self._cost

    @property
    def short_name(self) -> str:
        return self.name

    async def generate(self, prompt: str) -> str:
        print(f"Using OpenAI image model: {self.name} via {ORCHESTRATOR_MODEL}")
        response = await _client.responses.create(
            model=ORCHESTRATOR_MODEL,
            input=prompt,
            tools=[{"type": "image_generation", **PARAMS}],
        )
        image_b64 = next(
            (out.result for out in response.output if out.type == "image_generation_call"),
            None,
        )
        if not image_b64:
            raise RuntimeError("OpenAI image_generation tool returned no image")

        path = os.path.join(
            tempfile.gettempdir(),
            f"openai_{uuid.uuid4().hex}.{PARAMS['output_format']}",
        )
        with open(path, "wb") as f:
            f.write(base64.b64decode(image_b64))
        return path


def get_image_model(model_name: str | None = None) -> ImageModel:
    """Factory: returns an ImageModel ready to generate images.

    There's only one OpenAI image model surface to support, so model_name is
    accepted for interface symmetry but only affects the display label.
    """
    return ImageModel(model_name or DISPLAY_NAME)
