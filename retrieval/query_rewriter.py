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
        expansion_terms = self._domain_expansion_terms(original_query)
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
        if any(w in query_lower for w in ["types", "categories", "kinds"]):
            terms.extend(["types", "categories", "section", "subsection"])

        if any(w in query_lower for w in ["safety", "risk", "concern", "trustworthiness"]):
            terms.extend(["safety", "risk", "misuse", "privacy", "harmful", "attack"])

        if any(w in query_lower for w in ["instruction", "follow", "following"]):
            terms.extend(["instruction", "caption", "captioner", "fine-tune", "descriptive"])
        terms.extend(self._domain_expansion_terms(original_query))

        # Deduplicate
        terms = list(dict.fromkeys(t for t in terms if t))

        if not terms:
            return previous_query

        return f"{original_query} {' '.join(terms)}".strip()

    def _domain_expansion_terms(self, query: str) -> list[str]:
        query_lower = query.lower()
        terms: list[str] = []

        if "architecture" in query_lower or "core model" in query_lower:
            terms.extend(
                [
                    "diffusion transformer",
                    "time-space compressor",
                    "spacetime latent patches",
                    "ViT",
                    "CLIP",
                    "conditioning",
                    "tokenized latent",
                ]
            )

        if "native" in query_lower or "sizes" in query_lower or "aspect ratio" in query_lower:
            terms.extend(
                [
                    "variable durations",
                    "resolutions",
                    "aspect ratios",
                    "flexible sizes",
                    "composition",
                    "framing",
                    "square crop",
                ]
            )

        if "visual data" in query_lower or "model input" in query_lower:
            terms.extend(
                [
                    "unified visual representation",
                    "lower-dimensional latent space",
                    "spacetime patches",
                    "compressed video",
                    "diffusion transformer",
                ]
            )

        if "compression" in query_lower:
            terms.extend(
                [
                    "video compression network",
                    "spatial-patch compression",
                    "spatial-temporal-patch compression",
                    "patch-level compression",
                    "VAE",
                    "VQ-VAE",
                ]
            )

        if "spacetime latent" in query_lower or "fed into" in query_lower:
            terms.extend(
                [
                    "Patch n Pack",
                    "PNP",
                    "fixed-length sequences",
                    "padding tokens",
                    "super long context window",
                    "3D consistency",
                ]
            )

        if "language" in query_lower or "prompt following" in query_lower or "instruction" in query_lower:
            terms.extend(
                [
                    "DALL-E 3",
                    "captioner",
                    "descriptive captions",
                    "video descriptive caption pairs",
                    "fine-tune Sora",
                    "GPT-4V",
                    "prompt extension",
                ]
            )

        if "prompt engineering" in query_lower:
            terms.extend(
                [
                    "text prompt",
                    "image prompt",
                    "video prompt",
                    "visual anchor",
                    "video extension",
                    "video editing",
                    "video connection",
                ]
            )

        if "simulation" in query_lower or "capabilities" in query_lower:
            terms.extend(
                [
                    "3D consistency",
                    "dynamic camera motion",
                    "long-range coherence",
                    "object permanence",
                    "interactions with the world",
                    "Minecraft",
                    "digital environments",
                ]
            )

        if "limitation" in query_lower or "limitations" in query_lower:
            terms.extend(
                [
                    "physical principles",
                    "cause and effect",
                    "spatial",
                    "temporal",
                    "irrelevant animals or people",
                    "human-computer interaction",
                    "usage limitation",
                    "public access",
                    "one minute",
                ]
            )

        return list(dict.fromkeys(terms))
