from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from local_agent.app.config import load_config
from local_agent.storage.sqlite_store import SQLiteStore


ROOT = Path(__file__).resolve().parents[1]


def compact_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def load_gold_items(eval_path: Path) -> list[dict[str, Any]]:
    items = json.loads(eval_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError(f"Expected {eval_path} to contain a JSON list")
    return [item for item in items if isinstance(item, dict)]


def discover_raw_pdfs(documents_dir: Path) -> list[dict[str, Any]]:
    if not documents_dir.exists():
        return []
    return [
        {
            "source_path": str(path.resolve()),
            "file_name": path.name,
        }
        for path in sorted(documents_dir.rglob("*.pdf"))
    ]


def item_matches_document(item: dict[str, Any], document: dict[str, Any]) -> bool:
    expected_title = str(item.get("expected_doc_title") or "")
    doc_label = str(item.get("doc") or "")
    title = str(document.get("title") or "")
    source_path = str(document.get("source_path") or "")
    file_stem = Path(source_path).stem

    expected_compact = compact_text(expected_title)
    title_compact = compact_text(title)
    source_compact = compact_text(source_path)
    stem_compact = compact_text(file_stem)
    label_compact = compact_text(doc_label)

    if expected_compact and (
        expected_compact in title_compact
        or expected_compact in source_compact
        or expected_compact in stem_compact
    ):
        return True
    if title_compact and title_compact in compact_text(expected_title):
        return True
    if label_compact and (
        label_compact in title_compact
        or label_compact in source_compact
    ):
        return True
    return False


def coverage_status(eval_count: int, min_items: int, target_items: int) -> str:
    if eval_count <= 0:
        return "missing"
    if eval_count < min_items:
        return "undercovered"
    if eval_count < target_items:
        return "minimum"
    return "target"


def document_family(source_path: str, title: str) -> str:
    source = source_path.lower()
    title_lower = title.lower()
    if "arxiv" in source or "arxiv" in title_lower:
        return "arxiv"
    if "medium" in source or "medium" in title_lower or "plain english" in title_lower:
        return "medium_article"
    if "pdf" in source:
        return "pdf"
    return "unknown"


def build_report(
    *,
    eval_path: Path,
    documents_dir: Path,
    env_file: Path,
    output_path: Path,
    min_items_per_doc: int,
    target_items_per_doc: int,
) -> dict[str, Any]:
    config = load_config(env_file)
    store = SQLiteStore(config.sqlite_path)
    store.initialize()

    try:
        indexed_documents = store.list_documents()
    finally:
        store.close()

    gold_items = load_gold_items(eval_path)
    raw_pdfs = discover_raw_pdfs(documents_dir)

    matched_item_ids: set[str] = set()
    document_reports: list[dict[str, Any]] = []
    for document in indexed_documents:
        matched_items = [
            item
            for item in gold_items
            if item_matches_document(item, document)
        ]
        for item in matched_items:
            if item.get("id"):
                matched_item_ids.add(str(item["id"]))

        eval_count = len(matched_items)
        status = coverage_status(
            eval_count,
            min_items=min_items_per_doc,
            target_items=target_items_per_doc,
        )
        needed_for_minimum = max(0, min_items_per_doc - eval_count)
        needed_for_target = max(0, target_items_per_doc - eval_count)
        document_reports.append(
            {
                "doc_id": document.get("doc_id", ""),
                "title": document.get("title", ""),
                "source_path": document.get("source_path", ""),
                "family": document_family(
                    str(document.get("source_path") or ""),
                    str(document.get("title") or ""),
                ),
                "page_count": document.get("page_count", 0),
                "chunk_count": document.get("chunk_count", 0),
                "indexed_at": document.get("indexed_at", ""),
                "eval_count": eval_count,
                "coverage_status": status,
                "needed_for_minimum": needed_for_minimum,
                "needed_for_target": needed_for_target,
                "eval_ids": [item.get("id", "") for item in matched_items],
            }
        )

    indexed_paths = {
        str(document.get("source_path") or "").lower(): str(document.get("doc_id") or "")
        for document in indexed_documents
    }
    raw_pdf_reports = []
    for pdf in raw_pdfs:
        source_path = pdf["source_path"]
        matched_doc_id = indexed_paths.get(source_path.lower(), "")
        raw_pdf_reports.append(
            {
                **pdf,
                "indexed": bool(matched_doc_id),
                "doc_id": matched_doc_id,
            }
        )

    unmatched_eval_items = [
        {
            "id": item.get("id", ""),
            "doc": item.get("doc", ""),
            "question": item.get("question", ""),
            "expected_doc_title": item.get("expected_doc_title", ""),
        }
        for item in gold_items
        if str(item.get("id", "")) not in matched_item_ids
    ]
    eval_group_counts: dict[str, int] = {}
    for item in gold_items:
        doc_key = str(item.get("doc") or "unknown")
        eval_group_counts[doc_key] = eval_group_counts.get(doc_key, 0) + 1

    missing_docs = [
        item
        for item in document_reports
        if item["coverage_status"] == "missing"
    ]
    undercovered_docs = [
        item
        for item in document_reports
        if item["coverage_status"] == "undercovered"
    ]
    minimum_docs = [
        item
        for item in document_reports
        if item["coverage_status"] == "minimum"
    ]
    unindexed_pdfs = [item for item in raw_pdf_reports if not item["indexed"]]

    recommendations = []
    if missing_docs:
        recommendations.append(
            f"Add at least {min_items_per_doc} gold QA items for each missing indexed document."
        )
    if undercovered_docs:
        recommendations.append(
            f"Bring undercovered documents up to at least {min_items_per_doc} gold QA items."
        )
    if minimum_docs:
        recommendations.append(
            f"Consider bringing minimum-covered documents up to {target_items_per_doc} items over time."
        )
    if unindexed_pdfs:
        recommendations.append(
            "Ingest raw PDFs that are not yet indexed before creating final gold QA coverage."
        )
    if unmatched_eval_items:
        recommendations.append(
            "Review unmatched eval items; their expected document title may not match any indexed title."
        )
    if not recommendations:
        recommendations.append("Gold QA coverage meets the configured minimum for indexed documents.")

    report = {
        "eval_file": str(eval_path),
        "documents_dir": str(documents_dir),
        "sqlite_path": str(config.sqlite_path),
        "output_path": str(output_path),
        "min_items_per_doc": min_items_per_doc,
        "target_items_per_doc": target_items_per_doc,
        "summary": {
            "indexed_document_count": len(indexed_documents),
            "raw_pdf_count": len(raw_pdfs),
            "unindexed_pdf_count": len(unindexed_pdfs),
            "eval_item_count": len(gold_items),
            "covered_indexed_document_count": len(document_reports) - len(missing_docs),
            "missing_indexed_document_count": len(missing_docs),
            "undercovered_indexed_document_count": len(undercovered_docs),
            "minimum_covered_indexed_document_count": len(minimum_docs),
            "target_covered_indexed_document_count": sum(
                1 for item in document_reports if item["coverage_status"] == "target"
            ),
            "unmatched_eval_item_count": len(unmatched_eval_items),
        },
        "eval_group_counts": dict(sorted(eval_group_counts.items())),
        "documents": document_reports,
        "raw_pdfs": raw_pdf_reports,
        "unmatched_eval_items": unmatched_eval_items,
        "recommendations": recommendations,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit gold QA coverage against indexed PDFs.")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Environment file used to locate SQLite.",
    )
    parser.add_argument(
        "--eval-file",
        default="benchmarks/gold_qa/eval_multi_doc_rag.json",
        help="Gold QA JSON file to audit.",
    )
    parser.add_argument(
        "--documents-dir",
        default="data/raw/documents",
        help="Raw PDF folder to compare with indexed documents.",
    )
    parser.add_argument(
        "--output",
        default="var/logs/gold_qa_coverage_report.json",
        help="JSON report output path.",
    )
    parser.add_argument(
        "--min-items-per-doc",
        type=int,
        default=3,
        help="Minimum acceptable gold QA items per indexed document.",
    )
    parser.add_argument(
        "--target-items-per-doc",
        type=int,
        default=5,
        help="Target gold QA items per indexed document.",
    )
    parser.add_argument(
        "--fail-under-minimum",
        action="store_true",
        help="Exit with code 1 when any indexed document has fewer than the minimum items.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = build_report(
            eval_path=(ROOT / args.eval_file).resolve(),
            documents_dir=(ROOT / args.documents_dir).resolve(),
            env_file=(ROOT / args.env_file).resolve(),
            output_path=(ROOT / args.output).resolve(),
            min_items_per_doc=max(1, args.min_items_per_doc),
            target_items_per_doc=max(args.min_items_per_doc, args.target_items_per_doc),
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    summary = report["summary"]
    print("Gold QA coverage audit complete")
    print(f"Indexed documents: {summary['indexed_document_count']}")
    print(f"Raw PDFs: {summary['raw_pdf_count']}")
    print(f"Gold QA items: {summary['eval_item_count']}")
    print(f"Missing coverage: {summary['missing_indexed_document_count']}")
    print(f"Undercovered: {summary['undercovered_indexed_document_count']}")
    print(f"Unmatched eval items: {summary['unmatched_eval_item_count']}")
    print(f"Report: {report['output_path']}")

    if args.fail_under_minimum and (
        summary["missing_indexed_document_count"] > 0
        or summary["undercovered_indexed_document_count"] > 0
    ):
        print("FAILED: one or more indexed documents are below minimum gold QA coverage.")
        sys.exit(1)


if __name__ == "__main__":
    main()
