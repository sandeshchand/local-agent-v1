from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import HTTPException

from local_agent.app import web
from local_agent.storage.sqlite_store import SQLiteStore


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SQLiteStore(Path(tmpdir) / "memory_api.db")
        store.initialize()
        first_id = store.insert_memory_item(
            content="Do not use document-specific hardcoded keywords.",
            kind="project_decision",
            source="manual",
            importance=3.0,
        )
        second_id = store.insert_memory_item(
            content="Use short UI explanations.",
            kind="user_preference",
            session_id="memory-api-smoke",
            scope="session",
            source="manual",
            importance=2.0,
        )

        original_get_sqlite_store = web.get_sqlite_store
        web.get_sqlite_store = lambda: store
        try:
            listed = web.list_memory(session_id="memory-api-smoke", include_global=True, limit=10)
            assert listed.total == 2
            assert {item.memory_id for item in listed.items} == {first_id, second_id}

            deleted = web.delete_memory(second_id)
            assert deleted.deleted is True
            assert deleted.item.memory_id == second_id

            listed_after_delete = web.list_memory(session_id="memory-api-smoke", include_global=True, limit=10)
            assert listed_after_delete.total == 1
            assert listed_after_delete.items[0].memory_id == first_id

            try:
                web.delete_memory(second_id)
            except HTTPException as exc:
                assert exc.status_code == 404
            else:
                raise AssertionError("Deleting a missing memory item should raise 404.")
        finally:
            web.get_sqlite_store = original_get_sqlite_store
            store.close()

    print("Memory API smoke test passed.")


if __name__ == "__main__":
    main()
