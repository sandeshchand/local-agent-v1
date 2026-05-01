from __future__ import annotations

import re
from typing import Any


class QueryRewriter:
    def __init__(self) -> None:
        self.stopwords = {
            "a", "an", "the", "and", "or", "but", "if", "then",
            "is", "are", "was", "were", "be", "been",
            "what", "which", "who", "how", "why", "when", "where",
            "of", "in", "on", "at", "by", "for", "with", "about",
            "to", "from", "into", "through", "does", "do", "did",
        }

    def rewrite(
        self,
        query: str,
        results: list[dict] | None = None,
        session_memory: list[Any] | None = None,
    ) -> str:
        # Conservative first-pass rewrite: mostly cleanup
        original_query = query.strip()
        tokens = re.findall(r"\b\w+\b", original_query.lower())

        cleaned: list[str] = []
        for token in tokens:
            if len(token) < 3:
                continue
            if token in self.stopwords:
                continue
            cleaned.append(token)

        candidate = " ".join(dict.fromkeys(cleaned)).strip()
        return candidate or original_query

    def rewrite_for_retry(
        self,
        original_query: str,
        previous_query: str,
        missing_terms: list[str] | None = None,
        suggested_terms: list[str] | None = None,
        failure_reason: str = "",
    ) -> str:
        terms: list[str] = []

        if suggested_terms:
            terms.extend(suggested_terms)

        if missing_terms:
            terms.extend(missing_terms)

        query_lower = original_query.lower()

        # General intent expansion, still domain-independent enough for papers/docs
        if any(w in query_lower for w in ["types", "categories", "kinds"]):
            terms.extend(["types", "categories", "section", "subsection"])

        if any(w in query_lower for w in ["safety", "risk", "concern", "trustworthiness"]):
            terms.extend(["safety", "risk", "misuse", "privacy", "harmful", "attack"])

        if any(w in query_lower for w in ["instruction", "follow", "following"]):
            terms.extend(["instruction", "caption", "captioner", "fine-tune", "descriptive"])

        # Deduplicate
        terms = list(dict.fromkeys(t for t in terms if t))

        if not terms:
            return previous_query

        return f"{original_query} {' '.join(terms)}".strip()