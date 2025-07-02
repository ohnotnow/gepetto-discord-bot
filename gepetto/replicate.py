import json
import requests
import replicate
import random
import os

async def generate_image(prompt, model="black-forest-labs/flux-schnell", aspect_ratio="1:1", output_format="webp", output_quality=90, enhance_prompt=True):
    model_options = [
         "black-forest-labs/flux-1.1-pro",
         "black-forest-labs/flux-kontext-pro",
         "black-forest-labs/flux-kontext-dev",
        #  "bytedance/sdxl-lightning-4step:5599ed30703defd1d160a25a63321b4dec97101d98b4674bcc56e41f62f35637",
        #  "nvidia/sana:c6b5d2b7459910fec94432e9e1203c3cdce92d6db20f714f1355747990b52fa6",
        #  "luma/photon-flash",
        #  "google/imagen-3-fast",
        #  "recraft-ai/recraft-v3",
        #  "ideogram-ai/ideogram-v2a",
         "minimax/image-01",
        #  "google/imagen-3",
         "google/imagen-4",
        #  "bytedance/seedream-3",
    ]
    # if os.getenv("OPENAI_API_KEY", None) is not None:
    #     model_options.append("openai/gpt-image-1")
    # pick a random model from the list
    model = random.choice(model_options)
    print(f"Using model: {model}")
    cost = 0.003
    if model.startswith("black-forest-labs/"):
        input = {
            "prompt": prompt,
            "num_outputs": 1,
            "aspect_ratio": aspect_ratio,
            "output_format": output_format,
            "output_quality": output_quality,
            "prompt_upsampling": enhance_prompt,
            "disable_safety_checker": True,
            "output_format": "jpg",
        }
        cost = 0.04
    elif model.startswith("openai/"):
        input = {
            "prompt": prompt,
            "openai_api_key": os.getenv("OPENAI_API_KEY"),
            "moderation": "low",
        }
        cost = 0.001
    elif model.startswith("recraft-ai/"):
        input={
            "size": "1365x1024",
            "style": "any",
            "prompt": prompt,
            "aspect_ratio": aspect_ratio
        }
        cost = 0.04
    elif model.startswith("ideogram-ai/"):
        input={
            "prompt": prompt,
            "resolution": "None",
            "style_type": "None",
            "aspect_ratio": aspect_ratio,
            "magic_prompt_option": "Auto"
        }
        cost = 0.04
    elif model.startswith("bytedance/"):
        input={
            "width": 1024,
            "height": 1024,
            "prompt": prompt,
            "scheduler": "K_EULER",
        }
        cost = 0.003
    elif model.startswith("luma/"):
        input = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "image_reference_weight": 0.85,
            "style_reference_weight": 0.85
        }
        cost = 0.02
    elif model.startswith("google/"):
        input={
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "safety_filter_level": "block_only_high"
        }
        cost = 0.04
    elif model.startswith("minimax/"):
        input = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio
        }
        cost = 0.03
    else:
        # default to sana model format input parameters
        input = {
            "width": 1024,
            "height": 1024,
            "prompt": prompt,
            "guidance_scale": 5,
            "negative_prompt": "",
            "pag_guidance_scale": 2,
            "num_inference_steps": 18
        }
        cost = 0.003
    print(f"Generating image with model: {model}")
    output = await replicate.async_run(
        model,
        input=input,
        # use_file_output=False
    )
    if isinstance(output, list):
        image_url = output[0]
    else:
        image_url = output
    # strip any training :hash from the model name, eg nvidia/sana:c6b5d2b7459910fec94432e9e1203c3cdce92d6db20f714f1355747990b52fa6
    model_name = model.split(":")[0]
    return image_url, model_name, cost

async def generate_video(prompt, model="bytedance/seedance-1-lite"):
    input = {
        "prompt": prompt,
        "resolution": "480p",
        "duration": 5,
    }
    output = await replicate.async_run(
        model,
        input=input
    )
    cost = 0.01
    if isinstance(output, list):
        video_url = output[0]
    else:
        video_url = output
    # strip any training :hash from the model name, eg nvidia/sana:c6b5d2b7459910fec94432e9e1203c3cdce92d6db20f714f1355747990b52fa6
    model_name = model.split(":")[0]
    return video_url, model_name, cost
