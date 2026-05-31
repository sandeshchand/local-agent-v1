from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    approved_tools: list[str] = Field(default_factory=list)


class CitationItem(BaseModel):
    index: int
    title: str
    page_number: int | str
    source_path: str
    chunk_id: str | None = None
    score: float = 0.0


class ChatResponse(BaseModel):
    answer: str
    trace_id: int
    mode: str
    reason: str =""
    retrieval_query: str | None = None
    citations: list[CitationItem]
    needs_approval: bool = False
    approval_tool_name: str | None = None
    approval_reason: str = ""


class TraceSummary(BaseModel):
    trace_id: int
    session_id: str
    query: str
    final_answer: str
    verification_status: str | None = None
    created_at: str


class TraceDetail(BaseModel):
    trace_id: int
    session_id: str
    query: str
    top_k: int
    final_answer: str
    plan: dict[str, Any] = Field(default_factory=dict)
    retrieved_items: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class TraceFeedbackRequest(BaseModel):
    trace_id: int = Field(..., gt=0)
    rating: Literal["like", "dislike"]
    issue_type: str | None = None


class TraceFeedbackResponse(BaseModel):
    feedback_id: int
    trace_id: int
    rating: str
    issue_type: str = ""
    source: str
    created_at: str
    updated_at: str


class TraceFeedbackItem(BaseModel):
    feedback_id: int
    trace_id: int
    rating: str
    issue_type: str = ""
    source: str
    query: str
    final_answer: str
    created_at: str
    updated_at: str


class FeedbackSummary(BaseModel):
    total_count: int
    like_count: int
    dislike_count: int
    dislike_rate: float
    issue_counts: dict[str, int] = Field(default_factory=dict)
    latest_feedback_at: str
    recent_dislikes: list[TraceFeedbackItem]


class EvalCandidateCreateRequest(BaseModel):
    trace_id: int = Field(..., gt=0)


class EvalCandidateResponse(BaseModel):
    candidate_id: str
    trace_id: int
    status: Literal["created", "updated"]
    path: str
    candidate: dict[str, Any]


class EvalCandidateUpdateRequest(BaseModel):
    doc: str | None = None
    expected_doc_title: str | None = None
    expected_answer: str | None = None
    must_have: list[Any] | None = None
    should_have: list[Any] | None = None
    must_not_have: list[Any] | None = None
    notes: str | None = None
    status: Literal["draft", "reviewed", "promoted"] | None = None


class EvalCandidateItem(BaseModel):
    id: str
    status: str
    source: str | None = None
    trace_id: int | None = None
    feedback_id: int | None = None
    feedback_rating: str | None = None
    feedback_issue_type: str | None = None
    question: str
    doc: str = ""
    expected_doc_title: str = ""
    expected_answer: str = ""
    must_have: list[Any] = Field(default_factory=list)
    should_have: list[Any] = Field(default_factory=list)
    must_not_have: list[Any] = Field(default_factory=list)
    predicted_answer: str = ""
    suggested_evidence: list[dict[str, Any]] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class EvalCandidatePromoteResponse(BaseModel):
    candidate_id: str
    status: Literal["created", "updated"]
    path: str
    gold_item: dict[str, Any]
    candidate: dict[str, Any]


class EvalCandidateRunResponse(BaseModel):
    candidate_id: str
    score: float
    passed: bool
    output_path: str
    result: dict[str, Any]


class IngestPathRequest(BaseModel):
    path: str = Field(..., min_length=1)


class IngestFileResult(BaseModel):
    file_name: str
    success: bool
    message: str
    page_count: int | None = None
    chunk_count: int | None = None


class IngestPathResponse(BaseModel):
    success_count: int
    failed_count: int
    results: list[IngestFileResult]


class DocumentItem(BaseModel):
    doc_id: str
    source_path: str
    title: str
    page_count: int
    checksum: str
    indexed_at: str


class DocumentLibraryResponse(BaseModel):
    total: int
    limit: int
    offset: int
    query: str = ""
    items: list[DocumentItem]


class HealthResponse(BaseModel):
    status: str


class ToolItem(BaseModel):
    name: str
    description: str
    requires_approval: bool = False
    source: str = "local"
    metadata: dict[str, Any] = Field(default_factory=dict)


