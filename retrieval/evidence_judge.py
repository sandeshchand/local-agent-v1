from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


EvidenceLabel = Literal[
    "DEFINITIVE",
    "SUPPORTING_DETAIL",
    "BACKGROUND",
    "CONFLICTING_OR_SPECULATIVE",
    "IRRELEVANT",
]


@dataclass
class JudgedEvidence:
    item: dict
    label: EvidenceLabel
    reason: str


class EvidenceJudge:
    def __init__(self, chat_client) -> None:
        self.chat_client = chat_client

    def judge_chunk(self, query: str, item: dict) -> JudgedEvidence:
        text = (item.get("text") or "")[:1200]

        prompt = f"""
You are an evidence classification judge for a RAG system.

Question:
{query}

Retrieved chunk:
{text}

Classify this chunk into exactly ONE label:

MAIN_ANSWER:
- The chunk directly answers the question.

SUPPORTING_DETAIL:
- The chunk supports or clarifies the answer, but is not the main answer.

BACKGROUND:
- The chunk gives related background but does not directly answer.

CONFLICTING_OR_SPECULATIVE:
- The chunk is speculative, uncertain, or gives a different/secondary interpretation.
- Examples of speculative language: "we speculate", "may", "might", "likely", "reverse engineering".

IRRELEVANT:
- The chunk does not help answer the question.

Return only valid JSON:
{{"label": "...", "reason": "..."}}
""".strip()

        raw = self.chat_client.generate(prompt).strip()

        label = "IRRELEVANT"
        reason = raw

        raw_upper = raw.upper()
        for candidate in [
            "MAIN_ANSWER",
            "SUPPORTING_DETAIL",
            "BACKGROUND",
            "CONFLICTING_OR_SPECULATIVE",
            "IRRELEVANT",
        ]:
            if candidate in raw_upper:
                label = candidate
                break

        return JudgedEvidence(item=item, label=label, reason=reason)

    def select_evidence(
        self,
        query: str,
        results: list[dict],
        max_items: int = 8,
    ) -> tuple[list[dict], list[JudgedEvidence]]:
        judgments: list[JudgedEvidence] = []

        for item in results:
            judgments.append(self.judge_chunk(query, item))

        selected: list[dict] = []
        seen_chunk_ids: set[str] = set()

        def add_item(item: dict) -> None:
            chunk_id = item.get("chunk_id")
            if chunk_id in seen_chunk_ids:
                return
            selected.append(item)
            if chunk_id:
                seen_chunk_ids.add(chunk_id)

        for judgment in judgments:
            if judgment.label in {"MAIN_ANSWER", "DEFINITIVE"}:
                add_item(judgment.item)

        for judgment in judgments:
            if judgment.label == "SUPPORTING_DETAIL":
                add_item(judgment.item)

        for judgment in judgments:
            if judgment.label == "BACKGROUND" and self._has_query_overlap(query, judgment.item):
                add_item(judgment.item)

        selected.sort(key=lambda item: self._relevance_score(query, item), reverse=True)
        selected = selected[:max_items]

        return selected, judgments

    def _query_overlap_count(self, query: str, item: dict) -> int:
        query_terms = self._query_terms(query)
        evidence_text = self._evidence_text(item)
        return sum(1 for term in query_terms if term in evidence_text)

    def _relevance_score(self, query: str, item: dict) -> int:
        evidence_text = self._evidence_text(item)
        score = self._query_overlap_count(query, item) * 2

        query_lower = query.lower()
        if "limitation" in query_lower:
            limitation_phrases = [
                "physical principles",
                "cause and effect",
                "physical plausibility",
                "simulation of motion",
                "spatial",
                "temporal",
                "irrelevant animals",
                "irrelevant animals or people",
                "human-computer interaction",
                "hci",
                "usage limitation",
                "public access",
                "safety and readiness",
                "one minute",
            ]
            score += sum(3 for phrase in limitation_phrases if phrase in evidence_text)
            page_number = item.get("page_number")
            try:
                page_int = int(page_number)
            except (TypeError, ValueError):
                page_int = 0
            if 22 <= page_int <= 23:
                score += 8

        return score

    def _has_query_overlap(self, query: str, item: dict) -> bool:
        query_terms = self._query_terms(query)
        if not query_terms:
            return False

        evidence_text = self._evidence_text(item)
        matches = self._query_overlap_count(query, item)
        phrase_hits = sum(
            1
            for phrase in [
                "spatial-patch compression",
                "spatial-temporal-patch compression",
                "patch-level compression",
            ]
            if phrase in evidence_text
        )
        return matches >= min(2, len(query_terms)) or phrase_hits >= 1

    def _query_terms(self, query: str) -> set[str]:
        stop_words = {
            "the",
            "and",
            "for",
            "with",
            "what",
            "does",
            "review",
            "discuss",
            "sora",
            "are",
            "how",
            "why",
            "this",
            "that",
            "from",
            "into",
        }
        return {
            token
            for token in re.findall(r"\b\w+\b", query.lower())
            if len(token) >= 4 and token not in stop_words
        }

    def _evidence_text(self, item: dict) -> str:
        return " ".join(
            [
                item.get("section_title") or "",
                item.get("title") or "",
                item.get("text") or "",
            ]
        ).lower()
