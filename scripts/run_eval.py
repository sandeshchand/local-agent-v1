from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from difflib import SequenceMatcher


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def contains_phrase(text: str, phrase: str) -> bool:
    return normalize(phrase) in normalize(text)


def semantic_overlap(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


@dataclass
class EvalResult:
    qid: str
    question: str
    score_total: float
    score_key_coverage: float
    score_similarity: float
    score_focus: float
    score_citation_hint: float
    matched_must_have: list[str]
    missing_must_have: list[str]
    matched_should_have: list[str]
    triggered_must_not_have: list[str]
    notes: list[str]


def score_one(gold: dict[str, Any], predicted: str) -> EvalResult:
    pred = normalize(predicted)
    expected = gold["expected_answer"]

    must_have = gold.get("must_have", [])
    should_have = gold.get("should_have", [])
    must_not_have = gold.get("must_not_have", [])

    matched_must = [p for p in must_have if contains_phrase(pred, p)]
    missing_must = [p for p in must_have if p not in matched_must]
    matched_should = [p for p in should_have if contains_phrase(pred, p)]
    triggered_bad = [p for p in must_not_have if contains_phrase(pred, p)]

    # 1) key coverage: 0-4
    if must_have:
        key_coverage = 4.0 * (len(matched_must) / len(must_have))
    else:
        key_coverage = 4.0

    # 2) semantic similarity: 0-3
    sim = semantic_overlap(expected, predicted)
    similarity = round(3.0 * sim, 2)

    # 3) focus / drift: 0-2
    focus = 2.0
    if triggered_bad:
        focus -= 1.0
    if len(pred.split()) > max(120, 2 * len(expected.split())):
        focus -= 0.5
    if len(missing_must) >= max(1, len(must_have) // 2):
        focus -= 0.5
    focus = max(0.0, round(focus, 2))

    # 4) citation hint: 0-1
    citation_hint = 1.0 if re.search(r"\[\d+\]", predicted) else 0.0

    total = round(key_coverage + similarity + focus + citation_hint, 2)

    notes: list[str] = []
    if missing_must:
        notes.append(f"Missing key points: {', '.join(missing_must)}")
    if triggered_bad:
        notes.append(f"Off-target phrases: {', '.join(triggered_bad)}")
    if citation_hint == 0:
        notes.append("No citation markers found")
    if sim < 0.45:
        notes.append("Low semantic similarity to expected answer")

    return EvalResult(
        qid=gold["id"],
        question=gold["question"],
        score_total=total,
        score_key_coverage=round(key_coverage, 2),
        score_similarity=similarity,
        score_focus=focus,
        score_citation_hint=citation_hint,
        matched_must_have=matched_must,
        missing_must_have=missing_must,
        matched_should_have=matched_should,
        triggered_must_not_have=triggered_bad,
        notes=notes,
    )


def main() -> None:
    gold_path = Path("eval/qa_gold.json")
    pred_path = Path("eval/predictions.json")

    gold_items = json.loads(gold_path.read_text(encoding="utf-8"))
    predictions = json.loads(pred_path.read_text(encoding="utf-8"))

    pred_map = {item["id"]: item["predicted_answer"] for item in predictions}

    results: list[EvalResult] = []
    for gold in gold_items:
        predicted = pred_map.get(gold["id"], "")
        results.append(score_one(gold, predicted))

    report = [asdict(r) for r in results]
    avg = round(sum(r.score_total for r in results) / max(1, len(results)), 2)

    out = {
        "average_score": avg,
        "results": report,
    }

    Path("eval/report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Average score: {avg}/10")
    for r in results:
        print(f"{r.qid}: {r.score_total}/10")
        for note in r.notes:
            print(f"  - {note}")


if __name__ == "__main__":
    main()