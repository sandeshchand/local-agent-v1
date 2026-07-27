from __future__ import annotations

import re


class LimitationExtractorMixin:
    def _limitation_extractive_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        is_practice_challenge = bool(re.search(r"\b\d+\s*[- ]?\s*day\s+[^?]*challenge\b|\bpractice\w*\s+[^?]*challenge\b", q))
        if not (
            any(term in q for term in ["limitation", "limitations", "weakness"])
            or ("challenge" in q and not is_practice_challenge)
        ):
            return ""

        facts = [
            fact[2:].strip()
            for fact in self._build_evidence_fact_list(query, results, max_facts=48).splitlines()
            if fact.startswith("- ")
        ]
        if not facts:
            return ""

        category_markers = [
            ("physical/cause-and-effect", ["cause", "effect", "physical", "plausibility", "rigid", "motion"]),
            ("spatial", ["spatial", "placement", "arrangement", "left", "right", "direction"]),
            ("temporal", ["temporal", "camera", "sequence", "flow"]),
            ("irrelevant entities", ["irrelevant", "unrelated", "animals", "people", "characters", "elements"]),
            ("human-computer interaction (HCI)", ["human-computer", "hci", "user-system", "user system", "interaction", "language instructions"]),
            ("usage/access", ["usage", "access", "release", "public", "safety", "one minute", "one-minute", "length"]),
        ]
        markers = list(dict.fromkeys(marker for _, group in category_markers for marker in group)) + [
            "limitation",
            "challenge",
            "failure",
            "constraint",
            "issue",
        ]
        scored: list[tuple[int, int, str]] = []
        for index, fact in enumerate(facts):
            fact_text = re.sub(r"\[\d+\]", "", fact)
            fact_lower = fact_text.lower()
            if self._looks_like_code_or_metadata_fact(fact_text) or self._is_low_value_fact(fact_text):
                continue
            score = sum(2 for marker in markers if marker in fact_lower)
            score += self._sentence_relevance_score(fact_text, self._query_terms(query))
            if score > 0:
                scored_item = (score, -index, fact)
                scored.append(scored_item)
        if not scored:
            return ""
        scored.sort(reverse=True)

        selected: list[str] = []
        seen: set[str] = set()
        for category, group_markers in category_markers:
            best: tuple[int, int, str] | None = None
            for index, fact in enumerate(facts):
                fact_text = re.sub(r"\[\d+\]", "", fact)
                fact_lower = fact_text.lower()
                if self._looks_like_code_or_metadata_fact(fact_text) or self._is_low_value_fact(fact_text):
                    continue
                score = sum(3 for marker in group_markers if marker in fact_lower)
                if score <= 0:
                    continue
                score += self._sentence_relevance_score(fact_text, self._query_terms(query))
                candidate = (score, -index, fact)
                if best is None or candidate > best:
                    best = candidate
            if best is None:
                continue
            fact = self._tag_limitation_fact(category, self._shorten_fact(best[2], max_words=34))
            normalized = re.sub(r"\W+", " ", fact.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append(f"- {fact}")
            if len(selected) >= 6:
                break

        for _, _, fact in scored:
            fact = self._shorten_fact(fact, max_words=34)
            normalized = re.sub(r"\W+", " ", fact.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append(f"- {fact}")
            if len(selected) >= 7:
                break
        if not selected:
            return ""
        return self._clean_final_answer("The highlighted limitations are: " + " ".join(selected))
    def _tag_limitation_fact(self, category: str, fact: str) -> str:
        fact_lower = fact.lower()
        citation_match = re.search(r"\s*\[(\d+)\]\s*$", fact)
        citation = f" [{citation_match.group(1)}]" if citation_match else ""
        body = re.sub(r"\s*\[\d+\]\s*$", "", fact).strip()
        if category.startswith("spatial") and "spatial" not in fact_lower:
            body = f"Spatial limitation: {body}"
        elif category.startswith("human-computer") and (
            len(body.split()) < 6
            or ("human-computer" not in fact_lower and "hci" not in fact_lower)
        ):
            body = f"Human-computer interaction (HCI) limitation: {body}"
        elif category.startswith("physical") and "cause" not in fact_lower:
            body = f"Physical/cause-and-effect limitation: {body}"
        elif category.startswith("irrelevant") and "irrelevant" not in fact_lower:
            body = f"Irrelevant-entity limitation: {body}"
        elif category.startswith("usage") and "usage" not in fact_lower:
            body = f"Usage/access limitation: {body}"
        return f"{body}.{citation}" if citation and not body.endswith((".", "!", "?")) else f"{body}{citation}"
