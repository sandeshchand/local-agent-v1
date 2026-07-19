from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from local_agent.agent.memory_manager import MemoryManager
from local_agent.storage.sqlite_store import SQLiteStore


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


def run_memory_eval(eval_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    cases = json.loads(Path(eval_path).read_text(encoding="utf-8"))
    report_items = [score_memory_case(case) for case in cases]
    average = round(
        sum(item["score"] for item in report_items) / max(1, len(report_items)),
        2,
    )
    report = {
        "average_score": average,
        "pass_threshold": 9.0,
        "pass_count": sum(1 for item in report_items if item["score"] >= 9.0),
        "total_count": len(report_items),
        "items": report_items,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def score_memory_case(case: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SQLiteStore(Path(tmpdir) / "memory_eval.db")
        store.initialize()
        memory = MemoryManager(store)
        session_id = str(case.get("session_id") or f"memory-eval-{case['id']}")
        captured_count = 0

        try:
            for step in case.get("setup", []):
                captured_count += _apply_setup_step(memory, session_id, step)

            records = memory.load_memory_for_query(session_id, str(case["query"]))
            formatted_context = memory.format_memory_context(records)
            memory_text = "\n".join([item.content for item in records] + [formatted_context])
            loaded_kinds = [item.kind for item in records]

            must_have = case.get("must_include", [])
            must_not_have = case.get("must_not_include", [])
            required_kinds = [str(kind) for kind in case.get("required_kinds", [])]
            forbidden_kinds = [str(kind) for kind in case.get("forbidden_kinds", [])]
            expected_sections = [str(section) for section in case.get("expected_sections", [])]

            matched_must = [requirement_label(item) for item in must_have if contains_any(memory_text, item)]
            missing_must = [requirement_label(item) for item in must_have if not contains_any(memory_text, item)]
            triggered_bad = [requirement_label(item) for item in must_not_have if contains_any(memory_text, item)]
            matched_required_kinds = [kind for kind in required_kinds if kind in loaded_kinds]
            missing_required_kinds = [kind for kind in required_kinds if kind not in loaded_kinds]
            triggered_forbidden_kinds = [kind for kind in forbidden_kinds if kind in loaded_kinds]
            matched_sections = [section for section in expected_sections if section in formatted_context]
            missing_sections = [section for section in expected_sections if section not in formatted_context]

            include_score = 5.0 * _matched_ratio(matched_must, must_have)
            safety_score = 2.0 * _absence_ratio(triggered_bad, must_not_have)
            required_kind_score = 1.25 * _matched_ratio(matched_required_kinds, required_kinds)
            forbidden_kind_score = 0.75 * _absence_ratio(
                triggered_forbidden_kinds,
                forbidden_kinds,
            )
            section_score = 1.0 * _matched_ratio(matched_sections, expected_sections)
            total = round(
                include_score
                + safety_score
                + required_kind_score
                + forbidden_kind_score
                + section_score,
                2,
            )

            return {
                "id": case["id"],
                "description": case.get("description", ""),
                "query": case["query"],
                "score": total,
                "include_score": round(include_score, 2),
                "safety_score": round(safety_score, 2),
                "kind_score": round(required_kind_score + forbidden_kind_score, 2),
                "section_score": round(section_score, 2),
                "captured_count": captured_count,
                "loaded_count": len(records),
                "loaded_kinds": loaded_kinds,
                "matched_must_include": matched_must,
                "missing_must_include": missing_must,
                "triggered_must_not_include": triggered_bad,
                "matched_required_kinds": matched_required_kinds,
                "missing_required_kinds": missing_required_kinds,
                "triggered_forbidden_kinds": triggered_forbidden_kinds,
                "matched_sections": matched_sections,
                "missing_sections": missing_sections,
                "memory_records": [
                    {
                        "role": item.role,
                        "kind": item.kind,
                        "source": item.source,
                        "content": item.content,
                        "score": item.score,
                    }
                    for item in records
                ],
                "formatted_context": formatted_context,
            }
        finally:
            store.close()


def _apply_setup_step(memory: MemoryManager, session_id: str, step: dict[str, Any]) -> int:
    step_type = str(step.get("type") or step.get("role") or "user")
    content = str(step.get("content") or "")

    if step_type == "manual_memory":
        memory.remember(
            content,
            kind=step.get("kind", "project_decision"),
            session_id=str(step.get("session_id") or session_id),
            scope=str(step.get("scope") or "global"),
            source=str(step.get("source") or "manual"),
            importance=float(step.get("importance") or 1.0),
        )
        return 0

    if step_type == "assistant":
        memory.save_assistant_turn(session_id, content)
        return 0

    memory.save_user_turn(session_id, content)
    captured = memory.capture_long_term_memory(session_id, content)
    return len(captured)


def _matched_ratio(matched: list[Any], expected: list[Any]) -> float:
    if not expected:
        return 1.0
    return len(matched) / len(expected)


def _absence_ratio(triggered: list[Any], forbidden: list[Any]) -> float:
    if not forbidden:
        return 1.0
    return 1 - (len(triggered) / len(forbidden))
