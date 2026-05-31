from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from local_agent.storage.sqlite_store import SQLiteStore


def main() -> None:
    with TemporaryDirectory() as tmp:
        store = SQLiteStore(Path(tmp) / "app.db")
        try:
            store.initialize()
            for index in range(18):
                title = "Docker Guide" if index == 3 else f"Paper {index:02d}"
                store.upsert_document(
                    doc_id=f"doc-{index:02d}",
                    source_path=f"data/papers/paper-{index:02d}.pdf",
                    title=title,
                    page_count=index + 1,
                    checksum=f"checksum-{index:02d}",
                )

            assert store.count_documents() == 18
            first_page = store.list_documents(limit=5, offset=0)
            second_page = store.list_documents(limit=5, offset=5)
            assert len(first_page) == 5
            assert len(second_page) == 5
            assert {item["doc_id"] for item in first_page}.isdisjoint(
                {item["doc_id"] for item in second_page}
            )

            assert store.count_documents(search="docker") == 1
            docker_docs = store.list_documents(search="docker", limit=10)
            assert len(docker_docs) == 1
            assert docker_docs[0]["title"] == "Docker Guide"
        finally:
            store.close()

    print("Document library smoke test passed.")


if __name__ == "__main__":
    main()
