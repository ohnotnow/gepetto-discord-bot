import fal_client
import random


# Model configurations. Each entry is keyed by a prefix used to route a
# user-supplied model name back to its config, and contains:
#   model    — default model ID for this prefix
#   cost     — USD cost per image
#   params   — base input params merged with {"prompt": ...} at call time
#   in_pool  — True to include in the random-selection pool
#   strategy — "distill" for simple diffusion models that need a tight prompt
#              distilled by an LLM first, or "direct" for smart omni models
#              that cope well with our rich instructional prose directly.
MODEL_CONFIGS = {
    "fal-ai/flux-pro": {
        "model": "fal-ai/flux-pro/v1.1-ultra",
        "cost": 0.04,
        "params": {"image_size": "square_hd", "output_format": "png", "safety_tolerance": "5"},
        "in_pool": True,
        "strategy": "distill",
    },
    "fal-ai/flux/": {
        "model": "fal-ai/flux/dev",
        "cost": 0.025,
        "params": {"image_size": "square_hd", "output_format": "png"},
        "in_pool": False,
        "strategy": "distill",
    },
    "fal-ai/flux-schnell": {
        "model": "fal-ai/flux/schnell",
        "cost": 0.003,
        "params": {"image_size": "square_hd", "output_format": "png"},
        "in_pool": False,
        "strategy": "distill",
    },
    "fal-ai/recraft": {
        "model": "fal-ai/recraft-v3",
        "cost": 0.04,
        "params": {"image_size": {"width": 1536, "height": 768}, "style": "any", "output_format": "png"},
        "in_pool": True,
        # Recraft caps prompts at 1000 chars — distill first, don't stuff it
        # with a 3000-char direct instruction prompt.
        "strategy": "distill",
    },
    "fal-ai/bytedance/seedream/v5": {
        "model": "fal-ai/bytedance/seedream/v5/lite/text-to-image",
        "cost": 0.035,
        "params": {"image_size": "auto_2K", "num_images": 1, "max_images": 1, "enable_safety_checker": False, "enhance_prompt_mode": "standard"},
        "in_pool": True,
        "strategy": "direct",
    },
    "fal-ai/bytedance/seedream": {
        "model": "fal-ai/bytedance/seedream/v4.5/text-to-image",
        "cost": 0.04,
        "params": {"image_size": "landscape_4_3", "enable_safety_checker": False},
        "in_pool": False,
        "strategy": "direct",
    },
    "fal-ai/nano-banana": {
        "model": "fal-ai/nano-banana-2",
        "cost": 0.12,
        "params": {"num_images": 1, "aspect_ratio": "4:3", "output_format": "png", "safety_tolerance": "6", "resolution": "2K"},
        "in_pool": True,
        "strategy": "direct",
    },
    "fal-ai/ideogram": {
        "model": "fal-ai/ideogram/v3",
        "cost": 0.06,
        "params": {"aspect_ratio": "1:1"},
        "in_pool": False,
        "strategy": "distill",
    },
    "fal-ai/luma-photon": {
        "model": "fal-ai/luma-photon",
        "cost": 0.02,
        "params": {"image_size": "square_hd", "output_format": "png"},
        "in_pool": False,
        "strategy": "distill",
    },
    "openai/gpt-image-2": {
        "model": "openai/gpt-image-2",
        "cost": 0.17,
        "params": {"image_size": {"width": 1536, "height": 1024}, "quality": "medium", "output_format": "png"},
        "in_pool": False,
        "strategy": "direct",
    },
}

# Default fallback config
DEFAULT_CONFIG = {
    "model": "fal-ai/flux/schnell",
    "cost": 0.003,
    "params": {"image_size": "square_hd", "output_format": "png"},
    "in_pool": False,
    "strategy": "distill",
}

_client = fal_client.AsyncClient()


def _extract_url(result: dict) -> str:
    """Extract the image URL from a FAL response.

    FAL returns {"images": [{"url": "...", ...}]} for image models.
    """
    return result["images"][0]["url"]


class ImageModel:
    """A simple image generation model wrapper — same interface as replicate.ImageModel."""

    def __init__(self, name: str, params: dict, cost: float, strategy: str):
        self.name = name
        self._params = params
        self._cost = cost
        self.strategy = strategy

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
    pool = [cfg["model"] for cfg in MODEL_CONFIGS.values() if cfg["in_pool"]]
    return random.choice(pool)


def get_image_model(model_name: str | None = None) -> ImageModel:
    """Factory: returns an ImageModel ready to generate images.

    If model_name is None, selects a random model from the pool.
    """
    if model_name is None:
        model_name = _select_random_model()

    # Find matching config by prefix
    for prefix, cfg in MODEL_CONFIGS.items():
        if model_name.startswith(prefix):
            return ImageModel(model_name, cfg["params"], cfg["cost"], cfg["strategy"])

    return ImageModel(model_name, DEFAULT_CONFIG["params"], DEFAULT_CONFIG["cost"], DEFAULT_CONFIG["strategy"])
