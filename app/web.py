from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api_models import (
    ChatRequest,
    ChatResponse,
    CitationItem,
    DocumentItem,
    HealthResponse,
    IngestFileResult,
    IngestPathRequest,
    IngestPathResponse,
    TraceDetail,
    TraceSummary,
)
from app.bootstrap import bootstrap_app
from app.dependencies import AppDependencies
from ingestion.file_loader import discover_pdf_files
from ingestion.pipeline import IngestionPipeline

BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


@lru_cache(maxsize=1)
def get_deps() -> AppDependencies:
    return bootstrap_app(".env")


def build_citations(results: list[dict]) -> list[CitationItem]:
    citations: list[CitationItem] = []
    for index, item in enumerate(results, start=1):
        citations.append(
            CitationItem(
                index=index,
                title=item.get("title") or "Untitled",
                page_number=item.get("page_number") or "?",
                source_path=item.get("source_path") or "",
                chunk_id=item.get("chunk_id"),
                score=float(item.get("score", 0.0)),
            )
        )
    return citations


def parse_json_field(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def build_trace_detail(row: dict[str, Any]) -> TraceDetail:
    retrieved_payload = parse_json_field(row.get("retrieved_json"), {})
    return TraceDetail(
        trace_id=int(row["trace_id"]),
        session_id=row.get("session_id") or "default",
        query=row.get("query") or "",
        top_k=int(row.get("top_k") or 0),
        final_answer=row.get("final_answer") or "",
        plan=retrieved_payload.get("plan") or {},
        retrieved_items=retrieved_payload.get("retrieved_items") or [],
        steps=parse_json_field(row.get("steps_json"), []),
        tool_results=parse_json_field(row.get("tool_results_json"), []),
        verification=parse_json_field(row.get("verification_json"), {}),
        created_at=str(row.get("created_at") or ""),
    )


def build_trace_summary(row: dict[str, Any]) -> TraceSummary:
    verification = parse_json_field(row.get("verification_json"), {})
    return TraceSummary(
        trace_id=int(row["trace_id"]),
        session_id=row.get("session_id") or "default",
        query=row.get("query") or "",
        final_answer=row.get("final_answer") or "",
        verification_status=verification.get("status"),
        created_at=str(row.get("created_at") or ""),
    )


app = FastAPI(title="Local Agent V1")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": "Local Agent V1"},
    )


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@app.get("/api/documents", response_model=list[DocumentItem])
def list_documents():
    deps = get_deps()
    docs = deps.sqlite_store.list_documents()
    return [DocumentItem(**doc) for doc in docs]


@app.get("/api/traces", response_model=list[TraceSummary])
def list_traces(limit: int = 12):
    deps = get_deps()
    bounded_limit = min(max(limit, 1), 50)
    return [build_trace_summary(row) for row in deps.sqlite_store.list_traces(limit=bounded_limit)]


@app.get("/api/traces/{trace_id}", response_model=TraceDetail)
def get_trace(trace_id: int):
    deps = get_deps()
    row = deps.sqlite_store.get_trace(trace_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found.")
    return build_trace_detail(row)


@app.post("/api/chat", response_model=ChatResponse)
def chat(request_data: ChatRequest):
    deps = get_deps()

    results = deps.orchestrator.handle_query(
        request_data.query,
        approved_tools=request_data.approved_tools,
    )

    return ChatResponse(
        answer=results["answer"],
        trace_id=results["trace_id"],
        mode=results["mode"],
        reason=results["reason"],
        retrieval_query=results.get("retrieval_query"),
        citations=build_citations(results["citations"]),
    )


@app.post("/api/ingest-path", response_model=IngestPathResponse)
def ingest_path(request_data: IngestPathRequest):
    deps = get_deps()

    pipeline = IngestionPipeline(
        sqlite_store=deps.sqlite_store,
        qdrant_store=deps.qdrant_store,
        embedding_client=deps.embedding_client,
        chunk_size=deps.config.chunk_size,
        chunk_overlap=deps.config.chunk_overlap,
    )

    try:
        pdf_files = discover_pdf_files(request_data.path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not pdf_files:
        raise HTTPException(status_code=404, detail="No PDF files found.")

    success_count = 0
    failed_count = 0
    results: list[IngestFileResult] = []

    for pdf_file in pdf_files:
        try:
            summary = pipeline.ingest_pdf(pdf_file)
            success_count += 1
            results.append(
                IngestFileResult(
                    file_name=pdf_file.name,
                    success=True,
                    message="Indexed successfully",
                    page_count=summary.get("page_count"),
                    chunk_count=summary.get("chunk_count"),
                )
            )
        except Exception as exc:
            failed_count += 1
            results.append(
                IngestFileResult(
                    file_name=pdf_file.name,
                    success=False,
                    message=str(exc),
                )
            )

    return IngestPathResponse(
        success_count=success_count,
        failed_count=failed_count,
        results=results,
    )
