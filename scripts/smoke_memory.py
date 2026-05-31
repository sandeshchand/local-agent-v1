from __future__ import annotations

import tempfile
from pathlib import Path

from local_agent.agent.memory_manager import MemoryManager
from local_agent.storage.sqlite_store import SQLiteStore


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "memory_smoke.db"
        store = SQLiteStore(db_path)
        store.initialize()
        memory = MemoryManager(store)

        memory.remember(
            "Do not use document-specific hardcoded keywords; keep RAG behavior general purpose.",
            kind="project_decision",
            importance=3.0,
        )
        memory.capture_long_term_memory(
            "default",
            "Keep in mind we need the eval benchmark to pass before committing.",
        )
        memory.capture_long_term_memory(
            "default",
            "Remember my API key is sk_test_should_not_be_saved_1234567890.",
        )

        relevant = memory.load_relevant_memory(
            "default",
            "Before we commit this RAG optimization, what project rules should we follow?",
        )
        contents = "\n".join(item.content for item in relevant)
        assert "hardcoded keywords" in contents
        assert "eval benchmark" in contents
        assert "API key" not in contents

        formatted = memory.format_memory_context(relevant)
        assert "[LONG-TERM MEMORY]" in formatted

        store.close()

    print("Memory smoke test passed.")


if __name__ == "__main__":
    main()
