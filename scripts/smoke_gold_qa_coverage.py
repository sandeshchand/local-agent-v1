from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_gold_qa_coverage import build_report
from local_agent.storage.sqlite_store import SQLiteStore


def main() -> None:
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        sqlite_path = tmp_path / "app.db"
        qdrant_path = tmp_path / "qdrant"
        docs_dir = tmp_path / "documents"
        docs_dir.mkdir()
        indexed_pdf = docs_dir / "Indexed Guide.pdf"
        unindexed_pdf = docs_dir / "Unindexed Guide.pdf"
        indexed_pdf.write_text("placeholder", encoding="utf-8")
        unindexed_pdf.write_text("placeholder", encoding="utf-8")

        store = SQLiteStore(sqlite_path)
        try:
            store.initialize()
            store.upsert_document(
                doc_id="doc-indexed",
                source_path=str(indexed_pdf.resolve()),
                title="Indexed Guide",
                page_count=3,
                checksum="checksum-indexed",
                chunk_count=6,
                parser_version="parser-v1",
                chunking_version="chunking-v1",
                embedding_model="embed-v1",
            )
            store.upsert_document(
                doc_id="doc-missing",
                source_path=str((docs_dir / "Missing Coverage.pdf").resolve()),
                title="Missing Coverage",
                page_count=2,
                checksum="checksum-missing",
                chunk_count=4,
                parser_version="parser-v1",
                chunking_version="chunking-v1",
                embedding_model="embed-v1",
            )
        finally:
            store.close()

        env_file = tmp_path / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "OLLAMA_BASE_URL=http://127.0.0.1:11434",
                    "CHAT_MODEL=test-chat",
                    "EMBED_MODEL=test-embed",
                    f"QDRANT_PATH={qdrant_path}",
                    f"SQLITE_PATH={sqlite_path}",
                ]
            ),
            encoding="utf-8",
        )
        eval_path = tmp_path / "eval.json"
        eval_path.write_text(
            json.dumps(
                [
                    {
                        "id": "indexed_definition",
                        "doc": "indexed",
                        "question": "What is the indexed guide about?",
                        "expected_doc_title": "Indexed Guide",
                        "expected_answer": "It explains indexing.",
                        "must_have": ["indexing"],
                    },
                    {
                        "id": "indexed_steps",
                        "doc": "indexed",
                        "question": "What steps are listed?",
                        "expected_doc_title": "Indexed Guide",
                        "expected_answer": "It lists setup steps.",
                        "must_have": ["steps"],
                    },
                    {
                        "id": "orphan_item",
                        "doc": "orphan",
                        "question": "What is orphan?",
                        "expected_doc_title": "No Matching Title",
                        "expected_answer": "Nothing.",
                        "must_have": ["nothing"],
                    },
                ],
                indent=2,
            ),
            encoding="utf-8",
        )

        output_path = tmp_path / "coverage.json"
        report = build_report(
            eval_path=eval_path,
            documents_dir=docs_dir,
            env_file=env_file,
            output_path=output_path,
            min_items_per_doc=3,
            target_items_per_doc=5,
        )

        assert output_path.exists()
        assert report["summary"]["indexed_document_count"] == 2
        assert report["summary"]["raw_pdf_count"] == 2
        assert report["summary"]["unindexed_pdf_count"] == 1
        assert report["summary"]["missing_indexed_document_count"] == 1
        assert report["summary"]["undercovered_indexed_document_count"] == 1
        assert report["summary"]["unmatched_eval_item_count"] == 1

        docs_by_title = {item["title"]: item for item in report["documents"]}
        assert docs_by_title["Indexed Guide"]["coverage_status"] == "undercovered"
        assert docs_by_title["Indexed Guide"]["needed_for_minimum"] == 1
        assert docs_by_title["Missing Coverage"]["coverage_status"] == "missing"
        assert docs_by_title["Missing Coverage"]["needed_for_minimum"] == 3

    print("Gold QA coverage smoke test passed.")


if __name__ == "__main__":
    main()
