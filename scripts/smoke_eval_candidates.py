from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from local_agent.evaluation.eval_candidates import create_feedback_eval_candidate, load_feedback_eval_candidates
from local_agent.storage.sqlite_store import SQLiteStore


def main() -> None:
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        store = SQLiteStore(tmp_path / "feedback.db")
        store.initialize()
        try:
            trace_id = store.insert_trace(
                session_id="eval-candidate-smoke",
                query="What needs improvement?",
                top_k=3,
                retrieved_json=json.dumps(
                    {
                        "retrieved_items": [
                            {
                                "title": "General Test Document",
                                "page_number": 4,
                                "section_title": "Quality",
                                "chunk_id": "chunk-1",
                            }
                        ]
                    }
                ),
                final_answer="This answer is weak.",
                verification_json=json.dumps({"status": "needs_repair"}),
            )

            store.upsert_answer_feedback(trace_id=trace_id, rating="like")
            try:
                create_feedback_eval_candidate(
                    store,
                    trace_id,
                    path=tmp_path / "feedback_eval_candidates.json",
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Liked answers should not become eval candidates.")

            store.upsert_answer_feedback(
                trace_id=trace_id,
                rating="dislike",
                issue_type="bad_retrieval",
            )
            candidate_path = tmp_path / "feedback_eval_candidates.json"
            first = create_feedback_eval_candidate(store, trace_id, path=candidate_path)
            assert first["status"] == "created"
            assert first["candidate_id"] == f"feedback_trace_{trace_id}"
            assert first["candidate"]["question"] == "What needs improvement?"
            assert first["candidate"]["expected_doc_title"] == "General Test Document"
            assert first["candidate"]["predicted_answer"] == "This answer is weak."
            assert first["candidate"]["feedback_issue_type"] == "bad_retrieval"

            second = create_feedback_eval_candidate(store, trace_id, path=candidate_path)
            assert second["status"] == "updated"
            candidates = load_feedback_eval_candidates(candidate_path)
            assert len(candidates) == 1
            assert candidates[0]["id"] == first["candidate_id"]
        finally:
            store.close()

    print("Feedback eval candidate smoke passed.")


if __name__ == "__main__":
    main()
