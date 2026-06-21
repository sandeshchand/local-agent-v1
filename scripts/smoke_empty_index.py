from __future__ import annotations

import tempfile

from local_agent.storage.qdrant_store import QdrantStore


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        qdrant_store = QdrantStore(tmp)
        try:
            result = qdrant_store.search(query_vector=[0.1, 0.2, 0.3], limit=3)

            assert getattr(result, "points", []) == []
        finally:
            qdrant_store.close()

    print("Empty index smoke test passed.")


if __name__ == "__main__":
    main()
