"""Base class for embedding providers."""

import math
from abc import ABC, abstractmethod
from typing import List

from .response import EmbeddingsResponse


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    Pure Python implementation - no numpy dependency.
    Returns value between -1 and 1 (1 = identical, 0 = orthogonal).
    """
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} vs {len(b)}")

    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = math.sqrt(sum(x * x for x in a))
    magnitude_b = math.sqrt(sum(x * x for x in b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


class BaseEmbeddings(ABC):
    """Abstract base class for embedding providers."""

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    async def embed(self, text: str) -> EmbeddingsResponse:
        """
        Generate an embedding vector for the given text.

        Args:
            text: The text to embed

        Returns:
            EmbeddingsResponse with vector, token count, and model name
        """
        pass
