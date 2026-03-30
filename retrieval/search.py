from __future__ import annotations

from app.ollama_client import  OllamaEmbeddingClient
from storage.qdrant_store import QdrantStore


class RetrievalService:
    def __init__(
            self,
            qdrant_store: QdrantStore,
            embedding_client: OllamaEmbeddingClient,
            top_k: int = 5,
            ) -> None:
        self.qdrant_store = qdrant_store
        self.embedding_client = embedding_client
        self.top_K = top_k


    def search(self, query: str) -> list[dict]:
        query_vector = self.embedding_client.embed(query)
        result = self.qdrant_store.search(query_vector=query_vector, limit=self.top_K)

        points = getattr(result, "points", []) or []

        items: list[dict] = []
        for point in points:
            payload = getattr(point, "payload", {}) or {}
            items.append(
                {
                    "id": getattr(point, "id",None),
                    "score": float(getattr(point,"score",0.0)),
                    "doc_id":payload.get("doc_id"),
                    "chunk_id":payload.get("chunk_id"),
                    "title":payload.get("title"),
                    "source_path":payload.get("source_path"),
                    "page_number":payload.get("page_number"),
                    "text":payload.get("text","")
                }
            )
        return items
