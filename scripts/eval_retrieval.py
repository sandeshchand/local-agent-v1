from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from app.bootstrap import bootstrap_app


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def keyword_hits(keywords: list[str], results: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    combined = normalize(" ".join(item.get("text") or "" for item in results))
    combined_compact = compact(combined)
    matched = [
        keyword
        for keyword in keywords
        if normalize(keyword) in combined or compact(keyword) in combined_compact
    ]
    missing = [keyword for keyword in keywords if keyword not in matched]
    return matched, missing


def page_hits(expected_pages: list[int], results: list[dict[str, Any]]) -> list[int]:
    found_pages: set[int] = set()
    for item in results:
        if item.get("page_numbers"):
            found_pages.update(int(page) for page in item["page_numbers"])
        elif item.get("page_number") is not None:
            found_pages.add(int(item["page_number"]))
    return [page for page in expected_pages if page in found_pages]


def score_item(item: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    expected_pages = item.get("expected_pages", [])
    expected_keywords = item.get("expected_keywords", [])
    matched_keywords, missing_keywords = keyword_hits(expected_keywords, results)
    matched_pages = page_hits(expected_pages, results)

    page_score = len(matched_pages) / max(1, len(expected_pages))
    keyword_score = len(matched_keywords) / max(1, len(expected_keywords))
    total = round((page_score * 4.0) + (keyword_score * 6.0), 2)

    return {
        "id": item["id"],
        "question": item["question"],
        "score": total,
        "page_score": round(page_score, 2),
        "keyword_score": round(keyword_score, 2),
        "matched_pages": matched_pages,
        "missing_pages": [page for page in expected_pages if page not in matched_pages],
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "retrieved": [
            {
                "rank": index,
                "chunk_id": result.get("chunk_id"),
                "page": result.get("page_number"),
                "section": result.get("section_title"),
                "source": result.get("source"),
                "neighbor_role": result.get("neighbor_role"),
                "hybrid_score": result.get("hybrid_score"),
                "reranker_score": result.get("reranker_score"),
                "preview": (result.get("text") or "")[:240],
            }
            for index, result in enumerate(results, start=1)
        ],
    }


def run_eval(eval_path: Path, output_path: Path) -> dict[str, Any]:
    deps = bootstrap_app(".env")
    items = json.loads(eval_path.read_text(encoding="utf-8"))
    report_items: list[dict[str, Any]] = []

    for item in items:
        retrieval_query = deps.orchestrator.query_rewriter.rewrite(item["question"])
        routed_docs = deps.orchestrator.doc_router.route(retrieval_query, top_n=3)
        candidate_doc_ids = [doc["doc_id"] for doc in routed_docs]
        results = deps.retrieval_service.search(
            query=retrieval_query,
            candidate_doc_ids=candidate_doc_ids,
        )
        scored = score_item(item, results)
        scored["retrieval_query"] = retrieval_query
        scored["routed_docs"] = [
            {
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "routing_score": doc.get("routing_score", 0.0),
            }
            for doc in routed_docs
        ]
        report_items.append(scored)

    average = round(
        sum(item["score"] for item in report_items) / max(1, len(report_items)),
        2,
    )
    report = {
        "average_score": average,
        "items": report_items,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality against expected pages and keywords.")
    parser.add_argument("--eval-file", default="test/eval_sora.json")
    parser.add_argument("--output", default="eval/retrieval_report.json")
    args = parser.parse_args()

    report = run_eval(Path(args.eval_file), Path(args.output))
    print(f"Average retrieval score: {report['average_score']}/10")
    for item in report["items"]:
        print(f"{item['id']}: {item['score']}/10")
        if item["missing_pages"]:
            print(f"  missing pages: {item['missing_pages']}")
        if item["missing_keywords"]:
            print(f"  missing keywords: {item['missing_keywords']}")


if __name__ == "__main__":
    main()
