from __future__ import annotations

from pathlib import Path


def discover_pdf_files(path: str | Path) -> list[Path]:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {target}")
    if target.is_file():
        if target.suffix.lower() != ".pdf":
            raise ValueError(f"Not a pdf file:{target}")
        return [target]

    pdf_files = sorted(p for p in target.rglob("*.pdf") if p.is_file())
    return pdf_files
