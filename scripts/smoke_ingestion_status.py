from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from local_agent.storage.sqlite_store import SQLiteStore


def main() -> None:
    with TemporaryDirectory() as tmp:
        store = SQLiteStore(Path(tmp) / "app.db")
        try:
            store.initialize()
            source_path = str((Path(tmp) / "paper.pdf").resolve())

            store.record_document_ingestion_started(
                source_path=source_path,
                parser_version="parser-v1",
                chunking_version="chunking-v1",
                embedding_model="embed-v1",
                chunk_size=900,
                chunk_overlap=120,
            )
            status_rows = store.list_document_ingestion_status()
            assert status_rows[0]["status"] == "running"

            store.upsert_document(
                doc_id="doc-old",
                source_path=source_path,
                title="Paper",
                page_count=3,
                checksum="checksum-old",
                parser_version="parser-v1",
                chunking_version="chunking-v1",
                embedding_model="embed-v1",
                chunk_size=900,
                chunk_overlap=120,
                chunk_count=4,
            )
            indexed = store.get_document_by_source_path(source_path)
            assert indexed is not None
            assert indexed["doc_id"] == "doc-old"
            assert indexed["ingestion_status"] == "indexed"
            assert indexed["chunk_count"] == 4

            store.upsert_document(
                doc_id="doc-new",
                source_path=source_path,
                title="Paper Updated",
                page_count=5,
                checksum="checksum-new",
                parser_version="parser-v2",
                chunking_version="chunking-v2",
                embedding_model="embed-v2",
                chunk_size=1000,
                chunk_overlap=80,
                chunk_count=6,
            )
            updated = store.get_document_by_source_path(source_path)
            assert updated is not None
            assert updated["doc_id"] == "doc-new"
            assert updated["title"] == "Paper Updated"
            assert updated["checksum"] == "checksum-new"
            assert updated["parser_version"] == "parser-v2"
            assert updated["chunk_size"] == 1000

            store.record_document_ingestion_completed(
                source_path=source_path,
                doc_id="doc-new",
                title="Paper Updated",
                status="indexed",
                checksum="checksum-new",
                page_count=5,
                chunk_count=6,
                parser_version="parser-v2",
                chunking_version="chunking-v2",
                embedding_model="embed-v2",
                chunk_size=1000,
                chunk_overlap=80,
            )
            status_rows = store.list_document_ingestion_status()
            assert status_rows[0]["status"] == "indexed"
            assert status_rows[0]["chunk_count"] == 6

            failed_path = str((Path(tmp) / "broken.pdf").resolve())
            store.record_document_ingestion_failed(
                source_path=failed_path,
                error="No searchable text was extracted.",
                parser_version="parser-v2",
                chunking_version="chunking-v2",
                embedding_model="embed-v2",
                chunk_size=1000,
                chunk_overlap=80,
            )
            status_by_path = {
                row["source_path"]: row
                for row in store.list_document_ingestion_status(limit=10)
            }
            assert status_by_path[failed_path]["status"] == "failed"
            assert "No searchable text" in status_by_path[failed_path]["error"]
        finally:
            store.close()

    print("Ingestion status smoke test passed.")


if __name__ == "__main__":
    main()
