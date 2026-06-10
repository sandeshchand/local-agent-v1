from __future__ import annotations

import re

from local_agent.llm import OllamaChatClient
from local_agent.answering.cleaning import AnswerCleaningMixin
from local_agent.answering.evidence_facts import EvidenceFactMixin
from local_agent.answering.extractors import ExtractiveAnswerMixin
from local_agent.answering.prompts import AnswerPromptMixin
from local_agent.answering.query_intent import QueryIntentMixin
from local_agent.answering.source_windows import SourceWindowMixin
from local_agent.answering.tool_outputs import ToolOutputMixin
from local_agent.retrieval.context_builder import build_context


class AnswerService(
    AnswerPromptMixin,
    ToolOutputMixin,
    SourceWindowMixin,
    EvidenceFactMixin,
    ExtractiveAnswerMixin,
    QueryIntentMixin,
    AnswerCleaningMixin,
):
    """Build final RAG, direct, and tool answers from evidence."""

    def __init__(self, chat_client: OllamaChatClient) -> None:
        self.chat_client = chat_client
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
