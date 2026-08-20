from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from local_agent.app.api_models import (
    ChatRequest,
    ChatResponse,
    CitationItem,
    DocumentItem,
    DocumentLibraryResponse,
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
    IngestionStatusItem,
    IngestionStatusResponse,
    MemoryDeleteResponse,
    MemoryItem,
    MemoryListResponse,
    SystemStatusResponse,
    ToolAuditResponse,
    TraceDetail,
    TraceFeedbackItem,
    TraceFeedbackRequest,
    TraceFeedbackResponse,
    TraceSummary,
    ToolItem,
)
from local_agent.app.auth import AuthIdentity, authenticate_request, sanitize_session_id, sanitize_user_id
from local_agent.app.bootstrap import bootstrap_app
from local_agent.app.config import load_config
from local_agent.app.dependencies import AppDependencies
from local_agent.evaluation.eval_candidates import (
    create_feedback_eval_candidate,
    load_feedback_eval_candidates,
    list_feedback_eval_candidates,
    promote_feedback_eval_candidate,
    update_feedback_eval_candidate,
)
from local_agent.evaluation.eval_runner import load_gold_eval_item, run_candidate_eval
from local_agent.app.paths import EVAL_CANDIDATES_PATH, EVAL_OUTPUT_DIR, GOLD_EVAL_PATH, STATIC_DIR, TEMPLATES_DIR
from local_agent.app.system_status import build_system_status
from local_agent.app.tool_audit import build_tool_audit
from local_agent.ingestion.file_loader import discover_pdf_files
from local_agent.ingestion.pipeline import IngestionPipeline
from local_agent.storage.sqlite_store import SQLiteStore


@lru_cache(maxsize=1)
def get_deps() -> AppDependencies:
    return bootstrap_app(".env")


@lru_cache(maxsize=1)
def get_web_config():
    return load_config(".env")


@lru_cache(maxsize=1)
def get_sqlite_store() -> SQLiteStore:
    config = get_web_config()
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


def approval_payload(results: dict[str, Any]) -> dict[str, Any]:
    steps = results.get("steps") or []
    guardrail_steps = [step for step in steps if step.get("type") == "guardrail"]
    if not guardrail_steps:
        return {
            "needs_approval": False,
            "approval_tool_name": None,
            "approval_reason": "",
        }

    latest = guardrail_steps[-1]
    if latest.get("status") != "needs_approval":
        return {
            "needs_approval": False,
            "approval_tool_name": None,
            "approval_reason": "",
        }

    return {
        "needs_approval": True,
        "approval_tool_name": latest.get("tool_name"),
        "approval_reason": latest.get("reason") or "This action requires approval before execution.",
    }


app = FastAPI(title="Local Agent V1")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.middleware("http")
async def api_auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        try:
            request.state.auth_identity = authenticate_request(request, get_web_config())
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=503,
                content={"detail": str(exc)},
            )
    return await call_next(request)


def current_auth_identity(request: Request | None = None) -> AuthIdentity:
    if request is None:
        return AuthIdentity(
            enabled=False,
            authenticated=False,
            user_id="local",
            requested_session_id="default",
            session_id="default",
        )
    identity = getattr(request.state, "auth_identity", None)
    if isinstance(identity, AuthIdentity):
        return identity
    fallback_session = sanitize_session_id(request.headers.get("X-Local-Agent-Session"))
    return AuthIdentity(
        enabled=False,
        authenticated=False,
        user_id=sanitize_user_id(request.headers.get("X-Local-Agent-User"), fallback="local"),
        requested_session_id=fallback_session,
        session_id=fallback_session,
    )


def session_filter_for_identity(identity: AuthIdentity) -> str | None:
    return identity.session_id if identity.enabled else None


def document_access_kwargs(identity: AuthIdentity) -> dict[str, Any]:
    if not identity.enabled:
        return {"owner_id": None, "include_global": True}
    return {"owner_id": identity.user_id, "include_global": True}


def accessible_doc_ids_for_identity(identity: AuthIdentity, store: SQLiteStore) -> list[str] | None:
    if not identity.enabled:
        return None
    return store.accessible_document_ids(owner_id=identity.user_id, include_global=True)


def ingestion_namespace_for_identity(identity: AuthIdentity) -> tuple[str, str]:
    if identity.enabled:
        return identity.user_id, "user"
    return "global", "global"


def requested_session_id(identity: AuthIdentity, raw_session_id: str = "default") -> str:
    if identity.enabled:
        return identity.session_id
    return sanitize_session_id(raw_session_id, fallback="default")


def ensure_trace_access(trace: dict[str, Any], identity: AuthIdentity) -> None:
    if identity.enabled and trace.get("session_id") != identity.session_id:
        raise HTTPException(status_code=404, detail="Trace not found.")


def ensure_memory_access(memory: dict[str, Any], identity: AuthIdentity) -> None:
    if not identity.enabled:
        return
    if memory.get("scope") == "global":
        return
    if memory.get("session_id") != identity.session_id:
        raise HTTPException(status_code=404, detail="Memory item not found.")


