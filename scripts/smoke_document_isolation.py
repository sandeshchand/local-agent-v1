from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from local_agent.agent.guardrails import GuardrailPolicy
from local_agent.agent.orchestrator import Orchestrator
from local_agent.agent.schemas import AgentAction, AgentState, ToolSpec, VerificationResult
from local_agent.retrieval.doc_router import DocumentRouter
from local_agent.retrieval.search import RetrievalService
from local_agent.storage.sqlite_store import SQLiteStore, document_visible_to
from local_agent.tools import ToolRegistry


class FakeEmbeddingClient:
    model_name = "fake-embed"

    def embed(self, query: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class FakePoint:
    def __init__(self, point_id: str, payload: dict[str, Any], score: float) -> None:
        self.id = point_id
        self.payload = payload
        self.score = score


class FakeSearchResult:
    def __init__(self, points: list[FakePoint]) -> None:
        self.points = points


class FakeQdrantStore:
    def __init__(self, points: list[FakePoint]) -> None:
        self.points = points

    def search(
        self,
        *,
        query_vector: list[float],
        limit: int,
        doc_id: str | None = None,
    ) -> FakeSearchResult:
        del query_vector
        points = [
            point
            for point in self.points
            if doc_id is None or point.payload.get("doc_id") == doc_id
        ]
        return FakeSearchResult(points[:limit])


class VerifierStub:
    def verify(self, answer: str, retrieved_items: list[dict], query: str = "") -> VerificationResult:
        return VerificationResult(status="verified", issues=[], grounded=True)


class AnswerServiceStub:
    def answer_from_tool_result(
        self,
        query: str,
        tool_context: str,
        memory_context: str = "",
    ) -> str:
        return tool_context


def add_document(
    store: SQLiteStore,
    *,
    doc_id: str,
    title: str,
    text: str,
    owner_id: str = "global",
    visibility: str = "global",
) -> dict[str, Any]:
    source_path = f"data/raw/{doc_id}.pdf"
    store.upsert_document(
        doc_id=doc_id,
        source_path=source_path,
        title=title,
        page_count=1,
        checksum=f"checksum-{doc_id}",
        owner_id=owner_id,
        visibility=visibility,
    )
    store.insert_chunks(
        [
            {
                "chunk_id": f"{doc_id}-chunk-0",
                "doc_id": doc_id,
                "chunk_index": 0,
                "page_number": 1,
                "text": text,
                "token_estimate": len(text.split()),
                "section_title": title,
            }
        ]
    )
    return {
        "id": f"{doc_id}-point-0",
        "score": 0.9,
        "payload": {
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}-chunk-0",
            "chunk_index": 0,
            "title": title,
            "source_path": source_path,
            "section_title": title,
            "page_number": 1,
            "text": text,
            "owner_id": owner_id,
            "visibility": visibility,
        },
    }


def assert_storage_scopes(store: SQLiteStore) -> None:
    alice_ids = store.accessible_document_ids(owner_id="alice")
    bob_ids = store.accessible_document_ids(owner_id="bob")

    assert set(alice_ids) == {"global-doc", "alice-doc"}
    assert set(bob_ids) == {"global-doc", "bob-doc"}
    assert store.count_documents(owner_id="alice") == 2
    assert store.count_documents(owner_id="alice", include_global=False) == 1
    assert [doc["doc_id"] for doc in store.list_documents(owner_id="alice", doc_ids=["bob-doc"])] == []
    assert document_visible_to({"owner_id": "bob", "visibility": "user"}, "alice") is False
    assert document_visible_to({"owner_id": "bob", "visibility": "global"}, "alice") is True


def assert_router_scope(store: SQLiteStore) -> None:
    router = DocumentRouter(store, cache_enabled=True)
    alice_ids = store.accessible_document_ids(owner_id="alice")
    routed = router.route("bob private feature", accessible_doc_ids=alice_ids)
    assert all(doc["doc_id"] != "bob-doc" for doc in routed)

    global_routed = router.route("bob private feature")
    assert any(doc["doc_id"] == "bob-doc" for doc in global_routed)


def assert_retrieval_scope(store: SQLiteStore, qdrant_points: list[FakePoint]) -> None:
    service = RetrievalService(
        qdrant_store=FakeQdrantStore(qdrant_points),  # type: ignore[arg-type]
        sqlite_store=store,
        embedding_client=FakeEmbeddingClient(),  # type: ignore[arg-type]
        top_k=5,
        use_reranker=False,
        neighbor_window=0,
        final_context_limit=10,
        use_parent_context=False,
    )
    alice_ids = store.accessible_document_ids(owner_id="alice")
    results = service.search("bob private feature", accessible_doc_ids=alice_ids)
    assert results
    assert all(item["doc_id"] != "bob-doc" for item in results)

    unscoped_results = service.search("bob private feature")
    assert any(item["doc_id"] == "bob-doc" for item in unscoped_results)


def assert_list_documents_tool_scope(store: SQLiteStore) -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="list_documents",
            description="List documents",
            requires_approval=False,
        ),
        lambda: store.list_documents(),
    )

    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.tool_registry = registry
    orchestrator.sqlite_store = store
    orchestrator.verifier = VerifierStub()
    orchestrator.answer_service = AnswerServiceStub()
    orchestrator.guardrail_policy = GuardrailPolicy()

    state = AgentState(session_id="alice:default", user_query="list documents")
    action = AgentAction(
        action_type="tool_call",
        tool_call={"name": "list_documents", "args": {}},
    )
    orchestrator._handle_tool_action(
        query=state.user_query,
        memory_context="",
        state=state,
        action=action,
        step_no=2,
        accessible_doc_ids=store.accessible_document_ids(owner_id="alice"),
    )

    assert state.tool_results and state.tool_results[0].success
    doc_ids = {doc["doc_id"] for doc in state.tool_results[0].output}
    assert doc_ids == {"global-doc", "alice-doc"}


def main() -> None:
    with TemporaryDirectory() as tmp:
        store = SQLiteStore(Path(tmp) / "app.db")
        try:
            store.initialize()
            records = [
                add_document(
                    store,
                    doc_id="global-doc",
                    title="Global Docker Notes",
                    text="A global document visible to every user.",
                ),
                add_document(
                    store,
                    doc_id="alice-doc",
                    title="Alice Notes",
                    text="Alice private feature and retrieval notes.",
                    owner_id="alice",
                    visibility="user",
                ),
                add_document(
                    store,
                    doc_id="bob-doc",
                    title="Bob Notes",
                    text="Bob private feature and retrieval notes.",
                    owner_id="bob",
                    visibility="user",
                ),
            ]
            qdrant_points = [
                FakePoint(record["id"], record["payload"], record["score"])
                for record in records
            ]

            assert_storage_scopes(store)
            assert_router_scope(store)
            assert_retrieval_scope(store, qdrant_points)
            assert_list_documents_tool_scope(store)
        finally:
            store.close()

    print("Document isolation smoke test passed.")


if __name__ == "__main__":
    main()
