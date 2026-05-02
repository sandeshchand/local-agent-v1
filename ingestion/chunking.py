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
    section_title: str | None = None

def normalize_page_text(text:str)-> str:
    text= text.replace("\r\n","\n").replace("\r","\n")
    text= text.replace("\x00", " ")

    lines= [line.strip() for line in text.split("\n")]

    cleaned_lines: list[str] = []
    blank_streak = 0
    for line in lines:
        if not line:
            blank_streak += 1
            if blank_streak <=1:
                cleaned_lines.append("")
            continue
     
        blank_streak = 0
        cleaned_lines.append(line)
    
    text= "\n".join(cleaned_lines)
    text= re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
  
def split_paragraphs(text:str)-> list[str]:
    parts = [part.strip() for part in text.split("\n\n")]
    return [part for part in parts if part]

def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    parts = [part.strip() for part in parts if part.strip()]
    return parts if parts else [text.strip()]


def _find_safe_end(text: str, start: int, proposed_end: int, window: int = 80) -> int:
    if proposed_end >= len(text):
        return len(text)

    search_end = min(len(text), proposed_end + window)
    segment = text[proposed_end:search_end]

    match = re.search(r"[.!?。！？]", segment)
    if match:
        return proposed_end + match.start() + 1

    match = re.search(r"[\s,;:)]", segment)
    if match:
        return proposed_end + match.start()

    return proposed_end


def _find_safe_start(text: str, proposed_start: int, window: int = 80) -> int:
    if proposed_start <= 0:
        return 0

    search_start = max(0, proposed_start - window)
    segment = text[search_start:proposed_start]

    matches = list(re.finditer(r"[.!?。！？]\s+", segment))
    if matches:
        return search_start + matches[-1].end()

    matches = list(re.finditer(r"\s+", segment))
    if matches:
        return search_start + matches[-1].end()

    return proposed_start


def chunk_large_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        proposed_end = min(start + chunk_size, text_len)
        end = _find_safe_end(text, start, proposed_end)

        if end <= start:
            end = proposed_end

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break

        next_start = max(0, end - chunk_overlap)
        next_start = _find_safe_start(text, next_start)

        if next_start <= start:
            next_start = end

        start = next_start

    return chunks
def recursive_split_text(text:str, chunk_size: int, chunk_overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    paragraphs = split_paragraphs(text)
    if len(paragraphs) >1:
        results: list[str] = []
        current = ""

        for para in paragraphs:
            candidiate = f"{current}\n\n{para}".strip() if current else para
            if len(candidiate) <= chunk_size:
                current = candidiate
            else:
                if current:
                    results.append(current)
                if len(para)<= chunk_size:
                    current = para
                else:
                    results.extend(recursive_split_text(para, chunk_size, chunk_overlap))
                    current = ""
        if current:
            results.append(current)
        return results

    sentences = split_sentences(text)
    if len(sentences) >1:
        results: list[str] = []
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    results.append(current)
                if len(sentence) <= chunk_size:
                    current = sentence
                else:
                    results.extend(chunk_large_text(sentence, chunk_size, chunk_overlap))
                    current =""
        if current:
            results.append(current)
        return results
    
    return chunk_large_text(text, chunk_size, chunk_overlap)

def chunk_pages(
    pages: list[ParsedPage],
    doc_id: str,
    chunk_size: int = 900,
    chunk_overlap: int = 120,
    ) -> list[ChunkRecord]:
        chunks: list[ChunkRecord] = []
        chunk_index = 0

        for page in pages:
            cleaned = normalize_page_text(page.text)
            if not cleaned:
                continue
            text_chunks = recursive_split_text(
                text=cleaned,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap)

            for chunk_text in text_chunks:
                chunk_text= chunk_text.strip()
                if not chunk_text:
                    continue

                chunks.append(
                    ChunkRecord(
                        chunk_id=f"{doc_id}-p{page.page_number}-c{chunk_index}",
                        doc_id=doc_id,
                        chunk_index=chunk_index,
                        page_number=page.page_number,
                        text=chunk_text,
                        token_estimate=max(1, len(chunk_text) // 4),
                        section_title=page.section_title,
                    )
                )
                chunk_index += 1

        return chunks

