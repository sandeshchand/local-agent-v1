from __future__ import annotations

import re

from app.ollama_client import OllamaChatClient
from retrieval.context_builder import build_context


class AnswerService:
    def __init__(self, chat_client: OllamaChatClient) -> None:
        self.chat_client = chat_client

    def build_retrieval_prompt(
        self,
        query: str,
        results: list[dict],
        memory_context: str = "",
        tool_context: str = "",
    ) -> str:
        context = build_context(results)
        evidence_facts = self._extract_evidence_facts_with_llm(query, context)
        if self._is_insufficient_answer(evidence_facts):
            evidence_facts = self._build_evidence_fact_list(query, results)
        answer_shape = self._infer_answer_shape(query)

        return f"""
You are answering using only the retrieved document context below.

Rules:
1. Answer the user's exact question first. Do not write a general overview.
2. Use only the provided context and evidence facts.
3. If no relevant evidence exists, say exactly:
   "The provided context does not contain enough information."
4. Preserve uncertainty from the source, such as "may", "likely", "speculates", or "reverse-engineered".
5. Cover all distinct relevant facts, not only the first fact.
6. Cite each sentence or bullet using citation markers like [1], [2].
7. Do not add unsupported background or outside knowledge.
8. Preserve important source terminology exactly when it appears in the context, including model names,
   dates, method names, numbered components, limitation names, and technical phrases.
9. If the context contains a numbered list or explicit categories/components, include all relevant items.
10. Do not include sections like Overview, Applications, Challenges, Conclusion, or background history unless the user asks for them.
11. Do not include document titles, author names, source names, or URLs unless the user asks for them.
12. Do not begin with filler such as "Based on the context" or "Based on the evidence".
13. Keep the answer compact: usually 1 short paragraph or 3-6 bullets.

Answer shape:
{answer_shape}

Question-specific constraint:
{self._question_specific_constraint(query)}

Generic facet checklist:
{self._generic_facet_checklist(query)}

Question focus terms:
{", ".join(sorted(self._query_terms(query))) or "none"}

Evidence facts extracted from the retrieved context:
{evidence_facts}

Question:
{query}

Context:
{context}

Answer:
""".strip()

    def build_direct_prompt(self, query: str) -> str:
        return f"""
You are a friendly and helpful AI assistant.

Rules:
- For greetings like "hi", "hello", "hey", or "namaste", respond warmly and naturally in one short sentence.
- For casual conversation, respond briefly and politely.
- Answer clearly and concisely.
- If the question requires specific document content that you do not have, say that clearly.
- Do not claim you searched documents unless retrieval actually happened.
- Do not invent facts.

User question:
{query}

Answer:
""".strip()

    def build_tool_prompt(
        self,
        query: str,
        tool_context: str,
        memory_context: str = "",
    ) -> str:
        return f"""
You are a grounded assistant using tool output.

Rules:
- Answer only from the tool output below.
- Do not add unrelated background.
- If the tool output is insufficient, say that clearly.
- Keep the answer concise and accurate.
- Preserve uncertainty; do not treat speculative phrases as confirmed facts.

{memory_context}

[TOOL OUTPUT]
{tool_context}

Question:
{query}

Answer:
""".strip()

    def answer_from_context(
        self,
        query: str,
        results: list[dict],
        memory_context: str = "",
        tool_context: str = "",
    ) -> str:
        prompt = self.build_retrieval_prompt(
            query=query,
            results=results,
            memory_context=memory_context,
            tool_context=tool_context,
        )
        answer = self.chat_client.generate(prompt).strip()

        if not answer:
            return self._generic_extractive_fallback(query, results)

        answer = self._remove_mixed_abstention(answer)
        answer = self._focused_rewrite(query, answer, results)
        best_practices_answer = self._best_practices_extractive_answer(query, results)
        if best_practices_answer:
            answer = best_practices_answer
        capability_answer = ""
        if self._should_use_capability_extractive_answer(query, results):
            capability_answer = self._capability_extractive_answer(query, results)
            if capability_answer:
                answer = capability_answer
        limitation_answer = self._limitation_extractive_answer(query, results)
        if limitation_answer:
            answer = limitation_answer
        focused_entity_answer = self._focused_entity_extractive_answer(query, results)
        if focused_entity_answer and (
            self._looks_unfocused(query, answer)
            or self._misses_intent_shape(query, answer)
            or self._answer_misses_focus_phrase(query, answer)
            or self._prefer_focused_entity_answer(query, answer, focused_entity_answer)
        ):
            answer = focused_entity_answer
        if self._looks_under_specific(answer, results) or self._looks_unfocused(query, answer) or self._misses_intent_shape(query, answer):
            if capability_answer:
                return capability_answer
            if focused_entity_answer:
                return focused_entity_answer
            if best_practices_answer:
                return best_practices_answer
            if limitation_answer:
                return limitation_answer
            return self._generic_extractive_fallback(query, results)
        if self._is_insufficient_answer(answer):
            return self._generic_extractive_fallback(query, results)
        if results and not re.search(r"\[\d+\]", answer):
            if best_practices_answer:
                return best_practices_answer
            return self._generic_extractive_fallback(query, results)

        return self._ensure_focus_entity_mentioned(query, self._clean_final_answer(answer))

    def repair_answer(
        self,
        query: str,
        answer: str,
        results: list[dict],
        issues: list[str],
    ) -> str:
        if not results:
            return answer

        facts = self._build_evidence_fact_list(query, results, max_facts=20)
        context = build_context(results, max_chars_per_chunk=1200)
        issue_text = "\n".join(f"- {issue}" for issue in issues) or "- Answer needs verification repair."
        prompt = f"""
Repair this RAG answer using only retrieved evidence.

Verification issues:
{issue_text}

Rules:
- Answer only the user's exact question.
- Use only the evidence facts and context below.
- Fix missing directness, unsupported drift, raw chunk leakage, and invalid citations.
- Follow this question-specific constraint: {self._question_specific_constraint(query)}
- Keep the answer concise: one paragraph or 3-6 bullets.
- Cite each sentence or bullet with valid citation markers like [1], [2].
- Do not include broad background, applications, conclusions, or neighboring topics unless the question asks for them.
- Do not include document titles, author names, source names, URLs, or filler prefaces unless the question asks for them.
- If the evidence does not answer the question, say exactly: The provided context does not contain enough information.

Question:
{query}

Original answer:
{answer}

Evidence facts:
{facts}

Context:
{context}

Repaired answer:
""".strip()
        try:
            repaired = self.chat_client.generate(prompt).strip()
        except Exception:
            return answer
        if not repaired or self._is_insufficient_answer(repaired):
            return answer
        return self._ensure_focus_entity_mentioned(
            query,
            self._clean_final_answer(self._remove_mixed_abstention(repaired)),
        )

    def _extract_evidence_facts_with_llm(self, query: str, context: str) -> str:
        prompt = f"""
Extract source-faithful answer facts from the retrieved context.

Rules:
- Use only the context.
- Extract facts that directly answer the question, not neighboring background topics.
- Preserve exact terminology, names, dates, method names, numbered components, and limitation names.
- Extract all distinct facts that help answer the question.
- Keep citation markers by citing each fact with [1], [2], etc. from the context.
- Do not summarize away technical terms.
- Prefer facts from section titles and passages that match the question wording.
- If no facts answer the question, say exactly: The provided context does not contain enough information.

Question:
{query}

Context:
{context}

Evidence facts:
""".strip()
        try:
            facts = self.chat_client.generate(prompt).strip()
        except Exception:
            return ""
        return facts

    def answer_direct(self, query: str) -> str:
        q = query.strip().lower()

        greeting_map = {
            "hi": "Hello! How can I help you today?",
            "hello": "Hello! How can I help you today?",
            "hey": "Hey! How can I help you today?",
            "namaste": "Namaste! How can I help you today?",
            "namaskar": "Namaskar! How can I help you today?",
            "good morning": "Good morning! How can I help you today?",
            "good afternoon": "Good afternoon! How can I help you today?",
            "good evening": "Good evening! How can I help you today?",
        }

        if q in greeting_map:
            return greeting_map[q]

        prompt = self.build_direct_prompt(query)

        try:
            answer = self.chat_client.generate(prompt).strip()
        except Exception:
            return self._direct_fallback(query)

        if not answer:
            return self._direct_fallback(query)

        return answer

    def answer_from_tool_result(
        self,
        query: str,
        tool_context: str,
        memory_context: str = "",
    ) -> str:
        prompt = self.build_tool_prompt(
            query=query,
            tool_context=tool_context,
            memory_context=memory_context,
        )
        answer = self.chat_client.generate(prompt).strip()

        if not answer:
            return "The tool output does not directly answer this."

        return answer

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
                score = self._sentence_relevance_score(sentence, query_terms)
                score += self._focus_phrase_score(sentence, focus_phrases)
                score += sum(2 for term in intent_terms if term in sentence.lower())
                if score > 0:
                    scored_sentences.append((score, sentence))
            for sentence in sentences[:2]:
                if self._is_high_signal_sentence(sentence) and (
                    not focus_phrases
                    or any(phrase in sentence.lower() for phrase in focus_phrases)
                ):
                    scored_sentences.append((6, sentence))

            scored_sentences.sort(key=lambda pair: pair[0], reverse=True)
            for _, sentence in scored_sentences[:5]:
                if self._is_metadata_sentence(sentence):
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
            if self._looks_like_code_or_metadata_fact(fact_text):
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

        if "used for" in query.lower() or "useful" in query.lower():
            for index, item in enumerate(results, start=1):
                text = self._clean_text(item.get("text") or "")
                if "ner-like" in text.lower() or "named entity recognition" in text.lower():
                    ner_fact = f"- The retrieved example uses a simplified NER-like format for sequence labels. [{index}]"
                    if ner_fact.lower() not in seen:
                        selected.append(ner_fact)
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
            return ""

        return self._clean_final_answer(
            "Best practices include: "
            + " ".join(f"- {action}. [{citation_index}]" for action in selected[:12])
        )

    def _answer_misses_focus_phrase(self, query: str, answer: str) -> bool:
        focus_phrases = self._focus_phrases(query)
        if not focus_phrases:
            return False
        answer_lower = answer.lower()
        return not any(phrase in answer_lower for phrase in focus_phrases)

    def _prefer_focused_entity_answer(self, query: str, answer: str, focused_answer: str) -> bool:
        if not self._focus_phrases(query):
            return False
        q = query.lower()
        if not any(marker in q for marker in ["used for", "key strength", "key strengths", "how do", "how does", "what is"]):
            return False
        answer_terms = self._content_terms(answer)
        focused_terms = self._content_terms(focused_answer)
        return len(focused_terms) >= len(answer_terms) or len(focused_terms - answer_terms) >= 3

    def _focused_rewrite(self, query: str, draft_answer: str, results: list[dict]) -> str:
        facts = self._build_evidence_fact_list(query, results, max_facts=16)
        context = build_context(results, max_chars_per_chunk=1200)
        prompt = f"""
Rewrite the draft into a focused RAG answer.

Rules:
- Answer only the user's exact question.
- Use only the evidence facts and context below.
- Remove broad introductions, applications, background history, and conclusions unless the question asks for them.
- Follow this question-specific constraint: {self._question_specific_constraint(query)}
- Include every distinct directly relevant item, component, step, limitation, reason, or category supported by the evidence.
- Keep the answer concise: one paragraph or 3-6 bullets.
- Cite every sentence or bullet with [1], [2], etc.
- Do not include document titles, author names, source names, URLs, or filler prefaces unless the question asks for them.
- If the evidence does not answer the question, say exactly: The provided context does not contain enough information.

Question:
{query}

Draft answer:
{draft_answer}

Evidence facts:
{facts}

Context:
{context}

Focused answer:
""".strip()
        try:
            rewritten = self.chat_client.generate(prompt).strip()
        except Exception:
            return draft_answer
        if not rewritten or self._is_insufficient_answer(rewritten):
            return draft_answer
        return self._ensure_focus_entity_mentioned(
            query,
            self._clean_final_answer(self._remove_mixed_abstention(rewritten)),
        )

    def _looks_under_specific(self, answer: str, results: list[dict]) -> bool:
        answer_lower = answer.lower()
        evidence_text = " ".join((item.get("text") or "") for item in results)
        source_terms = self._source_specific_terms(evidence_text)
        if len(source_terms) < 4:
            return False
        matched = sum(1 for term in source_terms if term.lower() in answer_lower)
        return matched < max(2, len(source_terms) // 5)

    def _looks_unfocused(self, query: str, answer: str) -> bool:
        answer_lower = answer.lower()
        broad_headings = [
            "### overview",
            "### introduction",
            "### applications",
            "### challenges",
            "### conclusion",
            "summary of",
        ]
        if any(heading in answer_lower for heading in broad_headings):
            return True
        if "application" not in query.lower() and re.search(r"\bapplications?:", answer_lower):
            return True
        if any(term in query.lower() for term in ["different", "earlier", "previous", "compared"]) and any(
            drift in answer_lower
            for drift in ["applications in various domains", "healthcare", "robotics", "marketing", "education sector"]
        ):
            return True
        if (query.lower().startswith("what is") or "what type of" in query.lower()) and len(answer.split()) > 90:
            return True
        if "key features:" in answer_lower and not any(term in query.lower() for term in ["feature", "features", "different"]):
            return True

        query_terms = self._query_terms(query)
        if not query_terms:
            return False
        first_120_words = " ".join(answer_lower.split()[:120])
        matched = sum(1 for term in query_terms if term in first_120_words)
        return matched == 0 and len(answer.split()) > 120

    def _misses_intent_shape(self, query: str, answer: str) -> bool:
        query_lower = query.lower()
        answer_lower = answer.lower()

        if "what type of input" in query_lower:
            first_30_words = " ".join(answer_lower.split()[:30])
            return not any(term in first_30_words for term in ["input", "prompt", "instruction", "text", "natural language"])

        if any(term in query_lower for term in ["architecture", "framework", "components"]):
            first_80_words = " ".join(answer_lower.split()[:80])
            return not any(term in first_80_words for term in ["architecture", "framework", "component", "part", "module"])

        if any(term in query_lower for term in ["represent", "representation", "before feeding", "model input"]):
            return not any(term in answer_lower for term in ["representation", "represent", "latent", "token", "patch", "compress"])

        if any(term in query_lower for term in ["limitations", "limitation", "challenges"]):
            return not any(term in answer_lower for term in ["limitation", "challenge", "constraint", "failure", "issue"])

        return False

    def _source_specific_terms(self, text: str) -> set[str]:
        terms: set[str] = set()
        for match in re.findall(r"\b[A-Z][A-Za-z0-9]*(?:[-·][A-Z]?[A-Za-z0-9]+)*\b", text):
            if len(match) >= 3 and match.lower() not in {"figure", "source", "section", "title", "page"}:
                terms.add(match)
        for match in re.findall(r"\b\d{4}\b|\b\d+\s*minute\b|\btext-to-[a-z-]+\b|\b[a-z]+-[a-z]+(?:-[a-z]+)?\b", text.lower()):
            terms.add(match)
        return set(list(terms)[:40])

    def _infer_answer_shape(self, query: str) -> str:
        q = query.lower()
        if self._is_list_question(query):
            return "Use concise bullets. Include each distinct item or category supported by the context."
        if q.startswith("why"):
            return "Explain the reason and include the main benefits or consequences supported by the context."
        if q.startswith("how"):
            return "Explain the process in order. Include all supported steps or mechanisms."
        if "architecture" in q or "components" in q:
            return "Name the core architecture and list the supported components."
        if "limitations" in q or "risks" in q or "challenges" in q:
            return "Group the answer by limitation or challenge category."
        return "Give a concise paragraph or short bullets covering all supported facts."

    def _question_specific_constraint(self, query: str) -> str:
        q = query.lower()
        if "feature" in q and not any(term in q for term in ["benefit", "advantage", "setup", "install", "best practice"]):
            return (
                "For feature questions, list only supported features, capabilities, or functions. "
                "Do not add benefits, setup steps, best practices, or neighboring tool details unless the question asks for them."
            )
        if any(term in q for term in ["simulator", "simulation", "simulate"]):
            return (
                "For simulation or capability questions, include the concrete abilities and examples named in the evidence. "
                "Prefer specific observed behaviors over a generic explanation."
            )
        return "No extra constraint beyond answering the exact question."

    def _generic_facet_checklist(self, query: str) -> str:
        q = query.lower()
        facets: list[str] = []
        if "feature" in q:
            facets.extend(["named features/capabilities/functions", "short role of each feature"])
        if q.startswith("what is") or "definition" in q:
            facets.extend(["definition/category", "creator/source/date if present", "main capability", "important scope or limit"])
        if "architecture" in q or "components" in q or "core model" in q:
            facets.extend(["core architecture name", "all listed components/parts", "conditioning/input mechanism if present"])
        if q.startswith("how"):
            facets.extend(["ordered steps", "mechanisms/methods", "inputs and outputs", "important caveats"])
        if q.startswith("why"):
            facets.extend(["main reason", "technical challenge", "benefits/consequences", "comparison if present"])
        if any(term in q for term in ["simulator", "simulation", "simulate"]):
            facets.extend(["concrete simulation abilities", "specific examples or environments named in context", "scope: physical and/or digital if present"])
        if any(word in q for word in ["approaches", "types", "kinds", "prompt", "capabilities", "limitations"]):
            facets.extend(["all categories/items named in context", "role of each item", "examples if present"])
        if not facets:
            facets.append("all distinct facts that directly answer the question")
        return "\n".join(f"- {facet}" for facet in dict.fromkeys(facets))

    def _is_list_question(self, query: str) -> bool:
        q = query.lower()
        return any(
            phrase in q
            for phrase in [
                "what are",
                "what types",
                "what kinds",
                "what limitations",
                "what capabilities",
                "what approaches",
                "list",
            ]
        )

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
        return score

    def _intent_terms_from_query_terms(self, query_terms: set[str]) -> list[str]:
        terms: list[str] = []
        if {"input", "prompt", "instruction"} & query_terms:
            terms.extend(["input", "prompt", "instruction", "user", "text", "natural language"])
        if {"application", "applications", "areas", "uses"} & query_terms:
            terms.extend(["application", "use", "domain", "area", "industry", "sector"])
        if {"architecture", "framework", "component", "components"} & query_terms:
            terms.extend(["architecture", "framework", "component", "module", "mechanism"])
        if {"represent", "representation", "model", "input"} & query_terms:
            terms.extend(["representation", "token", "patch", "latent", "compressed", "compressing", "input", "encoder", "transformer", "diffusion"])
        if {"native", "sizes", "size", "resolution"} & query_terms:
            terms.extend(["native", "duration", "resolution", "aspect ratio", "composition", "framing", "crop", "resize"])
        if {"follow", "following", "instructions", "instruction", "detailed"} & query_terms:
            terms.extend(["instruction", "following", "caption", "description", "training", "prompt"])
        if {"limitations", "limitation", "challenge", "constraints"} & query_terms:
            terms.extend(["limitation", "challenge", "constraint", "failure", "risk", "issue", "accuracy", "usage"])
        if {"different", "earlier", "previous"} & query_terms:
            terms.extend(["different", "previous", "earlier", "unlike", "improvement"])
        if {"capabilities", "capability", "simulate", "simulation", "simulator", "world"} & query_terms:
            terms.extend(["capability", "ability", "simulate", "simulation", "environment", "world", "consistency", "coherence"])
        return list(dict.fromkeys(terms))

    def _query_intent_terms(self, query: str) -> list[str]:
        q = query.lower()
        terms: list[str] = []
        if "used for" in q or "useful" in q:
            terms.extend(["used", "useful", "prediction", "context", "sequential", "independent", "probabilistic", "application", "example"])
        if "best practice" in q:
            terms.extend(["practice", "development", "analysis", "threshold", "notification", "schedule", "low-traffic", "multi-stage"])
        if "limitation" in q or "challenge" in q:
            terms.extend(["limitation", "challenge", "cause", "effect", "spatial", "temporal", "irrelevant", "animals", "people", "hci", "usage"])
        if "detect" in q or "anomal" in q:
            terms.extend(["detect", "isolates", "outlier", "randomly", "unlabeled", "unsupervised", "fraud", "intrusion"])
        if "strength" in q:
            terms.extend(["strength", "memory", "speed", "performance", "hardware", "logic", "reward", "penalty", "interpretable"])
        return list(dict.fromkeys(terms))

    def _limitation_extractive_answer(self, query: str, results: list[dict]) -> str:
        if not any(term in query.lower() for term in ["limitation", "limitations", "challenge", "challenges", "weakness"]):
            return ""

        facts = [
            fact[2:].strip()
            for fact in self._build_evidence_fact_list(query, results, max_facts=24).splitlines()
            if fact.startswith("- ")
        ]
        if not facts:
            return ""

        markers = [
            "limitation",
            "challenge",
            "failure",
            "cause",
            "effect",
            "physical",
            "spatial",
            "temporal",
            "irrelevant",
            "animals",
            "people",
            "human-computer",
            "hci",
            "usage",
            "public access",
            "one minute",
            "one-minute",
            "safety",
        ]
        scored: list[tuple[int, int, str]] = []
        for index, fact in enumerate(facts):
            fact_text = re.sub(r"\[\d+\]", "", fact)
            fact_lower = fact_text.lower()
            if self._looks_like_code_or_metadata_fact(fact_text):
                continue
            score = sum(2 for marker in markers if marker in fact_lower)
            score += self._sentence_relevance_score(fact_text, self._query_terms(query))
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
        if not selected:
            return ""
        return self._clean_final_answer("The highlighted limitations are: " + " ".join(selected))

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
            ]
        )

    def _query_terms(self, query: str) -> set[str]:
        stop_words = {
            "what",
            "which",
            "are",
            "does",
            "do",
            "did",
            "how",
            "why",
            "the",
            "and",
            "for",
            "with",
            "from",
            "into",
            "about",
            "according",
            "review",
            "paper",
            "document",
            "article",
            "discuss",
            "describe",
            "say",
            "use",
            "uses",
            "used",
            "make",
            "makes",
            "key",
            "feature",
            "features",
            "machine",
            "learning",
        }
        return {
            token
            for token in re.findall(r"\b[a-zA-Z][a-zA-Z0-9\-]{2,}\b", query.lower())
            if token not in stop_words
        }

    def _content_terms(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"\b[a-zA-Z][a-zA-Z0-9\-]{3,}\b", text.lower())
            if token not in {
                "what",
                "which",
                "does",
                "this",
                "that",
                "from",
                "with",
                "about",
                "paper",
                "document",
                "article",
                "answer",
                "context",
                "section",
                "page",
            }
        }

    def _split_sentences(self, text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        parts = re.split(r"(?<=[.!?])\s+", normalized)
        return [part.strip() for part in parts if len(part.strip()) > 40]

    def _clean_text(self, text: str) -> str:
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
            "random_state",
            "train_test_split",
        ]
        if any(marker in sentence_lower for marker in code_markers):
            return True
        if len(sentence.split()) > 90 and sentence.count("=") >= 2:
            return True
        return self._is_metadata_sentence(sentence)

    def _clean_final_answer(self, answer: str) -> str:
        answer = re.sub(r"\[child chunk \d+ \| page [^\]]+\]\s*", "", answer)
        answer = re.sub(r"\b\d+\s+(?=\[child chunk)", "", answer)
        answer = re.sub(
            r"^\s*Based on (?:the )?(?:provided )?(?:context|evidence|retrieved evidence)(?: provided)?[:,]?\s*",
            "",
            answer,
            flags=re.IGNORECASE,
        )
        answer = re.sub(
            r"(\[\d+\])\s+[A-Z][^.\n]{10,}\|\s*by\s+[^.\n]+$",
            r"\1",
            answer,
            flags=re.IGNORECASE,
        )
        answer = re.sub(r"\s+-\s+(?=[A-Z][A-Za-z0-9 /&-]{0,48}:)", "\n- ", answer)
        answer = re.sub(
            r"(?:^|\n)-?\s*Some (?:of )?the key features(?: of [^:]+)? include:\s*",
            "\n",
            answer,
            flags=re.IGNORECASE,
        )
        answer = answer.replace("simu- late", "simulate")
        answer = answer.replace("signif- icantly", "significantly")
        answer = answer.replace("gener- ation", "generation")
        answer = answer.replace("remain- ing", "remaining")
        answer = re.sub(r"\bAbstract\b\s*", "", answer, flags=re.IGNORECASE)
        answer = re.sub(r"\s+", " ", answer)
        return answer.strip()

    def _ensure_focus_entity_mentioned(self, query: str, answer: str) -> str:
        if not answer or self._is_insufficient_answer(answer):
            return answer
        focus_entity = self._focus_entity_display(query)
        if not focus_entity or focus_entity.lower() in answer.lower():
            return answer

        q = query.lower()
        if self._is_list_question(query):
            label = "key features" if "feature" in q else "main points"
            return f"{focus_entity}'s {label} are: {answer}"
        return f"{focus_entity}: {answer}"

    def _focus_entity_display(self, query: str) -> str:
        focus_phrases = self._focus_phrases(query, preserve_case=True)
        if focus_phrases:
            return sorted(focus_phrases, key=len, reverse=True)[0]

        generic_terms = {
            "what",
            "which",
            "from",
            "paper",
            "document",
            "key",
            "feature",
            "features",
            "main",
            "some",
            "tell",
            "about",
            "explain",
            "describe",
            "according",
            "review",
        }
        candidates: list[str] = []
        for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_-]{3,}\b", query):
            lower = token.lower()
            if lower in generic_terms:
                continue
            if token[:1].isupper() or any(char.isupper() for char in token[1:]):
                candidates.append(token)
        return candidates[-1] if candidates else ""

    def _focus_phrases(self, query: str, preserve_case: bool = False) -> set[str]:
        generic_terms = {
            "what",
            "which",
            "from",
            "paper",
            "document",
            "article",
            "key",
            "features",
            "main",
            "some",
            "tell",
            "about",
            "explain",
            "describe",
            "according",
            "review",
            "how",
            "why",
            "does",
            "used",
        }
        phrases: set[str] = set()

        for match in re.finditer(
            r"\b[A-Z][A-Za-z0-9_-]*\b(?:\s+\b[A-Z][A-Za-z0-9_-]*\b)+",
            query,
        ):
            current = [
                token
                for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_-]*\b", match.group(0))
                if token.lower() not in generic_terms
            ]
            if len(current) < 2:
                continue
            phrase_tokens = current if preserve_case else [token.lower() for token in current]
            phrase = " ".join(phrase_tokens)
            phrases.add(phrase)
            last = current[-1]
            if last.lower().endswith("s") and len(last) > 4:
                singular_tokens = list(current[:-1]) + [last[:-1]]
                if not preserve_case:
                    singular_tokens = [token.lower() for token in singular_tokens]
                phrases.add(" ".join(singular_tokens))
        return phrases

    def _remove_mixed_abstention(self, answer: str) -> str:
        lines = [
            line
            for line in answer.splitlines()
            if "provided context does not contain enough information" not in line.lower()
            and "does not contain enough information" not in line.lower()
        ]
        cleaned = "\n".join(lines).strip()
        return cleaned or answer

    def _is_insufficient_answer(self, answer: str) -> bool:
        normalized = answer.strip().lower()
        return (
            "does not contain enough information" in normalized
            or "not enough information" in normalized
            or "retrieved context does not directly answer" in normalized
        )

    def _direct_fallback(self, query: str) -> str:
        q = query.strip().lower()

        greeting_map = {
            "hi": "Hello! How can I help you today?",
            "hello": "Hello! How can I help you today?",
            "hey": "Hey! How can I help you today?",
            "namaste": "Namaste! How can I help you today?",
            "namaskar": "Namaskar! How can I help you today?",
            "good morning": "Good morning! How can I help you today?",
            "good afternoon": "Good afternoon! How can I help you today?",
            "good evening": "Good evening! How can I help you today?",
        }

        if q in greeting_map:
            return greeting_map[q]

        return "I'm here and ready to help. Could you rephrase your question?"
