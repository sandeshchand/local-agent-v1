from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from local_agent.app.bootstrap import bootstrap_app


Requirement = str | list[str]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def alternatives(requirement: Requirement) -> list[str]:
    if isinstance(requirement, list):
        return [item for item in requirement if isinstance(item, str)]
    return [requirement]


def requirement_label(requirement: Requirement) -> str:
    return " / ".join(alternatives(requirement))


def contains_any(text: str, requirement: Requirement) -> bool:
    normalized_text = normalize(text)
    compact_text = compact(text)
    for phrase in alternatives(requirement):
        if not phrase:
            continue
        normalized_phrase = normalize(phrase)
        if re.fullmatch(r"[a-z0-9][a-z0-9-]{1,12}", normalized_phrase):
            if re.search(rf"\b{re.escape(normalized_phrase)}\b", normalized_text):
                return True
            continue
        if normalized_phrase in normalized_text or compact(phrase) in compact_text:
            return True
    return False


def citation_count(answer: str) -> int:
    return len(set(re.findall(r"\[(\d+)\]", answer)))


def top_routed_doc(response: dict[str, Any]) -> str:
    for step in response.get("steps", []):
        if step.get("type") != "retrieve":
            continue
        routed_docs = step.get("routed_docs") or []
        if routed_docs:
            return str(routed_docs[0].get("title") or "")
    return ""


def routed_docs(response: dict[str, Any]) -> list[dict[str, Any]]:
    for step in response.get("steps", []):
        if step.get("type") == "retrieve":
            return step.get("routed_docs") or []
    return []


def citation_titles(response: dict[str, Any]) -> list[str]:
    return [
        str(item.get("title") or "")
        for item in response.get("citations", [])
        if item.get("title")
    ]


def doc_match(expected_title: str, response: dict[str, Any]) -> bool:
    if not expected_title:
        return True
    expected = normalize(expected_title)
    candidates = [top_routed_doc(response), *citation_titles(response)]
    return any(expected in normalize(candidate) for candidate in candidates)


def verification_is_ok(response: dict[str, Any]) -> bool:
    verification = response.get("verification") or {}
    return verification.get("status") == "verified"


