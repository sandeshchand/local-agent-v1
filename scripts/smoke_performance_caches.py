from __future__ import annotations

from typing import Any

from local_agent.llm.ollama_client import OllamaEmbeddingClient
from local_agent.retrieval.doc_router import DocumentRouter


class CountingEmbeddingClient(OllamaEmbeddingClient):
    def __init__(self, cache_size: int = 2) -> None:
        super().__init__(
            base_url="http://unused.local",
            model_name="test-embed",
            cache_size=cache_size,
        )
        self.embed_many_calls = 0

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        self.embed_many_calls += 1
        return [[float(len(text)), float(self.embed_many_calls)] for text in texts]


class FakeRoutingStore:
    def __init__(self) -> None:
        self.version = 1
        self.document_calls = 0
        self.chunk_calls = 0
        self.docs = [
            {
                "doc_id": "alpha",
                "title": "Alpha Operations Guide",
                "source_path": "data/alpha.pdf",
                "page_count": 2,
                "indexed_at": "2026-01-01 00:00:00",
                "section_titles": "Features",
            },
            {
                "doc_id": "beta",
                "title": "Beta Reference",
                "source_path": "data/beta.pdf",
                "page_count": 1,
                "indexed_at": "2026-01-01 00:00:00",
                "section_titles": "Overview",
            },
        ]
        self.chunks = {
            "alpha": [
                {
                    "section_title": "Features",
                    "text": "Alpha has routing cache support and fast repeated lookup features.",
                }
            ],
            "beta": [
                {
                    "section_title": "Overview",
                    "text": "Beta is a small reference document.",
                }
            ],
        }

    def routing_corpus_signature(self) -> tuple[Any, ...]:
        return ("fake", self.version)

    def list_documents_for_routing(self) -> list[dict[str, Any]]:
        self.document_calls += 1
        return [dict(doc) for doc in self.docs]

    def list_chunks_for_retrieval(self, doc_id: str | None = None) -> list[dict[str, str]]:
        self.chunk_calls += 1
        if doc_id is None:
            return [chunk for chunks in self.chunks.values() for chunk in chunks]
        return [dict(chunk) for chunk in self.chunks.get(doc_id, [])]


def assert_embedding_cache() -> None:
    client = CountingEmbeddingClient(cache_size=2)

    first = client.embed("same query")
    first[0] = -1.0
    second = client.embed("same query")

    assert client.embed_many_calls == 1
    assert second == [10.0, 1.0]

    client.embed("second query")
    client.embed("third query")
    client.embed("same query")

    assert client.embed_many_calls == 4


def assert_document_router_cache() -> None:
    store = FakeRoutingStore()
    router = DocumentRouter(sqlite_store=store)  # type: ignore[arg-type]

    first = router.route("alpha routing features", top_n=1)
    assert first[0]["doc_id"] == "alpha"
    assert store.document_calls == 1
    assert store.chunk_calls == 2

    second = router.route("alpha routing features", top_n=1)
    assert second[0]["doc_id"] == "alpha"
    assert store.document_calls == 1
    assert store.chunk_calls == 2

    store.version = 2
    router.route("alpha routing features", top_n=1)
    assert store.document_calls == 2
    assert store.chunk_calls == 4


def main() -> None:
    assert_embedding_cache()
    assert_document_router_cache()
    print("Performance cache smoke test passed.")


if __name__ == "__main__":
    main()
