from unittest.mock import AsyncMock, patch

import pytest

from src.media.fal import _extract_url, get_image_model, ImageModel, _select_random_model


def test_extract_url_from_fal_response():
    result = {"images": [{"url": "https://fal.media/image.png", "width": 1024, "height": 1024}]}
    assert _extract_url(result) == "https://fal.media/image.png"


def test_extract_url_picks_first_image():
    result = {"images": [
        {"url": "https://fal.media/first.png"},
        {"url": "https://fal.media/second.png"},
    ]}
    assert _extract_url(result) == "https://fal.media/first.png"


def test_get_image_model_returns_matching_config():
    model = get_image_model("fal-ai/flux-pro/v1.1-ultra")
    assert model.name == "fal-ai/flux-pro/v1.1-ultra"
    assert model.cost == 0.04


def test_get_image_model_falls_back_to_default():
    model = get_image_model("fal-ai/unknown-model")
    assert model.name == "fal-ai/unknown-model"
    assert model.cost == 0.003  # default config cost


def test_get_image_model_random_selection():
    model = get_image_model(None)
    assert model.name is not None
    assert model.cost > 0


def test_select_random_model_only_from_pool():
    from src.media.fal import MODEL_CONFIGS
    pool_models = [cfg["model"] for cfg in MODEL_CONFIGS.values() if cfg["in_pool"]]
    for _ in range(20):
        selected = _select_random_model()
        assert selected in pool_models


def test_short_name_strips_hash():
    model = ImageModel("fal-ai/flux-pro:abc123", {}, 0.04, "distill")
    assert model.short_name == "fal-ai/flux-pro"


def test_short_name_without_hash():
    model = ImageModel("fal-ai/flux-pro/v1.1-ultra", {}, 0.04, "distill")
    assert model.short_name == "fal-ai/flux-pro/v1.1-ultra"


@pytest.mark.asyncio
async def test_generate_calls_fal_subscribe():
    mock_client = AsyncMock()
    mock_client.subscribe.return_value = {
        "images": [{"url": "https://fal.media/generated.png"}]
    }

    model = ImageModel("fal-ai/flux-pro/v1.1-ultra", {"image_size": "square_hd"}, 0.04, "distill")

    with patch("src.media.fal._client", mock_client):
        url = await model.generate("a cat in space")

    assert url == "https://fal.media/generated.png"
    mock_client.subscribe.assert_called_once_with(
        "fal-ai/flux-pro/v1.1-ultra",
        arguments={"prompt": "a cat in space", "image_size": "square_hd"},
    )
