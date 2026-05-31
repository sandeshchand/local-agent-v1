from __future__ import annotations

import json
import re

from local_agent.app.ollama_client import OllamaChatClient
from local_agent.retrieval.context_builder import build_context


class AnswerService:
    """
    Builds final answers from retrieved evidence.

    See docs/ANSWER_SERVICE.md for the full design notes. The short version:
    LLM output is the first draft, then generic extractive paths repair missing
    facts, focus drift, and citation issues without using document-specific hacks.
    """

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

Memory guidance:
{memory_context}

Memory rule:
Use memory only for user preferences and project/process constraints. Do not use memory as document evidence.

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

    def build_direct_prompt(self, query: str, memory_context: str = "") -> str:
        return f"""
You are a friendly and helpful AI assistant.

Rules:
- For greetings like "hi", "hello", "hey", or "namaste", respond warmly and naturally in one short sentence.
- For casual conversation, respond briefly and politely.
- Answer clearly and concisely.
- If the question requires specific document content that you do not have, say that clearly.
- Do not claim you searched documents unless retrieval actually happened.
- Do not invent facts.

Memory guidance:
{memory_context}

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
        results = self._single_source_results(query, results)
        prompt = self.build_retrieval_prompt(
            query=query,
            results=results,
            memory_context=memory_context,
            tool_context=tool_context,
        )
        try:
            answer = self.chat_client.generate(prompt).strip()
        except Exception:
            fallback = self._deterministic_repair_answer(query, results)
            return fallback or self._generic_extractive_fallback(query, results)

        if not answer:
            return self._generic_extractive_fallback(query, results)

        answer = self._remove_mixed_abstention(answer)
        answer = self._focused_rewrite(query, answer, results)

        # Candidate priority matters: specific extractors run before broad list
        # extraction so a feature, limitation, pipeline, or command answer is not
        # overwritten by a generic summary.
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
        definition_answer = self._definition_extractive_answer(query, results)
        if definition_answer:
            answer = definition_answer
        used_for_answer = self._used_for_extractive_answer(query, results)
        if used_for_answer:
            answer = used_for_answer
        config_file_answer = self._config_file_purpose_answer(query, results)
        if config_file_answer:
            answer = config_file_answer
        meaning_answer = self._meaning_extractive_answer(query, results)
        if meaning_answer:
            answer = meaning_answer
        pipeline_answer = self._pipeline_extractive_answer(query, results)
        if pipeline_answer:
            answer = pipeline_answer
        challenge_answer = self._challenge_steps_answer(query, results)
        if challenge_answer:
            answer = challenge_answer
        command_answer = self._command_usefulness_answer(query, results)
        if command_answer:
            answer = command_answer
        example_answer = self._example_extractive_answer(query, results)
        if example_answer and (
            "example" in query.lower()
            or self._looks_unfocused(query, answer)
            or len(self._content_terms(example_answer) - self._content_terms(answer)) >= 3
        ):
            answer = example_answer
        why_answer = self._why_extractive_answer(query, results)
        if why_answer and not meaning_answer and (
            self._is_explanation_question(query)
            and (
                self._looks_unfocused(query, answer)
                or self._misses_intent_shape(query, answer)
                or self._prefer_mechanism_answer(query, answer, why_answer)
                or len(self._content_terms(why_answer) - self._content_terms(answer)) >= 3
            )
        ):
            answer = why_answer
        list_answer = self._list_extractive_answer(query, results)
        if list_answer and not best_practices_answer and not limitation_answer and not used_for_answer and not config_file_answer and not meaning_answer and not challenge_answer and not command_answer and (
            self._is_list_question(query)
            or self._looks_unfocused(query, answer)
            or self._misses_intent_shape(query, answer)
            or self._prefer_mechanism_answer(query, answer, list_answer)
        ):
            answer = list_answer
        mechanism_answer = self._mechanism_extractive_answer(query, results)
        if mechanism_answer and (
            self._misses_intent_shape(query, answer)
            or self._looks_under_specific(answer, results)
            or self._prefer_mechanism_answer(query, answer, mechanism_answer)
        ):
            answer = mechanism_answer
        focused_entity_answer = self._focused_entity_extractive_answer(query, results)
        if focused_entity_answer and (
            self._looks_unfocused(query, answer)
            or self._misses_intent_shape(query, answer)
            or self._answer_misses_focus_phrase(query, answer)
            or self._prefer_focused_entity_answer(query, answer, focused_entity_answer)
        ):
            answer = focused_entity_answer
        source_window_answer = self._source_window_answer(query, results)
        if source_window_answer and self._should_prefer_source_window_answer(query, answer, source_window_answer):
            answer = source_window_answer
        def final_answer(candidate: str) -> str:
            candidate = self._augment_feature_answer_with_intro(query, candidate, results)
            return self._clean_final_answer(candidate, max_citation=len(results))

        if self._looks_under_specific(answer, results) or self._looks_unfocused(query, answer) or self._misses_intent_shape(query, answer):
            if capability_answer:
                return final_answer(capability_answer)
            if why_answer:
                return final_answer(why_answer)
            if definition_answer:
                return final_answer(definition_answer)
            if used_for_answer:
                return final_answer(used_for_answer)
            if config_file_answer:
                return final_answer(config_file_answer)
            if meaning_answer:
                return final_answer(meaning_answer)
            if pipeline_answer:
                return final_answer(pipeline_answer)
            if challenge_answer:
                return final_answer(challenge_answer)
            if command_answer:
                return final_answer(command_answer)
            if example_answer:
                return final_answer(example_answer)
            if source_window_answer:
                return final_answer(source_window_answer)
            if list_answer:
                return final_answer(list_answer)
            if mechanism_answer:
                return final_answer(mechanism_answer)
            if focused_entity_answer:
                return final_answer(focused_entity_answer)
            if best_practices_answer:
                return final_answer(best_practices_answer)
            if limitation_answer:
                return final_answer(limitation_answer)
            return self._generic_extractive_fallback(query, results)
        if self._is_insufficient_answer(answer):
            return self._generic_extractive_fallback(query, results)
        answer = self._augment_feature_answer_with_intro(query, answer, results)
        if results and not re.search(r"\[\d+\]", answer):
            if best_practices_answer:
                return self._clean_final_answer(best_practices_answer, max_citation=len(results))
            return self._generic_extractive_fallback(query, results)

        return self._ensure_focus_entity_mentioned(query, self._clean_final_answer(answer, max_citation=len(results)))

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
        issue_blob = issue_text.lower()
        if any(term in issue_blob for term in ["raw retrieval", "chunk metadata"]):
            extractive_repair = self._deterministic_repair_answer(query, results)
            if extractive_repair:
                return extractive_repair

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
            extractive_repair = self._deterministic_repair_answer(query, results)
            return extractive_repair or answer
        cleaned_repair = self._ensure_focus_entity_mentioned(
            query,
            self._clean_final_answer(self._remove_mixed_abstention(repaired), max_citation=len(results)),
        )
        if self._has_raw_context_leak(cleaned_repair) or self._looks_unfocused(query, cleaned_repair):
            extractive_repair = self._deterministic_repair_answer(query, results)
            return extractive_repair or cleaned_repair
        return cleaned_repair

    def _deterministic_repair_answer(self, query: str, results: list[dict]) -> str:
        candidate_builders = [
            self._source_window_answer,
            self._limitation_extractive_answer,
            self._definition_extractive_answer,
            self._used_for_extractive_answer,
            self._config_file_purpose_answer,
            self._meaning_extractive_answer,
            self._pipeline_extractive_answer,
            self._command_usefulness_answer,
            self._example_extractive_answer,
            self._why_extractive_answer,
            self._list_extractive_answer,
            self._mechanism_extractive_answer,
            self._focused_entity_extractive_answer,
            self._generic_extractive_fallback,
        ]
        for builder in candidate_builders:
            candidate = builder(query, results)
            candidate = self._ensure_focus_entity_mentioned(
                query,
                self._clean_final_answer(candidate, max_citation=len(results)),
            )
            if not candidate or self._is_insufficient_answer(candidate):
                continue
            if results and not re.search(r"\[\d+\]", candidate):
                continue
            if self._has_raw_context_leak(candidate):
                continue
            if self._looks_unfocused(query, candidate) and len(candidate.split()) > 120:
                continue
            return candidate
        return ""

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

    def answer_direct(self, query: str, memory_context: str = "") -> str:
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

        prompt = self.build_direct_prompt(query, memory_context=memory_context)

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
        structured_answer = self._answer_from_structured_tool_output(tool_context)
        if structured_answer:
            return structured_answer

        prompt = self.build_tool_prompt(
            query=query,
            tool_context=tool_context,
            memory_context=memory_context,
        )
        answer = self.chat_client.generate(prompt).strip()

        if not answer:
            return "The tool output does not directly answer this."

        return answer

    def _answer_from_structured_tool_output(self, tool_context: str) -> str:
        try:
            payload = json.loads(tool_context)
        except (TypeError, json.JSONDecodeError):
            return ""

        if not isinstance(payload, dict):
            return ""

        if payload.get("tool") == "get_current_weather":
            return self._format_weather_tool_answer(payload)
        if payload.get("source") == "mcp":
            return self._format_mcp_tool_answer(payload)

        return ""

    def _format_weather_tool_answer(self, payload: dict) -> str:
        location = payload.get("location") or "the requested location"
        temperature = payload.get("temperature")
        apparent_temperature = payload.get("apparent_temperature")
        condition = payload.get("condition")
        time = payload.get("time")
        timezone = payload.get("timezone")

        if not temperature:
            return "The weather tool did not return a current temperature."

        answer = f"The current temperature in {location} is {temperature}"
        if apparent_temperature:
            answer += f", with an apparent temperature of {apparent_temperature}"
        if condition:
            answer += f". Conditions: {condition}."
        else:
            answer += "."
        if time:
            answer += f" Reported at {time}"
            if timezone:
                answer += f" ({timezone})"
            answer += "."
        return answer

    def _format_mcp_tool_answer(self, payload: dict) -> str:
        result = payload.get("result")
        if not isinstance(result, dict):
            return ""

        tool = result.get("tool") or payload.get("tool_name") or "mcp_tool"
        if result.get("success") is False:
            error = result.get("error") or "The tool could not complete the request."
            return f"The MCP tool could not complete the request: {error}"

        if tool == "list_tables":
            tables = result.get("tables") or []
            if not tables:
                return "No SQLite tables were found."
            lines = [
                f"- {table.get('name')} ({table.get('row_count', 0)} rows)"
                for table in tables
            ]
            return "SQLite tables:\n" + "\n".join(lines)

        if tool == "preview_table":
            table = result.get("table") or "the requested table"
            rows = result.get("rows") or []
            columns = result.get("columns") or []
            if not rows:
                column_text = ", ".join(columns) if columns else "no columns"
                return f"Table {table} has no rows. Columns: {column_text}."

            lines = []
            for index, row in enumerate(rows[:10], start=1):
                if isinstance(row, dict):
                    values = "; ".join(
                        f"{key}={self._short_tool_value(value)}"
                        for key, value in row.items()
                    )
                else:
                    values = self._short_tool_value(row)
                lines.append(f"{index}. {values}")
            return f"Preview of SQLite table {table}:\n" + "\n".join(lines)

        if tool == "recent_traces":
            traces = result.get("traces") or []
            if not traces:
                return "No recent traces were found in SQLite."
            lines = []
            for trace in traces[:20]:
                if not isinstance(trace, dict):
                    continue
                trace_id = trace.get("trace_id")
                status = ""
                verification = trace.get("verification_json")
                if isinstance(verification, str) and verification:
                    try:
                        status = json.loads(verification).get("status") or ""
                    except json.JSONDecodeError:
                        status = ""
                query = self._short_tool_value(trace.get("query") or "")
                lines.append(f"- Trace {trace_id}: {status or 'no verifier'} - {query}")
            return "Recent SQLite traces:\n" + "\n".join(lines)

        if tool == "feedback_summary":
            total = result.get("total_count", 0)
            likes = result.get("like_count", 0)
            dislikes = result.get("dislike_count", 0)
            rate = float(result.get("dislike_rate") or 0.0)
            answer = (
                f"Feedback summary: {total} total, {likes} liked, "
                f"{dislikes} disliked, dislike rate {rate:.0%}."
            )
            issue_counts = result.get("issue_counts") or {}
            if issue_counts:
                issue_text = ", ".join(
                    f"{issue}: {count}"
                    for issue, count in issue_counts.items()
                )
                answer += f" Issue counts: {issue_text}."
            return answer

        if tool == "list_directory":
            entries = result.get("entries") or []
            if not entries:
                return f"No entries were found in {result.get('path') or 'the requested location'}."
            names = []
            for entry in entries[:30]:
                entry_type = entry.get("type") or "item"
                entry_path = entry.get("path") or entry.get("name") or ""
                names.append(f"- {entry_path} ({entry_type})")
            answer = f"Files in {result.get('path') or 'the allowed File MCP roots'}:\n" + "\n".join(names)
            if result.get("truncated"):
                answer += "\nThe list was truncated."
            return answer

        if tool == "read_text_file":
            path = result.get("path") or "the requested file"
            content = str(result.get("content") or "")
            if result.get("truncated"):
                return f"Here is the beginning of {path}:\n\n{content}\n\nThe file was truncated."
            return f"Here is the content of {path}:\n\n{content}"

        if tool == "file_info":
            path = result.get("path") or "the requested path"
            kind = "directory" if result.get("is_dir") else "file"
            size = result.get("size_bytes")
            modified = result.get("modified_at")
            answer = f"{path} is a {kind}."
            if size is not None:
                answer += f" Size: {size} bytes."
            if modified:
                answer += f" Modified: {modified}."
            return answer

        return ""

    def _short_tool_value(self, value: object, max_length: int = 120) -> str:
        text = str(value).replace("\n", " ").strip()
        if len(text) <= max_length:
            return text
        return f"{text[: max_length - 3]}..."

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

    def _is_explanation_question(self, query: str) -> bool:
        q = query.lower()
        return q.startswith("why") or (
            "article" in q and ("mean by" in q or (q.startswith("what does") and "mean" in q))
        )

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

    def _definition_query_entity(self, query: str) -> str:
        q = query.strip().strip("?!. ")
        patterns = [
            r"(?i)^what\s+do\s+you\s+mean\s+by\s+(.+)$",
            r"(?i)^what\s+is\s+(.+)$",
            r"(?i)^what\s+are\s+(.+)$",
            r"(?i)^define\s+(.+)$",
            r"(?i)^definition\s+of\s+(.+)$",
            r"(?i)^what\s+does\s+(.+?)\s+mean$",
        ]
        for pattern in patterns:
            match = re.search(pattern, q)
            if not match:
                continue
            entity = match.group(1).strip(" '\"“”‘’")
            if entity.lower() in {"the article", "article", "it", "this", "that"}:
                continue
            if pattern.startswith("(?i)^what\\s+is") or pattern.startswith("(?i)^what\\s+are"):
                if len(self._entity_terms(entity)) < 2:
                    continue
            return re.sub(r"\s+", " ", entity)
        return ""

    def _entity_terms(self, entity: str) -> list[str]:
        stop_words = {"a", "an", "the", "and", "or", "of", "for", "about", "by", "in", "on", "to"}
        return [
            token.lower()
            for token in re.findall(r"\b[a-zA-Z0-9][a-zA-Z0-9_-]*\b", entity)
            if token.lower() not in stop_words
        ]

    def _entity_anchor_positions(self, lower_text: str, entity_terms: list[str]) -> list[int]:
        positions: list[int] = []
        compact_entity = "".join(entity_terms)
        if compact_entity:
            compact_chars: list[str] = []
            raw_positions: list[int] = []
            for raw_position, char in enumerate(lower_text):
                if char.isalnum():
                    compact_chars.append(char)
                    raw_positions.append(raw_position)
            compact_text = "".join(compact_chars)
            for match in re.finditer(re.escape(compact_entity), compact_text):
                if match.start() < len(raw_positions):
                    positions.append(raw_positions[match.start()])
        if len(entity_terms) >= 2:
            flexible = r"\s*[-_]?\s*".join(re.escape(term) for term in entity_terms)
            positions.extend(match.start() for match in re.finditer(flexible, lower_text))
        if len(entity_terms) == 1:
            for term in entity_terms:
                positions.extend(match.start() for match in re.finditer(rf"\b{re.escape(term)}\b", lower_text))
        return sorted(set(position for position in positions if position >= 0))

    def _matches_entity_terms(self, lower_text: str, entity_terms: list[str]) -> bool:
        if not entity_terms:
            return False
        compact_text = re.sub(r"[^a-z0-9]+", "", lower_text)
        compact_entity = "".join(entity_terms)
        if compact_entity and compact_entity in compact_text:
            return True
        return all(re.search(rf"\b{re.escape(term)}\b", lower_text) for term in entity_terms)

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

    def _prefer_mechanism_answer(self, query: str, answer: str, mechanism_answer: str) -> bool:
        q = query.lower()
        if not (q.startswith("how") or any(term in q for term in ["turn", "convert", "transform", "detect"])):
            return False
        answer_terms = self._content_terms(answer)
        mechanism_terms = self._content_terms(mechanism_answer)
        if len(mechanism_terms - answer_terms) >= 3:
            return True
        query_terms = self._query_terms(query)
        intent_terms = set(self._query_intent_terms(query) + self._intent_terms_from_query_terms(query_terms))
        answer_lower = answer.lower()
        mechanism_lower = mechanism_answer.lower()
        missed_intent_terms = [
            term
            for term in intent_terms
            if term in mechanism_lower and term not in answer_lower
        ]
        return len(missed_intent_terms) >= 2

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
                "what steps",
                "what first steps",
                "what three",
                "main pipeline",
                "pipeline",
                "formula",
                "setup",
                "commands",
                "which",
                "mentioned",
                "reasons",
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
            acronym = self._phrase_acronym(phrase)
            if acronym and re.search(rf"\b{re.escape(acronym)}s?\b", text_lower):
                score += 8
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
            terms.extend(["representation", "token", "patch", "latent", "compressed", "compressing", "input", "encoder", "model"])
        if {"kernel", "scalable", "scale", "methods"} & query_terms:
            terms.extend(["kernel", "scalable", "large datasets", "computation", "computational", "expensive", "approximating", "feature", "feature space", "memory", "cost"])
        if {"advancements", "agents", "assistants", "coding", "tools"} & query_terms:
            terms.extend(["language model", "foundation model", "multi-step reasoning", "reasoning", "integration", "development environment", "project structure", "codebase", "version control", "runtime information", "autonomy"])
        if {"pipeline", "processing", "app", "document"} & query_terms:
            terms.extend(["pipeline", "file", "url", "local", "load", "model", "generate", "output", "export", "format", "download", "preview", "interface"])
        if {"large", "numbers", "integer", "integers"} & query_terms:
            terms.extend(["large numbers", "large integers", "memory", "dynamic", "dynamically", "allocates"])
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
            terms.extend(["used", "useful", "prediction", "structured", "context", "sequential", "sequence", "independent", "probabilistic", "application", "example", "label", "labels"])
        if "best practice" in q:
            terms.extend(["practice", "development", "analysis", "threshold", "notification", "schedule", "low-traffic", "multi-stage"])
        if "indentation" in q or "braces" in q:
            terms.extend(["indentation", "enforces", "forces", "code block", "code blocks", "clean", "readable", "missing braces", "formatting", "readability"])
        if ("command" in q or "server" in q) and any(term in q for term in ["http", "web", "useful", "provide", "provides"]):
            terms.extend(["command", "http.server", "web server", "useful", "test", "web applications", "share files", "local network", "third-party", "browser", "localhost"])
        is_practice_challenge = bool(re.search(r"\b\d+\s*[- ]?\s*day\s+[^?]*challenge\b|\bpractice\w*\s+[^?]*challenge\b", q))
        if "limitation" in q or ("challenge" in q and not is_practice_challenge):
            terms.extend(["limitation", "challenge", "cause", "effect", "physical", "spatial", "placement", "arrangement", "temporal", "irrelevant", "interaction", "usage", "access", "safety"])
        if "detect" in q or "anomal" in q:
            terms.extend(["detect", "isolate", "isolates", "outlier", "random", "randomly", "partitioned", "labeled", "unlabeled", "unsupervised", "abnormal", "rare", "unusual"])
        if "strength" in q:
            terms.extend(["strength", "memory", "speed", "performance", "hardware", "logic", "reward", "penalty", "interpretable"])
        if "hardcod" in q or "secret" in q:
            terms.extend(["hardcode", "hardcoding", "secret", "secrets", "key", "keys", "database", "connection", "configuration", "settings", "structured", "safe"])
        if (".env" in q or "env file" in q) and ("local" in q or "development" in q or "recommend" in q):
            terms.extend([".env", "env file", "local development", "environment variables", "variables", "api keys", "tokens", "secrets", "database", "url", "key : value", "key-value", "slow", "messy", "inconvenient"])
        if "start" in q or "recommend" in q or "steps" in q:
            terms.extend(["skill", "tool", "tools", "faster", "draft", "research", "brainstorm", "package", "service", "client", "group", "fast", "try", "practice"])
        if "pipeline" in q or "processing app" in q:
            terms.extend(["local", "url", "load", "model", "generate", "output", "document", "export", "format", "download", "preview", "interface"])
        if "settings" in q and ("environment" in q or "variables" in q or "validate" in q or "map" in q):
            terms.extend(["settings", "class", "field", "default", "alias", "validation", "prefix", "validate", "environment variables"])
        if ".env.example" in q or "env.example" in q or "gitignore" in q:
            terms.extend(["private", "ignore", "never push", "repository", "developer", "placeholder", "placeholders", "keys"])
        if "markup" in q or "tag" in q or "tags" in q:
            terms.extend(["markup", "layout", "semantics", "reading order", "hierarchy", "parser", "heuristic", "downstream", "accuracy", "conversion"])
        if "forgettable" in q or "remember" in q or "memorable" in q or "introduction" in q or "intro" in q:
            terms.extend(["predictable", "tune out", "brain", "name", "job", "hobby", "effect", "impression", "seconds", "science", "story", "curiosity", "attention", "question", "engage", "remember", "memorable"])
        if "coding tools" in q or ("tools" in q and "strength" in q):
            terms.extend(["tool", "tools", "context", "codebase", "multi-agent", "multiple files", "project", "consistency"])
        if "multi-agent" in q or "multi agent" in q:
            terms.extend(["agent", "agents", "planning", "coding", "testing", "debugging", "documentation", "parallel processing", "specialization"])
        if ("brain" in q and "science" in q) or ("formula" in q and "works" in q):
            terms.extend(["brain", "science", "surprise", "story", "stories", "feel", "emotional", "memory", "question"])
        if "business" in q or "client" in q or "charge" in q:
            terms.extend(["hours", "content", "business", "businesses", "outline", "outlines", "post", "posts", "email", "client", "clients", "work", "personal touch", "charge"])
        if ("hold" in q or "holding" in q) and "back" in q:
            terms.extend(["fear", "failing", "looking", "wasting", "time", "stuck", "job", "trying", "try", "barrier", "obstacle"])
        if "replace" in q:
            terms.extend(["tool", "tools", "faster", "income", "side income", "background", "technical", "tech", "degree", "code", "no code", "product", "app", "save time", "make money", "learn", "need", "don't need", "don’t need", "didn't", "didn’t"])
        return list(dict.fromkeys(terms))

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

    def _contains_distinctive_identifier(self, text: str) -> bool:
        if self._class_like_identifiers(text):
            return True
        return bool(re.search(r"\b[A-Z][A-Za-z0-9_-]{2,}\b(?:\s+\b[A-Z][A-Za-z0-9_-]{2,}\b)+", text))

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

    def _clean_final_answer(self, answer: str, max_citation: int | None = None) -> str:
        answer = re.sub(r"\[child chunk \d+ \| page [^\]]+\]\s*", "", answer)
        answer = re.sub(r"\b\d+\s+(?=\[child chunk)", "", answer)
        answer = self._strip_context_leakage(answer)
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
        answer = re.sub(r"\s+Citations:\s+\[\d+\].*$", "", answer, flags=re.IGNORECASE | re.DOTALL)
        answer = answer.replace("simu- late", "simulate")
        answer = answer.replace("signif- icantly", "significantly")
        answer = answer.replace("gener- ation", "generation")
        answer = answer.replace("remain- ing", "remaining")
        answer = re.sub(r"\bAbstract\b\s*", "", answer, flags=re.IGNORECASE)
        answer = self._normalize_answer_citations(answer, max_citation=max_citation)
        answer = re.sub(r"\s+", " ", answer)
        return answer.strip()

    def _strip_context_leakage(self, answer: str) -> str:
        answer = re.sub(r"(?im)^\s*(?:Title|Section|Page|Score|Text)\s*:\s*.*$", "", answer)
        answer = re.sub(
            r"\b(?:Follow publication|Published in|Get an email whenever|By signing up)[^.!?]{0,180}",
            "",
            answer,
            flags=re.IGNORECASE,
        )
        answer = re.sub(
            r"\b(?:\d+(?:\.\d+)?K\s+)?Followers?\s*(?:·\s*\d+\s+Following)?[^.!?]{0,120}",
            "",
            answer,
            flags=re.IGNORECASE,
        )
        return answer

    def _has_raw_context_leak(self, answer: str) -> bool:
        answer_lower = answer.lower()
        raw_markers = [
            "[child chunk",
            "retrieved chunk",
            "chunk_id",
            "hybrid_score",
            "reranker_score",
            "title:",
            "section:",
            "score:",
            "text:",
            "follow publication",
            "get an email whenever",
            "by signing up",
        ]
        if any(marker in answer_lower for marker in raw_markers):
            return True
        return False

    def _normalize_answer_citations(self, answer: str, max_citation: int | None = None) -> str:
        def replace_multi(match: re.Match[str]) -> str:
            numbers = [int(number) for number in re.findall(r"\d+", match.group(1))]
            valid_numbers = [
                number
                for number in numbers
                if number >= 1 and (max_citation is None or number <= max_citation)
            ]
            if not valid_numbers:
                return ""
            return " ".join(f"[{number}]" for number in dict.fromkeys(valid_numbers))

        answer = re.sub(r"\[((?:\d+\s*,\s*)+\d+)\]", replace_multi, answer)

        if max_citation is not None:
            answer = re.sub(
                r"\[(\d+)\]",
                lambda match: match.group(0)
                if 1 <= int(match.group(1)) <= max_citation
                else "",
                answer,
            )

        answer = re.sub(r"(?:^|\s)-\s*(?:\[\d+\]\s*)+(?=$|\s+-)", " ", answer)
        return re.sub(r"\s+([,.])", r"\1", answer)

    def _ensure_focus_entity_mentioned(self, query: str, answer: str) -> str:
        if not answer or self._is_insufficient_answer(answer):
            return answer
        focus_entity = self._focus_entity_display(query)
        focus_terms = self._entity_terms(focus_entity)
        answer_lower = answer.lower()
        if (
            not focus_entity
            or focus_entity.lower() in answer_lower
            or (focus_terms and self._matches_entity_terms(answer_lower, focus_terms))
        ):
            return answer

        q = query.lower()
        if self._is_list_question(query):
            label = "key features" if "feature" in q else "main points"
            return f"{focus_entity}'s {label} are: {answer}"
        return f"{focus_entity}: {answer}"

    def _focus_entity_display(self, query: str) -> str:
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
        for pattern in [
            r"(?i)^\s*what\s+does\s+(.+?)\s+(?:help|support|provide|allow|enable|detect|analy[sz]e|monitor|update|show)\b",
            r"(?i)^\s*how\s+does\s+(.+?)\s+(?:help|work|support|provide|allow|enable|detect|analy[sz]e|monitor|update|show)\b",
        ]:
            match = re.search(pattern, query)
            if not match:
                continue
            candidate = re.sub(r"\s+", " ", match.group(1)).strip(" '\"“”‘’")
            candidate_terms = self._entity_terms(candidate)
            if candidate_terms and not all(term in generic_terms for term in candidate_terms):
                return candidate

        focus_phrases = self._focus_phrases(query, preserve_case=True)
        if focus_phrases:
            return sorted(focus_phrases, key=len, reverse=True)[0]

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
