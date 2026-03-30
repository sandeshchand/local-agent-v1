from __future__ import annotations

def format_citations(results: list[dict]) -> str:
    if not results:
        return "No citations available."

    lines: list[str] = []
    for index, item in enumerate(results, start=1):
        title= item.get("title") or "Untitled"
        page_number= item.get("page_number") or "?"
        source_path = item.get("source_path") or ""
        lines.append(f"[{index}] {title}, page {page_number} ({source_path})")
    return "\n".join(lines)