import replicate as replicate_client
import random
import os


# Model configurations: prefix -> (default_model, cost, base_params)
MODEL_CONFIGS = {
    "black-forest-labs/": (
        "black-forest-labs/flux-2-pro",
        0.01,
        {"resolution": "1 MP", "aspect_ratio": "1:1", "input_images": [], "output_format": "webp", "output_quality": 80, "safety_tolerance": 5}
    ),
    "prunaai/": (
        "prunaai/z-image-turbo",
        0.005,
        {"guidance_scale": 0}
    ),
    "tencent/": (
        "tencent/hunyuan-image-3",
        0.08,
        {"disable_safety_checker": True}
    ),
    "qwen/": (
        "qwen/qwen-image",
        0.025,
        {}
    ),
    "bria/": (
        "bria/image-3.2",
        0.04,
        {}
    ),
    "openai/": (
        "openai/gpt-image-1.5",
        0.01,  # "low" quality
        {"quality": "low", "background": "auto", "moderation": "low", "aspect_ratio": "1:1", "output_format": "webp", "input_fidelity": "low", "number_of_images": 1, "output_compression": 90}
    ),
    "recraft-ai/": (
        "recraft-ai/recraft-v3",
        0.04,
        {"size": "1365x1024", "style": "any", "aspect_ratio": "1:1"}
    ),
    "ideogram-ai/": (
        "ideogram-ai/ideogram-v3",
        0.06,
        {"resolution": "None", "style_type": "None", "aspect_ratio": "1:1", "magic_prompt_option": "Auto"}
    ),
    "bytedance/seedream-3": (
        "bytedance/seedream-3",
        0.003,
        {"size": "regular", "width": 2048, "height": 2048, "aspect_ratio": "16:9", "guidance_scale": 2.5}
    ),
    "bytedance/seedream-4": (
        "bytedance/seedream-4",
        0.003,
        {"size": "2K", "width": 2048, "height": 2048, "max_images": 1, "image_input": [], "aspect_ratio": "4:3", "sequential_image_generation": "disabled"}
    ),
    "luma/": (
        "luma/photon-flash",
        0.02,
        {"aspect_ratio": "1:1", "image_reference_weight": 0.85, "style_reference_weight": 0.85}
    ),
    "google/gemini": (
        "google/gemini-2.5-flash-image",
        0.039,
        {}
    ),
    "google/nano-banana-pro": (
        "google/nano-banana-pro",
        0.14,
        {"resolution": "2K", "image_input": [], "aspect_ratio": "4:3", "output_format": "png", "safety_filter_level": "block_only_high"}
    ),
    "minimax/": (
        "minimax/image-01",
        0.03,
        {"aspect_ratio": "1:1"}
    ),
    "reve/": (
        "reve/create",
        0.025,
        {}
    ),
}

# Default fallback config (sana model format)
DEFAULT_CONFIG = (
    "nvidia/sana",
    0.003,
    {"width": 1024, "height": 1024, "guidance_scale": 5, "negative_prompt": "", "pag_guidance_scale": 2, "num_inference_steps": 18}
)


class ImageModel:
    """A simple image generation model wrapper."""

    def __init__(self, name: str, params: dict, cost: float):
        self.name = name
        self._params = params
        self._cost = cost

    @property
    def cost(self) -> float:
        return self._cost

    @property
    def short_name(self) -> str:
        """Model name without the :hash suffix."""
        return self.name.split(":")[0]

    async def generate(self, prompt: str) -> str:
        """Generate an image and return the URL."""
        input_params = {"prompt": prompt, **self._params}
        print(f"Using image model: {self.name} with cost: {self._cost}")
        output = await replicate_client.async_run(self.name, input=input_params)
        if isinstance(output, list):
            return output[0]
        return output


def _select_random_model() -> str:
    """Select a random model based on environment configuration."""
    model_options = []

    if os.getenv("ENABLE_NANO_BANANA_PRO", None) is not None:
        model_options = ["google/nano-banana-pro"]

    if os.getenv("ENABLE_GPT_IMAGE", None) is not None:
        model_options.append("openai/gpt-image-1.5")

    if len(model_options) == 0:
        model_options.append("black-forest-labs/flux-2-pro")

    return random.choice(model_options)


def get_image_model(model_name: str | None = None) -> ImageModel:
    """Factory: returns an ImageModel ready to generate images.

    If model_name is None, selects a random model based on env config.
    """
    if model_name is None:
        model_name = _select_random_model()

    # Find matching config by prefix
    for prefix, (default, cost, params) in MODEL_CONFIGS.items():
        if model_name.startswith(prefix):
            return ImageModel(model_name, params, cost)

    # Fallback to default config
    _, cost, params = DEFAULT_CONFIG
    return ImageModel(model_name, params, cost)


# Legacy function for backwards compatibility during migration
async def generate_image(prompt, aspect_ratio="1:1", output_format="webp", output_quality=90, enhance_prompt=True, model=None):
    """Legacy wrapper - prefer using get_image_model() directly."""
    image_model = get_image_model(model)
    image_url = await image_model.generate(prompt)
    return image_url, image_model.short_name, image_model.cost

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
    output = await replicate_client.async_run(
        model,
        input=input
    )
    cost = 0.05
    if isinstance(output, list):
        video_url = output[0]
    else:
        video_url = output

    model_name = model.split(":")[0]
    return video_url, model_name, cost
