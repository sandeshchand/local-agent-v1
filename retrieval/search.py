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
            neighbor_window: int = 1,
            final_context_limit: int = 6,
            ) -> None:
        self.qdrant_store = qdrant_store
        self.sqlite_store = sqlite_store
        self.embedding_client = embedding_client
        self.top_k = top_k
        self.rerank_candidates = max(rerank_candidates, top_k)
        self.neighbor_window = neighbor_window
        self.final_context_limit = final_context_limit

        self.reranker = (
            CrossEncoderReranker(
                model_name=rerank_model,
                top_n=top_k,
            )
            if use_reranker
            else None
        )
    

    def search(self, query: str) -> list[dict]:
        dense_limit = max(self.top_k *4, 12)
        sparse_limit = max(self.top_k *4, 12)

        dense_results= self._dense_search(query, dense_limit)
        sparse_results= self._sparse_search(query, sparse_limit)

        fused = self._rrf_fuse(
            dense_items=dense_results,
            sparse_items=sparse_results,
            limit=self.rerank_candidates,
            k=60,

        )
        ranked = fused[:self.top_k]

        if self.reranker is not None and fused:
            try:
                ranked= self.reranker.rerank(query, fused)
                ranked = ranked[:self.top_k]
            except Exception as e:
                print(f"Reranker failed: {e}")
                ranked = fused[: self.top_k]
        expanded = self._expand_with_neighbors(ranked)
        return expanded[:self.final_context_limit]

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
                    "chunk_index":payload.get("chunk_index_id"),
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
                        "chunk_index": chunk.get("chunk_index"),
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
            if not key:
                continue

            fused_scores[key]= fused_scores.get(key, 0.0) + 1.0 /(k + rank)

            if key not in fused_items:
                fused_items[key] = dict(item)
                fused_items[key]["dense_rank"]= rank
        
        for rank,item in enumerate(sparse_items, start=1):
            key = item["chunk_id"]
            if not key:
                continue

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
        seen: set[tuple[str | None ,int | None ,str | None]] = set()

        for chunk_id, item in ranked:
           key = (item.get("doc_id"), item.get("page_number"), item.get("chunk_id"))
           if key in seen:
               continue
           seen.add(key)

           item["score"] = fused_scores[chunk_id]
           item["hybrid_score"] = fused_scores[chunk_id]
           item["source"] = "hybrid"

           results.append(item)

           if len(results) >= limit:
               break
        return results

    def _expand_with_neighbors(self, ranked_items: list[dict]) -> list[dict]:
        """
        Add previous/next chunks for each top-ranked chunk.

        Important:
        - Only expands within the same doc_id.
        - Preserves ranked chunks first.
        - Adds neighbor chunks after their anchor chunk.
        - Deduplicates by chunk_id.
        """
        expanded: list[dict] = []
        seen_chunk_ids: set[str] = set()
       
        for item in ranked_items:
            doc_id = item.get("doc_id")
            chunk_id = item.get("chunk_id")
            chunk_index = item.get("chunk_index")

            if chunk_id and chunk_id not in seen_chunk_ids:
                expanded.append(item)
                seen_chunk_ids.add(chunk_id)

            if doc_id is None or chunk_index is None:
                continue

            try:
                chunk_index_int =int(chunk_index)
            except (ValueError, TypeError):
                continue
                
            neighbors = self.sqlite_store.get_neighbor_chunks(
                doc_id=doc_id, 
                chunk_index=chunk_index_int, 
                window=self.neighbor_window)
    
            for neighbor in neighbors:
                neighbor_chunk_id= neighbor.get("chunk_id")
                if not neighbor_chunk_id:
                    continue
                if neighbor_chunk_id in seen_chunk_ids:
                    continue

                neighbor["source"]= item.get("source" , 0.0)
                neighbor["hybrid_score"]= item.get("hybrid_score" , item.get("score",0.0))
                neighbor["source"] = "neighbor"
                neighbor["anchor_chunk_id"]= chunk_id
                neighbor["anchor_reranker_score"] = item.get("reranker_score")

                expanded.append(neighbor)
                seen_chunk_ids.add(neighbor_chunk_id)
            
            expanded.sort(
                key=lambda x: (
                    str(x.get("doc_id") or ""),
                    int(x.get("chunk_index") or 0),
                )
            )             
        return expanded
            

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\b\w+\b", text.lower())
                       
        