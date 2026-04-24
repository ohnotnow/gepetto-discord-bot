import replicate as replicate_client
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
    "black-forest-labs/": {
        "model": "black-forest-labs/flux-2-max",
        "cost": 0.04,
        "params": {"resolution": "1 MP", "aspect_ratio": "1:1", "input_images": [], "output_format": "webp", "output_quality": 80, "safety_tolerance": 5},
        "in_pool": True,
        "strategy": "distill",
    },
    "prunaai/": {
        "model": "prunaai/z-image-turbo",
        "cost": 0.005,
        "params": {"guidance_scale": 0},
        "in_pool": True,
        "strategy": "distill",
    },
    "tencent/": {
        "model": "tencent/hunyuan-image-3",
        "cost": 0.08,
        "params": {"disable_safety_checker": True},
        "in_pool": False,
        "strategy": "direct",
    },
    "qwen/": {
        "model": "qwen/qwen-image",
        "cost": 0.025,
        "params": {},
        "in_pool": False,
        "strategy": "distill",
    },
    "bria/": {
        "model": "bria/image-3.2",
        "cost": 0.04,
        "params": {},
        "in_pool": False,
        "strategy": "distill",
    },
    "openai/": {
        "model": "openai/gpt-image-1.5",
        "cost": 0.01,  # "low" quality
        "params": {"quality": "low", "background": "auto", "moderation": "low", "aspect_ratio": "2:3", "output_format": "webp", "input_fidelity": "low", "number_of_images": 1, "output_compression": 90},
        "in_pool": False,
        "strategy": "direct",
    },
    "recraft-ai/": {
        "model": "recraft-ai/recraft-v4",
        "cost": 0.04,
        "params": {"size": "1536x768", "style": "any", "aspect_ratio": "2:1"},
        "in_pool": True,
        # Recraft caps prompts at 1000 chars — treat it as a plain diffusion
        # model and let the LLM distill down first.
        "strategy": "distill",
    },
    "ideogram-ai/": {
        "model": "ideogram-ai/ideogram-v3",
        "cost": 0.06,
        "params": {"resolution": "None", "style_type": "None", "aspect_ratio": "1:1", "magic_prompt_option": "Auto"},
        "in_pool": False,
        # Ideogram's magic_prompt expands short prompts internally — a long
        # instructional prompt fights that behaviour. Distill first.
        "strategy": "distill",
    },
    "bytedance/seedream-5-lite": {
        "model": "bytedance/seedream-5-lite",
        "cost": 0.03,
        "params": {"size": "2K", "max_images": 1, "image_input": [], "aspect_ratio": "4:3", "sequential_image_generation": "disabled", "output_format": "png"},
        "in_pool": True,
        "strategy": "direct",
    },
    "bytedance/seedream-5": {
        "model": "bytedance/seedream-5",
        "cost": 0.03,
        "params": {"size": "2K", "max_images": 1, "image_input": [], "aspect_ratio": "4:3", "sequential_image_generation": "disabled", "output_format": "png"},
        "in_pool": True,
        "strategy": "direct",
    },
    "reve/create": {
        "model": "reve/create",
        "cost": 0.025,
        "params": {
            "version": "latest",
            "aspect_ratio": "3:2"
        },
        "in_pool": True,
        # Reve is a diffusion model with prompt-length constraints — distill.
        "strategy": "distill",
    },
    "luma/": {
        "model": "luma/photon-flash",
        "cost": 0.02,
        "params": {"aspect_ratio": "1:1", "image_reference_weight": 0.85, "style_reference_weight": 0.85},
        "in_pool": False,
        "strategy": "distill",
    },
    "google/nano-banana-pro": {
        "model": "google/nano-banana-pro",
        "cost": 0.14,
        "params": {"resolution": "2K", "image_input": [], "aspect_ratio": "4:3", "output_format": "png", "safety_filter_level": "block_only_high"},
        "in_pool": False,
        "strategy": "direct",
    },
    "google/nano-banana-2": {
        "model": "google/nano-banana-2",
        "cost": 0.10,
        "params": {"resolution": "2K", "image_input": [], "aspect_ratio": "4:3", "output_format": "png", "safety_filter_level": "block_only_high"},
        "in_pool": True,
        "strategy": "direct",
    },
}

# Default fallback config (sana model format)
DEFAULT_CONFIG = {
    "model": "nvidia/sana",
    "cost": 0.003,
    "params": {"width": 1024, "height": 1024, "guidance_scale": 5, "negative_prompt": "", "pag_guidance_scale": 2, "num_inference_steps": 18},
    "in_pool": False,
    "strategy": "distill",
}


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
    pool = [cfg["model"] for cfg in MODEL_CONFIGS.values() if cfg["in_pool"]]
    return random.choice(pool)


def get_image_model(model_name: str | None = None) -> ImageModel:
    """Factory: returns an ImageModel ready to generate images.

    If model_name is None, selects a random model based on env config.
    """
    if model_name is None:
        model_name = _select_random_model()

    # Find matching config by prefix
    for prefix, cfg in MODEL_CONFIGS.items():
        if model_name.startswith(prefix):
            return ImageModel(model_name, cfg["params"], cfg["cost"], cfg["strategy"])

    return ImageModel(model_name, DEFAULT_CONFIG["params"], DEFAULT_CONFIG["cost"], DEFAULT_CONFIG["strategy"])


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
