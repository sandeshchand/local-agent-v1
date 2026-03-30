from __future__ import annotations

from dataclasses import asdict
from pathlib import  Path

from app.ollama_client import OllamaEmbeddingClient
from ingestion.chunking import  chunk_pages
from ingestion.parsers.pdf_parser import parse_pdf
from  storage.qdrant_store import QdrantStore
from storage.sqlite_store import SQLiteStore


class IngestionPipeline:
    def __init__(self,
         sqlite_store: SQLiteStore,
         qdrant_store: QdrantStore,
         embedding_client: OllamaEmbeddingClient,
         chunk_size : int = 800,
         chunk_overlap: int = 120,
         ) -> None:
        self.sqlite_store = sqlite_store
        self.qdrant_store = qdrant_store
        self.embedding_client = embedding_client
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def ingest_pdf(self, pdf_path: str | Path) -> dict:
        parsed_doc = parse_pdf(pdf_path)

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

        qdrant_records = []
        sqlite_chunks = []

        for point_id,(chunk, vector) in enumerate(zip(chunks, vectors), start=1):
            payload = {
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "source_path": parsed_doc.source_path,
                "title": parsed_doc.title,
                "page_number": chunk.page_number,
                "text": chunk.text,
            }

            qdrant_records.append(
                {
                    "id": point_id,
                    "vector": vector,
                    "payload": payload,
                }
            )

            sqlite_chunks.append(asdict(chunk))

        self.sqlite_store.upsert_document(
            doc_id=parsed_doc.doc_id,
            source_path=parsed_doc.source_path,
            title=parsed_doc.title,
            page_count=parsed_doc.page_count,
            checksum=parsed_doc.checksum,
        )
        self.sqlite_store.delete_chunks_for_doc(parsed_doc.doc_id)
        self.sqlite_store.insert_chunks(sqlite_chunks)

        self.qdrant_store.upsert_chunks(qdrant_records)

        return {
            "doc_id": parsed_doc.doc_id,
            "title": parsed_doc.title,
            "source_path": parsed_doc.source_path,
            "page_count": parsed_doc.page_count,
            "chunk_count": len(chunks),
            "embedding_dimension": len(vectors[0]),
        }




