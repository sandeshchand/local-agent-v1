from __future__ import annotations

from dataclasses import dataclass
import re

@dataclass(slots=True)
class EvidenceCheckResult:
    sufficient: bool
    quality_score: float
    overlap_ratio: float
    matched_terms: list[str]
    reason: str

class EvidenceChecker:
    def __init__(self) -> None:
       self.stop_words = {
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
        "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
        "about", "against", "between", "into", "through", "during", "before", "after",
        "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
        "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
        "about", "against", "between", "into", "through", "during", "before", "after",
        "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
        "over", "under"
        }

    def evaluate(self, query: str, results: list[str])-> EvidenceCheckResult:
        if not results:
            return EvidenceCheckResult(
                sufficient=False,
                quality_score=0.0,
                overlap_ratio=0.0,
                matched_terms=[],
                reason="No  retrieval results found"
            )
        

        terms = self._extract_terms(query)
        if not terms:
            return EvidenceCheckResult(
                sufficient=len(results) > 0,
                quality_score=0.2 if results else 0.0,
                overlap_ratio=0.0,
                matched_terms=[],
                reason="No stron query terms extracted, but results exist."
            )
        top_chunks =results[:2]
        best_ratio= 0.0
        best_matches: list[str] = []

        query_lower = query.lower().strip()
        exact_phrase_hit = False
        title_hit = False

        for item in top_chunks:
            text = (item.get("text") or "").lower()
            title = (item.get("title") or "").lower()

            if query_lower and query_lower in text:
                exact_phrase_hit = True

            if any(term in title for term in terms):
                title_hit = True
            matches = [term for term in terms if term in text or term in title]
            ratio = len(matches) / max(len(terms), 1)

            if ratio > best_ratio:
                best_ratio = ratio
                best_matches = matches

        quality_score = best_ratio

        if exact_phrase_hit:
            quality_score = min(1.0, quality_score + 0.2)
        if title_hit:
            quality_score = min(1.0, quality_score + 0.1)
        
        sufficient = exact_phrase_hit or best_ratio > 0.45 or (best_ratio >= 0.34 and title_hit)

        reasons_parts = [
            f"overlap_ratio={best_ratio:.2f}",
            f"exact_phrase={exact_phrase_hit}",
            f"title_hit={title_hit}",
            f"matched_terms={best_matches}",
        ]

        return EvidenceCheckResult(
            sufficient=sufficient,
            quality_score=quality_score,
            overlap_ratio=best_ratio,
            matched_terms=best_matches,
            reason=", ".join(reasons_parts),
        )
        
    def _extract_terms(self, query: str) -> list[str]:
        tokens = re.findall(r"\b\w+\b", query.lower())
        cleaned: list[str] =[]
        for token in tokens:
            if len(token) < 3:
                continue
            if token in self.stop_words:
                continue
            cleaned.append(token)
        
        deduped: list[str] =[]
        seen: set[str] = set()
        for token in cleaned:
            if token not in seen:
                deduped.append(token)
                seen.add(token)
        return deduped
       
    
    