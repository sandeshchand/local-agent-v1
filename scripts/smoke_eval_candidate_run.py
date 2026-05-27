from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.eval_runner import run_candidate_eval


class OrchestratorStub:
    def handle_query(self, query: str, session_id: str) -> dict:
        assert query == "What should the system answer?"
        assert session_id == "ui-eval-feedback_trace_999"
        return {
            "answer": "The reviewed answer explains system behavior clearly. [1]",
            "steps": [
                {
                    "type": "retrieve",
                    "routed_docs": [
                        {
                            "title": "Review Test Document",
                            "routing_score": 1.0,
                        }
                    ],
                }
            ],
            "verification": {"status": "verified"},
            "citations": [
                {
                    "title": "Review Test Document",
                    "section_title": "Answer Quality",
                    "page_number": 2,
                    "chunk_id": "review-chunk-1",
                }
            ],
        }


def main() -> None:
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        gold_path = tmp_path / "eval_multi_doc_rag.json"
        gold_path.write_text(
            json.dumps(
                [
                    {
                        "id": "feedback_trace_999",
                        "doc": "review-doc",
                        "question": "What should the system answer?",
                        "expected_doc_title": "Review Test Document",
                        "expected_answer": "The system should provide the reviewed answer.",
                        "must_have": ["reviewed answer", "system behavior"],
                        "should_have": ["clearly"],
                        "must_not_have": ["weak answer"],
                    }
                ],
                indent=2,
            ),
            encoding="utf-8",
        )

        result = run_candidate_eval(
            OrchestratorStub(),
            "feedback_trace_999",
            gold_eval_path=gold_path,
            output_dir=tmp_path / "eval",
        )
        assert result["candidate_id"] == "feedback_trace_999"
        assert result["passed"] is True
        assert result["score"] >= 8.0
        assert Path(result["output_path"]).exists()
        assert result["result"]["missing_must_have"] == []

    print("Eval candidate run smoke passed.")


if __name__ == "__main__":
    main()
