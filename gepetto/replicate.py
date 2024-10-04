import json
import requests
import replicate

async def generate_image(prompt, model="black-forest-labs/flux-schnell", aspect_ratio="1:1", output_format="webp", output_quality=90):
    output = await replicate.async_run(
        model,
        input={
            "prompt": prompt,
            "num_outputs": 1,
            "aspect_ratio": aspect_ratio,
            "output_format": output_format,
            "output_quality": output_quality,
            "prompt_upsampling": True,
            "disable_safety_checker": True,
        }
    )
    image_url = output[0]
    return image_url