def eval_candidate_visible(candidate: dict[str, Any], identity: AuthIdentity) -> bool:
    if not identity.enabled:
        return True
    trace_id = candidate.get("trace_id")
    if trace_id is None:
        return False
    try:
        trace = get_sqlite_store().get_trace(int(trace_id))
    except (TypeError, ValueError):
        return False
    return trace is not None and trace.get("session_id") == identity.session_id


def ensure_eval_candidate_access(candidate_id: str, identity: AuthIdentity) -> None:
    if not identity.enabled:
        return
    candidates = load_feedback_eval_candidates(EVAL_CANDIDATES_PATH)
    candidate = next((item for item in candidates if item.get("id") == candidate_id), None)
    if candidate is None or not eval_candidate_visible(candidate, identity):
        raise HTTPException(status_code=404, detail=f"Eval candidate {candidate_id} not found.")


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


@app.get("/api/system/status", response_model=SystemStatusResponse)
def system_status(check_models: bool = True):
    return SystemStatusResponse(**build_system_status(get_deps(), check_models=check_models))


@app.get("/api/tools", response_model=list[ToolItem])
def list_tools():
    tools = get_deps().tool_registry.list_tools()
    return [ToolItem(**tool.model_dump()) for tool in tools]


@app.get("/api/tools/audit", response_model=ToolAuditResponse)
def tool_audit(request: Request = None, limit: int = 50):
    bounded_limit = min(max(limit, 1), 200)
    identity = current_auth_identity(request)
    return ToolAuditResponse(
        **build_tool_audit(
            get_sqlite_store(),
            get_deps().tool_registry,
            limit=bounded_limit,
            session_id=session_filter_for_identity(identity),
        )
    )


@app.get("/api/documents", response_model=list[DocumentItem])
def list_documents(request: Request = None):
    identity = current_auth_identity(request)
    docs = get_sqlite_store().list_documents(**document_access_kwargs(identity))
    return [DocumentItem(**doc) for doc in docs]


@app.get("/api/library/documents", response_model=DocumentLibraryResponse)
def list_library_documents(
    request: Request = None,
    q: str = "",
    limit: int = 12,
    offset: int = 0,
):
    bounded_limit = min(max(limit, 1), 100)
    bounded_offset = max(offset, 0)
    query = q.strip()
    store = get_sqlite_store()
    access_kwargs = document_access_kwargs(current_auth_identity(request))
    total = store.count_documents(search=query, **access_kwargs)
    docs = store.list_documents(
        search=query,
        limit=bounded_limit,
        offset=bounded_offset,
        **access_kwargs,
    )
    return DocumentLibraryResponse(
        total=total,
        limit=bounded_limit,
        offset=bounded_offset,
        query=query,
        items=[DocumentItem(**doc) for doc in docs],
    )


@app.get("/api/ingestion/status", response_model=IngestionStatusResponse)
def list_ingestion_status(
    request: Request = None,
    limit: int = 50,
    status: str = "",
):
    bounded_limit = min(max(limit, 1), 200)
    normalized_status = status.strip()
    store = get_sqlite_store()
    access_kwargs = document_access_kwargs(current_auth_identity(request))
    rows = store.list_document_ingestion_status(
        limit=bounded_limit,
        status=normalized_status or None,
        **access_kwargs,
    )
    summary = store.get_document_ingestion_status_summary(**access_kwargs)
    return IngestionStatusResponse(
        total=int(summary.get("total_count", len(rows))),
        limit=bounded_limit,
        status=normalized_status,
        summary=summary,
        items=[IngestionStatusItem(**row) for row in rows],
    )


@app.get("/api/memory", response_model=MemoryListResponse)
def list_memory(
    request: Request = None,
    session_id: str = "default",
    include_global: bool = True,
    limit: int = 50,
):
    bounded_limit = min(max(limit, 1), 200)
    normalized_session_id = requested_session_id(current_auth_identity(request), session_id)
    rows = get_sqlite_store().list_memory_items(
        session_id=normalized_session_id,
        include_global=include_global,
        limit=bounded_limit,
    )
    return MemoryListResponse(
        total=len(rows),
        session_id=normalized_session_id,
        include_global=include_global,
        items=[MemoryItem(**row) for row in rows],
    )


