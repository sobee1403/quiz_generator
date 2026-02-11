"""
OpenAI Embeddings API로 텍스트 임베딩.
"""

from openai import OpenAI

from app.core.config import settings


class EmbeddingService:
    EMBEDDING_MODEL = "text-embedding-3-small"
    DIMENSIONS = 1536

    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.REQUEST_TIMEOUT,
        )

    def embed(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(
            model=self.EMBEDDING_MODEL,
            input=text,
            dimensions=self.DIMENSIONS,
        )
        return resp.data[0].embedding


embedding_service = EmbeddingService()
