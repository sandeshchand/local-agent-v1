from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import os
import re
from threading import RLock
from typing import Any, List, Mapping

from rank_bm25 import BM25Okapi

from local_agent.storage.sqlite_store import SQLiteStore


@dataclass(frozen=True)
class _RoutingIndex:
    signature: tuple[Any, ...]
    docs: list[dict[str, Any]]
    corpus: list[list[str]]
    doc_text_cache: dict[str, str]
    bm25: BM25Okapi | None

class DocumentRouter:
    """
    Stage-1 retrieval:
    rank documents before chunk retrieval

    """
    def __init__(self,sqlite_store: SQLiteStore, cache_enabled: bool = True) -> None:
        self.sqlite_store = sqlite_store
        self.cache_enabled = cache_enabled
        self._cache_lock = RLock()
        self._routing_index: _RoutingIndex | None = None

    
    def route(
        self,
        query: str,
        top_n: int = 3,
        *,
        accessible_doc_ids: list[str] | None = None,
    ) -> List[Mapping[str, Any]]:
        if accessible_doc_ids is not None and not accessible_doc_ids:
            return []
        routing_index = self._get_routing_index(accessible_doc_ids=accessible_doc_ids)
        docs = routing_index.docs
        if not docs:
            return[]

        query_tokens = self._content_tokens(query)
        if not query_tokens:
            query_tokens = self._tokenize(query)
        if not query_tokens:
             return [dict(doc) for doc in docs[:top_n]]

        scores = (
            routing_index.bm25.get_scores(query_tokens)
            if routing_index.bm25 is not None
            else [0.0 for _ in docs]
        )

        scored_docs : List[dict[str,Any]] = []
        q_lower = query.lower()
        query_phrases = self._query_phrases(q_lower)
        distinctive_terms = self._distinctive_query_terms(query)

        for doc,score in zip(docs,scores):
            title_lower = (doc['title'] or '').lower()
            path_lower = (doc['source_path'] or '').lower()
            sections_lower = (doc.get('section_titles','') or '').lower()
            chunk_text_lower = routing_index.doc_text_cache.get(str(doc["doc_id"]), "").lower()
            searchable_text = self._normalize_for_phrase_search(
                " ".join([title_lower, path_lower, sections_lower, chunk_text_lower])
            )
            token_counts = Counter(self._tokenize(chunk_text_lower))
            title_tokens = set(self._tokenize(title_lower))
            section_tokens = set(self._tokenize(sections_lower))
            path_tokens = set(self._tokenize(path_lower))

            boost = 0.0
            matched_tokens: set[str] = set()
            title_or_section_matches = 0
            for token in query_tokens:
                token_boost = 0.0
                if token in title_tokens:
                    token_boost += 8.0
                    title_or_section_matches += 1
                if token in section_tokens:
                    token_boost += 4.0
                    title_or_section_matches += 1
                if token in path_tokens:
                    token_boost += 2.0
                frequency = token_counts.get(token, 0)
                if frequency > 0:
                    matched_tokens.add(token)
                    token_boost += 0.75 + min(2.5, math.log1p(frequency))
                    if len(token) >= 6:
                        token_boost += 1.25
                boost += token_boost
            coverage = len(matched_tokens) / max(1, len(set(query_tokens)))
            boost += coverage * 14.0
            boost += min(10.0, title_or_section_matches * 2.5)
            if q_lower and q_lower in title_lower:
                boost += 2.0
            if q_lower and q_lower in chunk_text_lower:
                boost += 4.0
            for phrase in query_phrases:
                if phrase in self._normalize_for_phrase_search(title_lower):
                    boost += 10.0
                elif phrase in self._normalize_for_phrase_search(sections_lower):
                    boost += 8.0
                elif phrase in searchable_text:
                    boost += 12.0
            for term in distinctive_terms:
                if self._contains_normalized_term(self._normalize_for_phrase_search(title_lower), term):
                    boost += 40.0
                elif self._contains_normalized_term(self._normalize_for_phrase_search(sections_lower), term):
                    boost += 30.0
                elif self._contains_normalized_term(self._normalize_for_phrase_search(path_lower), term):
                    boost += 24.0
                elif self._contains_normalized_term(searchable_text, term):
                    boost += 36.0

            enriched = dict(doc)
            enriched["routing_score"] = float(score) + boost
            scored_docs.append(enriched)
          
            
        scored_docs.sort(key=lambda x: x["routing_score"], reverse=True)
        return scored_docs[:top_n]    

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._routing_index = None

    def _get_routing_index(
        self,
        *,
        accessible_doc_ids: list[str] | None = None,
    ) -> _RoutingIndex:
        if accessible_doc_ids is not None:
            return self._build_routing_index(
                signature=("routing_v1_scoped", tuple(accessible_doc_ids)),
                doc_ids=accessible_doc_ids,
            )

        signature = self.sqlite_store.routing_corpus_signature()
        with self._cache_lock:
            if (
                self.cache_enabled
                and self._routing_index is not None
                and self._routing_index.signature == signature
            ):
                return self._routing_index

            routing_index = self._build_routing_index(signature=signature)
            if self.cache_enabled:
                self._routing_index = routing_index
            return routing_index

    def _build_routing_index(
        self,
        *,
        signature: tuple[Any, ...],
        doc_ids: list[str] | None = None,
    ) -> _RoutingIndex:
        if doc_ids is None:
            raw_docs = self.sqlite_store.list_documents_for_routing()
        else:
            raw_docs = self.sqlite_store.list_documents_for_routing(doc_ids=doc_ids)
        docs = [dict(doc) for doc in raw_docs]
        corpus: list[list[str]] = []
        doc_text_cache: dict[str, str] = {}

        for doc in docs:
            basename = os.path.basename(doc["source_path"])
            chunk_text = self._document_chunk_text(str(doc["doc_id"]))
            doc_text_cache[str(doc["doc_id"])] = chunk_text
            routing_text = (
                f"{doc['title']} "
                f"{basename} "
                f"{doc.get('section_titles','')} "
                f"{chunk_text}"
            ).strip()
            corpus.append(self._tokenize(routing_text))

        return _RoutingIndex(
            signature=signature,
            docs=docs,
            corpus=corpus,
            doc_text_cache=doc_text_cache,
            bm25=BM25Okapi(corpus) if corpus else None,
        )
    
    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b\w+\b", text.lower())

    def _query_phrases(self, query_lower: str) -> list[str]:
        stop_words = {
            "what",
            "which",
            "does",
            "article",
            "included",
            "include",
            "recommend",
            "according",
            "first",
            "steps",
            "step",
            "the",
            "and",
            "for",
            "with",
            "from",
            "into",
            "that",
            "this",
            "about",
            "why",
            "how",
            "are",
            "is",
        }
        tokens = [
            token
            for token in re.findall(r"\b[a-zA-Z0-9][a-zA-Z0-9-]{1,}\b", query_lower)
            if token not in stop_words
        ]
        phrases: list[str] = []
        for size in range(4, 1, -1):
            for index in range(0, len(tokens) - size + 1):
                phrase = self._normalize_for_phrase_search(" ".join(tokens[index : index + size]))
                if len(phrase) >= 7:
                    phrases.append(phrase)
        return list(dict.fromkeys(phrases))

    def _normalize_for_phrase_search(self, text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()

    def _document_chunk_text(self, doc_id: str, max_chars: int = 50000) -> str:
        parts: list[str] = []
        total = 0
        for chunk in self.sqlite_store.list_chunks_for_retrieval(doc_id=doc_id):
            text = " ".join(
                [
                    chunk.get("section_title") or "",
                    chunk.get("text") or "",
                ]
            )
            if not text.strip():
                continue
            remaining = max_chars - total
            if remaining <= 0:
                break
            parts.append(text[:remaining])
            total += len(parts[-1])
        return " ".join(parts)
        
          
            

            
        
        
        

        

    def _content_tokens(self, text: str) -> list[str]:
        stop_words = {
            "a",
            "an",
            "the",
            "and",
            "or",
            "but",
            "if",
            "then",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "what",
            "which",
            "who",
            "how",
            "why",
            "when",
            "where",
            "does",
            "do",
            "did",
            "of",
            "in",
            "on",
            "at",
            "by",
            "for",
            "with",
            "about",
            "to",
            "from",
            "into",
            "through",
            "that",
            "this",
            "these",
            "those",
            "it",
            "its",
            "they",
            "them",
            "their",
            "article",
            "paper",
            "document",
            "review",
            "give",
            "gives",
            "mean",
            "means",
            "included",
            "include",
            "useful",
            "help",
            "helps",
            "according",
            "first",
            "main",
            "key",
            "some",
            "tell",
            "explain",
            "describe",
            "recommend",
            "recommends",
            "steps",
            "step",
        }
        tokens = [
            token.lower()
            for token in re.findall(r"\b[a-zA-Z0-9][a-zA-Z0-9_-]*\b", text)
            if token.lower() not in stop_words and len(token) >= 2
        ]
        return list(dict.fromkeys(tokens))

    def _distinctive_query_terms(self, text: str) -> list[str]:
        stop_words = {
            "what",
            "which",
            "who",
            "how",
            "why",
            "when",
            "where",
            "does",
            "article",
            "paper",
            "document",
            "review",
            "first",
            "main",
            "key",
            "steps",
            "step",
        }
        terms: list[str] = []
        for raw in re.findall(r"\b[A-Za-z][A-Za-z0-9_-]{1,}\b", text):
            lower = raw.lower()
            if lower in stop_words:
                continue
            looks_distinctive = (
                len(raw) >= 4
                and (
                    raw[:1].isupper()
                    or any(char.isupper() for char in raw[1:])
                    or "-" in raw
                    or "_" in raw
                    or any(char.isdigit() for char in raw)
                )
            )
            if looks_distinctive:
                terms.append(self._normalize_for_phrase_search(raw))
        return list(dict.fromkeys(term for term in terms if term))

    def _contains_normalized_term(self, text: str, term: str) -> bool:
        if not term:
            return False
        return re.search(rf"\b{re.escape(term)}\b", text) is not None
        
