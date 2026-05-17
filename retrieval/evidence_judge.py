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
        query_terms = self._query_terms(query)
        section_text = " ".join(
            [
                item.get("section_title") or "",
                item.get("title") or "",
            ]
        ).lower()

        important_query_phrases = self._query_phrases(query_lower)
        score += sum(6 for phrase in important_query_phrases if phrase in section_text)
        score += sum(3 for phrase in important_query_phrases if phrase in evidence_text)
        if query_terms and all(term in evidence_text for term in query_terms):
            score += 4

        for term in self._intent_terms(query_lower):
            if term in section_text:
                score += 5
            if term in evidence_text:
                score += 2

        return score

    def _query_phrases(self, query_lower: str) -> list[str]:
        phrases: list[str] = []
        for separator in [" about ", " say about ", " does ", " do "]:
            if separator in query_lower:
                tail = query_lower.split(separator, 1)[1]
                tail = re.sub(r"\?$", "", tail).strip()
                if len(tail.split()) >= 2:
                    phrases.append(tail)
        words = [
            word
            for word in re.findall(r"\b[a-zA-Z][a-zA-Z0-9\-]{3,}\b", query_lower)
            if word not in self._stop_words()
        ]
        for index in range(len(words) - 1):
            phrases.append(f"{words[index]} {words[index + 1]}")
        return list(dict.fromkeys(phrases))

    def _has_query_overlap(self, query: str, item: dict) -> bool:
        query_terms = self._query_terms(query)
        if not query_terms:
            return False

        evidence_text = self._evidence_text(item)
        matches = self._query_overlap_count(query, item)
        intent_hits = sum(1 for term in self._intent_terms(query.lower()) if term in evidence_text)
        return matches >= min(2, len(query_terms)) or intent_hits >= 1

    def _query_terms(self, query: str) -> set[str]:
        stop_words = {
            *self._stop_words(),
        }
        return {
            token
            for token in re.findall(r"\b\w+\b", query.lower())
            if len(token) >= 4 and token not in stop_words
        }

    def _stop_words(self) -> set[str]:
        return {
            "the",
            "and",
            "for",
            "with",
            "what",
            "does",
            "review",
            "discuss",
            "are",
            "how",
            "why",
            "this",
            "that",
            "from",
            "into",
            "about",
            "they",
            "their",
            "before",
            "after",
            "using",
            "uses",
        }

    def _evidence_text(self, item: dict) -> str:
        return " ".join(
            [
                item.get("section_title") or "",
                item.get("title") or "",
                item.get("text") or "",
            ]
        ).lower()

    def _intent_terms(self, query_lower: str) -> list[str]:
        terms: list[str] = []
        if any(word in query_lower for word in ["input", "prompt", "instruction", "query"]):
            terms.extend(["input", "prompt", "instruction", "user", "text", "natural language"])
        if any(word in query_lower for word in ["application", "applications", "areas", "use case", "uses"]):
            terms.extend(["application", "applications", "use case", "domain", "area", "industry", "sector"])
        if any(word in query_lower for word in ["architecture", "framework", "component", "core model"]):
            terms.extend(["architecture", "framework", "component", "module", "mechanism"])
        if any(word in query_lower for word in ["represent", "representation", "encode", "encoding", "before feeding", "model input"]):
            terms.extend(["representation", "encoding", "token", "patch", "latent", "compressed", "input"])
        if any(word in query_lower for word in ["native", "size", "sizes", "resolution", "aspect ratio"]):
            terms.extend(["native", "duration", "resolution", "aspect ratio", "format", "composition", "framing", "crop", "resize"])
        if any(word in query_lower for word in ["follow", "following", "detailed", "language", "understanding"]):
            terms.extend(["instruction", "following", "caption", "description", "training", "fine-tune", "prompt"])
        if any(word in query_lower for word in ["limitation", "limitations", "risk", "challenge", "weakness", "constraint"]):
            terms.extend(["limitation", "challenge", "constraint", "failure", "risk", "issue", "accuracy", "usage"])
        if any(word in query_lower for word in ["different", "earlier", "previous", "compare", "compared"]):
            terms.extend(["different", "previous", "earlier", "compared", "unlike", "improvement"])
        if any(word in query_lower for word in ["capability", "capabilities", "simulate", "simulation", "simulator", "ability"]):
            terms.extend(["capability", "ability", "simulate", "simulation", "environment", "world", "consistency", "coherence"])
        return list(dict.fromkeys(terms))
