from __future__ import annotations

import re 
from typing import Any

from rank_bm25 import BM25Okapi

from app.ollama_client import  OllamaEmbeddingClient
from storage.qdrant_store import QdrantStore
from storage.sqlite_store import SQLiteStore
from retrieval.reranker import CrossEncoderReranker

class RetrievalService:
    def __init__(
            self,
            qdrant_store: QdrantStore,
            sqlite_store: SQLiteStore,
            embedding_client: OllamaEmbeddingClient,
            top_k: int = 5,
            use_reranker: bool = True,
            rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
            rerank_candidates: int = 20,
            neighbor_window: int = 2,
            final_context_limit: int = 24,
            use_parent_context: bool = True,
            parent_window: int = 3,
            parent_max_chars: int = 4200,
            ) -> None:
        self.qdrant_store = qdrant_store
        self.sqlite_store = sqlite_store
        self.embedding_client = embedding_client
        self.top_k = top_k
        self.rerank_candidates = max(rerank_candidates, top_k)
        self.neighbor_window = neighbor_window
        self.final_context_limit = final_context_limit
        self.use_parent_context = use_parent_context
        self.parent_window = parent_window
        self.parent_max_chars = parent_max_chars

        self.reranker = (
            CrossEncoderReranker(
                model_name=rerank_model,
                top_n=top_k,
            )
            if use_reranker
            else None
        )
    

    def search(
        self,
        query: str, 
        doc_id: str | None = None,  
        candidate_doc_ids: list[str] | None = None,  
        ) -> list[dict]:
        """
        Hybrid retrieval pipeline:
        1. Dense vector retrieval from Qdrant
        2. Sparse retrieval from SQLite (BM25 + boosts)
        3. RRF fusion over large candidate pool
        4. Cross-encoder reranking 
        5. Neighbor expansion for context coverage
        """
        dense_limit = max(self.top_k *5, self.rerank_candidates)
        sparse_limit = max(self.top_k *5, self.rerank_candidates)

        if candidate_doc_ids:
            dense_results= self._dense_search_many_docs(query, dense_limit,candidate_doc_ids=candidate_doc_ids)
            sparse_results= self._sparse_search(query, sparse_limit,candidate_doc_ids=candidate_doc_ids)
        else:
            dense_results= self._dense_search(query, dense_limit,doc_id=doc_id)
            sparse_results= self._sparse_search(query, sparse_limit,doc_id=doc_id)

        fused = self._rrf_fuse(
            dense_items=dense_results,
            sparse_items=sparse_results,
            limit=self.rerank_candidates,
            k=60,

        )
        if not fused:
            return []
            
        ranked = fused[:self.top_k]

        if self.reranker is not None :
            try:
                ranked= self.reranker.rerank(query, fused)
                ranked = ranked[:self.top_k]
            except Exception as exc:
                print(f"Reranker failed: {exc}")
                ranked = fused[: self.top_k]

        expanded = self._expand_with_neighbors(ranked)
        expanded = self._expand_with_section_context(query, expanded)
        expanded = self._expand_with_title_matched_sections(query, expanded)

        if self.use_parent_context:
            parent_contexts = self._build_parent_contexts(expanded, query=query)
            if parent_contexts:
                return parent_contexts[:self.final_context_limit]

        return expanded[:self.final_context_limit]

    def _dense_search_many_docs(
        self, 
        query:str, 
        limit:int,
        candidate_doc_ids: list[str],
        ) -> list[dict]:
        combined: list[dict] = []
        if not candidate_doc_ids:
            return combined
        
        per_doc_limit = max(4, limit // max(1, len(candidate_doc_ids)))
        for doc_id in candidate_doc_ids:
            combined.extend(
                self._dense_search(query=query, limit=per_doc_limit,doc_id=doc_id)
                )
            
        combined.sort(key=lambda x: x.get("score",0.0),reverse=True)
        return combined[:limit]  

    def _dense_search(self, query:str, limit:int,doc_id: str | None = None) -> list[dict]:
        query_vector = self.embedding_client.embed(query)
        result = self.qdrant_store.search(query_vector=query_vector, limit=limit,doc_id=doc_id)

        points = getattr(result, "points", []) or []
        items: list[dict] = []

        for point in points:
            payload = getattr(point, "payload", {}) or {}
            items.append(
                {
                    "id": getattr(point, "id",None),
                    "score": float(getattr(point,"score",0.0)),
                    "doc_id":payload.get("doc_id"),
                    "chunk_id":payload.get("chunk_id"),
                    "chunk_index":payload.get("chunk_index"),
                    "title":payload.get("title"),
                    "source_path":payload.get("source_path"),
                    "section_title":payload.get("section_title"),
                    "page_number":payload.get("page_number"),
                    "text":payload.get("text",""),
                    "source":"dense",
                }
            )
        return items
    def _sparse_search(
        self, 
        query:str, 
        limit:int,
        doc_id: str | None = None,
        candidate_doc_ids: list[str] | None = None,
        ) -> list[dict]:

        if candidate_doc_ids:
            allowed = set(candidate_doc_ids)
            chunks = [
                chunk
                for chunk in self.sqlite_store.list_chunks_for_retrieval()
                if chunk["doc_id"] in allowed
            ]
        else:
            chunks = self.sqlite_store.list_chunks_for_retrieval(doc_id=doc_id)
       
        
        tokenized_corpus = [self._tokenize(chunk["text"]) for chunk in chunks]
        bm25 = BM25Okapi(tokenized_corpus)
        query_tokens= self._tokenize(query)
        if not query_tokens:
            return []
        focus_phrases = self._focus_phrases(query)
     
        scores = bm25.get_scores(query_tokens)

        scored_items:list[tuple[float, dict[str, Any]]] = []
        for chunk, score in zip(chunks, scores):
            section_text = (
                f"{chunk.get('section_title') or ''} "
                f"{chunk.get('title', '')} "
                f"{chunk.get('text', '')} "

            )
            section_text_lower = section_text.lower()
            query_terms = set(query_tokens)
            section_title_lower= (chunk.get("section_title") or "").lower()
            
            overlap_boost = 0.0
            for phrase in focus_phrases:
                if phrase in section_title_lower:
                    overlap_boost += 8.0
                elif phrase in section_text_lower:
                    overlap_boost += 5.0
            for term in query_terms:
                if term in section_title_lower:
                    overlap_boost +=1.25
                elif term in section_text_lower:
                    overlap_boost +=0.25

            final_score = float(score) + overlap_boost
            scored_items.append(
                (
                    final_score,
                    {
                        "id": chunk["chunk_id"],
                        "score": float(final_score),
                        "doc_id": chunk["doc_id"],
                        "chunk_id": chunk["chunk_id"],
                        "chunk_index": chunk.get("chunk_index"),
                        "title": chunk.get("title"),
                        "source_path": chunk.get("source_path"),
                        "section_title": chunk.get("section_title"),
                        "page_number": chunk.get("page_number"),
                        "text": chunk["text"],
                        "source": "sparse",
                    },
                )
            )
        scored_items.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored_items[:limit]]

            
    def _rrf_fuse(
        self, 
        dense_items: list[dict], 
        sparse_items: list[dict], 
        limit: int, 
        k: int = 60) -> list[dict]:
        fused_scores: dict[str, float] = {}
        fused_items: dict[str, dict] = {}

        for rank,item in enumerate(dense_items, start=1):
            chunk_id = item["chunk_id"]
            if not chunk_id:
                continue

            fused_scores[chunk_id]= fused_scores.get(chunk_id, 0.0) + 1.0 /(k + rank)

            if chunk_id not in fused_items:
                fused_items[chunk_id] = dict(item)
                
            fused_items[chunk_id]["dense_rank"]= rank
        
        for rank,item in enumerate(sparse_items, start=1):
            chunk_id = item.get("chunk_id")
            if not chunk_id:
                continue

            fused_scores[chunk_id]= fused_scores.get(chunk_id, 0.0) + 1.0 /(k + rank)

            if chunk_id not in fused_items:
                fused_items[chunk_id] = dict(item)
            else:
                if not fused_items[chunk_id].get("text") and item.get("text"):
                    fused_items[chunk_id]["text"] = item["text"]
            fused_items[chunk_id]["sparse_rank"] = rank
        
        ranked = sorted(
            fused_items.items(),
            key=lambda pair: fused_scores[pair[0]],
            reverse=True,
        )

        results: list[dict] = []
        seen: set[tuple[str | None ,int | None ,str | None]] = set()

        for chunk_id, item in ranked:
           item["score"] = fused_scores[chunk_id]
           item["hybrid_score"] = fused_scores[chunk_id]
           item["source"] = "hybrid"

           results.append(item)

           if len(results) >= limit:
               break
        return results

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
        query_terms = set(self._tokenize(query))
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

        query_terms = self._meaningful_query_terms(query)
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

    def _meaningful_query_terms(self, query: str) -> set[str]:
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
            "core",
            "model",
            "use",
        }
        return {
            term
            for term in self._tokenize(query)
            if len(term) >= 4 and term not in stop_terms
        }

    def _build_parent_contexts(self, items: list[dict], query: str = "") -> list[dict]:
        parent_items: list[dict] = []
        seen_parent_keys: set[tuple[str, int, int]] = set()
        focus_phrases = self._focus_phrases(query)
        focus_terms = self._focus_terms(query)
        focus_units = focus_phrases or focus_terms

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
                    focused_text = self._focused_text(text, focus_units)
                    if focused_text:
                        text = focused_text
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
                

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\b\w+\b", text.lower())

    def _focus_terms(self, query: str) -> set[str]:
        generic_terms = {
            "what",
            "which",
            "from",
            "paper",
            "document",
            "key",
            "feature",
            "features",
            "main",
            "some",
            "tell",
            "about",
            "explain",
            "describe",
            "according",
            "review",
            "use",
            "uses",
            "using",
            "docker",
        }
        original_tokens = re.findall(r"\b[A-Za-z][A-Za-z0-9_-]{3,}\b", query)
        terms: set[str] = set()
        for token in original_tokens:
            lower = token.lower()
            if lower in generic_terms:
                continue
            if any(char.isupper() for char in token[1:]) or token[:1].isupper():
                terms.add(lower)
            elif len(lower) >= 8:
                terms.add(lower)
        return terms

    def _focus_phrases(self, query: str) -> set[str]:
        generic_terms = {
            "what",
            "which",
            "from",
            "paper",
            "document",
            "article",
            "key",
            "features",
            "main",
            "some",
            "tell",
            "about",
            "explain",
            "describe",
            "according",
            "review",
            "how",
            "why",
            "does",
            "used",
        }
        phrases: set[str] = set()

        for match in re.finditer(
            r"\b[A-Z][A-Za-z0-9_-]*\b(?:\s+\b[A-Z][A-Za-z0-9_-]*\b)+",
            query,
        ):
            phrase_tokens = [
                token
                for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_-]*\b", match.group(0))
                if token.lower() not in generic_terms
            ]
            if len(phrase_tokens) < 2:
                continue
            phrase = " ".join(token.lower() for token in phrase_tokens)
            phrases.add(phrase)
            last = phrase_tokens[-1]
            if last.lower().endswith("s") and len(last) > 4:
                phrases.add(" ".join([*(token.lower() for token in phrase_tokens[:-1]), last[:-1].lower()]))
        return phrases

    def _focused_text(self, text: str, focus_terms: set[str], radius: int = 2200) -> str:
        text_lower = text.lower()
        matches = [
            text_lower.find(term)
            for term in focus_terms
            if text_lower.find(term) != -1
        ]
        matches = [match for match in matches if match >= 0]
        if not matches:
            return ""

        anchor = min(matches)
        start = max(0, anchor - radius // 3)
        end = min(len(text), anchor + radius)

        sentence_start = max(
            text.rfind(". ", 0, start),
            text.rfind("\n", 0, start),
        )
        if sentence_start >= 0:
            start = sentence_start + 1

        sentence_end_candidates = [
            text.find(". ", end),
            text.find("\n", end),
        ]
        sentence_end_candidates = [candidate for candidate in sentence_end_candidates if candidate != -1]
        if sentence_end_candidates:
            end = min(sentence_end_candidates) + 1

        return text[start:end].strip()
                       
        
