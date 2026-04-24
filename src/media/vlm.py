"""Vision-language model caption helper.

Used after an image is generated to extract themes/reasoning from what
actually got drawn (rather than what we asked for). This preserves the
previous-themes dedup loop and the "chosen themes" UX when using the
"direct" image pipeline, which skips the LLM-prompt-distillation step.

Runs google/gemini-3-flash on Replicate. Cost is well under 1p per call.
Typical latency ~5s when passing a public URL (which is the real-world
case — image providers return CDN URLs).
"""

import json
import logging

import replicate as replicate_client


logger = logging.getLogger(__name__)

MODEL = "google/gemini-3-flash"

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


def _strip_fences(raw: str) -> str:
    """Defensively strip ```json ... ``` fences if the model adds them."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


async def caption_image(image_url: str) -> dict:
    """Caption an image and return {description, themes, style, reasoning}.

    Any failure (network, rate limit, JSON parse) is caught and logged —
    the caller gets an empty-fields dict back so the image can still be
    posted. The dedup loop will just miss one datapoint.
    """
    if not image_url:
        return dict(EMPTY_CAPTION)

    chunks: list[str] = []
    try:
        # async_stream returns a coroutine that resolves to an async iterator,
        # hence the explicit await before iterating.
        stream = await replicate_client.async_stream(
            MODEL,
            input={
                "prompt": CAPTION_PROMPT,
                "images": [image_url],
                "temperature": 0.4,
                "thinking_level": "low",
                "max_output_tokens": 2048,
            },
        )
        async for event in stream:
            chunks.append(str(event))
    except Exception as e:
        logger.warning(f"VLM caption call failed: {type(e).__name__}: {e}")
        return dict(EMPTY_CAPTION)

    raw = "".join(chunks)
    try:
        parsed = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as e:
        logger.warning(f"VLM caption returned non-JSON output ({e}): {raw[:200]!r}")
        return dict(EMPTY_CAPTION)

    return {
        "description": parsed.get("description", ""),
        "themes": parsed.get("themes", []) or [],
        "style": parsed.get("style", ""),
        "reasoning": parsed.get("reasoning", ""),
    }
