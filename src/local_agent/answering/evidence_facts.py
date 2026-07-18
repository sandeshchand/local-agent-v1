from __future__ import annotations

import re


class EvidenceFactMixin:
    def _build_evidence_fact_list(self, query: str, results: list[dict], max_facts: int = 28) -> str:
        facts: list[str] = []
        query_terms = self._query_terms(query)
        focus_phrases = self._focus_phrases(query)
        intent_terms = self._query_intent_terms(query)
        seen: set[str] = set()

        for fact in self._section_title_facts(query, results):
            if fact.lower() in seen:
                continue
            seen.add(fact.lower())
            facts.append(fact)
            if len(facts) >= max_facts:
                return "\n".join(facts)

        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            if not text:
                continue

            item_context = " ".join(
                [
                    item.get("section_title") or "",
                    item.get("title") or "",
                    text,
                ]
            )
            context_relevance = self._sentence_relevance_score(item_context, query_terms)
            context_relevance += self._focus_phrase_score(item_context, focus_phrases)
            context_relevance += sum(1 for term in intent_terms if term in item_context.lower())
            sentences = self._split_sentences(text)
            scored_sentences: list[tuple[int, str]] = []
            if index <= 4:
                for sentence in sentences[:5]:
                    if self._is_high_signal_sentence(sentence) and (
                        not focus_phrases
                        or any(phrase in sentence.lower() for phrase in focus_phrases)
                    ):
                        scored_sentences.append((7, sentence))
            for sentence in sentences:
                if self._looks_like_code_or_metadata_fact(sentence) and not self._should_keep_code_fact(query, sentence):
                    continue
                score = self._sentence_relevance_score(sentence, query_terms)
                score += self._focus_phrase_score(sentence, focus_phrases)
                score += sum(2 for term in intent_terms if term in sentence.lower())
                if context_relevance > 0 and self._looks_like_structured_fact(sentence):
                    score += min(6, context_relevance)
                if score > 0:
                    scored_sentences.append((score, sentence))
            for sentence in sentences[:2]:
                if self._is_high_signal_sentence(sentence) and (
                    not focus_phrases
                    or any(phrase in sentence.lower() for phrase in focus_phrases)
                ):
                    scored_sentences.append((6, sentence))

            scored_sentences.sort(key=lambda pair: pair[0], reverse=True)
            per_item_limit = 8 if self._needs_broad_fact_coverage(query) else 5
            for _, sentence in scored_sentences[:per_item_limit]:
                if self._looks_like_code_or_metadata_fact(sentence) and not self._should_keep_code_fact(query, sentence):
                    continue
                normalized_sentence = sentence.lower()
                if normalized_sentence in seen:
                    continue
                seen.add(normalized_sentence)
                facts.append(f"- {sentence} [{index}]")
                if len(facts) >= max_facts:
                    return "\n".join(facts)

        if not facts:
            return "- No directly matching facts were extracted from the retrieved context."

        return "\n".join(facts)
    def _section_title_facts(self, query: str, results: list[dict]) -> list[str]:
        query_lower = query.lower()
        if not self._is_list_question(query) and not any(word in query_lower for word in ["application", "areas", "types", "kinds", "categories"]):
            return []

        facts: list[str] = []
        seen_titles: set[str] = set()
        for index, item in enumerate(results, start=1):
            titles = [item.get("section_title") or ""]
            titles.extend(
                match.strip()
                for match in re.findall(r"\[child chunk \d+ \| page [^\]|]+ \| section ([^\]]+)\]", item.get("text") or "")
            )
            for title in titles:
                clean_title = self._clean_section_title(title)
                if not clean_title or clean_title.lower() in seen_titles:
                    continue
                if self._section_title_matches_query(query_lower, clean_title.lower()):
                    seen_titles.add(clean_title.lower())
                    facts.append(f"- The retrieved document section identifies this relevant item/category: {clean_title}. [{index}]")
        return facts
    def _clean_section_title(self, title: str) -> str:
        title = re.sub(r"^\d+(?:\.\d+)*\s*", "", title.strip())
        return re.sub(r"\s+", " ", title).strip(" :-")
    def _section_title_matches_query(self, query_lower: str, title_lower: str) -> bool:
        if not title_lower or title_lower in {"contents", "references", "unknown"}:
            return False
        if any(word in query_lower for word in ["application", "areas", "use case", "uses"]):
            non_answer_titles = [
                "application",
                "discussion",
                "conclusion",
                "introduction",
                "opportunities",
                "limitations",
                "safety",
                "concern",
                "reference",
            ]
            return not any(skip in title_lower for skip in non_answer_titles)
        if any(word in query_lower for word in ["types", "kinds", "categories", "name some"]):
            return not any(skip in title_lower for skip in ["discussion", "conclusion", "introduction"])
        return False
    def _generic_extractive_fallback(self, query: str, results: list[dict]) -> str:
        facts = self._build_evidence_fact_list(query, results, max_facts=6)
        if "No directly matching facts" in facts:
            return "The provided context does not contain enough information."

        clean_facts = [
            fact[2:].strip()
            for fact in facts.splitlines()
            if fact.startswith("- ")
        ]
        if not clean_facts:
            return "The provided context does not contain enough information."

        if self._is_list_question(query):
            return self._ensure_focus_entity_mentioned(query, self._clean_final_answer(" ".join(clean_facts)))

        return self._ensure_focus_entity_mentioned(query, self._clean_final_answer(" ".join(clean_facts[:4])))
    def _sentence_relevance_score(self, sentence: str, query_terms: set[str]) -> int:
        sentence_lower = sentence.lower()
        score = sum(1 for term in query_terms if term in sentence_lower)
        query_phrase = " ".join(sorted(query_terms))
        score += sum(2 for term in self._intent_terms_from_query_terms(query_terms) if term in sentence_lower)
        if query_phrase and query_phrase in sentence_lower:
            score += 2
        if any(marker in sentence_lower for marker in ["first", "second", "third", "finally", "include", "includes", "consists", "composed", "such as", "it has three parts", "(1)", "(2)", "(3)"]):
            score += 1
        if any(marker in sentence_lower for marker in ["limitation", "challenge", "benefit", "approach", "method", "architecture", "prompt", "compression", "released", "model", "called", "known as"]):
            score += 1
        return score
    def _focus_phrase_score(self, text: str, focus_phrases: set[str]) -> int:
        if not focus_phrases:
            return 0
        text_lower = text.lower()
        score = 0
        for phrase in focus_phrases:
            phrase_terms = phrase.split()
            if phrase in text_lower:
                score += 10
            elif len(phrase_terms) >= 2 and all(term in text_lower for term in phrase_terms):
                score += 5
            acronym = self._phrase_acronym(phrase)
            if acronym and re.search(rf"\b{re.escape(acronym)}s?\b", text_lower):
                score += 8
        return score
    def _looks_like_structured_fact(self, sentence: str) -> bool:
        sentence_lower = sentence.lower()
        return bool(
            re.search(r"\b(?:\d+[.)]|day\s*\d+|step\s*\d+|first|second|third|finally)\b", sentence_lower)
            or ":" in sentence[:100]
            or self._contains_distinctive_identifier(sentence)
        )
    def _needs_broad_fact_coverage(self, query: str) -> bool:
        q = query.lower()
        return self._is_list_question(query) or any(
            term in q
            for term in [
                "limitation",
                "challenge",
                "detect",
                "anomal",
                "useful",
                "scalable",
                "model input",
                "start",
                "pipeline",
                "formula",
                "architecture",
                "mentioned",
                "reasons",
                "command",
                "server",
                ".env",
                "env file",
                "indentation",
                "braces",
                "replace",
                "mean by",
            ]
        )
    def _is_high_signal_sentence(self, sentence: str) -> bool:
        sentence_lower = sentence.lower()
        return any(
            marker in sentence_lower
            for marker in [
                "is a",
                "released",
                "it has three parts",
                "(1)",
                "(2)",
                "(3)",
                "such as",
                "include",
                "limitation",
                "challenge",
                "approach",
                "method",
                "capability",
                "useful",
                "why is",
                "enforces",
                "forces",
                "key : value",
            ]
        )
    def _split_sentences(self, text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        list_parts = [
            match.group(1).strip()
            for match in re.finditer(
                r"(?:^|\s)(?:[-*]|\d+[.)])\s+([^.!?]{12,220}[.!?])",
                normalized,
            )
        ]
        command_parts = [
            match.group(0).strip()
            for match in re.finditer(
                r"\b(?:python\s+-m\s+[-\w.]+(?:\s+\d+)?|docker\s+run\b[^.!?]{0,160}|pip\s+install\s+[-\w.]+|uv\s+run\b[^.!?]{0,120}|npm\s+install\s+[-\w.]+|brew\s+install\s+[-\w.]+)",
                normalized,
                flags=re.IGNORECASE,
            )
        ]
        parts = re.split(r"(?<=[.!?])\s+", normalized)
        candidates = [*list_parts, *command_parts, *parts]
        results: list[str] = []
        seen: set[str] = set()
        for part in candidates:
            part = part.strip()
            if not part:
                continue
            word_count = len(part.split())
            is_short_list_item = part in list_parts and word_count >= 3
            part_lower = part.lower()
            is_short_high_signal = any(
                marker in part_lower
                for marker in [
                    "http.server",
                    "quickly test",
                    "share files",
                    "local network",
                    "third-party",
                    "clean",
                    "readable",
                    "missing braces",
                    "key : value",
                    "api keys",
                    "database",
                    "degree",
                    "computer science degree",
                    "tech bro",
                    "technical background",
                    "line of code",
                    "fancy app",
                    "product",
                    "don't need",
                    "don’t need",
                    "no code",
                    "save time",
                    "make money",
                ]
            )
            if len(part) <= 40 and not is_short_list_item and not is_short_high_signal:
                continue
            normalized_part = part.lower()
            if normalized_part in seen:
                continue
            seen.add(normalized_part)
            results.append(part)
        return results
    def _clean_text(self, text: str) -> str:
        text = self._repair_mojibake(text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        abstract_match = re.search(r"\bAbstract\b", text[:800], flags=re.IGNORECASE)
        if abstract_match:
            text = text[abstract_match.start():]
        text = re.sub(r"\[child chunk \d+ \| page [^\]]+\]\s*", " ", text)
        text = re.sub(r"\b\d+\s+(?=\[child chunk)", " ", text)
        text = re.sub(r"\bAbstract\b\s*", "", text, flags=re.IGNORECASE)
        text = text.replace("signif- icantly", "significantly")
        text = text.replace("simu- late", "simulate")
        text = text.replace("gener- ation", "generation")
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    def _is_metadata_sentence(self, sentence: str) -> bool:
        sentence_lower = sentence.lower()
        if any(term in sentence_lower for term in ["@article", "copyright", "all rights reserved"]):
            return True
        author_markers = sum(1 for marker in ["university", "research", "author", "corresponding", "email"] if marker in sentence_lower)
        capitalized_words = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", sentence)
        return author_markers >= 2 and len(capitalized_words) >= 4
    def _looks_like_code_or_metadata_fact(self, sentence: str) -> bool:
        sentence_lower = sentence.lower()
        code_markers = [
            "import ",
            "plt.",
            "np.",
            "print(",
            "pip install",
            "```",
            "def ",
            "elif ",
            "app.launch",
            "gr.",
            "tempfile.",
            "return gr.",
            "random_state",
            "train_test_split",
        ]
        if any(marker in sentence_lower for marker in code_markers):
            return True
        if re.search(r"\b(?:return|for|while|if|else)\s+[\w_(]", sentence_lower) and (
            sentence.count("=") >= 1 or sentence.count("(") >= 2
        ):
            if "used for" in sentence_lower:
                return False
            return True
        if re.search(r"\b\w+\s*=\s*[^.!?]{1,90}", sentence) and sentence.count("(") >= 2:
            return True
        if len(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\s*=", sentence)) >= 2:
            return True
        if len(sentence.split()) > 90 and sentence.count("=") >= 2:
            return True
        return self._is_metadata_sentence(sentence)
    def _should_keep_code_fact(self, query: str, sentence: str) -> bool:
        query_lower = query.lower()
        sentence_lower = sentence.lower()
        if not any(
                term in query_lower
            for term in ["command", "setup", "run", "install", "code", "example", "server", "large number", "numbers", "settings", "environment variables", "configuration"]
        ):
            return False
        return any(
            marker in sentence_lower
            for marker in ["pip ", "uv ", "install", "python", "print(", "**", "http", "localhost", "127.0.0.1", "load", "url", "alias", "prefix", "validation"]
        ) or self._contains_distinctive_identifier(sentence)
    def _is_low_value_fact(self, sentence: str) -> bool:
        sentence = re.sub(r"\s+", " ", sentence).strip()
        sentence_lower = sentence.lower()
        if re.match(r"^\d+(?:\.\d+)*\s+[A-Z][A-Za-z0-9 -]{2,70}\.?$", sentence):
            return True
        if sentence_lower.startswith("we discuss ") and len(sentence.split()) < 24:
            return True
        if sentence_lower.startswith("based on public") or sentence_lower.startswith("based on published"):
            return True
        if "comprehensive review" in sentence_lower and "current limitations" in sentence_lower:
            return True
        if any(marker in sentence_lower for marker in ["follow publication", "click here", "followers", "following"]):
            return True
        if any(marker in sentence_lower for marker in ["tag your", "clap if", "comment below", "share this"]):
            return True
        if sentence_lower.startswith("where can you use this") or sentence_lower.startswith("when to use"):
            return True
        return False
    def _extract_citation_number(self, fact: str) -> int | None:
        match = re.search(r"\[(\d+)\]\s*$", fact)
        if not match:
            return None
        return int(match.group(1))
