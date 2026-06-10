from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local_agent.app.paths import EVAL_CANDIDATES_PATH, GOLD_EVAL_PATH
from local_agent.storage.sqlite_store import SQLiteStore


DEFAULT_CANDIDATES_PATH = EVAL_CANDIDATES_PATH
DEFAULT_GOLD_EVAL_PATH = GOLD_EVAL_PATH
_WRITE_LOCK = threading.RLock()


def parse_json_field(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def load_feedback_eval_candidates(path: str | Path = DEFAULT_CANDIDATES_PATH) -> list[dict[str, Any]]:
    candidate_path = Path(path)
    if not candidate_path.exists():
        return []
    raw = json.loads(candidate_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("feedback eval candidate file must contain a JSON list")
    return [item for item in raw if isinstance(item, dict)]


def write_feedback_eval_candidates(
    candidates: list[dict[str, Any]],
    path: str | Path = DEFAULT_CANDIDATES_PATH,
) -> None:
    candidate_path = Path(path)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = candidate_path.with_suffix(f"{candidate_path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(candidates, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temp_path.replace(candidate_path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_requirement_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    cleaned: list[Any] = []
    for item in value:
        if isinstance(item, list):
            alternatives = [_clean_text(part) for part in item if _clean_text(part)]
            if alternatives:
                cleaned.append(alternatives)
            continue
        text = _clean_text(item)
        if text:
            cleaned.append(text)
    return cleaned


def _candidate_index(candidates: list[dict[str, Any]], candidate_id: str) -> int:
    for index, candidate in enumerate(candidates):
        if candidate.get("id") == candidate_id:
            return index
    raise LookupError(f"eval candidate {candidate_id} does not exist")


def list_feedback_eval_candidates(
    path: str | Path = DEFAULT_CANDIDATES_PATH,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    candidates = load_feedback_eval_candidates(path)
    bounded_limit = max(1, min(limit, 100))
    return candidates[:bounded_limit]


def update_feedback_eval_candidate(
    candidate_id: str,
    updates: dict[str, Any],
    *,
    path: str | Path = DEFAULT_CANDIDATES_PATH,
) -> dict[str, Any]:
    editable_fields = {
        "doc",
        "expected_doc_title",
        "expected_answer",
        "must_have",
        "should_have",
        "must_not_have",
        "notes",
        "status",
    }
    candidate_path = Path(path)
    with _WRITE_LOCK:
        candidates = load_feedback_eval_candidates(candidate_path)
        index = _candidate_index(candidates, candidate_id)
        candidate = {**candidates[index]}
        for field, value in updates.items():
            if field not in editable_fields:
                continue
            if field in {"must_have", "should_have", "must_not_have"}:
                candidate[field] = _clean_requirement_list(value)
            elif field == "status":
                status = _clean_text(value) or "draft"
                if status not in {"draft", "reviewed", "promoted"}:
                    raise ValueError("status must be draft, reviewed, or promoted")
                candidate[field] = status
            else:
                candidate[field] = _clean_text(value)
        candidate["updated_at"] = _now()
        candidates[index] = candidate
        write_feedback_eval_candidates(candidates, candidate_path)
    return candidate


def load_gold_eval_items(path: str | Path = DEFAULT_GOLD_EVAL_PATH) -> list[dict[str, Any]]:
    eval_path = Path(path)
    if not eval_path.exists():
        return []
    raw = json.loads(eval_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("gold eval file must contain a JSON list")
    return [item for item in raw if isinstance(item, dict)]


def write_gold_eval_items(items: list[dict[str, Any]], path: str | Path = DEFAULT_GOLD_EVAL_PATH) -> None:
    eval_path = Path(path)
    eval_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = eval_path.with_suffix(f"{eval_path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(items, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temp_path.replace(eval_path)


def _gold_item_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    if not _clean_text(candidate.get("question")):
        raise ValueError("candidate question is required")
    if not _clean_text(candidate.get("expected_answer")):
        raise ValueError("expected_answer is required before promotion")
    if not _clean_requirement_list(candidate.get("must_have")):
        raise ValueError("must_have must contain at least one requirement before promotion")

    return {
        "id": _clean_text(candidate.get("id")),
        "doc": _clean_text(candidate.get("doc")) or "feedback",
        "question": _clean_text(candidate.get("question")),
        "expected_doc_title": _clean_text(candidate.get("expected_doc_title")),
        "expected_answer": _clean_text(candidate.get("expected_answer")),
        "must_have": _clean_requirement_list(candidate.get("must_have")),
        "should_have": _clean_requirement_list(candidate.get("should_have")),
        "must_not_have": _clean_requirement_list(candidate.get("must_not_have")),
    }


def promote_feedback_eval_candidate(
    candidate_id: str,
    *,
    candidates_path: str | Path = DEFAULT_CANDIDATES_PATH,
    gold_eval_path: str | Path = DEFAULT_GOLD_EVAL_PATH,
) -> dict[str, Any]:
    candidate_path = Path(candidates_path)
    eval_path = Path(gold_eval_path)
    with _WRITE_LOCK:
        candidates = load_feedback_eval_candidates(candidate_path)
        candidate_index = _candidate_index(candidates, candidate_id)
        candidate = {**candidates[candidate_index]}
        gold_item = _gold_item_from_candidate(candidate)

        gold_items = load_gold_eval_items(eval_path)
        existing_index = next(
            (
                index
                for index, item in enumerate(gold_items)
                if item.get("id") == gold_item["id"]
            ),
            None,
        )
        status = "created"
        if existing_index is None:
            gold_items.append(gold_item)
        else:
            gold_items[existing_index] = gold_item
            status = "updated"
        write_gold_eval_items(gold_items, eval_path)

        candidate["status"] = "promoted"
        candidate["promoted_at"] = _now()
        candidate["updated_at"] = candidate["promoted_at"]
        candidates[candidate_index] = candidate
        write_feedback_eval_candidates(candidates, candidate_path)

    return {
        "candidate_id": candidate_id,
        "status": status,
        "path": str(eval_path),
        "gold_item": gold_item,
        "candidate": candidate,
    }


def _candidate_id(trace_id: int) -> str:
    return f"feedback_trace_{trace_id}"


def _compact_evidence(retrieved_payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = retrieved_payload.get("retrieved_items")
    if not isinstance(items, list):
        return []
    compact_items: list[dict[str, Any]] = []
    for item in items[:5]:
        if not isinstance(item, dict):
            continue
        compact_items.append(
            {
                "title": item.get("title") or "",
                "page_number": item.get("page_number") or item.get("page_numbers") or "",
                "section_title": item.get("section_title") or "",
                "chunk_id": item.get("chunk_id") or item.get("id") or "",
            }
        )
    return compact_items


def _suggest_doc_title(retrieved_payload: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    items = retrieved_payload.get("retrieved_items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("title"):
                return str(item["title"])

    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "retrieve":
            continue
        routed_docs = step.get("routed_docs")
        if not isinstance(routed_docs, list):
            continue
        for doc in routed_docs:
            if isinstance(doc, dict) and doc.get("title"):
                return str(doc["title"])
    return ""


def _build_candidate(
    trace: dict[str, Any],
    feedback: dict[str, Any],
    *,
    now: str,
) -> dict[str, Any]:
    trace_id = int(trace["trace_id"])
    retrieved_payload = parse_json_field(trace.get("retrieved_json"), {})
    steps = parse_json_field(trace.get("steps_json"), [])
    verification = parse_json_field(trace.get("verification_json"), {})
    if not isinstance(retrieved_payload, dict):
        retrieved_payload = {}
    if not isinstance(steps, list):
        steps = []
    if not isinstance(verification, dict):
        verification = {}

    return {
        "id": _candidate_id(trace_id),
        "status": "draft",
        "source": "web_feedback",
        "trace_id": trace_id,
        "feedback_id": int(feedback["feedback_id"]),
        "feedback_rating": feedback["rating"],
        "feedback_issue_type": feedback.get("issue_type") or "",
        "question": trace.get("query") or "",
        "doc": "",
        "expected_doc_title": _suggest_doc_title(retrieved_payload, steps),
        "expected_answer": "",
        "must_have": [],
        "should_have": [],
        "must_not_have": [],
        "predicted_answer": trace.get("final_answer") or "",
        "suggested_evidence": _compact_evidence(retrieved_payload),
        "verification": verification,
        "source_trace_created_at": str(trace.get("created_at") or ""),
        "feedback_updated_at": str(feedback.get("updated_at") or ""),
        "created_at": now,
        "updated_at": now,
    }


def _merge_with_existing(candidate: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    merged = {**candidate}
    for key in (
        "status",
        "doc",
        "expected_doc_title",
        "expected_answer",
        "must_have",
        "should_have",
        "must_not_have",
        "notes",
    ):
        if key in existing and existing[key] not in ("", [], None):
            merged[key] = existing[key]
    merged["created_at"] = existing.get("created_at") or candidate["created_at"]
    return merged


def create_feedback_eval_candidate(
    sqlite_store: SQLiteStore,
    trace_id: int,
    *,
    path: str | Path = DEFAULT_CANDIDATES_PATH,
) -> dict[str, Any]:
    trace = sqlite_store.get_trace(trace_id)
    if trace is None:
        raise LookupError(f"trace {trace_id} does not exist")

    feedback = sqlite_store.get_answer_feedback_for_trace(trace_id)
    if feedback is None:
        raise LookupError(f"trace {trace_id} does not have feedback")
    if feedback["rating"] != "dislike":
        raise ValueError("only disliked answers can be converted into eval candidates")

    now = _now()
    candidate = _build_candidate(trace, feedback, now=now)
    candidate_id = candidate["id"]
    candidate_path = Path(path)

    with _WRITE_LOCK:
        candidates = load_feedback_eval_candidates(candidate_path)
        existing_index = next(
            (
                index
                for index, item in enumerate(candidates)
                if item.get("id") == candidate_id or item.get("trace_id") == trace_id
            ),
            None,
        )
        status = "created"
        if existing_index is not None:
            candidate = _merge_with_existing(candidate, candidates[existing_index])
            candidates[existing_index] = candidate
            status = "updated"
        else:
            candidates.insert(0, candidate)
        write_feedback_eval_candidates(candidates, candidate_path)

    return {
        "candidate_id": candidate_id,
        "trace_id": trace_id,
        "status": status,
        "path": str(candidate_path),
        "candidate": candidate,
    }
