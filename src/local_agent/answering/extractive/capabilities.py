from __future__ import annotations

import re


class CapabilityExtractorMixin:
    def _should_use_capability_extractive_answer(self, query: str, results: list[dict]) -> bool:
        q = query.lower()
        if not any(term in q for term in ["simulator", "simulation", "simulate"]):
            return False
        facts = self._build_evidence_fact_list(query, results, max_facts=10).lower()
        concrete_markers = [
            "consistency",
            "coherence",
            "persistence",
            "interaction",
            "physical",
            "digital",
            "environment",
            "such as",
            "like",
            "exhibits",
            "includes",
        ]
        return sum(1 for marker in concrete_markers if marker in facts) >= 3
    def _capability_extractive_answer(self, query: str, results: list[dict]) -> str:
        facts = self._build_evidence_fact_list(query, results, max_facts=18)
        clean_facts = [
            fact[2:].strip()
            for fact in facts.splitlines()
            if fact.startswith("- ")
        ]
        if not clean_facts:
            return ""

        query_terms = self._query_terms(query)
        intent_terms = self._intent_terms_from_query_terms(query_terms)
        scored: list[tuple[int, int, str]] = []
        for index, fact in enumerate(clean_facts):
            fact_text = re.sub(r"\[\d+\]", "", fact)
            fact_lower = fact_text.lower()
            score = self._sentence_relevance_score(fact_text, query_terms)
            score += sum(2 for term in intent_terms if term in fact_lower)
            score += sum(
                2
                for marker in [
                    "simulate",
                    "simulation",
                    "world",
                    "physical",
                    "digital",
                    "environment",
                    "consistency",
                    "coherence",
                    "persistence",
                    "interaction",
                ]
                if marker in fact_lower
            )
            score += sum(
                1
                for marker in ["such as", "like", "including", "includes", "exhibits", "capability", "ability"]
                if marker in fact_lower
            )
            if score > 0:
                scored.append((score, -index, fact))

        if not scored:
            return ""
        scored.sort(reverse=True)

        selected: list[str] = []
        seen: set[str] = set()
        for _, _, fact in scored:
            fact = self._compress_list_fact(query, fact)
            normalized = re.sub(r"\W+", " ", fact.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append(f"- {fact}")
            if len(selected) >= 5:
                break

        if not selected:
            return ""

        entity = self._focus_entity_display(query) or "The system"
        if query.lower().startswith("why"):
            prefix = f"{entity} is described as a potential world simulator because:"
        else:
            prefix = f"{entity}'s relevant capabilities are:"
        return self._ensure_focus_entity_mentioned(query, self._clean_final_answer(f"{prefix} {' '.join(selected)}"))
    def _mechanism_extractive_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        if "example" in q:
            return ""
        if not (
            q.startswith("how")
            or any(term in q for term in ["turn", "convert", "transform", "work", "detect", "load", "validate"])
        ):
            return ""

        fact_lines = [
            fact[2:].strip()
            for fact in self._build_evidence_fact_list(query, results, max_facts=32).splitlines()
            if fact.startswith("- ")
        ]
        if not fact_lines:
            return ""

        query_terms = self._query_terms(query)
        focus_phrases = self._focus_phrases(query)
        intent_terms = self._query_intent_terms(query) + self._intent_terms_from_query_terms(query_terms)
        anchor_citations = {
            self._extract_citation_number(fact)
            for fact in fact_lines
            if self._focus_phrase_score(fact, focus_phrases) > 0
        }
        anchor_citations.discard(None)

        process_markers = [
            "first",
            "then",
            "finally",
            "instead",
            "using",
            "uses",
            "works",
            "detect",
            "load",
            "validate",
            "convert",
            "output",
            "project",
            "compress",
            "extract",
            "approximat",
            "transform",
            "map",
            "partition",
            "labeled",
            "feature",
            "space",
            "scalable",
            "cost",
            "computation",
        ]

        scored: list[tuple[int, int, str]] = []
        for index, fact in enumerate(fact_lines):
            fact_text = re.sub(r"\[\d+\]", "", fact)
            fact_lower = fact_text.lower()
            if self._looks_like_code_or_metadata_fact(fact_text) and not self._should_keep_code_fact(query, fact_text):
                continue
            if self._is_low_value_fact(fact_text):
                continue
            if len(fact_text.split()) > 70 and not any(
                term in fact_lower for term in query_terms
            ) and not self._contains_distinctive_identifier(fact_text):
                continue

            focus_score = self._focus_phrase_score(fact_text, focus_phrases)
            relevance_score = self._sentence_relevance_score(fact_text, query_terms)
            intent_score = sum(2 for term in intent_terms if term in fact_lower)
            process_score = sum(1 for marker in process_markers if marker in fact_lower)
            citation_number = self._extract_citation_number(fact)
            same_topic_score = 2 if citation_number in anchor_citations and (intent_score or process_score) else 0

            score = focus_score + relevance_score + intent_score + process_score + same_topic_score
            if score > 0:
                scored.append((score, -index, fact))

        if not scored:
            return ""
        scored.sort(reverse=True)

        selected: list[str] = []
        seen: set[str] = set()
        for _, _, fact in scored:
            normalized = re.sub(r"\W+", " ", fact.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append(f"- {fact}")
            if len(selected) >= 7:
                break

        if len(selected) < 2:
            return ""

        entity = self._focus_entity_display(query) or "It"
        if "detect" in q or "anomal" in q:
            prefix = f"{entity} detects or helps in these cases by:"
        elif "turn" in q or "convert" in q or "transform" in q:
            prefix = f"{entity} turns the input into a usable representation by:"
        else:
            prefix = f"{entity} works this way:"
        return self._ensure_focus_entity_mentioned(query, self._clean_final_answer(f"{prefix} {' '.join(selected)}"))
