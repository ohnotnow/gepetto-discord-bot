"""Response dataclass for embedding operations."""

from dataclasses import dataclass
from typing import List


@dataclass
class EmbeddingsResponse:
    """Response from an embeddings API call."""
    vector: List[float]  # The embedding vector
    tokens: int          # Token count used
    model: str           # Model that generated the embedding
