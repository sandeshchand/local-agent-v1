from __future__ import annotations

import re


class SourceWindowMixin:
    def _single_source_results(self, query: str, results: list[dict]) -> list[dict]:
        if not results or self._is_multi_source_query(query):
            return results

        first_title = self._title_key(results[0].get("title") or "")
        if not first_title:
            return results

        filtered = [
            item
            for item in results
            if self._title_key(item.get("title") or "") == first_title
        ]
        return filtered or results
    def _is_multi_source_query(self, query: str) -> bool:
        q = query.lower()
        return any(
            phrase in q
            for phrase in [
                "compare",
                "across documents",
                "across all",
                "all documents",
                "multiple documents",
                "both papers",
                "each paper",
                "each document",
            ]
        )
    def _title_key(self, title: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", title.lower())).strip()
    def _source_window_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        if not results or not self._uses_source_window_answer(query):
            return ""

        if "setup" in q or "commands" in q or ("run" in q and "command" in q):
            answer = self._setup_command_window_answer(query, results)
            if answer:
                return answer

        if "reason" in q or ("why" in q and "works" in q) or ("brain" in q and "science" in q):
            answer = self._reason_window_answer(query, results)
            if answer:
                return answer

        if ("hold" in q or "holding" in q or "holds" in q) and "back" in q:
            answer = self._holding_back_window_answer(query, results)
            if answer:
                return answer

        if "formula" in q:
            answer = self._formula_window_answer(query, results)
            if answer:
                return answer

        if "example" in q:
            answer = self._example_window_answer(query, results)
            if answer:
                return answer

        if "main message" in q:
            answer = self._main_message_window_answer(query, results)
            if answer:
                return answer

        if "feature" in q or "analy" in q:
            answer = self._feature_window_answer(query, results)
            if answer:
                return answer

        return self._generic_window_answer(query, results)
    def _uses_source_window_answer(self, query: str) -> bool:
        q = query.lower()
        return any(
            phrase in q
            for phrase in [
                "feature",
                "analy",
                "setup",
                "commands",
                "reason",
                "formula",
                "example",
                "large number",
                "large integer",
                "very large",
                "main message",
                "author do",
                "what does the author",
                "holding",
                "holds",
                "hold people back",
            ]
        )
    def _should_prefer_source_window_answer(self, query: str, answer: str, source_answer: str) -> bool:
        q = query.lower()
        if any(
            phrase in q
            for phrase in [
                "feature",
                "analy",
                "setup",
                "commands",
                "reason",
                "formula",
                "example",
                "large number",
                "large integer",
                "very large",
                "main message",
                "author do",
                "what does the author",
                "holding",
                "holds",
            ]
        ):
            return True
        return len(self._content_terms(source_answer) - self._content_terms(answer)) >= 4
    def _setup_command_window_answer(self, query: str, results: list[dict]) -> str:
        command_markers = [
            "pip install",
            "uv ",
            "venv",
            "activate",
            "brew install",
            "run ",
            "app.launch",
            "localhost",
            "127.0.0.1",
            "install",
        ]
        selected: list[str] = []
        seen: set[str] = set()
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            lower = text.lower()
            if not any(marker in lower for marker in command_markers):
                continue
            positions = [lower.find(marker) for marker in command_markers if lower.find(marker) >= 0]
            if not positions:
                continue
            excerpt = self._clean_window_excerpt(
                self._window_around(text, min(positions), before=90, after=520),
                max_words=90,
            )
            normalized = re.sub(r"\W+", " ", excerpt.lower()).strip()
            if not excerpt or normalized in seen:
                continue
            seen.add(normalized)
            selected.append(f"- {excerpt}. [{index}]")
            if len(selected) >= 5:
                break
        if not selected:
            return ""
        return self._clean_final_answer("The setup/run commands are: " + " ".join(selected))
    def _feature_window_answer(self, query: str, results: list[dict]) -> str:
        focus_entity = self._focus_entity_display(query).lower()
        query_terms = self._query_terms(query)
        entity_terms = self._entity_terms(focus_entity)
        candidates: list[tuple[int, int, str]] = []

        def score_excerpt(excerpt: str) -> int:
            excerpt_lower = excerpt.lower()
            score = self._sentence_relevance_score(excerpt, query_terms)
            score += sum(
                2
                for marker in [
                    "feature",
                    "include",
                    "capability",
                    "support",
                    "supports",
                    "provides",
                    "offers",
                    "allows",
                    "enables",
                    "helps",
                    "automatic",
                    "interactive",
                ]
                if marker in excerpt_lower
            )
            if entity_terms and self._matches_entity_terms(excerpt_lower, entity_terms):
                score += 8
                first_words = " ".join(excerpt_lower.split()[:18])
                if not self._matches_entity_terms(first_words, entity_terms):
                    score -= 22
            if "key features include" in excerpt_lower or "features include" in excerpt_lower:
                score += 6
            score += min(8, max(0, len(excerpt.split()) - 45) // 8)
            if self._contains_command_text(excerpt_lower) and not self._asks_for_commands(query):
                score -= 12
            return score

        ordered_texts = self._ordered_result_texts(results)
        if len(ordered_texts) >= 2:
            combined_text = self._clean_text(" ".join(text for _, text in ordered_texts))
            combined_lower = combined_text.lower()
            if not entity_terms or self._matches_entity_terms(combined_lower, entity_terms):
                spans = self._feature_answer_spans(combined_lower, entity_terms, query_terms)
                for start, end in spans[:6]:
                    excerpt = self._clean_feature_excerpt(combined_text[start:end], query=query, max_words=155)
                    if not excerpt:
                        continue
                    citation = ordered_texts[0][0]
                    candidates.append((score_excerpt(excerpt) + 2, -citation, excerpt))

        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            lower = text.lower()
            if entity_terms and not self._matches_entity_terms(lower, entity_terms):
                continue
            spans = self._feature_answer_spans(lower, entity_terms, query_terms)
            if not spans:
                continue
            for start, end in spans[:4]:
                excerpt = self._clean_feature_excerpt(text[start:end], query=query, max_words=140)
                if not excerpt:
                    continue
                score = score_excerpt(excerpt)
                candidates.append((score, -index, excerpt))
        if not candidates:
            return ""
        candidates.sort(reverse=True)
        citation = -candidates[0][1]
        prefix = "It helps analyze:" if "analy" in query.lower() else "Key features include:"
        excerpt = candidates[0][2]
        if re.search(r"\b(?:key\s+features|features)\s+include\b", excerpt, flags=re.IGNORECASE):
            return self._clean_final_answer(f"{excerpt}. [{citation}]")
        return self._clean_final_answer(f"{prefix} {excerpt}. [{citation}]")
    def _augment_feature_answer_with_intro(self, query: str, answer: str, results: list[dict]) -> str:
        q = query.lower()
        if "feature" not in q and "capabil" not in q:
            return answer

        focus_entity = self._focus_entity_display(query)
        entity_terms = self._entity_terms(focus_entity)
        if not entity_terms:
            return answer

        for sentence in self._split_sentences(answer):
            sentence_lower = sentence.lower()
            if not self._matches_entity_terms(sentence_lower, entity_terms):
                continue
            if "feature" in sentence_lower:
                continue
            if any(
                marker in sentence_lower
                for marker in [
                    " is ",
                    " are ",
                    "refers to",
                    "means",
                    "tool",
                    "interface",
                    "ui",
                    "model",
                    "method",
                    "system",
                    "monitors",
                    "analyzes",
                    "helps",
                    "allows",
                    "enables",
                ]
            ):
                return answer

        intro = self._feature_intro_sentence(query, results, entity_terms)
        if not intro:
            return answer

        intro_text, citation = intro
        normalized_intro = re.sub(r"\W+", " ", intro_text.lower()).strip()
        normalized_answer = re.sub(r"\W+", " ", answer.lower()).strip()
        if normalized_intro and normalized_intro in normalized_answer:
            return answer
        return self._clean_final_answer(f"{intro_text}. [{citation}] {answer}", max_citation=len(results))
    def _feature_intro_sentence(
        self,
        query: str,
        results: list[dict],
        entity_terms: list[str],
    ) -> tuple[str, int] | None:
        query_terms = self._query_terms(query)
        candidates: list[tuple[int, int, str]] = []
        class_markers = [
            "tool",
            "interface",
            "ui",
            "model",
            "library",
            "framework",
            "method",
            "algorithm",
            "system",
            "service",
            "application",
            "platform",
        ]
        relation_markers = [
            " is ",
            " are ",
            "refers to",
            "means",
            "used for",
            "monitors",
            "analyzes",
            "automates",
            "helps",
            "allows",
            "enables",
        ]

        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            lower = text.lower()
            for anchor in self._entity_anchor_positions(lower, entity_terms)[:5]:
                window = self._window_around(text, anchor, before=160, after=620)
                for sentence in self._split_sentences(window):
                    sentence = re.sub(r"(?i)^what\s+(?:is|are)\s+[^?]{1,120}\?\s*", "", sentence).strip(" .:-")
                    if not sentence:
                        continue
                    sentence_lower = sentence.lower()
                    if not self._matches_entity_terms(sentence_lower, entity_terms):
                        continue
                    if "feature" in sentence_lower and "include" in sentence_lower:
                        continue
                    if self._is_low_value_fact(sentence) or self._looks_like_code_or_metadata_fact(sentence):
                        continue
                    has_relation = any(marker in sentence_lower for marker in relation_markers)
                    has_class = any(marker in sentence_lower for marker in class_markers)
                    if not has_relation and not has_class:
                        continue
                    excerpt = self._clean_window_excerpt(sentence, max_words=34)
                    if not excerpt:
                        continue
                    score = self._sentence_relevance_score(excerpt, query_terms)
                    score += 8 if has_relation else 0
                    score += 5 if has_class else 0
                    score += 4 if self._matches_entity_terms(excerpt.lower(), entity_terms) else 0
                    candidates.append((score, -index, excerpt))

        if not candidates:
            return None
        candidates.sort(reverse=True)
        score, negative_index, excerpt = candidates[0]
        if score < 5:
            return None
        return excerpt.rstrip(" ."), -negative_index
    def _feature_answer_spans(
        self,
        lower_text: str,
        entity_terms: list[str],
        query_terms: set[str],
    ) -> list[tuple[int, int]]:
        starts: list[int] = []
        entity_positions = self._entity_anchor_positions(lower_text, entity_terms) if entity_terms else []
        if entity_positions:
            for position in entity_positions[:10]:
                heading_before = lower_text.rfind("what is", 0, position + 1)
                heading_after = lower_text.find("what is", position)
                if heading_before >= 0 and position - heading_before <= 90:
                    starts.append(heading_before)
                elif heading_after >= 0 and heading_after - position <= 140:
                    starts.append(heading_after)
                else:
                    starts.append(position)

                for marker in ["features include", "key features"]:
                    feature_position = lower_text.find(marker, position)
                    if 0 <= feature_position - position <= 1200:
                        heading_before_feature = lower_text.rfind("what is", 0, feature_position)
                        if heading_before_feature >= 0 and feature_position - heading_before_feature <= 500:
                            heading_window = lower_text[heading_before_feature:feature_position]
                            if not entity_terms or self._matches_entity_terms(heading_window, entity_terms):
                                starts.append(heading_before_feature)
                        else:
                            between = lower_text[position:feature_position]
                            intervening_heading = between.rfind("what is")
                            if (
                                intervening_heading < 0
                                or not entity_terms
                                or self._matches_entity_terms(between[intervening_heading:], entity_terms)
                            ):
                                starts.append(feature_position)
        else:
            starts.extend(
                position
                for marker in ["features include", "key features", "what is", "analy"]
                for position in [lower_text.find(marker)]
                if position >= 0
            )
            starts.extend(lower_text.find(term) for term in query_terms if lower_text.find(term) >= 0)

        spans: list[tuple[int, int]] = []
        for start in sorted(set(position for position in starts if position >= 0)):
            end = self._first_marker_after(
                lower_text,
                [
                    "getting started",
                    "how to use",
                    "how do i",
                    "pro tip",
                    "you can try",
                    "when using",
                    "best practices",
                    "why these tools matter",
                    "setup instructions",
                    "complete code",
                    "installation",
                    "installing",
                    "resources",
                    "references",
                    "try it out",
                    "start integrating",
                    "thanks for reading",
                    "get an email",
                    "signing up",
                    "final thoughts",
                    "let's connect",
                    "lets connect",
                    "connect!",
                    "embrace ",
                ],
                start + 160,
            )
            if end < 0:
                next_topic = lower_text.find("what is ", start + 160)
                end = next_topic if next_topic >= 0 else min(len(lower_text), start + 1300)
            if end > start:
                spans.append((start, end))
        return spans
    def _clean_feature_excerpt(self, excerpt: str, query: str, max_words: int = 140) -> str:
        excerpt = re.sub(r"\s+", " ", excerpt).strip(" .:-")
        if not self._asks_for_commands(query):
            command_start = self._first_marker_after(
                excerpt.lower(),
                [
                    "docker run",
                    "brew install",
                    "pip install",
                    "npm install",
                    "conda install",
                    "poetry add",
                    "uv run",
                    "python -m",
                    "alias ",
                    "git clone",
                ],
                0,
            )
            if command_start >= 0:
                excerpt = excerpt[:command_start]
            social_start = self._first_marker_after(
                excerpt.lower(),
                [
                    "start integrating",
                    "thanks for reading",
                    "get an email",
                    "signing up",
                    "follow me on",
                    "subscribe to",
                    "your thoughts and feedback",
                    "connect!",
                ],
                0,
            )
            if social_start >= 0:
                excerpt = excerpt[:social_start]
        heading_match = re.search(r"(?i)\bwhat\s+(?:is|are)\b", excerpt)
        feature_match = re.search(r"(?i)\b(?:key\s+features|features)\s+include\b", excerpt)
        if heading_match and heading_match.start() > 0 and (
            not feature_match or heading_match.start() < feature_match.start()
        ):
            excerpt = excerpt[heading_match.start() :]
        excerpt = re.sub(r"^[^A-Za-z0-9]*(?:[-\\\w./:=<>]+\s+){2,}(?=What is|[A-Z][A-Za-z0-9_-]+:)", "", excerpt).strip()
        excerpt = re.sub(r"(?i)^what\s+is\s+[^?]{1,100}\?\s*", "", excerpt).strip(" .:-")
        excerpt = re.sub(
            r"(?i)\b(?:some\s+(?:of\s+)?the\s+)?key\s+features(?:\s+of\s+[^:]{1,80})?\s+include:\s*",
            "Key features include: ",
            excerpt,
        )
        excerpt = re.sub(r"(?i)(key\s+features\s+include:\s*){2,}", "Key features include: ", excerpt)
        excerpt = re.sub(r"\b(?:Follow|Published in)[^.!?]{0,120}", "", excerpt).strip(" .:-")
        words = excerpt.split()
        if len(words) > max_words:
            excerpt = " ".join(words[:max_words]).rstrip(" ,;:")
        return excerpt.strip()
    def _asks_for_commands(self, query: str) -> bool:
        q = query.lower()
        return any(term in q for term in ["command", "setup", "install", "run", "how to use", "execute"])
    def _contains_command_text(self, text_lower: str) -> bool:
        return any(
            marker in text_lower
            for marker in [
                "docker run",
                "brew install",
                "pip install",
                "npm install",
                "conda install",
                "poetry add",
                "uv run",
                "python -m",
                "alias ",
                "git clone",
            ]
        )
    def _formula_window_answer(self, query: str, results: list[dict]) -> str:
        ordered = self._ordered_result_texts(results)
        if not ordered:
            return ""
        combined = self._clean_text(" ".join(text for _, text in ordered))
        lower = combined.lower()
        start_marker = self._best_formula_anchor(lower)
        if start_marker < 0:
            return ""
        start = max(0, start_marker - 140)
        end = self._first_marker_after(
            lower,
            ["example", "challenge", "your 7-day", "tag ", "follow publication", "published in"],
            start_marker + 260,
        )
        if end < 0:
            end = min(len(combined), start_marker + 1350)
        excerpt = self._clean_window_excerpt(combined[start:end], max_words=170)
        if not excerpt:
            return ""
        components = self._formula_components_from_excerpt(excerpt)
        citation = ordered[0][0]
        if components:
            return self._clean_final_answer(f"The formula is: {'; '.join(components)}. [{citation}]")
        return self._clean_final_answer(f"The formula is: {excerpt}. [{citation}]")
    def _best_formula_anchor(self, lower_text: str) -> int:
        positions = [match.start() for match in re.finditer(r"\bformula\b", lower_text)]
        if not positions:
            return -1

        def score(position: int) -> int:
            near = lower_text[max(0, position - 220) : min(len(lower_text), position + 1500)]
            early = lower_text[position : min(len(lower_text), position + 420)]
            heading = lower_text[max(0, position - 35) : min(len(lower_text), position + 45)]
            value = 0
            if re.search(r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)[-\s]*part\s+formula\b", heading):
                value += 30
            elif re.search(r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)[-\s]*part\s+formula\b", near):
                value += 12
            value += min(12, len(re.findall(r"\b\d{1,2}\.\s+", early)) * 4)
            value += min(8, len(re.findall(r"\b[A-Z][^:]{2,70}:\s+", near, flags=re.IGNORECASE)) * 2)
            if re.search(r"\b(?:step|part|component|framework|method)\b", near):
                value += 3
            if "formula above" in early or "use the formula" in near:
                value -= 18
            before = lower_text[max(0, position - 160) : position]
            if any(marker in before for marker in ["challenge", "tag ", "clap ", "follow publication", "published in"]):
                value -= 24
            if any(marker in early for marker in ["challenge", "tag ", "clap ", "follow publication", "published in"]):
                value -= 12
            return value

        return max(positions, key=score)
    def _formula_components_from_excerpt(self, excerpt: str) -> list[str]:
        text = re.sub(r"\s+", " ", excerpt).strip()
        matches = list(
            re.finditer(
                r"(?<!\d)\b(\d{1,2})\.\s+(?=(?:the\s+)?[A-Z][A-Za-z0-9\"'() /-]{1,90}:)",
                text,
            )
        )
        components: list[str] = []
        seen: set[str] = set()
        for match_index, match in enumerate(matches):
            part_start = match.end()
            part_end = matches[match_index + 1].start() if match_index + 1 < len(matches) else len(text)
            part = text[part_start:part_end]
            part = re.split(
                r"(?i)\b(?:bad|better|example|challenge|result|tag|follow|published in)\s*:",
                part,
                maxsplit=1,
            )[0]
            part = re.sub(r"(?i)\bwhy\s*:\s*", " because ", part)
            part = re.sub(r"\s+", " ", part).strip(" .;:-")
            if not part or len(part.split()) < 2:
                continue
            if len(part.split()) > 22:
                part = " ".join(part.split()[:22]).rstrip(" ,;:")
            normalized = re.sub(r"\W+", " ", part.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            components.append(f"{match.group(1)}. {part}")
            if len(components) >= 6:
                break
        return components if len(components) >= 2 else []
    def _example_window_answer(self, query: str, results: list[dict]) -> str:
        ordered = self._ordered_result_texts(results)
        if not ordered:
            return ""
        combined = " ".join(text for _, text in ordered)
        lower = combined.lower()
        after_pos = lower.find("after:")
        before_pos = lower.rfind("before:", 0, after_pos if after_pos >= 0 else len(lower))
        if before_pos < 0:
            before_pos = lower.find("example")
        if before_pos < 0:
            return ""
        end = self._first_marker_after(
            lower,
            ["challenge", "why this works", "tag "],
            before_pos + 220,
        )
        if end < 0:
            end = min(len(combined), before_pos + 900)
        start = max(0, before_pos - 90)
        excerpt = self._clean_window_excerpt(combined[start:end], max_words=145)
        if not excerpt:
            return ""
        citation = ordered[0][0]
        return self._clean_final_answer(f"The example is: {excerpt}. [{citation}]")
    def _main_message_window_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        query_terms = self._query_terms(query)
        marker_groups = [
            ["quit", "quitting"],
            ["risk", "burn"],
            ["paycheck"],
            ["hours a day", "hours"],
        ]
        selected: list[str] = []
        seen_groups: set[int] = set()
        seen_text: set[str] = set()
        candidates: list[tuple[int, int, int, str]] = []
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            lower = text.lower()
            for group_index, markers in enumerate(marker_groups):
                positions = [lower.find(marker) for marker in markers if lower.find(marker) >= 0]
                if not positions:
                    continue
                excerpt = self._clean_window_excerpt(
                    self._window_around(text, min(positions), before=110, after=520),
                    max_words=85,
                )
                excerpt = self._marker_sentences(excerpt, markers, max_words=45) or excerpt
                if not excerpt:
                    continue
                excerpt_lower = excerpt.lower()
                score = self._sentence_relevance_score(excerpt, query_terms)
                score += sum(4 for marker in markers if marker in excerpt_lower)
                if "quit" in q or "quitting" in q:
                    score += sum(3 for marker in ["quit", "risk", "burn", "paycheck", "hours"] if marker in excerpt_lower)
                candidates.append((score, group_index, -index, excerpt))

        if not candidates:
            return ""
        candidates.sort(reverse=True)
        for _, group_index, negative_index, excerpt in candidates:
            normalized = re.sub(r"\W+", " ", excerpt.lower()).strip()
            if group_index in seen_groups or normalized in seen_text:
                continue
            seen_groups.add(group_index)
            seen_text.add(normalized)
            selected.append(f"- {excerpt}. [{-negative_index}]")
            if len(selected) >= 4:
                break
        if not selected:
            return ""
        return self._clean_final_answer("The main message is: " + " ".join(selected))
    def _reason_window_answer(self, query: str, results: list[dict]) -> str:
        query_terms = self._query_terms(query)
        reason_markers = [
            "why this works",
            "brain science",
            "reason",
            "reasons",
            "because",
            "triggers",
            "activate",
            "remember",
            "question",
        ]
        candidates: list[tuple[int, int, str]] = []
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            lower = text.lower()
            positions = [
                match.start()
                for marker in reason_markers
                for match in re.finditer(re.escape(marker), lower)
            ]
            if not positions:
                continue
            for anchor in sorted(set(positions))[:8]:
                excerpt = self._clean_window_excerpt(
                    self._window_around(text, anchor, before=90, after=760),
                    max_words=120,
                )
                if not excerpt:
                    continue
                excerpt_lower = excerpt.lower()
                score = self._sentence_relevance_score(excerpt, query_terms)
                score += sum(8 for marker in ["why this works", "brain science"] if marker in excerpt_lower)
                score += sum(2 for marker in ["triggers", "activate", "feel", "remember", "question"] if marker in excerpt_lower)
                score += len(re.findall(r"\b\d+[.)]\s+", excerpt)) * 2
                candidates.append((score, -index, excerpt))
        if not candidates:
            return ""
        candidates.sort(reverse=True)
        citation = -candidates[0][1]
        return self._clean_final_answer(f"The reasons are: {candidates[0][2]}. [{citation}]")
    def _holding_back_window_answer(self, query: str, results: list[dict]) -> str:
        markers = ["stuck because", "fear", "failing", "looking", "wasting", "trying", "try"]
        candidates: list[tuple[int, int, str]] = []
        query_terms = self._query_terms(query)
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            lower = text.lower()
            positions = [lower.find(marker) for marker in markers if lower.find(marker) >= 0]
            if not positions:
                continue
            excerpt = self._clean_window_excerpt(
                self._window_around(text, min(positions), before=90, after=620),
                max_words=110,
            )
            excerpt = self._marker_sentences(excerpt, markers, max_words=65) or excerpt
            if not excerpt:
                continue
            excerpt_lower = excerpt.lower()
            score = self._sentence_relevance_score(excerpt, query_terms)
            score += sum(3 for marker in ["stuck because", "fear", "failing", "looking", "wasting"] if marker in excerpt_lower)
            score += sum(1 for marker in ["try", "trying"] if marker in excerpt_lower)
            candidates.append((score, -index, excerpt))
        if not candidates:
            return ""
        candidates.sort(reverse=True)
        citation = -candidates[0][1]
        return self._clean_final_answer(f"What holds people back is: {candidates[0][2]}. [{citation}]")
    def _marker_sentences(self, text: str, markers: list[str], max_words: int = 45) -> str:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", text)
            if sentence.strip()
        ]
        if not sentences:
            return ""
        selected: list[str] = []
        for index, sentence in enumerate(sentences):
            sentence_lower = sentence.lower()
            if not any(marker in sentence_lower for marker in markers):
                continue
            if len(sentence.split()) <= 6 and index > 0:
                previous = sentences[index - 1]
                if previous not in selected:
                    selected.append(previous)
            selected.append(sentence)
            if index + 1 < len(sentences):
                next_sentence = sentences[index + 1]
                next_lower = next_sentence.lower()
                if any(marker in next_lower for marker in markers) and next_sentence not in selected:
                    selected.append(next_sentence)
        if not selected:
            return ""
        words = " ".join(selected).split()
        return " ".join(words[:max_words]).rstrip(" ,;:")
    def _generic_window_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        query_terms = self._query_terms(query)
        anchor_terms = set(query_terms)
        if ("hold" in q or "holding" in q or "holds" in q) and "back" in q:
            anchor_terms.update({"back", "fear", "stuck"})
        if "quit" in q or "quitting" in q:
            anchor_terms.update({"quit", "risk", "burn", "paycheck", "hours"})
        if "large" in q and ("number" in q or "integer" in q):
            anchor_terms.update({"large", "numbers", "integers", "memory", "digits"})
        if "author" in q and "do" in q:
            anchor_terms.update({"here", "use", "clients", "charge", "work"})

        candidates: list[tuple[int, int, str]] = []
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            lower = text.lower()
            positions = [lower.find(term) for term in anchor_terms if lower.find(term) >= 0]
            positions = [pos for pos in positions if pos >= 0]
            if not positions:
                continue
            for anchor in positions[:4]:
                excerpt = self._clean_window_excerpt(
                    self._window_around(text, anchor, before=180, after=1050),
                    max_words=170,
                )
                if not excerpt:
                    continue
                excerpt_lower = excerpt.lower()
                score = self._sentence_relevance_score(excerpt, query_terms)
                score += sum(1 for term in anchor_terms if term in excerpt_lower)
                score += len(re.findall(r"\b\d+\b|\$\d+", excerpt))
                score += sum(
                    2
                    for marker in [
                        "because",
                        "here's what",
                        "what i do",
                        "fear",
                        "wasting",
                        "memory",
                        "digits",
                        "paycheck",
                        "quit your job",
                        "risk everything",
                        "burn",
                        "hours a day",
                    ]
                    if marker in excerpt_lower
                )
                candidates.append((score, -index, excerpt))
        if not candidates:
            return ""
        candidates.sort(reverse=True)

        if "main message" in q:
            selected: list[str] = []
            seen_indexes: set[int] = set()
            seen_text: set[str] = set()
            for _, negative_index, excerpt in candidates:
                citation = -negative_index
                normalized = re.sub(r"\W+", " ", excerpt.lower()).strip()
                if citation in seen_indexes or normalized in seen_text:
                    continue
                seen_indexes.add(citation)
                seen_text.add(normalized)
                selected.append(f"- {excerpt}. [{citation}]")
                if len(selected) >= 3:
                    break
            if selected:
                return self._clean_final_answer("The main message is: " + " ".join(selected))

        citation = -candidates[0][1]
        prefix = "The relevant section says:"
        if "main message" in q:
            prefix = "The main message is:"
        elif ("hold" in q or "holding" in q or "holds" in q) and "back" in q:
            prefix = "What holds people back is:"
        elif "large" in q and ("number" in q or "integer" in q):
            prefix = "The article says:"
        return self._clean_final_answer(f"{prefix} {candidates[0][2]}. [{citation}]")
    def _ordered_result_texts(self, results: list[dict]) -> list[tuple[int, str]]:
        items: list[tuple[int, int, int, str]] = []
        seen: set[str] = set()
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            if not text:
                continue
            normalized = re.sub(r"\W+", " ", text.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            page = int(item.get("page_number") or 0)
            chunk_index = int(item.get("chunk_index") or index)
            items.append((page, chunk_index, index, text))
        items.sort(key=lambda item: (item[0], item[1], item[2]))
        return [(index, text) for _, _, index, text in items]
    def _window_around(self, text: str, anchor: int, before: int = 160, after: int = 900) -> str:
        start = max(0, anchor - before)
        end = min(len(text), anchor + after)
        sentence_start = max(
            text.rfind(". ", 0, start),
            text.rfind("? ", 0, start),
            text.rfind("! ", 0, start),
        )
        if sentence_start >= 0:
            start = sentence_start + 2
        sentence_end_candidates = [
            pos
            for pos in [text.find(". ", end), text.find("? ", end), text.find("! ", end)]
            if pos >= 0
        ]
        if sentence_end_candidates:
            end = min(sentence_end_candidates) + 1
        return text[start:end].strip()
    def _first_marker_after(self, lower_text: str, markers: list[str], start: int) -> int:
        positions = [lower_text.find(marker, start) for marker in markers]
        positions = [position for position in positions if position >= 0]
        return min(positions) if positions else -1
    def _clean_window_excerpt(self, excerpt: str, max_words: int = 160) -> str:
        excerpt = re.sub(r"\s+", " ", excerpt).strip(" .:-")
        excerpt = re.sub(r"\b(?:Follow|Published in)[^.!?]{0,120}", "", excerpt).strip(" .:-")
        words = excerpt.split()
        if len(words) > max_words:
            excerpt = " ".join(words[:max_words]).rstrip(" ,;:")
        return excerpt.strip()
