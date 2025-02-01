import json
import requests
import replicate

async def generate_image(prompt, model="black-forest-labs/flux-schnell", aspect_ratio="1:1", output_format="webp", output_quality=90, enhance_prompt=True):
    if model.startswith("black-forest-labs/"):
        input = {
            "prompt": prompt,
            "num_outputs": 1,
            "aspect_ratio": aspect_ratio,
            "output_format": output_format,
            "output_quality": output_quality,
            "prompt_upsampling": enhance_prompt,
            "disable_safety_checker": True,
        }
    elif model.startswith("bytedance/"):
            input={
            "width": 1024,
            "height": 1024,
            "prompt": prompt,
            "scheduler": "K_EULER",
            "num_outputs": 1,
            "guidance_scale": 0,
            "negative_prompt": "worst quality, low quality",
            "num_inference_steps": 4,
            "disable_safety_checker": True,
    }
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
    return image_url
