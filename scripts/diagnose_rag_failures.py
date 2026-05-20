from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def answer_word_count(item: dict[str, Any]) -> int:
    return len(str(item.get("answer") or "").split())


def classify_item(item: dict[str, Any], threshold: float) -> list[str]:
    categories: list[str] = []
    verification = item.get("verification") or {}
    issues = [str(issue) for issue in verification.get("issues") or []]
    issues_text = " ".join(issues).lower()
    answer = str(item.get("answer") or "")
    answer_lower = normalize(answer)

    if float(item.get("routing_score") or 0.0) <= 0:
        categories.append("routing")
    if float(item.get("citation_score") or 0.0) <= 0:
        categories.append("citation")
    if verification.get("status") != "verified":
        categories.append("verification")
    if "raw retrieval" in issues_text or "chunk metadata" in issues_text or has_raw_leak(answer):
        categories.append("raw_context_leak")
    if "drift" in issues_text or item.get("triggered_must_not_have"):
        categories.append("focus_or_drift")
    if "different prominent entity" in issues_text:
        categories.append("entity_drift")
    if "low overlap" in issues_text:
        categories.append("evidence_overlap")
    if item.get("missing_must_have"):
        categories.append("missing_required_facts")
    if "does not contain enough information" in answer_lower:
        categories.append("abstention")
    if answer_word_count(item) > 180:
        categories.append("too_verbose")
    if float(item.get("score") or 0.0) < threshold and not categories:
        categories.append("low_score_uncategorized")

    return list(dict.fromkeys(categories))


def has_raw_leak(answer: str) -> bool:
    answer_lower = answer.lower()
    raw_markers = [
        "[child chunk",
        "retrieved chunk",
        "chunk_id",
        "hybrid_score",
        "reranker_score",
        "title:",
        "section:",
        "score:",
        "text:",
        "follow publication",
        "get an email whenever",
        "by signing up",
    ]
    if any(marker in answer_lower for marker in raw_markers):
        return True
    code_declaration = re.search(r"\b(?:def|class|import|elif)\s+[\w_(]", answer)
    code_flow = re.search(r"\b(?:return|for|while|if)\s+[\w_(][^.!?]{0,120}[=()]", answer)
    if (code_declaration or code_flow) and len(answer.split()) > 120:
        return True
    return False


def recommendation_for(category: str) -> str:
    recommendations = {
        "routing": "Improve document routing or query rewriting before retrieval.",
        "citation": "Require valid citations in answer generation and fallback paths.",
        "verification": "Route verifier failures through deterministic extractive repair before accepting the answer.",
        "raw_context_leak": "Strip metadata/code dumps and prefer intent-shaped summaries over raw chunk windows.",
        "focus_or_drift": "Tighten focus-entity detection and section-boundary trimming.",
        "entity_drift": "Penalize answers centered on a different prominent entity than the query focus.",
        "evidence_overlap": "Improve evidence selection or answer coverage from top retrieved facts.",
        "missing_required_facts": "Increase generic evidence coverage for list, feature, limitation, reason, and pipeline questions.",
        "abstention": "Retry retrieval with query expansion before answering insufficient evidence.",
        "too_verbose": "Compress answers after synthesis and trim unrelated neighboring sections.",
        "low_score_uncategorized": "Inspect manually and add a new generic failure category if the pattern repeats.",
    }
    return recommendations.get(category, "Inspect this category and add a generic remediation.")


def diagnose(report: dict[str, Any], threshold: float) -> dict[str, Any]:
    items = report.get("items") or []
    failing_items = [
        item
        for item in items
        if float(item.get("score") or 0.0) < threshold
        or (item.get("verification") or {}).get("status") != "verified"
    ]

    category_counts: Counter[str] = Counter()
    items_by_category: dict[str, list[str]] = defaultdict(list)
    item_diagnostics: list[dict[str, Any]] = []

    for item in failing_items:
        categories = classify_item(item, threshold)
        for category in categories:
            category_counts[category] += 1
            items_by_category[category].append(str(item.get("id") or "unknown"))
        item_diagnostics.append(
            {
                "id": item.get("id"),
                "doc": item.get("doc"),
                "question": item.get("question"),
                "score": item.get("score"),
                "categories": categories,
                "verification_status": (item.get("verification") or {}).get("status"),
                "verification_issues": (item.get("verification") or {}).get("issues") or [],
                "missing_must_have": item.get("missing_must_have") or [],
                "triggered_must_not_have": item.get("triggered_must_not_have") or [],
                "answer_words": answer_word_count(item),
                "answer_preview": str(item.get("answer") or "")[:360],
            }
        )

    ordered_categories = [
        {
            "category": category,
            "count": count,
            "items": items_by_category[category],
            "recommendation": recommendation_for(category),
        }
        for category, count in category_counts.most_common()
    ]

    return {
        "source_average_score": report.get("average_score"),
        "source_pass_count": report.get("pass_count"),
        "source_total_count": report.get("total_count"),
        "diagnosis_threshold": threshold,
        "failing_or_flagged_count": len(failing_items),
        "category_summary": ordered_categories,
        "items": item_diagnostics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose RAG eval failures by generic failure category.")
    parser.add_argument("--report", default="eval/rag_quality_report.json")
    parser.add_argument("--output", default="eval/rag_failure_diagnosis.json")
    parser.add_argument("--threshold", type=float, default=8.0)
    args = parser.parse_args()

    report_path = Path(args.report)
    output_path = Path(args.output)
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    diagnosis = diagnose(report, args.threshold)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(diagnosis, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Diagnosed {diagnosis['failing_or_flagged_count']} failing/flagged items.")
    for category in diagnosis["category_summary"]:
        print(f"{category['category']}: {category['count']} item(s)")


if __name__ == "__main__":
    main()