@app.delete("/api/memory/{memory_id}", response_model=MemoryDeleteResponse)
def delete_memory(memory_id: int, request: Request = None):
    store = get_sqlite_store()
    identity = current_auth_identity(request)
    existing = store.get_memory_item(memory_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Memory item {memory_id} not found.")
    ensure_memory_access(existing, identity)
    row = store.delete_memory_item(memory_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Memory item {memory_id} not found.")
    return MemoryDeleteResponse(deleted=True, item=MemoryItem(**row))


@app.get("/api/traces", response_model=list[TraceSummary])
def list_traces(request: Request = None, limit: int = 12):
    bounded_limit = min(max(limit, 1), 50)
    identity = current_auth_identity(request)
    return [
        build_trace_summary(row)
        for row in get_sqlite_store().list_traces(
            limit=bounded_limit,
            session_id=session_filter_for_identity(identity),
        )
    ]


@app.get("/api/traces/{trace_id}", response_model=TraceDetail)
def get_trace(trace_id: int, request: Request = None):
    row = get_sqlite_store().get_trace(trace_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found.")
    ensure_trace_access(row, current_auth_identity(request))
    return build_trace_detail(row)


@app.post("/api/feedback", response_model=TraceFeedbackResponse)
def save_feedback(request_data: TraceFeedbackRequest, request: Request = None):
    trace = get_sqlite_store().get_trace(request_data.trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"trace {request_data.trace_id} does not exist")
    ensure_trace_access(trace, current_auth_identity(request))
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
    request: Request = None,
    limit: int = 12,
    rating: str | None = None,
):
    bounded_limit = min(max(limit, 1), 50)
    identity = current_auth_identity(request)
    try:
        rows = get_sqlite_store().list_answer_feedback(
            rating=rating,
            limit=bounded_limit,
            session_id=session_filter_for_identity(identity),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [TraceFeedbackItem(**row) for row in rows]


@app.get("/api/feedback/summary", response_model=FeedbackSummary)
def feedback_summary(request: Request = None):
    identity = current_auth_identity(request)
    return FeedbackSummary(
        **get_sqlite_store().get_answer_feedback_summary(
            session_id=session_filter_for_identity(identity),
        )
    )


@app.post("/api/eval-candidates", response_model=EvalCandidateResponse)
def create_eval_candidate(request_data: EvalCandidateCreateRequest, request: Request = None):
    trace = get_sqlite_store().get_trace(request_data.trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace {request_data.trace_id} not found.")
    ensure_trace_access(trace, current_auth_identity(request))
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
def list_eval_candidates(request: Request = None, limit: int = 20):
    bounded_limit = min(max(limit, 1), 100)
    identity = current_auth_identity(request)
    if identity.enabled:
        candidates = load_feedback_eval_candidates(EVAL_CANDIDATES_PATH)
        rows = [
            candidate
            for candidate in candidates
            if eval_candidate_visible(candidate, identity)
        ][:bounded_limit]
    else:
        rows = list_feedback_eval_candidates(
            EVAL_CANDIDATES_PATH,
            limit=bounded_limit,
        )
    return [EvalCandidateItem(**row) for row in rows]


@app.patch("/api/eval-candidates/{candidate_id}", response_model=EvalCandidateItem)
def update_eval_candidate(candidate_id: str, request_data: EvalCandidateUpdateRequest, request: Request = None):
    ensure_eval_candidate_access(candidate_id, current_auth_identity(request))
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
def promote_eval_candidate(candidate_id: str, request: Request = None):
    ensure_eval_candidate_access(candidate_id, current_auth_identity(request))
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
def run_eval_candidate(candidate_id: str, request: Request = None):
    ensure_eval_candidate_access(candidate_id, current_auth_identity(request))
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
def chat(request_data: ChatRequest, request: Request = None):
    deps = get_deps()
    identity = current_auth_identity(request)
    store = get_sqlite_store()
    accessible_doc_ids = accessible_doc_ids_for_identity(identity, store)

    results = deps.orchestrator.handle_query(
        request_data.query,
        approved_tools=request_data.approved_tools,
        session_id=identity.session_id,
        accessible_doc_ids=accessible_doc_ids,
    )

    return ChatResponse(
        answer=results["answer"],
        trace_id=results["trace_id"],
        user_id=identity.user_id,
        requested_session_id=identity.requested_session_id,
        session_id=results.get("session_id") or identity.session_id,
        mode=results["mode"],
        reason=results["reason"],
        retrieval_query=results.get("retrieval_query"),
        citations=build_citations(results["citations"]),
        **approval_payload(results),
    )


@app.post("/api/ingest-path", response_model=IngestPathResponse)
def ingest_path(request_data: IngestPathRequest, request: Request = None):
    deps = get_deps()
    identity = current_auth_identity(request)
    owner_id, visibility = ingestion_namespace_for_identity(identity)

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
    skipped_count = 0
    failed_count = 0
    results: list[IngestFileResult] = []

    for pdf_file in pdf_files:
        try:
            summary = pipeline.ingest_pdf(
                pdf_file,
                force=request_data.force,
                owner_id=owner_id,
                visibility=visibility,
            )
            status = str(summary.get("status") or "indexed")
            if status == "skipped":
                skipped_count += 1
            else:
                success_count += 1
            results.append(
                IngestFileResult(
                    file_name=pdf_file.name,
                    success=status != "failed",
                    status=status,
                    message=str(summary.get("message") or "Indexed successfully"),
                    owner_id=str(summary.get("owner_id") or owner_id),
                    visibility=str(summary.get("visibility") or visibility),
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
                    status="failed",
                    owner_id=owner_id,
                    visibility=visibility,
                    message=str(exc),
                )
            )

    return IngestPathResponse(
        success_count=success_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        results=results,
    )
