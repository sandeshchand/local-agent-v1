from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from local_agent.agent.schemas import ToolSpec
from local_agent.app.system_status import build_system_status
from local_agent.tools import ToolRegistry


class SQLiteStoreStub:
    def health_check(self) -> bool:
        return True

    def count_documents(self) -> int:
        return 3


class QdrantStoreStub:
    collection_name = "knowledge_chunks"

    def health_check(self) -> bool:
        return True

    def collection_exists(self) -> bool:
        return True


def main() -> None:
    tool_registry = ToolRegistry()
    tool_registry.register(
        ToolSpec(
            name="safe_tool",
            description="Safe read-only tool",
            requires_approval=False,
        ),
        lambda: "ok",
    )

    deps = SimpleNamespace(
        config=SimpleNamespace(
            sqlite_path=Path("var/sqlite/app.db"),
            qdrant_path=Path("var/qdrant"),
            ollama_base_url="http://127.0.0.1:11434",
            chat_model="chat-model",
            embed_model="embed-model",
        ),
        sqlite_store=SQLiteStoreStub(),
        qdrant_store=QdrantStoreStub(),
        tool_registry=tool_registry,
    )

    status = build_system_status(deps, check_models=False)

    assert status["status"] == "degraded"
    assert status["summary"]["document_count"] == 3
    assert status["summary"]["tool_count"] == 1
    assert {item["name"] for item in status["components"]} == {
        "SQLite",
        "Qdrant",
        "Ollama Chat Model",
        "Ollama Embedding Model",
        "Tool Registry",
    }

    print("System status smoke test passed.")


if __name__ == "__main__":
    main()
