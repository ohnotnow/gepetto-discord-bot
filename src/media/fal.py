import fal_client
import random


# Model configurations: prefix -> (default_model, cost, base_params, in_pool)
# FAL model IDs use the "fal-ai/" prefix and different paths from Replicate.
# Set in_pool=True to include a model in the random selection pool.
MODEL_CONFIGS = {
    "fal-ai/flux-pro": (
        "fal-ai/flux-pro/v1.1-ultra",
        0.04,
        {"image_size": "square_hd", "output_format": "png", "safety_tolerance": "5"},
        True,
    ),
    "fal-ai/flux/": (
        "fal-ai/flux/dev",
        0.025,
        {"image_size": "square_hd", "output_format": "png"},
        False,
    ),
    "fal-ai/flux-schnell": (
        "fal-ai/flux/schnell",
        0.003,
        {"image_size": "square_hd", "output_format": "png"},
        False,
    ),
    "fal-ai/recraft": (
        "fal-ai/recraft-v3",
        0.04,
        {"image_size": {"width": 1536, "height": 768}, "style": "any", "output_format": "png"},
        True,
    ),
    "fal-ai/bytedance/seedream/v5": (
        "fal-ai/bytedance/seedream/v5/lite/text-to-image",
        0.035,
        {"image_size": "auto_2K", "num_images": 1, "max_images": 1, "enable_safety_checker": False, "enhance_prompt_mode": "standard"},
        True,
    ),
    "fal-ai/bytedance/seedream": (
        "fal-ai/bytedance/seedream/v4.5/text-to-image",
        0.04,
        {"image_size": "landscape_4_3", "enable_safety_checker": False},
        False,
    ),
    "fal-ai/nano-banana": (
        "fal-ai/nano-banana-2",
        0.08,
        {"num_images": 1, "aspect_ratio": "4:3", "output_format": "png", "safety_tolerance": "6", "resolution": "2K"},
        True,
    ),
    "fal-ai/ideogram": (
        "fal-ai/ideogram/v3",
        0.06,
        {"aspect_ratio": "1:1"},
        False,
    ),
    "fal-ai/luma-photon": (
        "fal-ai/luma-photon",
        0.02,
        {"image_size": "square_hd", "output_format": "png"},
        False,
    ),
    "openai/gpt-image-2": (
        "openai/gpt-image-2",
        0.08,
        {"image_size": {"width": 1536, "height": 1024}, "quality": "high", "output_format": "png"},
        False,
    ),
}

# Default fallback config
DEFAULT_CONFIG = (
    "fal-ai/flux/schnell",
    0.003,
    {"image_size": "square_hd", "output_format": "png"},
    False,
)

_client = fal_client.AsyncClient()


def _extract_url(result: dict) -> str:
    """Extract the image URL from a FAL response.

    FAL returns {"images": [{"url": "...", ...}]} for image models.
    """
    return result["images"][0]["url"]


class ImageModel:
    """A simple image generation model wrapper — same interface as replicate.ImageModel."""

    def __init__(self, name: str, params: dict, cost: float):
        self.name = name
        self._params = params
        self._cost = cost

    @property
    def cost(self) -> float:
        return self._cost

    @property
    def short_name(self) -> str:
        """Model name without any trailing version hash."""
        return self.name.split(":")[0]

    async def generate(self, prompt: str) -> str:
        """Generate an image and return the URL."""
        input_params = {"prompt": prompt, **self._params}
        print(f"Using FAL image model: {self.name} with cost: {self._cost}")
        result = await _client.subscribe(self.name, arguments=input_params)
        return _extract_url(result)


def _select_random_model() -> str:
    """Select a random model from the pool (those with in_pool=True)."""
    pool = [model for model, _cost, _params, in_pool in MODEL_CONFIGS.values() if in_pool]
    return random.choice(pool)


def get_image_model(model_name: str | None = None) -> ImageModel:
    """Factory: returns an ImageModel ready to generate images.

    If model_name is None, selects a random model from the pool.
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
