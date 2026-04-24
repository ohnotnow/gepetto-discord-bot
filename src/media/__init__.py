import os

from . import images
from . import images_direct
from . import replicate
from . import sora
from . import vlm

__all__ = ['images', 'images_direct', 'replicate', 'sora', 'vlm', 'get_image_model']


def get_image_model(model_name=None):
    """Route to the correct image provider based on IMAGE_PROVIDER env var."""
    provider = os.getenv("IMAGE_PROVIDER", "replicate")
    if provider == "fal":
        from . import fal
        return fal.get_image_model(model_name)
    return replicate.get_image_model(model_name)
