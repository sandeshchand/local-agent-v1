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

        dense_results= self._dense_search(query, dense_limit)
        sparse_results= self._sparse_search(query, sparse_limit)

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

        scored_items:list[tuple[float, dict[str, Any]]] = []
        for chunk, score in zip(chunks, scores):
            title_text = f"{chunk.get('title') or ''}{chunk.get('text') or ''}"
            title_text_lower = title_text.lower()
            
            query_terms = set(query_tokens)
            overlap_boost = sum(
                0.25 for term in query_terms if term in title_text_lower 
            )

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
        """
        Add previous/next chunks for each top-ranked chunk.
        This improves context coverage while staying safe for multiple documents:
        neighbors are fetched only by same doc_id + adjacent chunk_index.
        """
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
                neighbor["neighbor_role"] = "context"
                neighbor["anchor_chunk_id"]= chunk_id
                neighbor["anchor_reranker_score"] = item.get("reranker_score")

                expanded.append(neighbor)
                seen_chunk_ids.add(neighbor_chunk_id)
        
        expanded.sort(
            key=lambda item: (
                str(item.get("doc_id") or ""),
                int(item.get("chunk_index") or 0),
            )
        )             
        return expanded
            

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\b\w+\b", text.lower())
                       
        