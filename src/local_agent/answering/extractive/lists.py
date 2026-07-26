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
        focus_entity = self._focus_entity_display(query)
        focus_phrases = set(self._focus_phrases(query))
        if focus_entity:
            focus_phrases.add(focus_entity.lower())
        focused_entity_list = bool(focus_phrases) and (
            self._is_list_question(query)
            or any(
                term in q
                for term in [
                    "feature",
                    "features",
                    "capability",
                    "capabilities",
                    "strength",
                    "strengths",
                    "advantage",
                    "advantages",
                    "benefit",
                    "benefits",
                    "role",
                    "roles",
                    "component",
                    "components",
                ]
            )
        )
        focus_citations = self._focused_result_citations(results, focus_phrases)
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
            if focused_entity_list:
                focus_score = self._focus_phrase_score(fact_text, focus_phrases)
                if self._mentions_competing_named_topic(fact_text, focus_phrases):
                    continue
                if not self._is_focused_list_detail_fact(fact_text, intent_terms):
                    continue
                citation_number = self._extract_citation_number(fact)
                if focus_score == 0 and not (
                    citation_number in focus_citations
                    and self._is_focused_list_followup_fact(fact_text)
                ):
                    continue

            score = self._sentence_relevance_score(fact_text, query_terms)
            score += sum(2 for term in intent_terms if term in fact_lower)
            score += sum(2 for marker in list_markers if marker in fact_lower)
            if focused_entity_list:
                score += min(6, self._focus_phrase_score(fact_text, focus_phrases))
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
            max_selected = 6 if focused_entity_list else 8
            if len(selected) >= max_selected:
                break

        if len(selected) < 2:
            return ""

        focus_entity = focus_entity if focused_entity_list else ""
        focus_prefix = ""
        if focus_entity:
            suffix = "'" if focus_entity.lower().endswith("s") else "'s"
            focus_prefix = f"{focus_entity}{suffix}"

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
        elif "strength" in q or "advantage" in q or "benefit" in q:
            prefix = f"{focus_prefix} strengths are:" if focus_prefix else "The strengths are:"
        elif "role" in q or "roles" in q:
            prefix = f"{focus_prefix} roles are:" if focus_prefix else "The roles are:"
        elif "component" in q or "components" in q:
            prefix = f"{focus_prefix} components are:" if focus_prefix else "The components are:"
        elif "feature" in q or "features" in q:
            prefix = f"{focus_prefix} key features are:" if focus_prefix else "The key features are:"
        elif "setup" in q or "commands" in q:
            prefix = "The setup/run items are:"
        else:
            prefix = "The steps are:"
        return self._clean_final_answer(f"{prefix} {' '.join(selected)}")

    def _focused_result_citations(self, results: list[dict], focus_phrases: set[str]) -> set[int]:
        if not focus_phrases:
            return set()
        citations: set[int] = set()
        for index, item in enumerate(results, start=1):
            context = " ".join(
                [
                    item.get("section_title") or "",
                    item.get("title") or "",
                    item.get("text") or "",
                ]
            )
            if self._focus_phrase_score(context, focus_phrases) > 0:
                citations.add(index)
        return citations

    def _is_focused_list_detail_fact(self, fact: str, intent_terms: list[str]) -> bool:
        fact_lower = fact.lower()
        if any(term in fact_lower for term in intent_terms):
            return True
        detail_markers = [
            "feature",
            "strength",
            "advantage",
            "benefit",
            "capability",
            "requires",
            "require",
            "uses",
            "utilizes",
            "supports",
            "allows",
            "enables",
            "helps",
            "provides",
            "offers",
            "includes",
            "include",
            "monitors",
            "monitoring",
            "detects",
            "detecting",
            "updates",
            "updating",
            "watches",
            "alerts",
            "low memory",
            "high learning",
            "less computation",
            "low-power",
            "low power",
            "efficient",
            "efficiency",
            "performance",
            "hardware",
            "security",
            "stability",
        ]
        return any(marker in fact_lower for marker in detail_markers)

    def _is_focused_list_followup_fact(self, fact: str) -> bool:
        fact_lower = fact.lower().lstrip("- ").strip()
        if re.match(
            r"^(?:unlike|additionally|also|it|its|they|their|this|one|another|"
            r"a further|further|requires|can|uses|utilizes)\b",
            fact_lower,
        ):
            return True
        return bool(re.match(r"^[a-z ]{2,32}\s*(?:-|:|\u2013|\u2014)\s+", fact_lower))

    def _mentions_competing_named_topic(self, fact: str, focus_phrases: set[str]) -> bool:
        focus_compacts = {self._compact_text(phrase) for phrase in focus_phrases}
        for phrase in focus_phrases:
            acronym = self._phrase_acronym(phrase)
            if acronym:
                focus_compacts.add(self._compact_text(acronym))
                focus_compacts.add(self._compact_text(f"{acronym}s"))
        if not focus_compacts:
            return False
        generic_topic_terms = {
            "key",
            "main",
            "feature",
            "features",
            "benefit",
            "benefits",
            "strength",
            "strengths",
            "limitation",
            "limitations",
            "overview",
            "introduction",
            "conclusion",
            "summary",
            "getting",
            "started",
            "when",
            "use",
            "normal",
            "data",
            "some",
            "outliers",
            "anomalies",
            "monitoring",
            "detecting",
            "updating",
            "installation",
            "usage",
            "setup",
            "configuration",
        }
        for phrase in re.findall(
            r"\b[A-Z][A-Za-z0-9_-]{2,}\b(?:\s+\(?[A-Z][A-Za-z0-9_-]{1,}\)?\b){1,5}",
            fact,
        ):
            tokens = [
                token.lower()
                for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_-]*\b", phrase)
            ]
            if not tokens or all(token in generic_topic_terms for token in tokens):
                continue
            compact = self._compact_text(" ".join(tokens))
            if any(focus in compact or compact in focus for focus in focus_compacts):
                continue
            if self._looks_like_topic_introduction(phrase, fact):
                return True
        for token in re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,}\b", fact):
            token_lower = token.lower()
            if token_lower in generic_topic_terms:
                continue
            compact = self._compact_text(token_lower)
            if any(focus in compact or compact in focus for focus in focus_compacts):
                continue
            has_tool_style_case = any(char.isupper() for char in token[1:]) and not token.isupper()
            has_heading_punctuation = bool(re.search(rf"\b{re.escape(token)}\b\s*(?::|-|\u2013|\u2014)", fact))
            if has_tool_style_case or has_heading_punctuation:
                return True
        return False

    def _compact_text(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", text.lower())

    def _looks_like_topic_introduction(self, phrase: str, fact: str) -> bool:
        escaped = re.escape(phrase)
        match = re.search(escaped, fact)
        if not match:
            return False
        if match.start() <= 12:
            return True
        if re.search(rf"(?:^|[.;]\s*){escaped}\s*(?::|-|\u2013|\u2014)", fact):
            return True
        subject_pattern = (
            rf"\b{escaped}\b(?:\s+\([A-Z0-9]+\))?\s+"
            r"(?:is|are|can|helps|allows|provides|offers|includes|include|"
            r"monitors|detects|updates|discovers|uses|utilizes)\b"
        )
        return bool(re.search(subject_pattern, fact))
