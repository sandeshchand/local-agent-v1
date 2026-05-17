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
        expansion_terms = self._intent_expansion_terms(original_query)
        expanded = " ".join(dict.fromkeys([original_query, candidate, *expansion_terms])).strip()
        return expanded or original_query

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
        terms.extend(self._intent_expansion_terms(original_query))

        # Deduplicate
        terms = list(dict.fromkeys(t for t in terms if t))

        if not terms:
            return previous_query

        return f"{original_query} {' '.join(terms)}".strip()

    def _intent_expansion_terms(self, query: str) -> list[str]:
        query_lower = query.lower()
        terms: list[str] = []

        if any(word in query_lower for word in ["input", "prompt", "instruction", "query"]):
            terms.extend(["input", "prompt", "instruction", "user", "natural language", "text"])

        if any(word in query_lower for word in ["application", "applications", "areas", "use case", "uses"]):
            terms.extend(["applications", "use cases", "areas", "domains", "industries", "sectors", "examples"])

        if any(word in query_lower for word in ["architecture", "framework", "component", "components", "core model"]):
            terms.extend(["architecture", "framework", "components", "module", "model", "mechanism"])

        if any(word in query_lower for word in ["represent", "representation", "encode", "encoding", "before feeding", "model input"]):
            terms.extend(["representation", "encoding", "tokens", "patches", "latent", "compressed", "input", "encoder", "transformer"])

        if any(word in query_lower for word in ["native", "size", "sizes", "resolution", "aspect ratio"]):
            terms.extend(["native", "duration", "resolution", "aspect ratio", "format", "composition", "framing", "crop", "resize"])

        if any(word in query_lower for word in ["follow", "following", "detailed", "language", "understanding"]):
            terms.extend(["instruction", "following", "caption", "description", "fine-tune", "training", "prompt"])

        if any(word in query_lower for word in ["limitation", "limitations", "risk", "challenge", "weakness", "constraint"]):
            terms.extend(["limitations", "challenges", "constraints", "failure", "risk", "issue", "accuracy", "usage"])

        if any(word in query_lower for word in ["different", "earlier", "previous", "compare", "compared"]):
            terms.extend(["different", "previous", "earlier", "compared", "unlike", "improvement"])

        if any(word in query_lower for word in ["capability", "capabilities", "simulate", "simulation", "simulator", "ability"]):
            terms.extend(["capabilities", "ability", "simulate", "simulation", "environment", "world", "consistency", "coherence"])

        return list(dict.fromkeys(terms))
