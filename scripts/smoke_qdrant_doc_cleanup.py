from __future__ import annotations

import tempfile

from local_agent.storage.qdrant_store import QdrantStore


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        qdrant_store = QdrantStore(tmp)
        try:
            qdrant_store.initialize_collection(vector_size=3)
            qdrant_store.upsert_chunks(
                [
                    {
                        "id": 1,
                        "vector": [0.1, 0.2, 0.3],
                        "payload": {"doc_id": "doc-a", "chunk_id": "a-1", "text": "alpha"},
                    },
                    {
                        "id": 2,
                        "vector": [0.3, 0.2, 0.1],
                        "payload": {"doc_id": "doc-b", "chunk_id": "b-1", "text": "beta"},
                    },
                ]
            )

            before = qdrant_store.search([0.1, 0.2, 0.3], doc_id="doc-a")
            assert len(getattr(before, "points", []) or []) == 1

            qdrant_store.delete_chunks_for_doc("doc-a")

            deleted = qdrant_store.search([0.1, 0.2, 0.3], doc_id="doc-a")
            remaining = qdrant_store.search([0.3, 0.2, 0.1], doc_id="doc-b")
            assert getattr(deleted, "points", []) == []
            assert len(getattr(remaining, "points", []) or []) == 1
        finally:
            qdrant_store.close()

    print("Qdrant document cleanup smoke test passed.")


if __name__ == "__main__":
    main()
