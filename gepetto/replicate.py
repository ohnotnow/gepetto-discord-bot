import json
import requests
import replicate
import random
import os

async def generate_image(prompt, aspect_ratio="1:1", output_format="webp", output_quality=90, enhance_prompt=True):
    model_options = [
         "black-forest-labs/flux-1.1-pro",
         "black-forest-labs/flux-krea-dev",
         "bria/image-3.2",
         "google/imagen-4",
         "google/gemini-2.5-flash-image",
         "qwen/qwen-image",
        #  "bytedance/seedream-3",
        #  "ideogram-ai/ideogram-v3-balanced",
        #  "minimax/image-01",
        #  "black-forest-labs/flux-kontext-pro",
        #  "black-forest-labs/flux-kontext-dev", # seems to only work as an image->image model
        #  "bytedance/sdxl-lightning-4step:5599ed30703defd1d160a25a63321b4dec97101d98b4674bcc56e41f62f35637",
        #  "nvidia/sana:c6b5d2b7459910fec94432e9e1203c3cdce92d6db20f714f1355747990b52fa6",
        #  "luma/photon-flash",
        #  "google/imagen-3-fast",
        #  "recraft-ai/recraft-v3",
        #  "ideogram-ai/ideogram-v2a",
    ]
    if os.getenv("ENABLE_GPT_IMAGE", None) is not None:
        model_options.append("openai/gpt-image-1")
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
    elif model.startswith("qwen/"):
        input = {
            "prompt": prompt,
        }
        cost = 0.025
    elif model.startswith("bria/"):
        input = {
            "prompt": prompt,
        }
        cost = 0.04
    elif model.startswith("prunaai/"):
        input = {
            "prompt": prompt,
            "seed": -1,
        }
        cost = 0.02
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
        cost = 0.06
    elif model.startswith("bytedance/seedream-3"):
        input={
            "size": "regular",
            "width": 2048,
            "height": 2048,
            "prompt": prompt,
            "aspect_ratio": "16:9",
            "guidance_scale": 2.5
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
    elif model.startswith("google/gemini"):
        input={
            "prompt": prompt,
        }
        cost = 0.039
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

async def generate_video(prompt, model="wan-video/wan-2.2-t2v-fast"):
    input = {
        "prompt": prompt,
        "go_fast": True,
        "num_frames": 81,
        "resolution": "480p",
        "aspect_ratio": "16:9",
        "sample_shift": 12,
        "optimize_prompt": False,
        "frames_per_second": 16,
        "lora_scale_transformer": 1,
        "lora_scale_transformer_2": 1
    }
    output = await replicate.async_run(
        model,
        input=input
    )
    cost = 0.05
    if isinstance(output, list):
        video_url = output[0]
    else:
        video_url = output

    # strip any training :hash from the model name, eg nvidia/sana:c6b5d2b7459910fec94432e9e1203c3cdce92d6db20f714f1355747990b52fa6
    model_name = model.split(":")[0]
    return video_url, model_name, cost
