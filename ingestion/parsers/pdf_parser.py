from __future__ import  annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pypdf import PdfReader

@dataclass(slots=True)
class ParsedPage:
    page_number: int
    text: str

@dataclass(slots=True)
class ParsedDocument:
    doc_id: str
    source_path: str
    title: str
    page_count: int
    checksum: str
    pages: list[ParsedPage]


def parse_pdf(pdf_path: str | Path)-> ParsedDocument:
    path = Path(pdf_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"PDF not found:{path}")
    checksum = sha256(path.read_bytes()).hexdigest()
    doc_id = checksum[:16]

    reader = PdfReader(str(path))
    metadata = reader.metadata
    title = ""
    if metadata is not None:
        title = getattr(metadata, "title","") or ""
    if not title:
        title = path.stem

    pages: list[ParsedPage] = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(
            ParsedPage(
                page_number=index,
                text=text,
            )
        )

    return ParsedDocument(
        doc_id=doc_id,
        source_path=str(path),
        title=title,
        page_count=len(reader.pages),
        checksum=checksum,
        pages=pages,
    )

