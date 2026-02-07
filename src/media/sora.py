import os

import replicate

from src.media.replicate import _extract_url


async def generate_video(prompt, model="openai/sora-2", seconds=4):
    input = {
        "prompt": prompt,
        "seconds": seconds,
        "openai_api_key": os.getenv("OPENAI_API_KEY")
    }
    output = await replicate.async_run(
        model,
        input=input
    )
    cost = seconds * 0.10
    video_url = _extract_url(output)

    return video_url, model, cost
