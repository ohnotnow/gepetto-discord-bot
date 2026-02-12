import replicate as replicate_client
import random


# Model configurations: prefix -> (default_model, cost, base_params, in_pool)
# Set in_pool=True to include a model in the random selection pool.
MODEL_CONFIGS = {
    "black-forest-labs/": (
        "black-forest-labs/flux-2-pro",
        0.01,
        {"resolution": "1 MP", "aspect_ratio": "1:1", "input_images": [], "output_format": "webp", "output_quality": 80, "safety_tolerance": 5},
        True,
    ),
    "prunaai/": (
        "prunaai/z-image-turbo",
        0.005,
        {"guidance_scale": 0},
        True,
    ),
    "tencent/": (
        "tencent/hunyuan-image-3",
        0.08,
        {"disable_safety_checker": True},
        False,
    ),
    "qwen/": (
        "qwen/qwen-image",
        0.025,
        {},
        False,
    ),
    "bria/": (
        "bria/image-3.2",
        0.04,
        {},
        False,
    ),
    "openai/": (
        "openai/gpt-image-1.5",
        0.01,  # "low" quality
        {"quality": "low", "background": "auto", "moderation": "low", "aspect_ratio": "2:3", "output_format": "webp", "input_fidelity": "low", "number_of_images": 1, "output_compression": 90},
        False,
    ),
    "recraft-ai/": (
        "recraft-ai/recraft-v3",
        0.04,
        {"size": "1365x1024", "style": "any", "aspect_ratio": "1:1"},
        False,
    ),
    "ideogram-ai/": (
        "ideogram-ai/ideogram-v3",
        0.06,
        {"resolution": "None", "style_type": "None", "aspect_ratio": "1:1", "magic_prompt_option": "Auto"},
        False,
    ),
    "bytedance/seedream-3": (
        "bytedance/seedream-3",
        0.003,
        {"size": "regular", "width": 2048, "height": 2048, "aspect_ratio": "16:9", "guidance_scale": 2.5},
        False,
    ),
    "bytedance/seedream-4": (
        "bytedance/seedream-4",
        0.003,
        {"size": "2K", "width": 2048, "height": 2048, "max_images": 1, "image_input": [], "aspect_ratio": "4:3", "sequential_image_generation": "disabled"},
        True,
    ),
    "luma/": (
        "luma/photon-flash",
        0.02,
        {"aspect_ratio": "1:1", "image_reference_weight": 0.85, "style_reference_weight": 0.85},
        False,
    ),
    "google/nano-banana-pro": (
        "google/nano-banana-pro",
        0.14,
        {"resolution": "2K", "image_input": [], "aspect_ratio": "4:3", "output_format": "png", "safety_filter_level": "block_only_high"},
        False,
    ),
}

# Default fallback config (sana model format)
DEFAULT_CONFIG = (
    "nvidia/sana",
    0.003,
    {"width": 1024, "height": 1024, "guidance_scale": 5, "negative_prompt": "", "pag_guidance_scale": 2, "num_inference_steps": 18},
    False,
)


def _extract_url(output) -> str:
    """Extract a URL string from Replicate output.

    Replicate's SDK returns FileOutput objects instead of plain URLs.
    This normalises the output so the rest of the codebase always gets a string.
    """
    if isinstance(output, list):
        return str(output[0])
    return str(output)


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
        return _extract_url(output)


def _select_random_model() -> str:
    """Select a random model from the pool (those with in_pool=True)."""
    pool = [model for model, _cost, _params, in_pool in MODEL_CONFIGS.values() if in_pool]
    return random.choice(pool)


def get_image_model(model_name: str | None = None) -> ImageModel:
    """Factory: returns an ImageModel ready to generate images.

    If model_name is None, selects a random model based on env config.
    """
    if model_name is None:
        model_name = _select_random_model()

    # Find matching config by prefix
    for prefix, (default, cost, params, _) in MODEL_CONFIGS.items():
        if model_name.startswith(prefix):
            return ImageModel(model_name, params, cost)

    # Fallback to default config
    _, cost, params, _ = DEFAULT_CONFIG
    return ImageModel(model_name, params, cost)


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
    video_url = _extract_url(output)
    model_name = model.split(":")[0]
    return video_url, model_name, cost
