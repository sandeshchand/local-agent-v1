from __future__ import annotations

from collections import Counter
import os
import re
from typing import Any, List, Mapping

from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from storage.sqlite_store import SQLiteStore

class DocumentRouter:
    """
    Stage-1 retrieval:
    rank documents before chunk retrieval

    """
    def __init__(self,sqlite_store: SQLiteStore) -> None:
        self.sqlite_store = sqlite_store

    
    def route(self,query:str, top_n:int = 3)-> List[Mapping[str,Any]]:
        docs = self.sqlite_store.list_documents_for_routing()
        if not docs:
            return[]
        
        corpus = []
        doc_text_cache: dict[str, str] = {}
        
        for doc in docs:
            basename = os.path.basename(doc["source_path"])
            chunk_text = self._document_chunk_text(str(doc["doc_id"]))
            doc_text_cache[str(doc["doc_id"])] = chunk_text
            routing_text =(
                f"{doc['title']} "
                f"{basename} "
                f"{doc.get('section_titles','')} "
                f"{chunk_text}"
                
            ).strip()
            corpus.append(self._tokenize(routing_text))

        query_tokens = self._tokenize(query)
        if not query_tokens:
             return docs[:top_n]

        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(query_tokens)

        scored_docs : List[dict[str,Any]] = []
        q_lower = query.lower()

        for doc,score in zip(docs,scores):
            title_lower = (doc['title'] or '').lower()
            path_lower = (doc['source_path'] or '').lower()
            sections_lower = (doc.get('section_titles','') or '').lower()
            chunk_text_lower = doc_text_cache.get(str(doc["doc_id"]), "").lower()
            token_counts = Counter(self._tokenize(chunk_text_lower))

            boost = 0.0
            for token in query_tokens:
                if token in title_lower:
                    boost += 1.5
                if token in sections_lower:
                    boost += 1.0
                if token in path_lower:
                    boost += 0.5
                if token_counts.get(token, 0) > 0:
                    boost += 2.0 + min(3.0, token_counts[token] * 0.25)
            if q_lower and q_lower in title_lower:
                boost += 2.0
            if q_lower and q_lower in chunk_text_lower:
                boost += 4.0

            enriched = dict(doc)
            enriched["routing_score"] = float(score) + boost
            scored_docs.append(enriched)
          
            
        scored_docs.sort(key=lambda x: x["routing_score"], reverse=True)
        return scored_docs[:top_n]    
    
    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b\w+\b", text.lower())

    def _document_chunk_text(self, doc_id: str, max_chars: int = 12000) -> str:
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
        
          
            

            
        
        
        


        
