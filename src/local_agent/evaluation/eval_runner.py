from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from local_agent.evaluation.eval_candidates import load_gold_eval_items


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


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")
    return cleaned or "eval_candidate"


def load_gold_eval_item(candidate_id: str, gold_eval_path: str | Path) -> dict[str, Any]:
    for item in load_gold_eval_items(gold_eval_path):
        if item.get("id") == candidate_id:
            return item
    raise LookupError(f"promoted eval item {candidate_id} does not exist")


def write_eval_result(
    candidate_id: str,
    result: dict[str, Any],
    *,
    output_dir: str | Path,
) -> str:
    output_path = Path(output_dir) / f"rag_quality_{_safe_filename(candidate_id)}_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "average_score": result["score"],
        "pass_threshold": 8.0,
        "pass_count": 1 if result["score"] >= 8.0 else 0,
        "total_count": 1,
        "items": [result],
    }
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(output_path)


def run_candidate_eval(
    orchestrator: Any,
    candidate_id: str,
    *,
    gold_eval_path: str | Path,
    output_dir: str | Path = "eval",
) -> dict[str, Any]:
    gold_item = load_gold_eval_item(candidate_id, gold_eval_path)
    response = orchestrator.handle_query(
        gold_item["question"],
        session_id=f"ui-eval-{candidate_id}",
    )
    result = score_item(gold_item, response)
    output_path = write_eval_result(candidate_id, result, output_dir=output_dir)
    return {
        "candidate_id": candidate_id,
        "score": result["score"],
        "passed": result["score"] >= 8.0,
        "output_path": output_path,
        "result": result,
    }
