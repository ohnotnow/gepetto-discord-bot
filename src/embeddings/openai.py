"""OpenAI embeddings provider."""

import os
from openai import AsyncOpenAI

from .base import BaseEmbeddings
from .response import EmbeddingsResponse


DEFAULT_MODEL = "text-embedding-3-small"


class OpenAIEmbeddings(BaseEmbeddings):
    """OpenAI embeddings using the openai SDK."""

    def __init__(self, model: str = None):
        model = model or os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)
        super().__init__(model)
        self._client = AsyncOpenAI()  # Uses OPENAI_API_KEY from env

    async def embed(self, text: str) -> EmbeddingsResponse:
        """Generate embedding using OpenAI API."""
        response = await self._client.embeddings.create(
            input=text,
            model=self.model
        )

        return EmbeddingsResponse(
            vector=response.data[0].embedding,
            tokens=response.usage.total_tokens,
            model=self.model
        )
