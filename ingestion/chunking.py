from __future__ import annotations

from dataclasses import dataclass
import re

from ingestion.parsers.pdf_parser import ParsedPage

@dataclass(slots=True)
class ChunkRecord:
    chunk_id: str
    doc_id: str
    chunk_index: int
    page_number: int
    text: str
    token_estimate: int


def normalize_text(text: str)-> str:
    text= text.replace("\x00", " ")
    text= re.sub(r"\s+"," ", text)
    return text.strip()


def chunk_pages(
    pages: list[ParsedPage],
    doc_id: str,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
    ) -> list[ChunkRecord]:
        chunks: list[ChunkRecord] = []
        chunk_index = 0

        for page in pages:
            cleaned = normalize_text(page.text)
            if not cleaned:
                continue

            start = 0
            while start < len(cleaned):
                end = min(start + chunk_size, len(cleaned))
                chunk_text = cleaned[start:end].strip()

                if chunk_text:
                    chunks.append(
                        ChunkRecord(
                            chunk_id=f"{doc_id}-p{page.page_number}-c{chunk_index}",
                            doc_id=doc_id,
                            chunk_index=chunk_index,
                            page_number=page.page_number,
                            text=chunk_text,
                            token_estimate=max(1, len(chunk_text) // 4),


                        )
                    )
                    chunk_index +=1

                if end >= len(cleaned):
                    break

                start = max(0, end - chunk_overlap)
            return chunks

