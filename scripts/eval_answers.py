from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from local_agent.app.bootstrap import bootstrap_app


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def contains(text: str, phrase: str) -> bool:
    normalized_text = normalize(text)
    normalized_phrase = normalize(phrase)
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{1,12}", normalized_phrase):
        return bool(re.search(rf"\b{re.escape(normalized_phrase)}\b", normalized_text))
    return normalized_phrase in normalized_text or compact(phrase) in compact(text)


def citation_count(answer: str) -> int:
    return len(set(re.findall(r"\[(\d+)\]", answer)))


def score_answer(gold: dict[str, Any], answer: str, citations: list[dict[str, Any]]) -> dict[str, Any]:
    must_have = gold.get("must_have", [])
    should_have = gold.get("should_have", [])
    must_not_have = gold.get("must_not_have", [])

    matched_must = [phrase for phrase in must_have if contains(answer, phrase)]
    missing_must = [phrase for phrase in must_have if phrase not in matched_must]
    matched_should = [phrase for phrase in should_have if contains(answer, phrase)]
    triggered_bad = [phrase for phrase in must_not_have if contains(answer, phrase)]

    key_score = 5.5 * (len(matched_must) / max(1, len(must_have)))
    optional_score = 1.0 * (len(matched_should) / max(1, len(should_have)))
    citation_score = 1.5 if citation_count(answer) > 0 and citations else 0.0
    focus_score = 2.0
    if triggered_bad:
        focus_score -= 1.5
    if len(answer.split()) > 180:
        focus_score -= 0.5
    if "does not contain enough information" in normalize(answer):
        focus_score = 0.0
    focus_score = max(0.0, focus_score)

    total = round(key_score + optional_score + citation_score + focus_score, 2)
    return {
        "id": gold["id"],
        "question": gold["question"],
        "score": total,
        "key_score": round(key_score, 2),
        "optional_score": round(optional_score, 2),
        "citation_score": round(citation_score, 2),
        "focus_score": round(focus_score, 2),
        "matched_must_have": matched_must,
        "missing_must_have": missing_must,
        "matched_should_have": matched_should,
        "triggered_must_not_have": triggered_bad,
        "answer": answer,
        "citations": [
            {
                "rank": index,
                "chunk_id": item.get("chunk_id"),
                "page": item.get("page_number"),
                "pages": item.get("page_numbers"),
                "section": item.get("section_title"),
            }
            for index, item in enumerate(citations, start=1)
        ],
    }


def run_eval(eval_path: Path, output_path: Path) -> dict[str, Any]:
    deps = bootstrap_app(".env")
    gold_items = json.loads(eval_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []

    for gold in gold_items:
        response = deps.orchestrator.handle_query(
            gold["question"],
            session_id=f"answer-eval-{gold['id']}",
        )
        results.append(score_answer(gold, response["answer"], response.get("citations", [])))

    average = round(sum(item["score"] for item in results) / max(1, len(results)), 2)
    report = {
        "average_score": average,
        "items": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate full RAG answer quality.")
    parser.add_argument("--eval-file", default="benchmarks/gold_qa/eval_sora_answers.json")
    parser.add_argument("--output", default="eval/answer_report.json")
    args = parser.parse_args()

    report = run_eval(Path(args.eval_file), Path(args.output))
    print(f"Average answer score: {report['average_score']}/10")
    for item in report["items"]:
        print(f"{item['id']}: {item['score']}/10")
        if item["missing_must_have"]:
            print(f"  missing: {item['missing_must_have']}")
        if item["triggered_must_not_have"]:
            print(f"  unwanted: {item['triggered_must_not_have']}")


if __name__ == "__main__":
    main()
