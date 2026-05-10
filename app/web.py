from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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
)
from app.bootstrap import bootstrap_app
from app.dependencies import AppDependencies
from ingestion.file_loader import discover_pdf_files
from ingestion.pipeline import IngestionPipeline
from observability.traces import save_trace

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


@app.post("/api/chat", response_model=ChatResponse)
def chat(request_data: ChatRequest):
    deps = get_deps()

    results = deps.orchestrator.handle_query(request_data.query)

    trace_id = save_trace(
        sqlite_store=deps.sqlite_store,
        query=request_data.query,
        top_k=deps.config.top_k,
        retrieved_items=results["citations"],
        final_answer=results["answer"],
        plan=results["plan"],
    )
    return ChatResponse(
        answer=results["answer"],
        trace_id=trace_id,
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