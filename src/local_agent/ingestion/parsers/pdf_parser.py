from __future__ import  annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pypdf import PdfReader
import re

MIN_SEARCHABLE_TEXT_CHARS = 25

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

BOILERPLATE_HEADING_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"^https?://",
        r"https?://\S+",
        r"^\d{1,2}/\d{1,2}/\d{2,4},\s+\d{1,2}:\d{2}\s+[AP]M\b",
        r"^\d+\s*/\s*\d+$",
        r"^member-only story\b",
        r"^listen\s+share\s+more\b",
        r"^follow$",
        r"^responses?\s*\(\d+\)$",
        r"^see all from\b",
        r"^more from\b",
        r"^recommended from medium\b",
        r"^read next:?$",
        r"^photo by\b",
        r"^image by\b",
        r"^published in\b",
        r"^open in app$",
        r"^search$",
        r"^previous$",
        r"^written by\b",
        r"^in by$",
        r"^subscribe\b",
        r"^upgrade to paid\b",
        r"^before you go:?$",
        r"^further reads?:?$",
        r"^see more recommendations\b",
        r"^create your own chatbot\b",
        r"^\d+\s+min read\b",
        r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\b",
    ]
]

TERMINAL_HEADING_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"^no responses yet$",
        r"^responses?\s*(\(\d+\))?$",
        r"^read next:?$",
        r"^more from\b",
        r"^recommended from\b",
        r"^see more recommendations\b",
        r"^before you go:?$",
        r"^further reads?:?$",
    ]
]


def is_boilerplate_heading(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line.strip())
    if not normalized:
        return False
    if any(pattern.search(normalized) for pattern in BOILERPLATE_HEADING_PATTERNS):
        return True
    if " | by " in normalized and " | " in normalized and len(normalized) > 90:
        return True
    return False


def is_terminal_heading(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line.strip())
    return any(pattern.search(normalized) for pattern in TERMINAL_HEADING_PATTERNS)


def is_heading_line(line:str)->bool:
    line = line.strip()
    if not line:
        return False
    if len(line) > 120:
        return False
    if is_boilerplate_heading(line):
        return False

    if NUMBERED_HEADING_PATTERN.match(line):
        return True

    if HEADING_PATTERN.match(line):
        # reject lines that look like normal paragraphs
        word_count = len(line.split())
        titleish_words = sum(1 for word in line.split() if word[:1].isupper() or word.isupper())
        if word_count <=12 and not line.endswith(".") and titleish_words >= max(1, word_count // 2):
            return True
    return False

def extract_page_sections_title(text:str, fallback:str | None = None) ->str| None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    clean_lines = []
    for line in lines:
        if is_terminal_heading(line):
            break
        if not is_boilerplate_heading(line):
            clean_lines.append(line)
    for line in clean_lines[:16]:
        if is_heading_line(line):
            return line
    return fallback
            
        

def has_searchable_text(text: str) -> bool:
    return len(re.sub(r"\s+", "", text or "")) >= MIN_SEARCHABLE_TEXT_CHARS


def ocr_page_text(pdf_path: Path, page_number: int) -> str:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except Exception:
        return ""

    try:
        images = convert_from_path(
            str(pdf_path),
            first_page=page_number,
            last_page=page_number,
            dpi=200,
        )
        if not images:
            return ""
        return pytesseract.image_to_string(images[0]) or ""
    except Exception:
        return ""


def scanned_pdf_error(path: Path) -> RuntimeError:
    return RuntimeError(
        "No searchable text was extracted from this PDF. It may be scanned or image-only. "
        "Install optional OCR support with `pip install .[ocr]`, then install Tesseract OCR "
        "and Poppler on the machine, and ingest the PDF again: "
        f"{path}"
    )





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
        if not has_searchable_text(text):
            text = ocr_page_text(path, index)
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

    if pages and not any(has_searchable_text(page.text) for page in pages):
        raise scanned_pdf_error(path)

    return ParsedDocument(
        doc_id=doc_id,
        source_path=str(path),
        title=title,
        page_count=len(reader.pages),
        checksum=checksum,
        pages=pages,
    )

