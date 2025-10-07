import json
import requests
import replicate
import random
import os
from openai import OpenAI

async def generate_video(prompt, model="openai/sora-2"):
    input = {
        "prompt": prompt,
        "seconds": 8,
        "openai_api_key": os.getenv("OPENAI_API_KEY")
    }
    output = await replicate.async_run(
        model,
        input=input
    )
    cost = 0.40

    if isinstance(output, list):
        video_url = output[0]
    else:
        video_url = output

    return video_url, model, cost
