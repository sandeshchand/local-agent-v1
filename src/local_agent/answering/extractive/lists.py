from __future__ import annotations

import re


class ListExtractorMixin:
    def _list_extractive_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        is_practice_challenge = bool(re.search(r"\b\d+\s*[- ]?\s*day\s+[^?]*challenge\b|\bpractice\w*\s+[^?]*challenge\b", q))
        list_intent = (
            self._is_list_question(query)
            or q.startswith("which")
            or any(
                term in q
                for term in [
                    "pipeline",
                    "formula",
                    "advancements",
                    "best practices",
                    "setup",
                    "commands",
                    "recommend",
                    "mentioned",
                    "tools",
                    "role",
                    "roles",
                    "component",
                    "components",
                    "strengths",
                    "architecture",
                    "collaboration",
                    "reasons",
                ]
            )
        )
        if not list_intent:
            return ""

        fact_lines = [
            fact[2:].strip()
            for fact in self._build_evidence_fact_list(query, results, max_facts=40).splitlines()
            if fact.startswith("- ")
        ]
        if not fact_lines:
            return ""

        query_terms = self._query_terms(query)
        intent_terms = self._query_intent_terms(query) + self._intent_terms_from_query_terms(query_terms)
        list_markers = [
            "day ",
            "step",
            "first",
            "second",
            "third",
            "finally",
            "hook",
            "highlight",
            "handoff",
            "load",
            "generate",
            "export",
            "download",
            "preview",
            "local",
            "url",
            "model",
            "format",
            "reasoning",
            "integration",
            "environment",
            "version control",
            "runtime",
            "prompt",
            "test",
            "practice",
            "agent",
            "tool",
            "context",
            "codebase",
            "multi-file",
            "multi-agent",
            "surprise",
            "story",
            "emotional",
            "question",
            "client",
            "business",
            "skill",
            "service",
            "fear",
            "learn",
            "parallel",
            "specialization",
        ]
        if is_practice_challenge:
            list_markers.extend(["day ", "hook", "practice", "mirror", "friend", "feedback", "real life", "challenge"])

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
            score += sum(2 for marker in list_markers if marker in fact_lower)
            if re.search(r"\b(?:day\s*\d+|\d+[.)])\b", fact_lower):
                score += 6
            if ":" in fact_text[:80]:
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
            if len(selected) >= 8:
                break

        if len(selected) < 2:
            return ""

        if "pipeline" in q:
            prefix = "The main pipeline is:"
        elif "formula" in q:
            prefix = "The formula is:"
        elif "advancements" in q:
            prefix = "The key advancements are:"
        elif is_practice_challenge:
            prefix = "The challenge steps are:"
        elif "limitation" in q or "limitations" in q or "challenge" in q:
            prefix = "The limitations are:"
        elif "reason" in q or q.startswith("why"):
            prefix = "The reasons are:"
        elif "role" in q or "roles" in q:
            prefix = "The roles are:"
        elif "component" in q or "components" in q:
            prefix = "The components are:"
        elif "setup" in q or "commands" in q:
            prefix = "The setup/run items are:"
        else:
            prefix = "The steps are:"
        return self._clean_final_answer(f"{prefix} {' '.join(selected)}")
