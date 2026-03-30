from __future__ import annotations


def build_context(results: list[dict], max_chars_per_chunk: int = 600) -> str:
    parts: list[str] = []

    for index, item in enumerate(results, start =1):
        text = (item.get("text") or "").strip()
        if len(text) > max_chars_per_chunk:
            text = text[:max_chars_per_chunk].rstrip() + "..."

        title = item.get("title") or "Untitled"
        page_number = item.get("page_number") or "?"
        score = float(item.get("Score", 0.0))
        parts.append(
            f"[{index}]\n"
            f"Title:{title}\n"
            f"Page:{page_number}\n"
            f"Score:{score:.4f}\n"
            f"Text:{text}\n"
        )
    return "\n".join(parts)