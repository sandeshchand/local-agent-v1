from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


EvidenceLabel = Literal[
    "MAIN_ANSWER",
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
        max_items: int = 4,
    ) -> tuple[list[dict], list[JudgedEvidence]]:
        judgments: list[JudgedEvidence] = []

        for item in results:
            judgments.append(self.judge_chunk(query, item))

        selected: list[dict] = []

        for judgment in judgments:
            if judgment.label == "MAIN_ANSWER":
                selected.append(judgment.item)

        for judgment in judgments:
            if judgment.label == "SUPPORTING_DETAIL":
                selected.append(judgment.item)

        selected = selected[:max_items]

        return selected, judgments