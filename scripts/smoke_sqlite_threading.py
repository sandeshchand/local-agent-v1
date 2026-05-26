from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from pathlib import Path

from storage.sqlite_store import SQLiteStore


def main() -> None:
    with TemporaryDirectory() as tmp_dir:
        store = SQLiteStore(Path(tmp_dir) / "app.db")
        try:
            store.initialize()
            trace_id = store.insert_trace(
                session_id="default",
                query="threaded feedback test",
                top_k=1,
                retrieved_json="{}",
                final_answer="ok",
            )

            store.list_traces(limit=1)

            def save_feedback(rating: str) -> str:
                row = store.upsert_answer_feedback(trace_id=trace_id, rating=rating)
                return row["rating"]

            with ThreadPoolExecutor(max_workers=1) as executor:
                assert executor.submit(save_feedback, "like").result() == "like"
                assert executor.submit(save_feedback, "dislike").result() == "dislike"

            feedback_items = store.list_answer_feedback(limit=5)
            assert len(feedback_items) == 1
            assert feedback_items[0]["rating"] == "dislike"
            assert feedback_items[0]["query"] == "threaded feedback test"
            assert store.list_answer_feedback(rating="like", limit=5) == []
            assert store.list_answer_feedback(rating="dislike", limit=5)[0]["trace_id"] == trace_id
        finally:
            store.close()

    print("SQLite threading smoke test passed.")


if __name__ == "__main__":
    main()
