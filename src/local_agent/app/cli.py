from __future__ import annotations

import argparse
from pathlib import Path

from local_agent.agent.schemas import MemoryKind
from local_agent.app.dependencies import AppDependencies
from local_agent.ingestion.file_loader import discover_pdf_files
from local_agent.ingestion.pipeline import IngestionPipeline



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local-agent-v1")
    subparser = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparser.add_parser("ingest")
    ingest_parser.add_argument(
        "--path",
        required=True,
        help= "PDF file or folder path",
    )

    ask_parser = subparser.add_parser("ask")
    ask_parser.add_argument(
        "--query",
        required=True,
        help="Question to ask"
    )
    ask_parser.add_argument(
        "--approve-tool",
        action="append",
        default=[],
        help="Approve an approval-required tool for this one request. Can be used multiple times.",
    )
    subparser.add_parser("list-docs")

    remember_parser = subparser.add_parser("remember")
    remember_parser.add_argument("--content", required=True, help="Memory text to store")
    remember_parser.add_argument(
        "--kind",
        default="project_decision",
        choices=[
            "user_preference",
            "project_decision",
            "task_status",
            "evaluation_result",
            "known_issue",
        ],
        help="Memory category",
    )
    remember_parser.add_argument(
        "--scope",
        default="global",
        choices=["global", "session"],
        help="Use global for project memory or session for one chat session",
    )
    remember_parser.add_argument("--session-id", default="default", help="Session id for session-scoped memory")
    remember_parser.add_argument("--importance", type=float, default=1.0, help="Memory importance from 1.0 to 3.0")

    list_memory_parser = subparser.add_parser("list-memory")
    list_memory_parser.add_argument("--session-id", default="default")
    list_memory_parser.add_argument("--limit", type=int, default=30)

    return parser


def run_ingest(deps: AppDependencies, path:str) -> None:
    pipeline = IngestionPipeline(
        sqlite_store=deps.sqlite_store,
        qdrant_store=deps.qdrant_store,
        embedding_client=deps.embedding_client,
        chunk_size=deps.config.chunk_size,
        chunk_overlap=deps.config.chunk_overlap
    )

    pdf_files= discover_pdf_files(path)
    if not pdf_files:
        print("No pdf files found.")
        return
    print(f"Found{len(pdf_files)} PDF file(s).\n")

    success_count = 0
    failed_count = 0

    for pdf_file in pdf_files:
        try:
            summary = pipeline.ingest_pdf(pdf_file)
            success_count += 1
            print(f"[OK] {Path(summary['source_path']).name}")
            print(f"pages={summary['page_count']} chunks={summary['chunk_count']}")
        except Exception as exc:
            failed_count += 1
            print(f"[FAIL] {pdf_file.name} -> {exc}")

    print(f"\nIngestion complete. success={success_count}, failed={failed_count}")


def run_ask(
    deps: AppDependencies,
    query: str,
    approved_tools: list[str] | None = None,
) -> None:
    print(f"Running agent for query: {query}")
    result = deps.orchestrator.handle_query(
        query,
        approved_tools=approved_tools or [],
    )
    

    print(f"\nMode selected: {result['mode']}")
    print(f"Reason: {result['reason']}")
    
    plan_dict = result.get("plan", {})
    if plan_dict and plan_dict.get("retrieval_query"):
        print(f"Retrieval Query: {plan_dict['retrieval_query']}")

    verif = result.get("verification", {})
    is_grounded = verif.get("grounded", True)

    if result["citations"] and is_grounded:
        print("\nTop retrieved chunks:")
        for idx, item in enumerate(result["citations"], start=1):
            hybrid_score = item.get('hybrid_score')
            hybrid_score_str = f"{hybrid_score:.4f}" if hybrid_score is not None else "N/A"
            reranker_score = item.get('reranker_score', 0.0)
            reranker_score_str = f"{reranker_score:.4f}" if reranker_score is not None else "N/A"
            
            print(
                f"[{idx}] page= {item.get('page_number')}\n"
                f"section {item.get('section_title')}\n"
                f"hybrid_score={hybrid_score_str}\n"
                f"reranker_score={reranker_score_str}"
            )
            print(f"   {item.get('text', '')[:500]}...")
            print()
    
    print()
    print(f"Answer: {result['answer']}")
    

    if verif:
        print(f"\nVerification Status: {verif.get('status')}")
        for issue in verif.get("issues", []):
            print(f"  - {issue}")
            
    print(f"\nTrace saved with id: {result.get('trace_id')}")

    if result.get("citations") and is_grounded:
        print("\nCitations Summary:")
        for idx, item in enumerate(result["citations"], start=1):
            print(
                f"[{idx}] {item.get('title')} | "
                f"section {item.get('section_title')} | "
                f"page {item.get('page_number')} | {item.get('source_path')}"
            )


def run_list_docs(deps:AppDependencies)->None:
    docs = deps.sqlite_store.list_documents()
    if not docs:
        print("No indexed documents found.")
        return
 
    for index, doc in enumerate(docs, start=1):
        print(f"[{index}] {doc['title']}")
        print(f"path: {doc['source_path']}")
        print(f"pages: {doc['page_count']}")
        print(f"indexed_at: {doc['indexed_at']}\n")


def run_remember(
    deps: AppDependencies,
    *,
    content: str,
    kind: MemoryKind,
    scope: str,
    session_id: str,
    importance: float,
) -> None:
    memory_id = deps.memory_manager.remember(
        content,
        kind=kind,
        session_id=session_id,
        scope=scope,
        source="manual",
        importance=importance,
    )
    if memory_id is None:
        print("Memory was not stored because it was empty or looked sensitive.")
        return
    print(f"Stored memory #{memory_id} ({kind}, scope={scope}).")


def run_list_memory(deps: AppDependencies, *, session_id: str, limit: int) -> None:
    rows = deps.sqlite_store.list_memory_items(
        session_id=session_id,
        include_global=True,
        limit=limit,
    )
    if not rows:
        print("No memory items found.")
        return
    for row in rows:
        print(f"[{row['memory_id']}] {row['kind']} | scope={row['scope']} | importance={row['importance']}")
        print(f"{row['content']}")
        print(f"source={row['source']} updated_at={row['updated_at']}\n")
