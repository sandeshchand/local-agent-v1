from __future__ import annotations

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
        
        for doc in docs:
            basename = os.path.basename(doc["source_path"])
            routing_text =(
                f"{doc['title']}"
                f"{basename}"
                f"{doc.get('section_title','')}"
                
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
            sections_lower = (doc.get('section_title','') or '').lower()

            boost = 0.0
            for token in query_tokens:
                if token in title_lower:
                    boost += 1.5
                if token in sections_lower:
                    boost += 1.0
                if token in path_lower:
                    boost += 0.5
            if q_lower and q_lower in title_lower:
                boost += 2.0

            enriched = dict(doc)
            enriched["routing_score"] = float(score) + boost
            scored_docs.append(enriched)
          
            
        scored_docs.sort(key=lambda x: x["routing_score"], reverse=True)
        return scored_docs[:top_n]    
    
    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b\w+\b", text.lower())
        
          
            

            
        
        
        


        