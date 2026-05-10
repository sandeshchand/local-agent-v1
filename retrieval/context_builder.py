from __future__ import annotations


def build_context(results: list[dict], max_chars_per_chunk: int = 1800) -> str:
    parts: list[str] = []

    for index, item in enumerate(results, start =1):
        text = (item.get("text") or "").strip()
        if len(text) > max_chars_per_chunk:
            text = text[:max_chars_per_chunk].rstrip() + "..."

        title = item.get("title") or "Untitled"
        page_numbers = item.get("page_numbers")
        if page_numbers:
            page_number = ", ".join(str(page) for page in page_numbers)
        else:
            page_number = item.get("page_number") or "?"
        score = float(item.get("score", item.get("hybrid_score") or 0.0))
        section_title = item.get("section_title") or "Unknown"
        parts.append(
            f"[{index}]\n"
            f"Title:{title}\n"
            f"Section:{section_title}\n"
            f"Page:{page_number}\n"
            f"Score:{score:.4f}\n"
            f"Text:{text}\n"
        )
    return "\n".join(parts)
