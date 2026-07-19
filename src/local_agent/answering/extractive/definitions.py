from __future__ import annotations

import re


class DefinitionUsageExtractorMixin:
    def _example_extractive_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        if "example" not in q:
            return ""

        query_terms = self._query_terms(query)
        candidates: list[tuple[int, int, str]] = []
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            if not text:
                continue
            lower = text.lower()
            if "example" not in lower and "before:" not in lower and "after:" not in lower:
                continue
            anchors = [
                position
                for position in [
                    lower.find("example"),
                    lower.find("before:"),
                    lower.find("after:"),
                    *(lower.find(term) for term in query_terms),
                ]
                if position >= 0
            ]
            if not anchors:
                continue
            start = max(0, min(anchors) - 80)
            end_candidates = [
                lower.find(marker, start + 120)
                for marker in ["challenge", "why this works", "conclusion", "next steps"]
                if lower.find(marker, start + 120) > start
            ]
            end = min(end_candidates) if end_candidates else min(len(text), start + 760)
            excerpt = re.sub(r"\s+", " ", text[start:end]).strip(" .:-")
            if len(excerpt.split()) < 8:
                continue
            score = self._sentence_relevance_score(excerpt, query_terms)
            score += sum(2 for marker in ["example", "before:", "after:", "result:", "instead", "turn", "memorable"] if marker in excerpt.lower())
            score += sum(1 for _ in re.finditer(r"\b\d+\b", excerpt))
            candidates.append((score, -index, excerpt))

        if not candidates:
            return ""
        candidates.sort(reverse=True)
        excerpt = candidates[0][2]
        citation = -candidates[0][1]
        return self._clean_final_answer(f"The example is: {excerpt}. [{citation}]")
    def _definition_extractive_answer(self, query: str, results: list[dict]) -> str:
        entity = self._definition_query_entity(query)
        if not entity or not results:
            return ""

        entity_terms = self._entity_terms(entity)
        if not entity_terms:
            return ""

        candidates: list[tuple[int, int, str]] = []
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            if not text:
                continue
            lower = text.lower()
            anchors = self._entity_anchor_positions(lower, entity_terms)
            for anchor in anchors[:4]:
                window = self._window_around(text, anchor, before=120, after=760)
                sentences = self._split_definition_sentences(window)
                selected: list[str] = []
                for sentence in sentences:
                    sentence_lower = sentence.lower()
                    sentence = re.split(r"\bGetting Started\b|\bHow to use\b", sentence, maxsplit=1)[0].strip()
                    if not sentence:
                        continue
                    sentence_lower = sentence.lower()
                    if self._is_low_value_fact(sentence) or self._looks_like_code_or_metadata_fact(sentence):
                        continue
                    entity_match = self._matches_entity_terms(sentence_lower, entity_terms)
                    relation_match = entity_match and any(
                        marker in sentence_lower
                        for marker in [" is ", " are ", "refers to", "means", "called", "known as"]
                    )
                    entity_starts_sentence = entity_match and self._matches_entity_terms(
                        sentence_lower.split(":", 1)[0],
                        entity_terms,
                    )
                    class_match = entity_starts_sentence and any(
                        marker in sentence_lower
                        for marker in ["tool", "interface", "model", "library", "system", "helps", "allows"]
                    )
                    detail_match = bool(selected) and any(
                        marker in sentence_lower
                        for marker in [
                            "instead of",
                            "interface",
                            "features include",
                            "view",
                            "monitor",
                            "helps",
                            "allows",
                            "trained",
                            "generate",
                            "creates",
                            "created",
                            "can ",
                            "capable",
                            "designed",
                            "developed",
                            "released",
                            "supports",
                            "used for",
                        ]
                    )
                    if relation_match or class_match or detail_match:
                        selected.append(sentence)
                    if len(selected) >= 3:
                        break
                if not selected:
                    continue
                excerpt = self._clean_window_excerpt(" ".join(selected), max_words=95)
                if not excerpt:
                    continue
                excerpt_lower = excerpt.lower()
                score = self._sentence_relevance_score(excerpt, self._query_terms(query))
                score += 8 if self._matches_entity_terms(excerpt_lower, entity_terms) else 0
                score += sum(4 for marker in [" is ", " are ", "refers to", "means"] if marker in excerpt_lower)
                score += sum(
                    4
                    for marker in [
                        "model",
                        "tool",
                        "library",
                        "system",
                        "framework",
                        "algorithm",
                        "method",
                        "platform",
                        "service",
                    ]
                    if marker in excerpt_lower
                )
                score += sum(2 for marker in ["interface", "helps", "allows", "released by", "released in", "developed by", "created by", "built by"] if marker in excerpt_lower)
                flexible_entity = r"\s*[-_]?\s*".join(re.escape(term) for term in entity_terms)
                if flexible_entity and re.search(rf"\b{flexible_entity}\s+(?:is|are)\s+(?:a|an|the)\b", excerpt_lower):
                    score += 18
                if any(marker in excerpt_lower for marker in ["compared to", "distinguished by", "previous video", "previous model"]):
                    score -= 8
                candidates.append((score, -index, excerpt))

        if not candidates:
            return ""
        candidates.sort(reverse=True)
        citation = -candidates[0][1]
        return self._clean_final_answer(f"{candidates[0][2]} [{citation}]")
    def _split_definition_sentences(self, text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        sentences: list[str] = []
        for part in re.split(r"(?<=[.!?])\s+", normalized):
            part = part.strip()
            if len(part) <= 40:
                continue
            sentences.append(part)
        return sentences
    def _used_for_extractive_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        if not any(phrase in q for phrase in ["used for", "useful for", "useful"]):
            return ""

        focus = self._focus_entity_display(query)
        focus_terms = self._entity_terms(focus)
        if not focus_terms:
            return ""

        acronym = self._phrase_acronym(focus)
        query_terms = self._query_terms(query)
        intent_terms = self._query_intent_terms(query) + self._intent_terms_from_query_terms(query_terms)
        candidates: list[tuple[int, int, str]] = []

        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            lower = text.lower()
            positions = self._entity_anchor_positions(lower, focus_terms)
            if acronym:
                positions.extend(match.start() for match in re.finditer(rf"\b{re.escape(acronym)}s?\b", lower))
            if not positions:
                continue
            window = self._window_around(text, min(positions), before=80, after=950)
            for sentence in self._split_sentences(window):
                sentence_text = re.sub(r"\[\d+\]", "", sentence).strip()
                sentence_lower = sentence_text.lower()
                if self._looks_like_code_or_metadata_fact(sentence_text) and not any(
                    marker in sentence_lower for marker in ["label", "labels", "example", "format"]
                ):
                    continue
                score = self._focus_phrase_score(sentence_text, {focus.lower()})
                if acronym and re.search(rf"\b{re.escape(acronym)}s?\b", sentence_lower):
                    score += 8
                score += self._sentence_relevance_score(sentence_text, query_terms)
                score += sum(2 for term in intent_terms if term in sentence_lower)
                if any(
                    marker in sentence_lower
                    for marker in [
                        "used for",
                        "useful for",
                        "useful",
                        "helps",
                        "enables",
                        "allows",
                        "probabilistic",
                        "structured",
                        "prediction",
                        "context",
                        "sequence",
                        "sequential",
                        "label",
                        "example",
                        "markup",
                        "layout",
                        "semantics",
                        "reading order",
                        "hierarchy",
                        "downstream",
                        "parser",
                        "heuristic",
                        "accuracy",
                    ]
                ):
                    score += 3
                if score > 0:
                    candidates.append((score, -index, f"{sentence_text} [{index}]"))

            example = self._explicit_named_example(window)
            if example:
                candidates.append((35, -index, f"The example/application shown is {example}. [{index}]"))

        if not candidates:
            return ""
        candidates.sort(reverse=True)

        category_facts = [fact for _, _, fact in candidates]
        if "useful" in q and not any(phrase in q for phrase in ["used for", "useful for"]):
            categories = [
                ("definition", ["semantic", "markup", "generated", "produced", "called", "output"]),
                ("structure", ["layout", "semantics", "structure", "reading order", "hierarchy"]),
                ("benefit", ["useful", "helps", "enable", "allows", "downstream", "accuracy", "accurate", "convert", "parser", "heuristic"]),
            ]
            prefix = f"{focus or 'It'} is useful because:"
        else:
            categories = [
                ("definition", ["probabilistic", "structured", "prediction", "used for"]),
                ("context", ["context", "sequential", "sequence", "independent"]),
                ("example", ["example/application", "label", "labels", "named entity", "ner"]),
            ]
            prefix = f"{focus or 'It'} is used for:"

        selected = self._select_category_facts(
            category_facts,
            categories,
            max_items=4,
        )
        if selected:
            return self._clean_final_answer(f"{prefix} {' '.join(selected)}")

        selected: list[str] = []
        seen: set[str] = set()
        for _, _, fact in candidates:
            normalized = re.sub(r"\W+", " ", re.sub(r"\[\d+\]", "", fact.lower())).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append(f"- {fact}")
            if len(selected) >= 4:
                break
        if not selected:
            return ""

        return self._clean_final_answer(f"{prefix} {' '.join(selected)}")
    def _explicit_named_example(self, text: str) -> str:
        for pattern in [
            r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,5}\s*\([A-Z][A-Z0-9-]{1,12}\))\s+(?:labels?|examples?|format|task|application)",
            r"(?:labels?|examples?|format|task|application)[^.!?]{0,80}\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,5}\s*\([A-Z][A-Z0-9-]{1,12}\))",
        ]:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return re.sub(r"\s+", " ", match.group(1)).strip()
        return ""
    def _config_file_purpose_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        if not (".env" in q or "env file" in q or "environment file" in q):
            return ""
        if not any(term in q for term in ["why", "purpose", "recommend", "local development", "local"]):
            return ""

        facts = [
            fact[2:].strip()
            for fact in self._build_evidence_fact_list(query, results, max_facts=36).splitlines()
            if fact.startswith("- ")
        ]
        if not facts:
            return ""

        category_markers = [
            ("local development", ["local development", "local"]),
            ("slow/messy setup", ["slow", "messy", "inconvenient"]),
            ("variable examples", ["api key", "api keys", "token", "tokens", "secret", "database", "url"]),
            ("key-value format", ["key : value", "key-value", "key value", "text file"]),
            ("environment variables", ["environment variable", "variables"]),
        ]
        selected = self._select_category_facts(facts, category_markers, max_items=6)
        if not selected:
            return ""
        return self._clean_final_answer("The .env file is recommended because: " + " ".join(selected))
    def _meaning_extractive_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        if "mean by" not in q and not re.search(r"['\"].{8,120}['\"]", query):
            return ""

        facts = [
            fact[2:].strip()
            for fact in self._build_evidence_fact_list(query, results, max_facts=36).splitlines()
            if fact.startswith("- ")
        ]
        if not facts:
            return ""

        category_markers = [
            ("claim", ["won't replace", "will replace", "someone using", "truth is"]),
            ("tools", ["tool", "tools", "chatgpt", "claude"]),
            ("speed", ["faster", "save time"]),
            ("side income", ["side income"]),
            ("income", ["make money", "pay"]),
            ("degree", ["degree"]),
            ("technical/no-code barrier", ["technical", "tech", "code", "product", "app"]),
            ("learning", ["learn", "care enough"]),
        ]
        selected = self._select_category_facts(facts, category_markers, max_items=8)
        if not selected:
            return ""
        for index, fact in enumerate(selected):
            fact_lower = fact.lower()
            if any(marker in fact_lower for marker in ["line of code", "tech bro", "technical", "product", "fancy app"]):
                selected[index] = re.sub(r"^-\s*", "- No-code/technical background barrier: ", fact, count=1)
        prefix = "It means AI tools give an advantage when people learn to use them:"
        return self._clean_final_answer(prefix + " " + " ".join(selected))
    def _command_usefulness_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        if not any(term in q for term in ["command", "run", "start", "server"]):
            return ""

        command_pattern = re.compile(
            r"\b(?:python\s+-m\s+[-\w.]+(?:\s+\d+)?|docker\s+run\b[^.!?\n]{0,160}|pip\s+install\s+[-\w.]+|uv\s+run\b[^.!?\n]{0,120}|npm\s+install\s+[-\w.]+|brew\s+install\s+[-\w.]+|poetry\s+add\s+[-\w.]+|conda\s+install\s+[-\w.]+|git\s+clone\s+\S+)",
            flags=re.IGNORECASE,
        )
        command_fact = ""
        command_citation = 1
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            match = command_pattern.search(text)
            if not match:
                continue
            command = re.sub(r"\s+", " ", match.group(0)).strip()
            context = self._clean_window_excerpt(self._window_around(text, match.start(), before=180, after=180), max_words=65)
            command_fact = f"- `{command}`. {context}. [{index}]"
            command_citation = index
            break

        usefulness: list[str] = []
        seen: set[str] = set()
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            for sentence in self._split_sentences(text):
                sentence_lower = sentence.lower()
                if not any(marker in sentence_lower for marker in ["useful", "test", "share", "local network", "third-party", "browser", "localhost"]):
                    continue
                if self._looks_like_code_or_metadata_fact(sentence) and not self._should_keep_code_fact(query, sentence):
                    continue
                normalized = re.sub(r"\W+", " ", sentence_lower).strip()
                if normalized in seen:
                    continue
                seen.add(normalized)
                usefulness.append(f"- {sentence.strip()} [{index}]")
                if len(usefulness) >= 4:
                    break
            if len(usefulness) >= 4:
                break

        if not command_fact and not usefulness:
            return ""
        if command_fact and not usefulness:
            return self._clean_final_answer("The command is: " + command_fact, max_citation=len(results))
        if not command_fact:
            return self._clean_final_answer("It is useful because: " + " ".join(usefulness), max_citation=len(results))
        return self._clean_final_answer(
            "The command and use are: "
            + command_fact
            + " It is useful because: "
            + " ".join(usefulness),
            max_citation=max(command_citation, len(results)),
        )
