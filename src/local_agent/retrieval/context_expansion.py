from __future__ import annotations

from local_agent.retrieval.query_terms import (
    focus_phrases,
    focus_terms,
    focused_text,
    meaningful_query_terms,
    tokenize,
)
from local_agent.storage.sqlite_store import SQLiteStore


class RetrievalContextExpander:
    """Expand ranked anchor chunks with nearby and section-level context."""

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        neighbor_window: int = 2,
        parent_window: int = 3,
        parent_max_chars: int = 4200,
    ) -> None:
        self.sqlite_store = sqlite_store
        self.neighbor_window = neighbor_window
        self.parent_window = parent_window
        self.parent_max_chars = parent_max_chars

    def expand(
        self,
        query: str,
        ranked_items: list[dict],
        *,
        use_parent_context: bool = True,
        final_context_limit: int = 24,
    ) -> list[dict]:
        expanded = self._expand_with_neighbors(ranked_items)
        expanded = self._expand_with_section_context(query, expanded)
        expanded = self._expand_with_title_matched_sections(query, expanded)

        if use_parent_context:
            parent_contexts = self._build_parent_contexts(expanded, query=query)
            if parent_contexts:
                return parent_contexts[:final_context_limit]

        return expanded[:final_context_limit]

    def _expand_with_neighbors(self, ranked_items: list[dict]) -> list[dict]:
        expanded: list[dict] = []
        seen_chunk_ids: set[str] = set()

        for item in ranked_items:
            doc_id = item.get("doc_id")
            chunk_id = item.get("chunk_id")
            chunk_index = item.get("chunk_index")

            if chunk_id and chunk_id not in seen_chunk_ids:
                item["neighbor_role"] = "anchor"
                expanded.append(item)
                seen_chunk_ids.add(chunk_id)

            if doc_id is None or chunk_index is None:
                continue

            try:
                chunk_index_int = int(chunk_index)
            except (ValueError, TypeError):
                continue

            neighbors = self.sqlite_store.get_neighbor_chunks(
                doc_id=doc_id,
                chunk_index=chunk_index_int,
                window=self.neighbor_window,
            )

            before_neighbors: list[dict] = []
            after_neighbors: list[dict] = []

            for neighbor in neighbors:
                neighbor_chunk_id = neighbor.get("chunk_id")
                if not neighbor_chunk_id or neighbor_chunk_id in seen_chunk_ids:
                    continue

                neighbor["hybrid_score"] = item.get("hybrid_score", item.get("score", 0.0))
                neighbor["source"] = "neighbor"
                neighbor["neighbor_role"] = "context"
                neighbor["anchor_chunk_id"] = chunk_id
                neighbor["anchor_reranker_score"] = item.get("reranker_score")

                try:
                    neighbor_chunk_index = int(neighbor.get("chunk_index"))
                except (ValueError, TypeError):
                    neighbor_chunk_index = chunk_index_int

                if neighbor_chunk_index < chunk_index_int:
                    before_neighbors.append(neighbor)
                elif neighbor_chunk_index > chunk_index_int:
                    after_neighbors.append(neighbor)

                seen_chunk_ids.add(neighbor_chunk_id)

            if before_neighbors:
                expanded.extend(before_neighbors)

            if after_neighbors:
                expanded.extend(after_neighbors)

        return expanded

    def _expand_with_section_context(self, query: str, items: list[dict]) -> list[dict]:
        expanded = list(items)
        seen_chunk_ids = {item.get("chunk_id") for item in expanded if item.get("chunk_id")}
        query_terms = set(tokenize(query))
        stop_terms = {
            "what",
            "does",
            "review",
            "sora",
            "with",
            "from",
            "that",
            "this",
            "into",
            "their",
            "about",
        }
        query_terms = {term for term in query_terms if len(term) >= 4 and term not in stop_terms}

        for anchor in items:
            doc_id = anchor.get("doc_id")
            section_title = anchor.get("section_title")
            if not doc_id or not section_title:
                continue

            section_chunks = [
                chunk
                for chunk in self.sqlite_store.list_chunks_for_retrieval(doc_id=doc_id)
                if chunk.get("section_title") == section_title
                and chunk.get("chunk_id") not in seen_chunk_ids
            ]
            scored: list[tuple[int, dict]] = []
            for chunk in section_chunks:
                section_text = " ".join(
                    [
                        chunk.get("section_title") or "",
                        chunk.get("text") or "",
                    ]
                ).lower()
                overlap = sum(1 for term in query_terms if term in section_text)
                if overlap:
                    scored.append((overlap, chunk))

            scored.sort(key=lambda pair: pair[0], reverse=True)
            for _, chunk in scored[:2]:
                chunk["source"] = "section_context"
                chunk["neighbor_role"] = "section_context"
                chunk["anchor_chunk_id"] = anchor.get("chunk_id")
                chunk["hybrid_score"] = anchor.get("hybrid_score", anchor.get("score", 0.0))
                expanded.append(chunk)
                seen_chunk_ids.add(chunk.get("chunk_id"))

        return expanded

    def _expand_with_title_matched_sections(self, query: str, items: list[dict]) -> list[dict]:
        expanded = list(items)
        seen_chunk_ids = {item.get("chunk_id") for item in expanded if item.get("chunk_id")}
        doc_ids = list(dict.fromkeys(item.get("doc_id") for item in expanded if item.get("doc_id")))
        if not doc_ids:
            return expanded

        query_terms = meaningful_query_terms(query)
        if not query_terms:
            return expanded

        scored: list[tuple[int, dict]] = []
        for doc_id in doc_ids:
            for chunk in self.sqlite_store.list_chunks_for_retrieval(doc_id=doc_id):
                chunk_id = chunk.get("chunk_id")
                if not chunk_id or chunk_id in seen_chunk_ids:
                    continue

                section_title = (chunk.get("section_title") or "").lower()
                text = (chunk.get("text") or "").lower()
                title_hits = sum(1 for term in query_terms if term in section_title)
                if title_hits == 0:
                    continue
                text_hits = sum(1 for term in query_terms if term in text)
                score = (title_hits * 5) + text_hits
                scored.append((score, chunk))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        for _, chunk in scored[:6]:
            chunk["source"] = "section_title_match"
            chunk["neighbor_role"] = "section_title_match"
            chunk["hybrid_score"] = chunk.get("hybrid_score", chunk.get("score", 0.0))
            expanded.append(chunk)
            seen_chunk_ids.add(chunk.get("chunk_id"))

        return expanded

    def _build_parent_contexts(self, items: list[dict], query: str = "") -> list[dict]:
        parent_items: list[dict] = []
        seen_parent_keys: set[tuple[str, int, int]] = set()
        query_focus_phrases = focus_phrases(query)
        query_focus_terms = focus_terms(query)
        focus_units = query_focus_phrases or query_focus_terms

        for item in items:
            doc_id = item.get("doc_id")
            chunk_index = item.get("chunk_index")
            if doc_id is None or chunk_index is None:
                continue

            try:
                anchor_index = int(chunk_index)
            except (TypeError, ValueError):
                continue

            start_index = max(0, anchor_index - self.parent_window)
            end_index = anchor_index + self.parent_window
            parent_key = (str(doc_id), start_index, end_index)
            if parent_key in seen_parent_keys:
                continue
            seen_parent_keys.add(parent_key)

            chunks = self.sqlite_store.get_neighbor_chunks(
                doc_id=str(doc_id),
                chunk_index=anchor_index,
                window=self.parent_window,
            )
            if not chunks:
                continue
            matching_chunk_positions: set[int] = set()
            if focus_units:
                for position, chunk in enumerate(chunks):
                    text_lower = (chunk.get("text") or "").lower()
                    if any(unit in text_lower for unit in focus_units):
                        matching_chunk_positions.add(position)
                for position in list(matching_chunk_positions):
                    if position + 1 < len(chunks):
                        matching_chunk_positions.add(position + 1)
                    if position > 0:
                        matching_chunk_positions.add(position - 1)

            parent_text_parts: list[str] = []
            total_chars = 0
            included_focus_chunk = False
            for position, chunk in enumerate(chunks):
                text = (chunk.get("text") or "").strip()
                if not text:
                    continue
                if focus_units:
                    focused = focused_text(text, focus_units)
                    if focused:
                        text = focused
                        included_focus_chunk = True
                    elif position in matching_chunk_positions:
                        text = text[:2200].strip()
                    else:
                        continue
                chunk_header = (
                    f"[child chunk {chunk.get('chunk_index')} | "
                    f"page {chunk.get('page_number')} | "
                    f"section {chunk.get('section_title') or 'Unknown'}]\n"
                )
                block = f"{chunk_header}{text}"
                if total_chars + len(block) > self.parent_max_chars:
                    remaining = self.parent_max_chars - total_chars
                    if remaining > 300:
                        parent_text_parts.append(block[:remaining].rstrip() + "...")
                    break
                parent_text_parts.append(block)
                total_chars += len(block)

            if focus_units and not included_focus_chunk:
                continue

            if not parent_text_parts:
                continue

            page_numbers = [
                chunk.get("page_number")
                for chunk in chunks
                if chunk.get("page_number") is not None
            ]
            chunk_indexes = [
                chunk.get("chunk_index")
                for chunk in chunks
                if chunk.get("chunk_index") is not None
            ]
            first_chunk = chunks[0]
            parent_items.append(
                {
                    "id": f"{doc_id}-parent-{start_index}-{end_index}",
                    "chunk_id": f"{doc_id}-parent-{start_index}-{end_index}",
                    "doc_id": doc_id,
                    "chunk_index": anchor_index,
                    "child_chunk_ids": [
                        chunk.get("chunk_id")
                        for chunk in chunks
                        if chunk.get("chunk_id")
                    ],
                    "child_chunk_indexes": chunk_indexes,
                    "title": item.get("title") or first_chunk.get("title"),
                    "source_path": item.get("source_path") or first_chunk.get("source_path"),
                    "section_title": item.get("section_title") or first_chunk.get("section_title"),
                    "page_number": min(page_numbers) if page_numbers else item.get("page_number"),
                    "page_numbers": sorted(set(page_numbers)),
                    "text": "\n\n".join(parent_text_parts),
                    "source": "parent_context",
                    "neighbor_role": "parent_context",
                    "anchor_chunk_id": item.get("chunk_id"),
                    "hybrid_score": item.get("hybrid_score", item.get("score", 0.0)),
                    "reranker_score": item.get("reranker_score"),
                }
            )

        return parent_items
