from __future__ import annotations

import argparse
import sys
from pathlib import  Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from local_agent.app.bootstrap import bootstrap_app
from local_agent.ingestion.pipeline import IngestionPipeline
from local_agent.retrieval.search import RetrievalService

def build_context(results: list[dict]) -> str:
    parts: list[str] = []
    for index, item in enumerate(results, start=1):
        parts.append(
            f"[{index}] Title: {item['title']}\n"
            f"Page: {item['page_number']}\n"
            f"Score: {item['score']:.4f}\n"
            f"Text: {item['text']}\n")
    return "\n".join(parts)


def build_prompt(question: str, context: str) -> str:
        return f"""
    You are answering only from the retrieved context below.
    
    Rules:
    - Use only the provided context.
    - If the context is insufficient, say that clearly.
    - Cite supporting chunks using [1], [2], [3] style.
    
    Question:
    {question}
    
    Context:
    {context}
    
    Answer:
    """.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pdf",
        default="data/raw/documents/sora.pdf",
        help="Path to the PDF file to ingest",
    )
    parser.add_argument(
        "--query",
        required=True,
        help="Question to ask after ingestion",
    )
    args = parser.parse_args()

    deps = bootstrap_app(".env")

    pipeline = IngestionPipeline(
        sqlite_store=deps.sqlite_store,
        qdrant_store=deps.qdrant_store,
        embedding_client=deps.embedding_client,
        chunk_size=deps.config.chunk_size,
        chunk_overlap=deps.config.chunk_overlap,
    )

    retrieval = RetrievalService(
        qdrant_store=deps.qdrant_store,
        embedding_client=deps.embedding_client,
        top_k=deps.config.top_k,
    )

    print("\n=== INGESTING PDF ===")
    summary = pipeline.ingest_pdf(args.pdf)
    for key, value in summary.items():
        print(f"{key}: {value}")

    print("\n=== RETRIEVAL ===")
    results = retrieval.search(args.query)
    if not results:
        print("No retrieval results found.")
        return

    for idx, item in enumerate(results, start=1):
        print(f"\n[{idx}] score={item['score']:.4f} page={item['page_number']}")
        print(item["text"][:500])

    print("\n=== ANSWER ===")
    context = build_context(results)
    prompt = build_prompt(args.query, context)
    answer = deps.chat_client.generate(prompt)
    print(answer)


if __name__ == "__main__":
    main()