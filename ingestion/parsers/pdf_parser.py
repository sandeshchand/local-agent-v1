from __future__ import  annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pypdf import PdfReader
import re

@dataclass(slots=True)
class ParsedPage:
    page_number: int
    text: str
    section_title:str|None = None   


@dataclass(slots=True)
class ParsedDocument:
    doc_id: str
    source_path: str
    title: str
    page_count: int
    checksum: str
    pages: list[ParsedPage]

HEADING_PATTERN = re.compile(
    r"^\s*((\d+(\.\d+){0,3})\s+)?[A-Z][A-Za-z0-9 ,:/()'’\-]{3,}$"
)

NUMBERED_HEADING_PATTERN = re.compile(
    r"^\s*\d+(\.\d+){0,3}\s+[A-Z][A-Za-z0-9 ,:/()'’\-]{2,}$"
)

def is_heading_line(line:str)->bool:
    line = line.strip()
    if not line:
        return False
    if len(line) > 120:
        return False

    if NUMBERED_HEADING_PATTERN.match(line):
        return True

    if HEADING_PATTERN.match(line):
        # reject lines that look like normal paragraphs
        word_count = len(line.split())
        if word_count <=12 and not line.endswith("."):
            return True
    return False

def extract_page_sections_title(text:str, fallback:str | None = None) ->str| None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:12]:
        if is_heading_line(line):
            return line
    return fallback
            
        




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
    current_section_title:str |None = None

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        page_section_title = extract_page_sections_title(
            text=text,
            fallback=current_section_title
        )
        if page_section_title:
            current_section_title = page_section_title
        pages.append(
            ParsedPage(
                page_number=index,
                text=text,
                section_title=page_section_title,
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

