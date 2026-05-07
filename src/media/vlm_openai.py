"""OpenAI vision-language caption helper.

Same contract as src/media/vlm.py (Replicate/Gemini): given an image URL or
local file path, return {description, themes, style, reasoning}.

Used after image generation to extract themes/reasoning from what actually
got drawn — particularly relevant when the image came from openai_direct,
which returns a local path rather than a CDN URL.
"""

import base64
import json
import logging
import mimetypes
import os

from openai import AsyncOpenAI


logger = logging.getLogger(__name__)

MODEL = os.getenv("VLM_OPENAI_MODEL", "gpt-4.1")

CAPTION_PROMPT = """Look at this image carefully.

Return a JSON object (and nothing else — no markdown fence, no prose before
or after) with exactly these keys:

{
  "description": "a 1-2 sentence plain-English description of what the image shows",
  "themes": ["4-8 short theme tags covering subject, mood, artistic style, palette"],
  "style": "a short phrase naming the artistic style or medium",
  "reasoning": "one sentence on the emotional or narrative hook of the image"
}
"""

EMPTY_CAPTION = {"description": "", "themes": [], "style": "", "reasoning": ""}

_client = AsyncOpenAI()


def _strip_fences(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


def _to_image_input(image_url_or_path: str) -> str:
    """Return a value suitable for the Responses API `image_url` field.

    Remote URLs pass through. Local paths are read and base64-encoded into a
    data URL so we don't need to host the file anywhere.
    """
    if image_url_or_path.startswith(("http://", "https://", "data:")):
        return image_url_or_path

    mime, _ = mimetypes.guess_type(image_url_or_path)
    if not mime:
        mime = "image/png"
    with open(image_url_or_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


async def caption_image(image_url_or_path: str) -> dict:
    """Caption an image using the OpenAI Responses API.

    Returns a fresh dict with the same shape as vlm.EMPTY_CAPTION. Any
    failure (network, file read, JSON parse) logs and returns empty so the
    caller can still post the image.
    """
    if not image_url_or_path:
        return dict(EMPTY_CAPTION)

    try:
        image_input = _to_image_input(image_url_or_path)
    except OSError as e:
        logger.warning(f"VLM (openai) could not read image at {image_url_or_path!r}: {e}")
        return dict(EMPTY_CAPTION)

    try:
        response = await _client.responses.create(
            model=MODEL,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": CAPTION_PROMPT},
                        {"type": "input_image", "image_url": image_input},
                    ],
                }
            ],
        )
    except Exception as e:
        logger.warning(f"VLM (openai) call failed: {type(e).__name__}: {e}")
        return dict(EMPTY_CAPTION)

    raw = getattr(response, "output_text", "") or ""
    if not raw:
        logger.warning("VLM (openai) returned no output_text")
        return dict(EMPTY_CAPTION)

    try:
        parsed = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as e:
        logger.warning(f"VLM (openai) returned non-JSON output ({e}): {raw[:200]!r}")
        return dict(EMPTY_CAPTION)

    return {
        "description": parsed.get("description", ""),
        "themes": parsed.get("themes", []) or [],
        "style": parsed.get("style", ""),
        "reasoning": parsed.get("reasoning", ""),
    }
