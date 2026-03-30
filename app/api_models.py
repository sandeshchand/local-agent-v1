from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)


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
    citations: list[CitationItem]


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


