from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path

from storage.sqlite_store import SQLiteStore


def main() -> None:
    with TemporaryDirectory() as tmpdir:
        store = SQLiteStore(Path(tmpdir) / "feedback.db")
        store.initialize()
        try:
            first_trace = store.insert_trace(
                session_id="feedback-smoke",
                query="good answer",
                top_k=3,
                retrieved_json="{}",
                final_answer="useful answer",
            )
            second_trace = store.insert_trace(
                session_id="feedback-smoke",
                query="weak answer",
                top_k=3,
                retrieved_json="{}",
                final_answer="needs improvement",
            )
            third_trace = store.insert_trace(
                session_id="feedback-smoke",
                query="another weak answer",
                top_k=3,
                retrieved_json="{}",
                final_answer="also needs improvement",
            )

            store.upsert_answer_feedback(trace_id=first_trace, rating="like")
            store.upsert_answer_feedback(trace_id=second_trace, rating="dislike")
            store.upsert_answer_feedback(trace_id=third_trace, rating="dislike")

            summary = store.get_answer_feedback_summary(recent_limit=2)
            assert summary["total_count"] == 3
            assert summary["like_count"] == 1
            assert summary["dislike_count"] == 2
            assert round(summary["dislike_rate"], 2) == 0.67
            assert len(summary["recent_dislikes"]) == 2
            assert all(item["rating"] == "dislike" for item in summary["recent_dislikes"])
        finally:
            store.close()

    print("Feedback analytics smoke passed.")


if __name__ == "__main__":
    main()
