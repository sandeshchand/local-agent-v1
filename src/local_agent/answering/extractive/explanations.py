from __future__ import annotations

import re


class ExplanationExtractorMixin:
    def _why_extractive_answer(self, query: str, results: list[dict]) -> str:
        if not self._is_explanation_question(query):
            return ""

        q = query.lower()
        fact_lines = [
            fact[2:].strip()
            for fact in self._build_evidence_fact_list(query, results, max_facts=32).splitlines()
            if fact.startswith("- ")
        ]
        if not fact_lines:
            return ""

        query_terms = self._query_terms(query)
        intent_terms = self._query_intent_terms(query) + self._intent_terms_from_query_terms(query_terms)
        broad_subject_terms = {"python", "article", "paper", "document", "review", "pydantic", "ai"}
        specific_terms = query_terms - broad_subject_terms
        scored: list[tuple[int, int, str]] = []
        for index, fact in enumerate(fact_lines):
            fact_text = re.sub(r"\[\d+\]", "", fact)
            fact_lower = fact_text.lower()
            if self._looks_like_code_or_metadata_fact(fact_text) and not self._should_keep_code_fact(query, fact_text):
                continue
            if self._is_low_value_fact(fact_text):
                continue
            score = self._sentence_relevance_score(fact_text, query_terms)
            score += sum(2 for term in intent_terms if term in fact_lower)
            score += sum(1 for marker in [
                "because",
                "so that",
                "instead",
                "predictable",
                "tune out",
                "impression",
                "effect",
                "story",
                "attention",
                "remember",
                "safe",
                "structured",
                "configuration",
                "settings",
                "secrets",
                "hardcoding",
                "clean",
                "readable",
                "enforce",
                "forces",
                "slow",
                "messy",
                "inconvenient",
                "faster",
                "save time",
                "make money",
                "degree",
                "technical",
                "code",
            ] if marker in fact_lower)
            if specific_terms and not any(term in fact_lower for term in specific_terms) and not any(term in fact_lower for term in intent_terms):
                score -= 4
            if score > 0:
                scored.append((score, -index, fact))

        if not scored:
            return ""
        scored.sort(reverse=True)

        if any(term in q for term in ["forgettable", "remember", "memorable", "introduction", "intro"]):
            category_facts = [fact for _, _, fact in scored]
            selected_by_category = self._select_category_facts(
                category_facts,
                [
                    ("predictability", ["predictable", "tune out", "name", "job", "hobby"]),
                    ("impression", ["effect", "impression", "decide", "seconds", "stick"]),
                    ("memory/story", ["science", "fix", "story", "curiosity", "attention", "question", "engage", "remember", "memorable"]),
                ],
                max_items=5,
            )
            if len(selected_by_category) >= 2:
                return self._clean_final_answer("Because: " + " ".join(selected_by_category))

        selected: list[str] = []
        seen: set[str] = set()
        for _, _, fact in scored:
            normalized = re.sub(r"\W+", " ", fact.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append(f"- {fact}")
            if len(selected) >= 5:
                break

        if len(selected) < 2:
            return ""
        return self._clean_final_answer("Because: " + " ".join(selected))
    def _focused_entity_extractive_answer(self, query: str, results: list[dict]) -> str:
        focus_phrases = self._focus_phrases(query)
        if not focus_phrases:
            return ""

        query_terms = self._query_terms(query)
        clean_facts = [
            fact[2:].strip()
            for fact in self._build_evidence_fact_list(query, results, max_facts=28).splitlines()
            if fact.startswith("- ")
        ]
        if not clean_facts:
            return ""

        scored: list[tuple[int, int, str]] = []
        for index, fact in enumerate(clean_facts):
            fact_text = re.sub(r"\[\d+\]", "", fact)
            fact_lower = fact_text.lower()
            if self._looks_like_code_or_metadata_fact(fact_text) and not self._should_keep_code_fact(query, fact_text):
                continue
            focus_score = self._focus_phrase_score(fact_text, focus_phrases)
            if focus_phrases and focus_score == 0:
                continue
            score = focus_score
            score += self._sentence_relevance_score(fact_text, query_terms)
            score += sum(1 for term in self._intent_terms_from_query_terms(query_terms) if term in fact_lower)
            if any(marker in fact_lower for marker in ["is a", "are ", "used for", "useful", "helps", "allows", "features include", "key features", "strengths", "unlike", "instead"]):
                score += 2
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
            if len(selected) >= 6:
                break

        if not selected:
            return ""

        entity = self._focus_entity_display(query) or sorted(focus_phrases, key=len, reverse=True)[0].title()
        if "feature" in query.lower() or "strength" in query.lower():
            prefix = f"{entity}'s key points are:"
        elif query.lower().startswith("how"):
            prefix = f"{entity} works this way:"
        elif "used for" in query.lower() or "useful" in query.lower():
            prefix = f"{entity} is used for:"
        else:
            prefix = f"{entity}:"
        return self._clean_final_answer(f"{prefix} {' '.join(selected)}")
