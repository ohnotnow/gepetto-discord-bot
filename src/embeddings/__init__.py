"""
Embeddings module for generating text embeddings.

Usage:
    from src.embeddings import get_embeddings_model, EmbeddingsResponse

    model = get_embeddings_model()  # Uses EMBEDDING_PROVIDER env var
    response = await model.embed("some text")
    vector = response.vector
"""

import os

from .response import EmbeddingsResponse
from .base import BaseEmbeddings, cosine_similarity


def get_embeddings_model(provider: str = None) -> BaseEmbeddings:
    """
    Factory function to get an embeddings model instance.

    Args:
        provider: Provider name ("openai" or "openrouter").
                  If None, reads from EMBEDDING_PROVIDER env var.

    Returns:
        An embeddings model instance ready to use.

    Raises:
        ValueError: If provider is not recognised.
    """
    if provider is None:
        provider = os.getenv("EMBEDDING_PROVIDER", "").lower()

    if provider == "openai":
        from .openai import OpenAIEmbeddings
        return OpenAIEmbeddings()
    elif provider == "openrouter":
        from .openrouter import OpenRouterEmbeddings
        return OpenRouterEmbeddings()
    else:
        raise ValueError(
            f"Unknown embedding provider: '{provider}'. "
            "Set EMBEDDING_PROVIDER to 'openai' or 'openrouter'."
        )


__all__ = [
    "get_embeddings_model",
    "EmbeddingsResponse",
    "BaseEmbeddings",
    "cosine_similarity",
]
