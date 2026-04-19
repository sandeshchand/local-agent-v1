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
            rerank_candidates: int = 8,
            ) -> None:
        self.qdrant_store = qdrant_store
        self.sqlite_store = sqlite_store
        self.embedding_client = embedding_client
        self.top_k = top_k
        self.rerank_candidates = max(rerank_candidates, top_k)
        self.reranker = (
            CrossEncoderReranker(
                model_name=rerank_model,
                top_n=top_k,
            )
            if use_reranker
            else None
        )
    

    def search(self, query: str) -> list[dict]:
        dense_limit = max(self.top_k *4, 8)
        sparse_limit = max(self.top_k *4, 8)

        dense_results= self._dense_search(query, dense_limit)
        sparse_results= self._sparse_search(query, sparse_limit)

        fused = self._rrf_fuse(
            dense_items=dense_results,
            sparse_items=sparse_results,
            limit=self.top_k,
            k=60,

        )
        if self.reranker is not None:
            try:
                return self.reranker.rerank(query, fused)
            except Exception as e:
                print(f"Reranker failed: {e}")
        return fused[:self.top_k]

    def _dense_search(self, query:str, limit:int) -> list[dict]:
        query_vector = self.embedding_client.embed(query)
        result = self.qdrant_store.search(query_vector=query_vector, limit=limit)

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
                    "title":payload.get("title"),
                    "source_path":payload.get("source_path"),
                    "page_number":payload.get("page_number"),
                    "text":payload.get("text",""),
                    "source":"dense",
                }
            )
        return items
    def _sparse_search(self, query:str, limit:int) -> list[dict]:
        chunks = self.sqlite_store.list_chunks_for_retrieval()
        if not chunks:
            return []
        
        tokenized_corpus = [self._tokenize(chunk["text"]) for chunk in chunks]
        bm25 = BM25Okapi(tokenized_corpus)
        query_tokens= self._tokenize(query)
        if not query_tokens:
            return []
     
        scores = bm25.get_scores(query_tokens)
        query_lower= query.lower().strip()
        query_term = set(query_tokens)

        scored_items:list[tuple[float, dict[str, Any]]] = []
        for chunk, score in zip(chunks, scores):
            text_lower = chunk["text"].lower()
            title_lower = (chunk.get("title", "") or "").lower()

            boost = 0.0
            if query_lower  and query_lower in title_lower:
                boost += 2.0
            if any(term in title_lower for term in query_term):
                boost += 1.0
            if any(term in text_lower for term in query_term):
                boost += 0.5
            
            final_score = float(score) + boost
            scored_items.append(
                (
                    final_score,
                    {
                        "id": chunk["chunk_id"],
                        "score": float(final_score),
                        "doc_id": chunk["doc_id"],
                        "chunk_id": chunk["chunk_id"],
                        "title": chunk.get("title"),
                        "source_path": chunk.get("source_path"),
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
            key = item["chunk_id"]
            fused_scores[key]= fused_scores.get(key, 0.0) + 1.0 /(k + rank)
            if key not in fused_items:
                fused_items[key] = dict(item)
            fused_items[key]["dense_rank"]= rank
        for rank,item in enumerate(sparse_items, start=1):
            key = item["chunk_id"]
            fused_scores[key]= fused_scores.get(key, 0.0) + 1.0 /(k + rank)
            if key not in fused_items:
                fused_items[key] = dict(item)
            else:
                if not fused_items[key].get("text") and item.get("text"):
                    fused_items[key]["text"] = item["text"]
                fused_items[key]["sparse_rank"] = rank
        
        ranked = sorted(
            fused_items.items(),
            key=lambda pair: fused_scores[pair[0]],
            reverse=True,
        )

        results: list[dict] = []
        seen = set()

        for chunk_id, item in ranked:
           key = (item.get("doc_id"), item.get("page_number"), item.get("chunk_id"))
           if key in seen:
               continue
           seen.add(key)

           item["score"] = fused_scores[chunk_id]
           item["source"] = "hybrid"
           results.append(item)

           if len(results) >= limit:
               break
        return results

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\b\w+\b", text.lower())
                       
        