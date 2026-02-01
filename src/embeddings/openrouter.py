"""OpenRouter embeddings provider."""

import os
import aiohttp

from .base import BaseEmbeddings
from .response import EmbeddingsResponse


DEFAULT_MODEL = "openai/text-embedding-3-small"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/embeddings"


class OpenRouterEmbeddings(BaseEmbeddings):
    """OpenRouter embeddings using direct HTTP calls."""

    def __init__(self, model: str = None):
        model = model or os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)
        super().__init__(model)
        self._api_key = os.getenv("OPENROUTER_API_KEY")
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")

    async def embed(self, text: str) -> EmbeddingsResponse:
        """Generate embedding using OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "input": text,
            "model": self.model,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload
            ) as response:
                response.raise_for_status()
                data = await response.json()

        return EmbeddingsResponse(
            vector=data["data"][0]["embedding"],
            tokens=data.get("usage", {}).get("total_tokens", 0),
            model=self.model
        )
