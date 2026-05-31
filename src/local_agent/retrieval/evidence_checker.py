from __future__ import annotations

from dataclasses import dataclass
import re

@dataclass(slots=True)
class EvidenceCheckResult:
    sufficient: bool
    need_retry: bool
    quality_score: float
    overlap_ratio: float
    matched_terms: list[str]
    missing_terms: list[str]
    suggested_terms: list[str]
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
                need_retry=True,
                quality_score=0.0,
                overlap_ratio=0.0,
                matched_terms=[],
                missing_terms=[],
                suggested_terms=[],
                reason="No  retrieval results found"
            )
        

        terms = self._extract_terms(query)
        if not terms:
            return EvidenceCheckResult(
                sufficient= True,
                need_retry=False,
                quality_score=0.3,
                overlap_ratio=0.0,
                matched_terms=[],
                missing_terms=[],
                suggested_terms=[],
                reason="No strong query terms extracted, but results exist."
            )
        top_chunks =results[:3]
        combined_text = " ".join((item.get("title") or " " + (item.get("text") or ""))
        for item in top_chunks
        ).lower()

        matched_terms = [term for term in terms if term in combined_text]
        missing_terms = [term for term in terms if term not in matched_terms]

        overlap_ratio = len(matched_terms) / max(len(terms),1)

        query_lower = query.lower()
        exact_phrase_hit = query_lower in combined_text

        list_intent = any(
            word in query_lower for word in ["types", "categories", "list", "different types", "kinds"]
        )
        safety_intent = any(
            word in query_lower for word in ["safety", "risk", "risks", "concern", "concerns", "trustworthiness"]
        )
        instructions_intent = any(
            word in query_lower for word in ["instruction", "instructions","following", "follow"]
        )

        suggested_terms: list[str] = []
        if list_intent:
            suggested_terms.extend(["types", "text prompt", "image prompt", "video prompt", "categories"])
        if safety_intent:
             suggested_terms.extend([
            "safety",
            "jailbreak",
            "harmful",
            "misuse",
            "privacy",
            "multimodal",
            "authenticity",
        ])
        if instructions_intent:
            suggested_terms.extend([
            "caption",
            "captioner",
            "descriptive captions",
            "fine-tune",
            "instruction following",
        ])

        # Remove duplicates while preserving order 
        suggested_terms = list(dict.fromkeys(suggested_terms))

        quality_score = overlap_ratio
        if exact_phrase_hit:
            quality_score = min(1.0, quality_score + 0.2)
        
        # Intent-specific sufficiency
        if list_intent:
            category_hits = sum(
                1 for phrase in ["text prompt", "image prompt", "video prompt"]
                if phrase in combined_text
            )
            sufficient = category_hits >=2 or overlap_ratio >= 0.25
            need_retry = category_hits < 3
            reason = (
            f"list_intent=True, category_hits={category_hits}, "
            f"overlap_ratio={overlap_ratio:.2f}, matched_terms={matched_terms}"
            )
        elif safety_intent:
            safety_hits= sum(
                1 for phrase in ["safety", "jailbreak", "harmful", "misuse", "privacy", "multimodal", "authenticity"]
                if phrase in combined_text
            )
            sufficient = safety_hits >=2 or overlap_ratio >= 0.45
            need_retry = safety_hits < 2
            reason = (
            f"safety_intent=True, safety_hits={safety_hits}, "
            f"overlap_ratio={overlap_ratio:.2f}, matched_terms={matched_terms}"
            )
        elif instructions_intent:
            instructions_keywords = [
                                "caption",
                                "captioner",
                                "captioning",
                                "descriptive",
                                "description",
                                "fine-tune",
                                "fine-tuning",
                                "training data",
                                "instruction following",
                                "follow text instructions",
                                "user prompts",
                                "text prompts",
                            ]

            instruction_hits = sum(
                1 for phrase in instructions_keywords
                if phrase in combined_text
            )
            sufficient = instruction_hits >=2 or overlap_ratio >= 0.35
            need_retry = instruction_hits < 2
            reason = (
            f"instruction_intent=True, instruction_hits={instruction_hits}, "
            f"overlap_ratio={overlap_ratio:.2f}, matched_terms={matched_terms}"
            )
        else:
            sufficient = exact_phrase_hit or overlap_ratio >= 0.45
            need_retry = not sufficient
            reason = (
            f"generic_check=True, exact_phrase={exact_phrase_hit}, "
            f"overlap_ratio={overlap_ratio:.2f}, matched_terms={matched_terms}"
            )  

        return EvidenceCheckResult(
            sufficient=sufficient,
            need_retry=need_retry,
            quality_score=quality_score,
            overlap_ratio=overlap_ratio,
            matched_terms=matched_terms,
            missing_terms=missing_terms,
            suggested_terms=suggested_terms,
            reason=reason,
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
       
    
    