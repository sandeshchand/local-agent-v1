from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from local_agent.app import web
from local_agent.app.cli import run_ingest_status
from local_agent.storage.sqlite_store import SQLiteStore


def main() -> None:
    with TemporaryDirectory() as tmpdir:
        store = SQLiteStore(Path(tmpdir) / "ingestion_status_api.db")
        store.initialize()
        indexed_path = str((Path(tmpdir) / "indexed.pdf").resolve())
        failed_path = str((Path(tmpdir) / "failed.pdf").resolve())

        store.record_document_ingestion_completed(
            source_path=indexed_path,
            doc_id="doc-indexed",
            title="Indexed Paper",
            status="indexed",
            checksum="checksum-indexed",
            page_count=4,
            chunk_count=7,
            parser_version="parser-v1",
            chunking_version="chunking-v1",
            embedding_model="embed-v1",
            chunk_size=900,
            chunk_overlap=120,
        )
        store.record_document_ingestion_failed(
            source_path=failed_path,
            error="No searchable text was extracted.",
            parser_version="parser-v1",
            chunking_version="chunking-v1",
            embedding_model="embed-v1",
            chunk_size=900,
            chunk_overlap=120,
        )

        original_get_sqlite_store = web.get_sqlite_store
        web.get_sqlite_store = lambda: store
        try:
            response = web.list_ingestion_status(limit=10)
            assert response.total == 2
            assert response.summary["indexed_count"] == 1
            assert response.summary["failed_count"] == 1
            assert {item.status for item in response.items} == {"indexed", "failed"}

            failed_response = web.list_ingestion_status(limit=10, status="failed")
            assert failed_response.total == 2
            assert failed_response.status == "failed"
            assert len(failed_response.items) == 1
            assert failed_response.items[0].source_path == failed_path
            assert "No searchable text" in failed_response.items[0].error

            output = StringIO()
            with redirect_stdout(output):
                run_ingest_status(
                    SimpleNamespace(sqlite_store=store),
                    limit=10,
                    status="failed",
                )
            rendered = output.getvalue()
            assert "failed=1" in rendered
            assert "No searchable text" in rendered
        finally:
            web.get_sqlite_store = original_get_sqlite_store
            store.close()

    print("Ingestion status API smoke test passed.")


if __name__ == "__main__":
    main()