def score_item(gold: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    answer = response.get("answer") or ""
    must_have = gold.get("must_have", [])
    should_have = gold.get("should_have", [])
    must_not_have = gold.get("must_not_have", [])

    matched_must = [requirement_label(item) for item in must_have if contains_any(answer, item)]
    missing_must = [requirement_label(item) for item in must_have if not contains_any(answer, item)]
    matched_should = [requirement_label(item) for item in should_have if contains_any(answer, item)]
    triggered_bad = [requirement_label(item) for item in must_not_have if contains_any(answer, item)]

    fact_score = 5.0 * (len(matched_must) / max(1, len(must_have)))
    optional_score = 1.0 * (len(matched_should) / max(1, len(should_have))) if should_have else 1.0
    citation_score = 1.0 if citation_count(answer) > 0 and response.get("citations") else 0.0
    routing_score = 1.0 if doc_match(gold.get("expected_doc_title", ""), response) else 0.0
    verifier_score = 1.0 if verification_is_ok(response) else 0.0

    focus_score = 1.0
    if triggered_bad:
        focus_score -= 0.75
    if len(answer.split()) > gold.get("max_words", 220):
        focus_score -= 0.25
    if "does not contain enough information" in normalize(answer):
        focus_score = 0.0
    focus_score = max(0.0, focus_score)

    total = round(
        fact_score
        + optional_score
        + citation_score
        + routing_score
        + verifier_score
        + focus_score,
        2,
    )

    return {
        "id": gold["id"],
        "doc": gold.get("doc"),
        "question": gold["question"],
        "score": total,
        "fact_score": round(fact_score, 2),
        "optional_score": round(optional_score, 2),
        "citation_score": round(citation_score, 2),
        "routing_score": round(routing_score, 2),
        "verifier_score": round(verifier_score, 2),
        "focus_score": round(focus_score, 2),
        "matched_must_have": matched_must,
        "missing_must_have": missing_must,
        "matched_should_have": matched_should,
        "triggered_must_not_have": triggered_bad,
        "expected_doc_title": gold.get("expected_doc_title", ""),
        "top_routed_doc": top_routed_doc(response),
        "verification": response.get("verification") or {},
        "answer": answer,
        "citations": [
            {
                "rank": index,
                "title": item.get("title"),
                "section": item.get("section_title"),
                "page": item.get("page_number"),
                "pages": item.get("page_numbers"),
                "chunk_id": item.get("chunk_id"),
            }
            for index, item in enumerate(response.get("citations", []), start=1)
        ],
        "routed_docs": [
            {
                "rank": index,
                "title": item.get("title"),
                "routing_score": item.get("routing_score", 0.0),
            }
            for index, item in enumerate(routed_docs(response), start=1)
        ],
    }


def run_eval(eval_path: Path, output_path: Path) -> dict[str, Any]:
    deps = bootstrap_app(".env")
    items = json.loads(eval_path.read_text(encoding="utf-8"))
    report_items: list[dict[str, Any]] = []

    try:
        for gold in items:
            response = deps.orchestrator.handle_query(
                gold["question"],
                session_id=f"multi-doc-eval-{gold['id']}",
            )
            report_items.append(score_item(gold, response))
    finally:
        deps.sqlite_store.close()
        if deps.qdrant_store.client is not None:
            deps.qdrant_store.client.close()

    average = round(
        sum(item["score"] for item in report_items) / max(1, len(report_items)),
        2,
    )
    pass_count = sum(1 for item in report_items if item["score"] >= 8.0)
    report = {
        "average_score": average,
        "pass_threshold": 8.0,
        "pass_count": pass_count,
        "total_count": len(report_items),
        "items": report_items,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate multi-document RAG answer quality.")
    parser.add_argument("--eval-file", default="benchmarks/gold_qa/eval_multi_doc_rag.json")
    parser.add_argument("--output", default="var/logs/rag_quality_report.json")
    parser.add_argument(
        "--ids",
        default="",
        help="Comma-separated eval item ids to run, useful for quick targeted checks.",
    )
    parser.add_argument(
        "--fail-under-average",
        type=float,
        default=None,
        help="Exit with code 1 when the average score is below this value.",
    )
    parser.add_argument(
        "--fail-under-item",
        type=float,
        default=None,
        help="Exit with code 1 when any individual question score is below this value.",
    )
    args = parser.parse_args()

    if args.ids:
        source_path = Path(args.eval_file)
        output_path = Path(args.output)
        selected_ids = {item.strip() for item in args.ids.split(",") if item.strip()}
        source_items = json.loads(source_path.read_text(encoding="utf-8"))
        filtered_items = [item for item in source_items if item.get("id") in selected_ids]
        temp_path = output_path.parent / ".tmp_selected_eval.json"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(json.dumps(filtered_items, indent=2), encoding="utf-8")
        try:
            report = run_eval(temp_path, output_path)
        finally:
            temp_path.unlink(missing_ok=True)
    else:
        report = run_eval(Path(args.eval_file), Path(args.output))
    print(f"Average RAG quality score: {report['average_score']}/10")
    print(f"Passed: {report['pass_count']}/{report['total_count']} at >= {report['pass_threshold']}/10")
    for item in report["items"]:
        print(f"{item['id']}: {item['score']}/10")
        if item["routing_score"] == 0:
            print(f"  wrong doc: {item['top_routed_doc']}")
        if item["missing_must_have"]:
            print(f"  missing: {item['missing_must_have']}")
        if item["triggered_must_not_have"]:
            print(f"  unwanted: {item['triggered_must_not_have']}")
        if item["verifier_score"] == 0:
            print(f"  verifier: {item['verification']}")

    failed = False
    if args.fail_under_average is not None and report["average_score"] < args.fail_under_average:
        print(
            f"FAILED: average score {report['average_score']}/10 is below "
            f"{args.fail_under_average}/10"
        )
        failed = True
    if args.fail_under_item is not None:
        low_items = [
            item
            for item in report["items"]
            if item["score"] < args.fail_under_item
        ]
        if low_items:
            failed_ids = ", ".join(item["id"] for item in low_items)
            print(f"FAILED: these items are below {args.fail_under_item}/10: {failed_ids}")
            failed = True
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
