from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bootstrap import bootstrap_app  # noqa: E402


def print_header(title: str) -> None:
    print(f"\n{'=' * 20} {title} {'=' * 20}")


def main() -> None:
    deps = bootstrap_app(".env")

    print_header("CONFIG")
    print(f"Ollama base URL: {deps.config.ollama_base_url}")
    print(f"Chat model:      {deps.config.chat_model}")
    print(f"Embed model:     {deps.config.embed_model}")
    print(f"SQLite path:     {deps.config.sqlite_path}")
    print(f"Qdrant path:     {deps.config.qdrant_path}")

    print_header("CHAT TEST")
    chat_response = deps.chat_client.generate("Reply with only: local chat ok")
    print(f"Chat response: {chat_response}")
    if "local chat ok" not in chat_response.lower():
        raise RuntimeError("Chat test failed: unexpected response from Ollama.")
    print("Chat test passed.")

    print_header("EMBEDDING TEST")
    sample_text = "This document describes a local retrieval system."
    vector = deps.embedding_client.embed(sample_text)
    print(f"Embedding length: {len(vector)}")
    if not vector:
        raise RuntimeError("Embedding test failed: empty vector.")
    print("Embedding test passed.")

    print_header("SQLITE TEST")
    if not deps.sqlite_store.health_check():
        raise RuntimeError("SQLite health check failed.")

    row_id = deps.sqlite_store.insert_test_row(name="day1", value="sqlite ok")
    row = deps.sqlite_store.read_test_row(row_id)
    print(f"Inserted row id: {row_id}")
    print(f"Fetched row: {row}")
    if row is None or row["value"] != "sqlite ok":
        raise RuntimeError("SQLite test failed: row round-trip mismatch.")
    print("SQLite test passed.")

    print_header("QDRANT TEST")
    if not deps.qdrant_store.health_check():
        raise RuntimeError("Qdrant health check failed.")

    deps.qdrant_store.initialize_collection(vector_size=len(vector))
    deps.qdrant_store.upsert_test_vector(
        point_id=1,
        vector=vector,
        payload={"name": "day1_test_vector", "source": "smoke_test"},
    )
    search_result = deps.qdrant_store.search_test_vector(query_vector=vector, limit=3)

    points = getattr(search_result, "points", None)
    if points is None:
        points = []

    print(f"Returned points: {len(points)}")
    if not points:
        raise RuntimeError("Qdrant test failed: no points returned from search.")

    top_point = points[0]
    top_id = getattr(top_point, "id", None)
    print(f"Top point id: {top_id}")
    print("Qdrant test passed.")

    print_header("DAY 1 RESULT")
    print("All Day 1 smoke tests passed successfully.")


if __name__ == "__main__":
    main()
