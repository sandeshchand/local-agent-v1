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


class TraceFeedbackResponse(BaseModel):
    feedback_id: int
    trace_id: int
    rating: str
    source: str
    created_at: str
    updated_at: str


class TraceFeedbackItem(BaseModel):
    feedback_id: int
    trace_id: int
    rating: str
    source: str
    query: str
    final_answer: str
    created_at: str
    updated_at: str


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


class HealthResponse(BaseModel):
    status: str


