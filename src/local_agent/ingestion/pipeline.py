from __future__ import annotations

from dataclasses import asdict
import hashlib
from pathlib import  Path

from local_agent.llm import OllamaEmbeddingClient
from local_agent.ingestion.chunking import  chunk_pages
from local_agent.ingestion.metadata import CHUNKING_VERSION, PARSER_VERSION
from local_agent.ingestion.parsers.pdf_parser import parse_pdf
from local_agent.storage.qdrant_store import QdrantStore
from local_agent.storage.sqlite_store import (
    SQLiteStore,
    document_visible_to,
    normalize_document_owner_id,
    normalize_document_visibility,
)


class IngestionPipeline:
    def __init__(self,
         sqlite_store: SQLiteStore,
         qdrant_store: QdrantStore,
         embedding_client: OllamaEmbeddingClient,
         chunk_size : int = 900,
         chunk_overlap: int = 120,
         ) -> None:
        self.sqlite_store = sqlite_store
        self.qdrant_store = qdrant_store
        self.embedding_client = embedding_client
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def _make_point_id(self, chunk_id:str) -> int:
        return int(hashlib.md5(chunk_id.encode("utf-8")).hexdigest()[:12], 16)

    def ingest_pdf(
        self,
        pdf_path: str | Path,
        *,
        force: bool = False,
        owner_id: str = "global",
        visibility: str = "global",
    ) -> dict:
        source_path = str(Path(pdf_path).expanduser().resolve())
        normalized_owner_id = normalize_document_owner_id(owner_id)
        normalized_visibility = normalize_document_visibility(visibility)
        existing_doc = self.sqlite_store.get_document_by_source_path(source_path)
        if existing_doc and not document_visible_to(existing_doc, normalized_owner_id):
            raise PermissionError("Document path is already indexed for another user namespace.")
        if existing_doc:
            normalized_owner_id = normalize_document_owner_id(existing_doc.get("owner_id"))
            normalized_visibility = normalize_document_visibility(existing_doc.get("visibility"))

        self.sqlite_store.record_document_ingestion_started(
            source_path=source_path,
            parser_version=PARSER_VERSION,
            chunking_version=CHUNKING_VERSION,
            embedding_model=self.embedding_client.model_name,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            owner_id=normalized_owner_id,
            visibility=normalized_visibility,
        )

        try:
            summary = self._ingest_pdf(
                source_path,
                force=force,
                owner_id=normalized_owner_id,
                visibility=normalized_visibility,
            )
        except Exception as exc:
            self.sqlite_store.record_document_ingestion_failed(
                source_path=source_path,
                error=str(exc),
                parser_version=PARSER_VERSION,
                chunking_version=CHUNKING_VERSION,
                embedding_model=self.embedding_client.model_name,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                owner_id=normalized_owner_id,
                visibility=normalized_visibility,
            )
            raise

        return summary

    def _ingest_pdf(
        self,
        pdf_path: str | Path,
        *,
        force: bool,
        owner_id: str,
        visibility: str,
    ) -> dict:
        parsed_doc = parse_pdf(pdf_path)
        existing_doc = self.sqlite_store.get_document_by_source_path(parsed_doc.source_path)
        if existing_doc and not document_visible_to(existing_doc, owner_id):
            raise PermissionError("Document path is already indexed for another user namespace.")
        effective_owner_id = normalize_document_owner_id(owner_id)
        effective_visibility = normalize_document_visibility(visibility)
        if existing_doc:
            effective_owner_id = normalize_document_owner_id(existing_doc.get("owner_id"))
            effective_visibility = normalize_document_visibility(existing_doc.get("visibility"))
        if not force and self._is_current_index(existing_doc, parsed_doc.checksum):
            chunk_count = int(existing_doc.get("chunk_count") or 0) if existing_doc else 0
            self.sqlite_store.record_document_ingestion_completed(
                source_path=parsed_doc.source_path,
                doc_id=parsed_doc.doc_id,
                title=parsed_doc.title,
                status="skipped",
                checksum=parsed_doc.checksum,
                page_count=parsed_doc.page_count,
                chunk_count=chunk_count,
                parser_version=PARSER_VERSION,
                chunking_version=CHUNKING_VERSION,
                embedding_model=self.embedding_client.model_name,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                owner_id=effective_owner_id,
                visibility=effective_visibility,
            )
            return {
                "doc_id": parsed_doc.doc_id,
                "title": parsed_doc.title,
                "source_path": parsed_doc.source_path,
                "page_count": parsed_doc.page_count,
                "chunk_count": chunk_count,
                "embedding_dimension": None,
                "status": "skipped",
                "owner_id": effective_owner_id,
                "visibility": effective_visibility,
                "message": "Already indexed with current parser, chunking, and embedding settings.",
            }

        chunks = chunk_pages(
            pages=parsed_doc.pages,
            doc_id=parsed_doc.doc_id,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

        if not chunks:
            raise RuntimeError("No text chunks were created from the PDF.")

        vectors = self.embedding_client.embed_many([chunk.text for chunk in chunks])
        if not vectors:
            raise RuntimeError("No embeddings were returned.")

        self.qdrant_store.initialize_collection(vector_size=len(vectors[0]))
        if existing_doc and existing_doc.get("doc_id") != parsed_doc.doc_id:
            old_doc_id = str(existing_doc.get("doc_id") or "")
            self.sqlite_store.delete_chunks_for_doc(old_doc_id)
            self.qdrant_store.delete_chunks_for_doc(old_doc_id)
        self.qdrant_store.delete_chunks_for_doc(parsed_doc.doc_id)

        qdrant_records = []
        sqlite_chunks = []

        for chunk, vector in zip(chunks, vectors):
            payload = {
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "source_path": parsed_doc.source_path,
                "title": parsed_doc.title,
                "owner_id": effective_owner_id,
                "visibility": effective_visibility,
                "page_number": chunk.page_number,
                "section_title": chunk.section_title,
                "text": chunk.text,
            }

            qdrant_records.append(
                {
                    "id": self._make_point_id(chunk.chunk_id),
                    "vector": vector,
                    "payload": payload,
                }
            )

            sqlite_chunks.append(asdict(chunk))

        self.qdrant_store.upsert_chunks(qdrant_records)

        self.sqlite_store.upsert_document(
            doc_id=parsed_doc.doc_id,
            source_path=parsed_doc.source_path,
            title=parsed_doc.title,
            page_count=parsed_doc.page_count,
            checksum=parsed_doc.checksum,
            parser_version=PARSER_VERSION,
            chunking_version=CHUNKING_VERSION,
            embedding_model=self.embedding_client.model_name,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            chunk_count=len(chunks),
            ingestion_status="indexed",
            owner_id=effective_owner_id,
            visibility=effective_visibility,
        )
        self.sqlite_store.delete_chunks_for_doc(parsed_doc.doc_id)
        self.sqlite_store.insert_chunks(sqlite_chunks)
        self.sqlite_store.record_document_ingestion_completed(
            source_path=parsed_doc.source_path,
            doc_id=parsed_doc.doc_id,
            title=parsed_doc.title,
            status="indexed",
            checksum=parsed_doc.checksum,
            page_count=parsed_doc.page_count,
            chunk_count=len(chunks),
            parser_version=PARSER_VERSION,
            chunking_version=CHUNKING_VERSION,
            embedding_model=self.embedding_client.model_name,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            owner_id=effective_owner_id,
            visibility=effective_visibility,
        )

        return {
            "doc_id": parsed_doc.doc_id,
            "title": parsed_doc.title,
            "source_path": parsed_doc.source_path,
            "page_count": parsed_doc.page_count,
            "chunk_count": len(chunks),
            "embedding_dimension": len(vectors[0]),
            "status": "indexed",
            "owner_id": effective_owner_id,
            "visibility": effective_visibility,
            "message": "Indexed successfully",
        }

    def _is_current_index(self, existing_doc: dict | None, checksum: str) -> bool:
        if not existing_doc:
            return False
        return (
            existing_doc.get("checksum") == checksum
            and existing_doc.get("parser_version") == PARSER_VERSION
            and existing_doc.get("chunking_version") == CHUNKING_VERSION
            and existing_doc.get("embedding_model") == self.embedding_client.model_name
            and int(existing_doc.get("chunk_size") or 0) == int(self.chunk_size)
            and int(existing_doc.get("chunk_overlap") or 0) == int(self.chunk_overlap)
            and int(existing_doc.get("chunk_count") or 0) > 0
            and (existing_doc.get("ingestion_status") or "indexed") == "indexed"
        )


