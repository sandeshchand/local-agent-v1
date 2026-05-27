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
    EvalCandidateCreateRequest,
    EvalCandidateItem,
    EvalCandidatePromoteResponse,
    EvalCandidateRunResponse,
    EvalCandidateResponse,
    EvalCandidateUpdateRequest,
    FeedbackSummary,
    HealthResponse,
    IngestFileResult,
    IngestPathRequest,
    IngestPathResponse,
    TraceDetail,
    TraceFeedbackItem,
    TraceFeedbackRequest,
    TraceFeedbackResponse,
    TraceSummary,
    ToolItem,
)
from app.bootstrap import bootstrap_app
from app.config import load_config
from app.dependencies import AppDependencies
from app.eval_candidates import (
    create_feedback_eval_candidate,
    list_feedback_eval_candidates,
    promote_feedback_eval_candidate,
    update_feedback_eval_candidate,
)
from app.eval_runner import load_gold_eval_item, run_candidate_eval
from ingestion.file_loader import discover_pdf_files
from ingestion.pipeline import IngestionPipeline
from storage.sqlite_store import SQLiteStore

BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
EVAL_CANDIDATES_PATH = BASE_DIR / "data" / "evals" / "feedback_eval_candidates.json"
GOLD_EVAL_PATH = BASE_DIR / "test" / "eval_multi_doc_rag.json"
EVAL_OUTPUT_DIR = BASE_DIR / "eval"


@lru_cache(maxsize=1)
def get_deps() -> AppDependencies:
    return bootstrap_app(".env")


@lru_cache(maxsize=1)
def get_sqlite_store() -> SQLiteStore:
    config = load_config(".env")
    store = SQLiteStore(config.sqlite_path)
    store.initialize()
    return store


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


@app.get("/api/tools", response_model=list[ToolItem])
def list_tools():
    tools = get_deps().tool_registry.list_tools()
    return [ToolItem(**tool.model_dump()) for tool in tools]


@app.get("/api/documents", response_model=list[DocumentItem])
def list_documents():
    docs = get_sqlite_store().list_documents()
    return [DocumentItem(**doc) for doc in docs]


@app.get("/api/traces", response_model=list[TraceSummary])
def list_traces(limit: int = 12):
    bounded_limit = min(max(limit, 1), 50)
    return [
        build_trace_summary(row)
        for row in get_sqlite_store().list_traces(limit=bounded_limit)
    ]


@app.get("/api/traces/{trace_id}", response_model=TraceDetail)
def get_trace(trace_id: int):
    row = get_sqlite_store().get_trace(trace_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found.")
    return build_trace_detail(row)


@app.post("/api/feedback", response_model=TraceFeedbackResponse)
def save_feedback(request_data: TraceFeedbackRequest):
    try:
        row = get_sqlite_store().upsert_answer_feedback(
            trace_id=request_data.trace_id,
            rating=request_data.rating,
            issue_type=request_data.issue_type,
            source="web",
        )
    except ValueError as exc:
        status_code = 404 if "does not exist" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return TraceFeedbackResponse(**row)


@app.get("/api/feedback", response_model=list[TraceFeedbackItem])
def list_feedback(
    limit: int = 12,
    rating: str | None = None,
):
    bounded_limit = min(max(limit, 1), 50)
    try:
        rows = get_sqlite_store().list_answer_feedback(
            rating=rating,
            limit=bounded_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [TraceFeedbackItem(**row) for row in rows]


@app.get("/api/feedback/summary", response_model=FeedbackSummary)
def feedback_summary():
    return FeedbackSummary(**get_sqlite_store().get_answer_feedback_summary())


@app.post("/api/eval-candidates", response_model=EvalCandidateResponse)
def create_eval_candidate(request_data: EvalCandidateCreateRequest):
    try:
        result = create_feedback_eval_candidate(
            get_sqlite_store(),
            request_data.trace_id,
            path=EVAL_CANDIDATES_PATH,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EvalCandidateResponse(**result)


@app.get("/api/eval-candidates", response_model=list[EvalCandidateItem])
def list_eval_candidates(limit: int = 20):
    rows = list_feedback_eval_candidates(
        EVAL_CANDIDATES_PATH,
        limit=min(max(limit, 1), 100),
    )
    return [EvalCandidateItem(**row) for row in rows]


@app.patch("/api/eval-candidates/{candidate_id}", response_model=EvalCandidateItem)
def update_eval_candidate(candidate_id: str, request_data: EvalCandidateUpdateRequest):
    updates = request_data.model_dump(exclude_none=True)
    try:
        candidate = update_feedback_eval_candidate(
            candidate_id,
            updates,
            path=EVAL_CANDIDATES_PATH,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EvalCandidateItem(**candidate)


@app.post("/api/eval-candidates/{candidate_id}/promote", response_model=EvalCandidatePromoteResponse)
def promote_eval_candidate(candidate_id: str):
    try:
        result = promote_feedback_eval_candidate(
            candidate_id,
            candidates_path=EVAL_CANDIDATES_PATH,
            gold_eval_path=GOLD_EVAL_PATH,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EvalCandidatePromoteResponse(**result)


@app.post("/api/eval-candidates/{candidate_id}/run-eval", response_model=EvalCandidateRunResponse)
def run_eval_candidate(candidate_id: str):
    try:
        load_gold_eval_item(candidate_id, GOLD_EVAL_PATH)
        result = run_candidate_eval(
            get_deps().orchestrator,
            candidate_id,
            gold_eval_path=GOLD_EVAL_PATH,
            output_dir=EVAL_OUTPUT_DIR,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return EvalCandidateRunResponse(**result)


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
