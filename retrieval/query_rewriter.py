from __future__ import annotations

import re

class QueryRewriter:
    def __init__(self) -> None:
        self.stopwords= {
            "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "where", "why", "how",
            "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
            "my", "your", "his", "its", "our", "their",
            "is", "am", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "having",
            "do", "does", "did", "doing",
            "will", "would", "should", "could", "may", "might", "must",
            "to", "of", "in", "on", "at", "by", "for", "with", "about", "as", "from",
            "this", "that", "these", "those",
            "what", "which", "who", "whom", "whose",
            "some", "any", "no", "not", "all", "many", "much", "more", "most",
            "such", "so", "very", "too", "just", "only", "also", "even",
            "up", "down", "out", "off", "over", "under", "again", "further",
            "then", "once", "here", "there", "when", "where", "why", "how",
            "about", "against", "between", "into", "through", "during", "before", "after",
            "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
            "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
            "about", "against", "between", "into", "through", "during", "before", "after",
            "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
            "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
            "about", "against", "between", "into", "through", "during", "before", "after",
            "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
            "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
            "about", "against", "between", "into", "through", "during", "before", "after",
            "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
            "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
            "about", "against", "between", "into", "through", "during", "before", "after",
            "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
            "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
            "about", "against", "between", "into", "through", "during", "before", "after",
            "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
            "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
            "about", "against", "between", "into", "through", "during", "before", "after",
            "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
            "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
            "about", "against", "between", "into", "through", "during", "before", "after",
            "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
            "over", "under"
        }

    def rewrite(self, query: str, results: list[dict]| None = None, session_memory: list | None = None) -> str:
        original_query = query.strip()
        
        # Remove punctuation
        tokens  = re.findall(r'\b\w+\b', query.lower())

        cleaned: list[str] =[]

        for token in tokens:
            if len(token) < 3:
                continue
            if token in self.stopwords:
                continue
            cleaned.append(token)

        deduped: list[str] = []
        seen: set[str] = set()

        for token in cleaned:
            if token not in seen:
                seen.add(token)
                deduped.append(token)

        candidate = " ".join(deduped).strip()

        if results:
            top_title = (results[0].get("title") or "").lower()
            if "sora" in top_title and  "sora" not in candidate:
                candidate =f"{candidate} sora".strip()
        
        if not candidate:
            return query

        if candidate.lower() == query.lower().strip():
            return query
        
        return candidate
            