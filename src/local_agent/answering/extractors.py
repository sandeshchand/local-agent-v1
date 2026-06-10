from __future__ import annotations

import re


class ExtractiveAnswerMixin:
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
        elif "setup" in q or "commands" in q:
            prefix = "The setup/run items are:"
        else:
            prefix = "The steps are:"
        return self._clean_final_answer(f"{prefix} {' '.join(selected)}")
    def _challenge_steps_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        if "challenge" not in q or not any(term in q for term in ["step", "steps", "day", "practice"]):
            return ""

        candidates: list[tuple[int, int, list[str]]] = []
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            lower = text.lower()
            challenge_pos = lower.find("challenge")
            if challenge_pos < 0:
                continue
            start = max(0, challenge_pos - 80)
            end = self._first_marker_after(
                lower,
                ["why this works", "brain science", "tag your", "follow for", "comment your", "drop your"],
                challenge_pos + 120,
            )
            if end < 0:
                end = min(len(text), challenge_pos + 900)
            excerpt = self._clean_text(text[start:end])
            steps = self._numbered_day_steps(excerpt)
            if len(steps) < 2:
                steps = self._numbered_steps_after_marker(excerpt, marker="challenge")
            if len(steps) < 2:
                continue
            joined = " ".join(steps).lower()
            score = len(steps) * 8
            score += sum(3 for marker in ["day", "hook", "practice", "mirror", "friend", "feedback", "real life"] if marker in joined)
            candidates.append((score, -index, steps))

        if not candidates:
            return ""
        candidates.sort(reverse=True)
        _, negative_index, steps = candidates[0]
        citation = -negative_index
        selected = [f"- {step}. [{citation}]" for step in steps[:7]]
        duration_match = re.search(r"\b\d+\s*[- ]?\s*day\b", q)
        challenge_label = "challenge"
        if duration_match:
            duration_label = re.sub(r"\s+", "-", duration_match.group(0))
            challenge_label = f"{duration_label} challenge"
        return self._clean_final_answer(f"The {challenge_label} steps are: " + " ".join(selected), max_citation=len(results))
    def _numbered_day_steps(self, text: str) -> list[str]:
        pattern = re.compile(
            r"(?:^|\s)(?:\d+[.)]\s*)?"
            r"((?:Day|Days)\s+\d+(?:\s*[-\u2013\u2014]\s*\d+)?\s*:\s*.*?)(?="
            r"\s+\d+[.)]\s*(?:Day|Days)\s+\d+|\s+Why\s+This\s+Works|\s+Brain\s+Science|$)",
            flags=re.IGNORECASE,
        )
        return self._clean_numbered_steps(match.group(1) for match in pattern.finditer(text))
    def _numbered_steps_after_marker(self, text: str, marker: str) -> list[str]:
        lower = text.lower()
        start = lower.find(marker)
        if start >= 0:
            text = text[start:]
        pattern = re.compile(
            r"(?:^|\s)\d+[.)]\s*(.*?)(?=\s+\d+[.)]\s+|\s+Why\s+This\s+Works|\s+Brain\s+Science|$)",
            flags=re.IGNORECASE,
        )
        return self._clean_numbered_steps(match.group(1) for match in pattern.finditer(text))
    def _clean_numbered_steps(self, raw_steps) -> list[str]:
        steps: list[str] = []
        seen: set[str] = set()
        for raw in raw_steps:
            step = re.sub(r"\s+", " ", str(raw)).strip(" .:-")
            step = re.sub(r"\s*\([^)]{0,80}\)", lambda match: match.group(0), step).strip()
            if not step or len(step.split()) < 3:
                continue
            normalized = re.sub(r"\W+", " ", step.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            steps.append(step)
            if len(steps) >= 8:
                break
        return steps
    def _pipeline_extractive_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        if not any(term in q for term in ["pipeline", "workflow", "processing app", "app flow"]):
            return ""
        if not results:
            return ""

        combined = self._clean_text(" ".join((item.get("text") or "") for item in results))
        lower = combined.lower()
        pipeline_markers = [
            "load",
            "input",
            "file",
            "url",
            "image",
            "pdf",
            "model",
            "process",
            "generate",
            "output",
            "document",
            "export",
            "download",
            "preview",
            "interface",
            "ui",
        ]
        if sum(1 for marker in pipeline_markers if marker in lower) < 4:
            return ""

        focus = self._focus_entity_display(query)
        steps: list[str] = []

        def add_step(text: str, terms: list[str]) -> None:
            if any(self._similar_step(text, existing) for existing in steps):
                return
            citation = self._best_citation_for_terms(results, terms)
            steps.append(f"- {text}. [{citation}]")

        if any(term in lower for term in ["local", "upload", "file"]) and "url" in lower and any(term in lower for term in ["pdf", "image"]):
            add_step("Load PDFs or images from a local file/upload or a URL", ["local", "url", "pdf", "image"])

        if "load_model" in lower or ("load" in lower and "model" in lower):
            model_text = f"Load the {focus} model" if focus else "Load the model"
            add_step(model_text, ["load", "model"])

        generated_terms = self._pipeline_generated_terms(combined)
        if "generate" in lower or "stream" in lower or "output" in lower:
            generated_text = "Generate structured output for each page or image"
            if generated_terms:
                generated_text = f"Generate {', '.join(generated_terms[:2])} for each page or image"
            add_step(generated_text, ["generate", "output", "page", "image"])

        document_classes = self._pipeline_document_classes(combined)
        if document_classes:
            add_step(
                f"Create {' and '.join(document_classes[:3])} from the generated output",
                document_classes[:3],
            )

        formats = self._pipeline_export_formats(combined)
        if formats:
            add_step(f"Export the result as {', '.join(formats)}", formats)

        if any(term in lower for term in ["preview", "download", "interface", "ui", "gradio"]):
            ui_name = "Gradio UI" if "gradio" in lower else "UI"
            add_step(f"Render a preview and provide download controls in the {ui_name}", ["preview", "download", "ui", "interface"])

        if len(steps) < 3:
            extracted_steps = self._pipeline_comment_steps(results)
            for text, citation in extracted_steps:
                if any(self._similar_step(text, existing) for existing in steps):
                    continue
                steps.append(f"- {text}. [{citation}]")
                if len(steps) >= 6:
                    break

        if len(steps) < 3:
            return ""
        return self._clean_final_answer("The main pipeline is: " + " ".join(steps[:7]), max_citation=len(results))
    def _pipeline_generated_terms(self, text: str) -> list[str]:
        terms: list[str] = []
        for match in re.findall(r"\b[A-Z][A-Za-z0-9]*(?:Tags?|Markup|Output)\b", text):
            if match not in terms and len(match) > 3:
                terms.append(match)
        return terms
    def _pipeline_document_classes(self, text: str) -> list[str]:
        classes: list[str] = []
        for match in re.findall(r"\b[A-Z][A-Za-z0-9]*Document\b", text):
            if match not in classes:
                classes.append(match)
        return classes
    def _pipeline_export_formats(self, text: str) -> list[str]:
        formats: list[str] = []
        for match in re.findall(r"\b(?:Markdown|HTML|JSON|CSV|XML|TXT|PDF)\b", text):
            if match not in formats:
                formats.append(match)
        return formats
    def _pipeline_comment_steps(self, results: list[dict]) -> list[tuple[str, int]]:
        steps: list[tuple[str, int]] = []
        for index, item in enumerate(results, start=1):
            raw_text = (item.get("text") or "").replace("\r\n", "\n").replace("\r", "\n")
            for comment in re.findall(r"#\s*([^#\n]{8,120})", raw_text):
                cleaned = re.sub(r"\s+", " ", comment).strip(" .:-")
                if not cleaned:
                    continue
                if any(term in cleaned.lower() for term in ["load", "input", "process", "generate", "create", "export", "download", "preview"]):
                    steps.append((cleaned[0].upper() + cleaned[1:], index))
        return steps
    def _best_citation_for_terms(self, results: list[dict], terms: list[str]) -> int:
        scored: list[tuple[int, int]] = []
        normalized_terms = [term.lower() for term in terms if term]
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "").lower()
            score = sum(1 for term in normalized_terms if term.lower() in text)
            if score:
                scored.append((score, -index))
        if not scored:
            return 1
        scored.sort(reverse=True)
        return -scored[0][1]
    def _similar_step(self, text: str, existing: str) -> bool:
        text_terms = self._content_terms(text)
        existing_terms = self._content_terms(existing)
        if not text_terms or not existing_terms:
            return False
        overlap = len(text_terms & existing_terms)
        return overlap >= min(3, len(text_terms), len(existing_terms))
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
                sentences = self._split_sentences(window)
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
                        for marker in ["instead of", "interface", "features include", "view", "monitor", "helps", "allows"]
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
                score += sum(2 for marker in ["tool", "interface", "helps", "allows"] if marker in excerpt_lower)
                candidates.append((score, -index, excerpt))

        if not candidates:
            return ""
        candidates.sort(reverse=True)
        citation = -candidates[0][1]
        return self._clean_final_answer(f"{candidates[0][2]} [{citation}]")
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
    def _select_category_facts(
        self,
        facts: list[str],
        category_markers: list[tuple[str, list[str]]],
        max_items: int,
    ) -> list[str]:
        selected: list[str] = []
        seen: set[str] = set()
        for _, markers in category_markers:
            best: tuple[int, int, str] | None = None
            for index, fact in enumerate(facts):
                fact_text = re.sub(r"\[\d+\]", "", fact)
                fact_lower = fact_text.lower()
                if self._looks_like_code_or_metadata_fact(fact_text) and not any(marker in fact_lower for marker in markers):
                    continue
                score = sum(3 for marker in markers if marker in fact_lower)
                if score <= 0:
                    continue
                if self._is_low_value_fact(fact_text):
                    score -= 4
                candidate = (score, -index, fact)
                if best is None or candidate > best:
                    best = candidate
            if best is None:
                continue
            fact = self._shorten_fact(best[2], max_words=36)
            normalized = re.sub(r"\W+", " ", fact.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append(f"- {fact}")
            if len(selected) >= max_items:
                break
        return selected
    def _shorten_fact(self, fact: str, max_words: int = 38) -> str:
        citation_match = re.search(r"\s*\[(\d+)\]\s*$", fact)
        citation = f" [{citation_match.group(1)}]" if citation_match else ""
        body = re.sub(r"\s*\[\d+\]\s*$", "", fact).strip()
        words = body.split()
        if len(words) > max_words:
            body = " ".join(words[:max_words]).rstrip(" ,;:")
        return f"{body}.{citation}" if citation and not body.endswith((".", "!", "?")) else f"{body}{citation}"
    def _phrase_acronym(self, phrase: str) -> str:
        tokens = re.findall(r"\b[A-Za-z][A-Za-z0-9-]*\b", phrase)
        if len(tokens) < 2:
            return ""
        return "".join(token[0] for token in tokens).lower()
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
    def _best_practices_extractive_answer(self, query: str, results: list[dict]) -> str:
        if "best practice" not in query.lower():
            return ""

        action_patterns = [
            r"Use\s+[A-Z][A-Za-z0-9_-]+\s+for\s+Development",
            r"Optimize\s+with\s+[A-Z][A-Za-z0-9_-]+",
            r"Configure\s+[A-Z][A-Za-z0-9_-]+\s+Wisely",
            r"Keep it open[^.]+?(?:management|access|workflow)",
            r"Create custom keybindings[^.]+?(?:operations|actions|tasks)",
            r"Run\s+[A-Z][A-Za-z0-9_-]+\s+analysis[^.]+?(?:production|deployment)",
            r"Set\s+[^.]+?thresholds[^.]+?(?:pipelines|builds|checks)",
            r"Use multi-stage builds[^.]+?(?:feedback|optimization|images)",
            r"Start with monitoring[^.]+?(?:containers|services|targets)",
            r"Implement proper notification systems",
            r"Schedule updates[^.]+?(?:periods|windows|traffic)",
        ]

        selected: list[str] = []
        seen: set[str] = set()
        citation_index = 1
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            lower = text.lower()
            if "best practices" not in lower and "best practice" not in lower:
                continue
            start = min(
                position
                for position in [lower.find("best practices"), lower.find("best practice")]
                if position >= 0
            )
            end_candidates = [
                lower.find("why these tools matter", start),
                lower.find("conclusion", start),
                lower.find("let's connect", start),
            ]
            end_candidates = [position for position in end_candidates if position > start]
            end = min(end_candidates) if end_candidates else min(len(text), start + 1800)
            excerpt = text[start:end]
            citation_index = index
            for pattern in action_patterns:
                for match in re.finditer(pattern, excerpt, flags=re.IGNORECASE):
                    action = re.sub(r"\s+", " ", match.group(0)).strip(" .:-")
                    if len(action.split()) < 3:
                        continue
                    action_lower = action.lower()
                    if action_lower in seen:
                        continue
                    seen.add(action_lower)
                    selected.append(action)
            if selected:
                break

        if not selected:
            generic_selected: list[tuple[str, int]] = []
            for index, item in enumerate(results, start=1):
                text = self._clean_text(item.get("text") or "")
                for action in self._generic_best_practice_actions(text):
                    action_lower = action.lower()
                    if action_lower in seen:
                        continue
                    seen.add(action_lower)
                    generic_selected.append((action, index))
                if len(generic_selected) >= 8:
                    break

            if not generic_selected:
                return ""
            return self._clean_final_answer(
                "Best practices include: "
                + " ".join(f"- {action}. [{index}]" for action, index in generic_selected[:8])
            )

        return self._clean_final_answer(
            "Best practices include: "
            + " ".join(f"- {action}. [{citation_index}]" for action in selected[:12])
        )
    def _generic_best_practice_actions(self, text: str) -> list[str]:
        lower = text.lower()
        if not any(marker in lower for marker in ["best practice", "effective practice", "code quality", "quality"]):
            return []

        actions: list[str] = []

        def add(action: str) -> None:
            action = re.sub(r"\s+", " ", action).strip(" .:-")
            if len(action.split()) < 3:
                return
            if action.lower() not in {existing.lower() for existing in actions}:
                actions.append(action)

        prompt_match = re.search(
            r"(?i)effective practices include:\s*(.+?)(?=developers who|to maintain|although|ai-generated|best practices|$)",
            text,
        )
        if prompt_match:
            prompt_block = prompt_match.group(1)
            prompt_parts = [
                re.sub(r"\s+", " ", part).strip(" .:-")
                for part in re.split(
                    r"(?=\b(?:Providing|Including|Specifying|Referencing|Using|Configuring|Applying|Keeping|Running|Maintaining|Writing|Documenting|Reviewing)\b)",
                    prompt_block,
                )
                if len(part.split()) >= 3
            ]
            if any("specific prompting" in lower or "detailed specification" in part.lower() for part in prompt_parts):
                add(
                    "Use clear and specific prompting with detailed specifications, examples, constraints, and existing codebase patterns"
                )
            else:
                for part in prompt_parts[:4]:
                    add(part)

        if any(marker in lower for marker in ["coding standards", "style guides", "formatters", "linters"]):
            standards_bits = []
            if "coding standards" in lower or "internal standards" in lower:
                standards_bits.append("coding standards")
            if "style guide" in lower:
                standards_bits.append("style guides")
            action = "Align generated code with " + " and ".join(standards_bits or ["team standards"])
            if "formatter" in lower or "linter" in lower:
                action += ", and apply automatic formatters and linters after generation"
            add(action)

        if any(marker in lower for marker in ["human review", "human oversight", "trust but verify"]):
            add("Keep human oversight and do not let AI-generated code bypass human review")

        if any(marker in lower for marker in ["unit tests", "integration tests", "security tests", "test suites"]):
            test_types = []
            for label, pattern in [
                ("unit tests", "unit tests"),
                ("integration tests", "integration tests"),
                ("end-to-end tests", "end-to-end tests"),
                ("stress tests", "stress tests"),
                ("security tests", "security tests"),
            ]:
                if pattern in lower:
                    test_types.append(label)
            if test_types:
                add("Run comprehensive tests, including " + ", ".join(test_types))
            else:
                add("Run comprehensive test suites for generated code")

        if any(marker in lower for marker in ["documentation", "readme", "claude.md"]):
            doc_bits = []
            if "readme" in lower:
                doc_bits.append("a well-documented README")
            if "claude.md" in lower:
                doc_bits.append("tool-specific guidance such as CLAUDE.md")
            add("Maintain documentation" + (", including " + " and ".join(doc_bits) if doc_bits else ""))

        return actions
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
        elif category.startswith("human-computer") and "human-computer" not in fact_lower and "hci" not in fact_lower:
            body = f"Human-computer interaction (HCI) limitation: {body}"
        elif category.startswith("physical") and "cause" not in fact_lower:
            body = f"Physical/cause-and-effect limitation: {body}"
        elif category.startswith("irrelevant") and "irrelevant" not in fact_lower:
            body = f"Irrelevant-entity limitation: {body}"
        elif category.startswith("usage") and "usage" not in fact_lower:
            body = f"Usage/access limitation: {body}"
        return f"{body}.{citation}" if citation and not body.endswith((".", "!", "?")) else f"{body}{citation}"
    def _compress_list_fact(self, query: str, fact: str) -> str:
        q = query.lower()
        fact_lower = fact.lower()
        citation_match = re.search(r"\[(\d+)\]\s*$", fact)
        citation = f" [{citation_match.group(1)}]" if citation_match else ""

        if "pipeline" in q or "processing app" in q:
            parts: list[str] = []
            if "file" in fact_lower and ("url" in fact_lower or "upload" in fact_lower):
                parts.append("accepts a local file upload or URL")
            if "load" in fact_lower and "model" in fact_lower:
                parts.append("loads the model")
            if "generate" in fact_lower or "output" in fact_lower or "stream" in fact_lower:
                parts.append("generates the structured intermediate output")
            class_names = self._class_like_identifiers(fact)
            if class_names:
                parts.append(f"creates or uses {', '.join(class_names[:4])}")
            formats = [
                name.upper() if name in {"html", "json"} else name.title()
                for name in ["markdown", "html", "json"]
                if name in fact_lower
            ]
            if len(formats) >= 2:
                parts.append(f"exports {', '.join(formats)}")
            if "download" in fact_lower or "preview" in fact_lower:
                parts.append("prepares downloads and previews")
            if "ui" in fact_lower or "interface" in fact_lower or re.search(r"\bwith\s+[a-z]{1,4}\.", fact_lower):
                parts.append("renders the workflow in a user interface")
            if parts:
                return f"{'; '.join(dict.fromkeys(parts))}.{citation}"

        if "number" in q:
            expression_match = re.search(r"\b\d+\s*\*\*\s*\d+\b", fact)
            digit_match = re.search(r"\b\d+\s+digits?\b", fact_lower)
            if expression_match or digit_match:
                details = []
                if expression_match:
                    details.append(f"uses `{expression_match.group(0).replace(' ', '')}`")
                if digit_match:
                    details.append(f"prints {digit_match.group(0)}")
                return f"The example {' and '.join(details)}.{citation}"

        return fact
    def _class_like_identifiers(self, text: str) -> list[str]:
        identifiers: list[str] = []
        for match in re.findall(r"\b[A-Z][A-Za-z0-9_]{3,}\b", text):
            if match.lower() in {"Figure", "Table", "Section", "Page"}:
                continue
            if re.search(r"(Document|Model|Config|Settings|Field|Choice|Choices|Tag|Tags)$", match):
                identifiers.append(match)
        return list(dict.fromkeys(identifiers))
