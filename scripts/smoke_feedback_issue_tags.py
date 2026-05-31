from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from local_agent.storage.sqlite_store import SQLiteStore


def main() -> None:
    with TemporaryDirectory() as tmpdir:
        store = SQLiteStore(Path(tmpdir) / "feedback.db")
        store.initialize()
        try:
            trace_id = store.insert_trace(
                session_id="feedback-issue-smoke",
                query="why was the answer weak?",
                top_k=3,
                retrieved_json="{}",
                final_answer="weak answer",
            )

            row = store.upsert_answer_feedback(
                trace_id=trace_id,
                rating="dislike",
                issue_type="bad_retrieval",
            )
            assert row["issue_type"] == "bad_retrieval"

            row = store.upsert_answer_feedback(
                trace_id=trace_id,
                rating="dislike",
                issue_type="wrong_document",
            )
            assert row["issue_type"] == "wrong_document"
            assert store.list_answer_feedback(rating="dislike", limit=1)[0]["issue_type"] == "wrong_document"

            summary = store.get_answer_feedback_summary()
            assert summary["issue_counts"]["wrong_document"] == 1

            try:
                store.upsert_answer_feedback(
                    trace_id=trace_id,
                    rating="dislike",
                    issue_type="document_specific_hack",
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Unknown issue tags should be rejected.")

            row = store.upsert_answer_feedback(trace_id=trace_id, rating="like")
            assert row["issue_type"] == ""
        finally:
            store.close()

    print("Feedback issue tag smoke passed.")


if __name__ == "__main__":
    main()
