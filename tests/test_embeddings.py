"""Tests for the embeddings module."""

import os
import pytest
from unittest.mock import patch

from src.embeddings import (
    cosine_similarity,
    EmbeddingsResponse,
    get_embeddings_model,
)
from src.embeddings.openai import OpenAIEmbeddings
from src.embeddings.openrouter import OpenRouterEmbeddings


class TestCosineSimilarity:
    """Tests for the cosine_similarity function."""

    def test_identical_vectors_return_one(self):
        assert cosine_similarity([1, 0, 0], [1, 0, 0]) == 1.0
        assert cosine_similarity([0.5, 0.5], [0.5, 0.5]) == pytest.approx(1.0)

    def test_orthogonal_vectors_return_zero(self):
        assert cosine_similarity([1, 0, 0], [0, 1, 0]) == 0.0
        assert cosine_similarity([1, 0], [0, 1]) == 0.0

    def test_opposite_vectors_return_negative_one(self):
        assert cosine_similarity([1, 0], [-1, 0]) == -1.0

    def test_zero_magnitude_returns_zero(self):
        assert cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0
        assert cosine_similarity([1, 2, 3], [0, 0, 0]) == 0.0

    def test_mismatched_lengths_raises_value_error(self):
        with pytest.raises(ValueError, match="Vector length mismatch"):
            cosine_similarity([1, 0], [1, 0, 0])

    def test_similar_vectors(self):
        # Vectors at ~45 degrees should be ~0.707
        result = cosine_similarity([1, 0], [1, 1])
        assert 0.7 < result < 0.72


class TestEmbeddingsResponse:
    """Tests for the EmbeddingsResponse dataclass."""

    def test_creates_response(self):
        resp = EmbeddingsResponse(
            vector=[0.1, 0.2, 0.3],
            tokens=10,
            model="test-model"
        )
        assert resp.vector == [0.1, 0.2, 0.3]
        assert resp.tokens == 10
        assert resp.model == "test-model"


class TestGetEmbeddingsModel:
    """Tests for the factory function."""

    def test_raises_for_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            get_embeddings_model("unknown")

    def test_raises_for_empty_provider(self):
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            get_embeddings_model("")

    def test_returns_openai_embeddings(self):
        model = get_embeddings_model("openai")
        assert isinstance(model, OpenAIEmbeddings)

    def test_returns_openrouter_embeddings(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            model = get_embeddings_model("openrouter")
            assert isinstance(model, OpenRouterEmbeddings)

    def test_reads_from_env_var(self):
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "openai"}):
            model = get_embeddings_model()
            assert isinstance(model, OpenAIEmbeddings)


class TestOpenAIEmbeddings:
    """Tests for the OpenAI embeddings provider."""

    def test_default_model(self):
        embeddings = OpenAIEmbeddings()
        assert embeddings.model == "text-embedding-3-small"

    def test_custom_model(self):
        embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
        assert embeddings.model == "text-embedding-3-large"

    def test_env_model_override(self):
        with patch.dict(os.environ, {"EMBEDDING_MODEL": "text-embedding-ada-002"}):
            embeddings = OpenAIEmbeddings()
            assert embeddings.model == "text-embedding-ada-002"


class TestOpenRouterEmbeddings:
    """Tests for the OpenRouter embeddings provider."""

    def test_raises_without_api_key(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}, clear=False):
            # Need to remove the key entirely
            env = os.environ.copy()
            env.pop("OPENROUTER_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
                    OpenRouterEmbeddings()

    def test_default_model(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            embeddings = OpenRouterEmbeddings()
            assert embeddings.model == "openai/text-embedding-3-small"

    def test_custom_model(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            embeddings = OpenRouterEmbeddings(model="openai/text-embedding-3-large")
            assert embeddings.model == "openai/text-embedding-3-large"
