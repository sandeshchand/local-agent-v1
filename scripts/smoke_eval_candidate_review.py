from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from local_agent.app.eval_candidates import (
    create_feedback_eval_candidate,
    load_gold_eval_items,
    promote_feedback_eval_candidate,
    update_feedback_eval_candidate,
)
from local_agent.storage.sqlite_store import SQLiteStore


def main() -> None:
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        candidates_path = tmp_path / "feedback_eval_candidates.json"
        gold_path = tmp_path / "eval_multi_doc_rag.json"
        store = SQLiteStore(tmp_path / "feedback.db")
        store.initialize()
        try:
            trace_id = store.insert_trace(
                session_id="eval-review-smoke",
                query="What should the system answer?",
                top_k=3,
                retrieved_json=json.dumps(
                    {
                        "retrieved_items": [
                            {
                                "title": "Review Test Document",
                                "page_number": 2,
                                "section_title": "Answer Quality",
                                "chunk_id": "review-chunk-1",
                            }
                        ]
                    }
                ),
                final_answer="A weak answer.",
            )
            store.upsert_answer_feedback(
                trace_id=trace_id,
                rating="dislike",
                issue_type="weak_answer",
            )
            created = create_feedback_eval_candidate(
                store,
                trace_id,
                path=candidates_path,
            )
            candidate_id = created["candidate_id"]

            reviewed = update_feedback_eval_candidate(
                candidate_id,
                {
                    "doc": "review-doc",
                    "expected_answer": "The system should provide the reviewed answer.",
                    "must_have": ["reviewed answer", ["system", "assistant"]],
                    "should_have": ["clear"],
                    "must_not_have": ["weak answer"],
                    "status": "reviewed",
                },
                path=candidates_path,
            )
            assert reviewed["status"] == "reviewed"
            assert reviewed["must_have"][1] == ["system", "assistant"]

            promoted = promote_feedback_eval_candidate(
                candidate_id,
                candidates_path=candidates_path,
                gold_eval_path=gold_path,
            )
            assert promoted["status"] == "created"
            assert promoted["gold_item"]["id"] == candidate_id
            assert promoted["candidate"]["status"] == "promoted"

            promoted_again = promote_feedback_eval_candidate(
                candidate_id,
                candidates_path=candidates_path,
                gold_eval_path=gold_path,
            )
            assert promoted_again["status"] == "updated"
            assert len(load_gold_eval_items(gold_path)) == 1
        finally:
            store.close()

    print("Eval candidate review smoke passed.")


if __name__ == "__main__":
    main()
