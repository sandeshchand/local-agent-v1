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

        if any(word in query_lower for word in ["applications", "areas", "use case", "uses"]):
            terms.extend(["applications", "use cases", "areas", "domains", "industries", "sectors", "examples"])

        if any(word in query_lower for word in ["architecture", "framework", "component", "components", "core model"]):
            terms.extend(["architecture", "framework", "components", "module", "model", "mechanism"])

        if any(word in query_lower for word in ["represent", "representation", "encode", "encoding", "before feeding", "model input"]):
            terms.extend(["representation", "encoding", "tokens", "patches", "latent", "compressed", "input", "encoder", "model"])

        if any(word in query_lower for word in ["native", "size", "sizes", "resolution", "aspect ratio"]):
            terms.extend(["native", "duration", "resolution", "aspect ratio", "format", "composition", "framing", "crop", "resize"])

        if any(word in query_lower for word in ["follow", "following", "detailed", "language", "understanding"]):
            terms.extend(["instruction", "following", "caption", "description", "fine-tune", "training", "prompt"])

        is_practice_challenge = bool(re.search(r"\b\d+\s*[- ]?\s*day\s+[^?]*challenge\b|\bpractice\w*\s+[^?]*challenge\b", query_lower))
        if any(word in query_lower for word in ["limitation", "limitations", "risk", "weakness", "constraint"]) or (
            "challenge" in query_lower and not is_practice_challenge
        ):
            terms.extend([
                "limitations",
                "challenges",
                "constraints",
                "failure",
                "risk",
                "issue",
                "accuracy",
                "usage",
                "physical",
                "spatial",
                "temporal",
                "interaction",
                "access",
                "safety",
            ])

        if any(word in query_lower for word in ["different", "earlier", "previous", "compare", "compared"]):
            terms.extend(["different", "previous", "earlier", "compared", "unlike", "improvement"])

        if any(word in query_lower for word in ["capability", "capabilities", "simulate", "simulation", "simulator", "ability"]):
            terms.extend(["capabilities", "ability", "simulate", "simulation", "environment", "world", "consistency", "coherence"])

        terms.extend(self._query_keyphrases(query))

        return list(dict.fromkeys(terms))

    def _query_keyphrases(self, query: str) -> list[str]:
        tokens = [
            token
            for token in re.findall(r"\b[a-zA-Z0-9][a-zA-Z0-9._-]{1,}\b", query)
            if token.lower() not in self.stopwords
        ]
        phrases: list[str] = []
        for match in re.finditer(
            r"\b[A-Z][A-Za-z0-9._-]*\b(?:\s+\b[A-Z][A-Za-z0-9._-]*\b){0,3}",
            query,
        ):
            phrase = match.group(0).strip()
            if len(phrase) >= 3 and phrase.lower() not in self.stopwords:
                phrases.append(phrase)
        for size in range(4, 1, -1):
            for index in range(0, len(tokens) - size + 1):
                phrase = " ".join(tokens[index : index + size]).strip()
                if len(phrase) >= 7:
                    phrases.append(phrase)
        return phrases[:16]
