from __future__ import annotations

import argparse
from pathlib import Path

from agent.planner import Planner
from agent.orchestrator import Orchestrator
from app.dependencies import AppDependencies
from ingestion.file_loader import discover_pdf_files
from ingestion.pipeline import IngestionPipeline
from observability.traces import save_trace
from retrieval.answer_service import AnswerService
from retrieval.search import RetrievalService



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
    subparser.add_parser("list-docs")

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


def run_ask(deps: AppDependencies, query:str) ->None:
    planner = Planner(chat_client=deps.chat_client)
    retrieval = RetrievalService(
        qdrant_store=deps.qdrant_store,
        embedding_client=deps.embedding_client,
        top_k = deps.config.top_k,
    )
    answer_service = AnswerService(chat_client=deps.chat_client)
    orchestrator = Orchestrator(
        planner=planner,
        retrieval_service=retrieval,
        answer_service=answer_service,
    )
    
    result = orchestrator.handle_query(query)
    trace_id = save_trace(
        sqlite_store=deps.sqlite_store,
        query=query,
        top_k=deps.config.top_k,
        retrieved_items=result["citations"],
        final_answer=result["answer"],
        plan=result["plan"],
    )

    print(f"Mode: {result['mode']}")
    print(f"Reason: {result['reason']}")
    if result["retrieval_query"]:
        print(f"Retrieval Query: {result['retrieval_query']}")
    
    print()
    print(f"Answer: {result['answer']}")
    print(f"\n Trace saved with id:{trace_id}")

    if result["citations"]:
        print("\nCitations:")
        for idx, item in enumerate(result["citations"], start=1):
            print(
                f"[{idx}]{item.get('title')} | page {item.get('page_number')} | {item.get('source_path')}")


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