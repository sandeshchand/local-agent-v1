from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from local_agent.llm import OllamaChatClient
from local_agent.answering.cleaning import AnswerCleaningMixin
from local_agent.answering.evidence_facts import EvidenceFactMixin
from local_agent.answering.extractors import ExtractiveAnswerMixin
from local_agent.answering.prompts import AnswerPromptMixin
from local_agent.answering.query_intent import QueryIntentMixin
from local_agent.answering.source_windows import SourceWindowMixin
from local_agent.answering.tool_outputs import ToolOutputMixin
from local_agent.retrieval.context_builder import build_context


@dataclass(frozen=True)
class AnswerGenerationResult:
    answer: str
    trace: dict[str, Any]


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
        return self.answer_from_context_result(
            query=query,
            results=results,
            memory_context=memory_context,
            tool_context=tool_context,
        ).answer

    def answer_from_context_result(
        self,
        query: str,
        results: list[dict],
        memory_context: str = "",
        tool_context: str = "",
    ) -> AnswerGenerationResult:
        results = self._single_source_results(query, results)
        fast_answer, fast_trace = self._extractive_fast_path_answer_with_trace(
            query=query,
            results=results,
            memory_context=memory_context,
            tool_context=tool_context,
        )
        trace: dict[str, Any] = {
            "path": "extractive_fast_path" if fast_answer else "llm_generation",
            "used_answer_fast_path": bool(fast_answer),
            "used_llm_generation": False,
            "fast_path": fast_trace,
        }

        def done(answer: str, source: str) -> AnswerGenerationResult:
            result_trace = dict(trace)
            result_trace["final_answer_source"] = source
            if source != "llm_generation":
                result_trace["path"] = source
            return AnswerGenerationResult(answer=answer, trace=result_trace)

        if fast_answer:
            return done(fast_answer, "extractive_fast_path")

        prompt = self.build_retrieval_prompt(
            query=query,
            results=results,
            memory_context=memory_context,
            tool_context=tool_context,
        )
        try:
            answer = self.chat_client.generate(prompt).strip()
            trace["used_llm_generation"] = True
        except Exception:
            fallback = self._deterministic_repair_answer(query, results)
            trace["fallback_reason"] = "llm_generation_exception"
            if fallback:
                return done(fallback, "deterministic_repair_fallback")
            return done(self._generic_extractive_fallback(query, results), "generic_extractive_fallback")

        if not answer:
            trace["fallback_reason"] = "empty_llm_answer"
            return done(self._generic_extractive_fallback(query, results), "generic_extractive_fallback")

        answer = self._remove_mixed_abstention(answer)
        answer = self._focused_rewrite(query, answer, results)
        answer_source = "llm_generation"

        # Candidate priority matters: specific extractors run before broad list
        # extraction so a feature, limitation, pipeline, or command answer is not
        # overwritten by a generic summary.
        best_practices_answer = self._best_practices_extractive_answer(query, results)
        if best_practices_answer:
            answer = best_practices_answer
            answer_source = "best_practices_extractive_replacement"
        capability_answer = ""
        if self._should_use_capability_extractive_answer(query, results):
            capability_answer = self._capability_extractive_answer(query, results)
            if capability_answer:
                answer = capability_answer
                answer_source = "capability_extractive_replacement"
        limitation_answer = self._limitation_extractive_answer(query, results)
        if limitation_answer:
            answer = limitation_answer
            answer_source = "limitation_extractive_replacement"
        definition_answer = self._definition_extractive_answer(query, results)
        if definition_answer:
            answer = definition_answer
            answer_source = "definition_extractive_replacement"
        used_for_answer = self._used_for_extractive_answer(query, results)
        if used_for_answer:
            answer = used_for_answer
            answer_source = "used_for_extractive_replacement"
        config_file_answer = self._config_file_purpose_answer(query, results)
        if config_file_answer:
            answer = config_file_answer
            answer_source = "config_file_extractive_replacement"
        meaning_answer = self._meaning_extractive_answer(query, results)
        if meaning_answer:
            answer = meaning_answer
            answer_source = "meaning_extractive_replacement"
        pipeline_answer = self._pipeline_extractive_answer(query, results)
        if pipeline_answer:
            answer = pipeline_answer
            answer_source = "pipeline_extractive_replacement"
        challenge_answer = self._challenge_steps_answer(query, results)
        if challenge_answer:
            answer = challenge_answer
            answer_source = "challenge_extractive_replacement"
        command_answer = self._command_usefulness_answer(query, results)
        if command_answer:
            answer = command_answer
            answer_source = "command_extractive_replacement"
        example_answer = self._example_extractive_answer(query, results)
        if example_answer and (
            "example" in query.lower()
            or self._looks_unfocused(query, answer)
            or len(self._content_terms(example_answer) - self._content_terms(answer)) >= 3
        ):
            answer = example_answer
            answer_source = "example_extractive_replacement"
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
            answer_source = "why_extractive_replacement"
        list_answer = self._list_extractive_answer(query, results)
        if list_answer and not best_practices_answer and not limitation_answer and not used_for_answer and not config_file_answer and not meaning_answer and not challenge_answer and not command_answer and (
            self._is_list_question(query)
            or self._looks_unfocused(query, answer)
            or self._misses_intent_shape(query, answer)
            or self._prefer_mechanism_answer(query, answer, list_answer)
        ):
            answer = list_answer
            answer_source = "list_extractive_replacement"
        mechanism_answer = self._mechanism_extractive_answer(query, results)
        if mechanism_answer and (
            self._misses_intent_shape(query, answer)
            or self._looks_under_specific(answer, results)
            or self._prefer_mechanism_answer(query, answer, mechanism_answer)
        ):
            answer = mechanism_answer
            answer_source = "mechanism_extractive_replacement"
        focused_entity_answer = self._focused_entity_extractive_answer(query, results)
        if focused_entity_answer and (
            self._looks_unfocused(query, answer)
            or self._misses_intent_shape(query, answer)
            or self._answer_misses_focus_phrase(query, answer)
            or self._prefer_focused_entity_answer(query, answer, focused_entity_answer)
        ):
            answer = focused_entity_answer
            answer_source = "focused_entity_extractive_replacement"
        source_window_answer = self._source_window_answer(query, results)
        if source_window_answer and self._should_prefer_source_window_answer(query, answer, source_window_answer):
            answer = source_window_answer
            answer_source = "source_window_extractive_replacement"

        def final_answer(candidate: str) -> str:
            candidate = self._augment_feature_answer_with_intro(query, candidate, results)
            return self._clean_final_answer(candidate, max_citation=len(results))

        if self._looks_under_specific(answer, results) or self._looks_unfocused(query, answer) or self._misses_intent_shape(query, answer):
            trace["fallback_reason"] = "llm_answer_unfocused_or_under_specific"
            if capability_answer:
                return done(final_answer(capability_answer), "capability_extractive_replacement")
            if why_answer:
                return done(final_answer(why_answer), "why_extractive_replacement")
            if definition_answer:
                return done(final_answer(definition_answer), "definition_extractive_replacement")
            if used_for_answer:
                return done(final_answer(used_for_answer), "used_for_extractive_replacement")
            if config_file_answer:
                return done(final_answer(config_file_answer), "config_file_extractive_replacement")
            if meaning_answer:
                return done(final_answer(meaning_answer), "meaning_extractive_replacement")
            if pipeline_answer:
                return done(final_answer(pipeline_answer), "pipeline_extractive_replacement")
            if challenge_answer:
                return done(final_answer(challenge_answer), "challenge_extractive_replacement")
            if command_answer:
                return done(final_answer(command_answer), "command_extractive_replacement")
            if example_answer:
                return done(final_answer(example_answer), "example_extractive_replacement")
            if source_window_answer:
                return done(final_answer(source_window_answer), "source_window_extractive_replacement")
            if list_answer:
                return done(final_answer(list_answer), "list_extractive_replacement")
            if mechanism_answer:
                return done(final_answer(mechanism_answer), "mechanism_extractive_replacement")
            if focused_entity_answer:
                return done(final_answer(focused_entity_answer), "focused_entity_extractive_replacement")
            if best_practices_answer:
                return done(final_answer(best_practices_answer), "best_practices_extractive_replacement")
            if limitation_answer:
                return done(final_answer(limitation_answer), "limitation_extractive_replacement")
            return done(self._generic_extractive_fallback(query, results), "generic_extractive_fallback")
        if self._is_insufficient_answer(answer):
            trace["fallback_reason"] = "insufficient_llm_answer"
            return done(self._generic_extractive_fallback(query, results), "generic_extractive_fallback")
        answer = self._augment_feature_answer_with_intro(query, answer, results)
        if results and not re.search(r"\[\d+\]", answer):
            trace["fallback_reason"] = "missing_citations"
            if best_practices_answer:
                return done(
                    self._clean_final_answer(best_practices_answer, max_citation=len(results)),
                    "best_practices_extractive_replacement",
                )
            return done(self._generic_extractive_fallback(query, results), "generic_extractive_fallback")

        return done(
            self._ensure_focus_entity_mentioned(
                query,
                self._clean_final_answer(answer, max_citation=len(results)),
            ),
            answer_source,
        )

    def _extractive_fast_path_answer(
        self,
        query: str,
        results: list[dict],
        memory_context: str = "",
        tool_context: str = "",
    ) -> str:
        answer, _ = self._extractive_fast_path_answer_with_trace(
            query=query,
            results=results,
            memory_context=memory_context,
            tool_context=tool_context,
        )
        return answer

    def _extractive_fast_path_answer_with_trace(
        self,
        query: str,
        results: list[dict],
        memory_context: str = "",
        tool_context: str = "",
    ) -> tuple[str, dict[str, Any]]:
        trace: dict[str, Any] = {
            "eligible": False,
            "used": False,
            "reason": "",
            "candidate_count": 0,
            "accepted_candidate_source": "",
            "accepted_candidate_index": None,
            "memory_context_present": bool(memory_context.strip()),
            "rejections": [],
        }

        if not results:
            trace["reason"] = "no_results"
            return "", trace
        if tool_context.strip():
            trace["reason"] = "tool_context_present"
            return "", trace
        if not self._is_extractively_answerable_query(query):
            trace["reason"] = "unsupported_query_shape"
            return "", trace

        trace["eligible"] = True
        candidates = self._extractive_fast_path_candidates(query, results)
        trace["candidate_count"] = len(candidates)

        for index, (source, candidate) in enumerate(candidates, start=1):
            candidate = self._finalize_extractive_candidate(query, candidate, results)
            rejection_reason = self._high_confidence_extractive_rejection_reason(
                query=query,
                candidate=candidate,
                results=results,
            )
            if not rejection_reason:
                trace["used"] = True
                trace["reason"] = "accepted_high_confidence_candidate"
                trace["accepted_candidate_source"] = source
                trace["accepted_candidate_index"] = index
                return candidate, trace
            if len(trace["rejections"]) < 8:
                trace["rejections"].append(
                    {
                        "candidate_source": source,
                        "reason": rejection_reason,
                    }
                )

        trace["reason"] = "no_high_confidence_candidate"
        return "", trace

    def _is_extractively_answerable_query(self, query: str) -> bool:
        q = query.lower()
        return bool(
            self._definition_query_entity(query)
            or self._is_list_question(query)
            or self._is_explanation_question(query)
            or q.startswith("how")
            or any(
                term in q
                for term in [
                    "feature",
                    "features",
                    "capability",
                    "capabilities",
                    "limitation",
                    "limitations",
                    "weakness",
                    "used for",
                    "useful",
                    "mean by",
                    "pipeline",
                    "formula",
                    "example",
                    "role",
                    "roles",
                    "component",
                    "components",
                    "setup",
                    "commands",
                    "reason",
                    "main message",
                    "simulator",
                    "simulation",
                    "simulate",
                ]
            )
        )

    def _extractive_fast_path_candidates(self, query: str, results: list[dict]) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []

        def add(source: str, candidate: str) -> None:
            if candidate:
                candidates.append((source, candidate))

        source_window_answer = self._source_window_answer(query, results)
        add("source_window", source_window_answer)

        best_practices_answer = self._best_practices_extractive_answer(query, results)
        add("best_practices", best_practices_answer)

        if self._should_use_capability_extractive_answer(query, results):
            capability_answer = self._capability_extractive_answer(query, results)
            add("capability", capability_answer)

        for source, builder in [
            ("limitation", self._limitation_extractive_answer),
            ("definition", self._definition_extractive_answer),
            ("used_for", self._used_for_extractive_answer),
            ("config_file", self._config_file_purpose_answer),
            ("meaning", self._meaning_extractive_answer),
            ("pipeline", self._pipeline_extractive_answer),
            ("challenge", self._challenge_steps_answer),
            ("command", self._command_usefulness_answer),
            ("example", self._example_extractive_answer),
            ("why", self._why_extractive_answer),
            ("list", self._list_extractive_answer),
            ("mechanism", self._mechanism_extractive_answer),
            ("focused_entity", self._focused_entity_extractive_answer),
        ]:
            add(source, builder(query, results))
        return candidates

    def _finalize_extractive_candidate(self, query: str, candidate: str, results: list[dict]) -> str:
        if not candidate:
            return ""
        candidate = self._augment_feature_answer_with_intro(query, candidate, results)
        candidate = self._clean_final_answer(candidate, max_citation=len(results))
        return self._ensure_focus_entity_mentioned(query, candidate)

    def _is_high_confidence_extractive_answer(
        self,
        query: str,
        candidate: str,
        results: list[dict],
    ) -> bool:
        return not self._high_confidence_extractive_rejection_reason(
            query=query,
            candidate=candidate,
            results=results,
        )

    def _high_confidence_extractive_rejection_reason(
        self,
        query: str,
        candidate: str,
        results: list[dict],
    ) -> str:
        if not candidate:
            return "empty_candidate"
        if self._is_insufficient_answer(candidate):
            return "insufficient_candidate"
        if self._has_raw_context_leak(candidate):
            return "raw_context_leak"
        if self._contains_unrequested_code(candidate, query):
            return "unrequested_code"
        if self._is_practice_challenge_query(query) and not self._has_practice_challenge_coverage(candidate):
            return "practice_challenge_coverage_missing"
        if self._looks_unfocused(query, candidate):
            return "unfocused_candidate"
        if self._misses_intent_shape(query, candidate):
            return "intent_shape_missing"
        if self._answer_misses_focus_phrase(query, candidate):
            return "focus_phrase_missing"
        if self._has_competing_focus_topic(query, candidate):
            return "competing_named_topic"
        citation_numbers = [int(match) for match in re.findall(r"\[(\d+)\]", candidate)]
        if not citation_numbers:
            return "missing_citation"
        if any(number < 1 or number > len(results) for number in citation_numbers):
            return "invalid_citation"

        is_command_query = self._is_command_or_server_query(query)
        if is_command_query and not self._has_command_answer_coverage(candidate):
            return "command_coverage_missing"
        if not is_command_query and self._has_low_value_candidate_items(candidate):
            return "low_value_candidate_items"
        is_definition_query = bool(self._definition_query_entity(query))
        if is_definition_query and not self._has_definition_answer_coverage(query, candidate):
            return "definition_coverage_missing"
        has_large_number_coverage = self._has_large_number_answer_coverage(query, candidate)
        has_formula_coverage = self._has_formula_answer_coverage(query, candidate)
        has_pipeline_coverage = self._has_pipeline_answer_coverage(query, candidate)

        candidate_lower = candidate.lower()
        query_terms = self._query_terms(query)
        distinctive_query_terms = {
            term
            for term in query_terms
            if len(term) >= 4 and term not in {"document", "article", "paper"}
        }
        if distinctive_query_terms and not any(term in candidate_lower for term in distinctive_query_terms):
            focus_phrases = self._focus_phrases(query)
            if not focus_phrases or self._focus_phrase_score(candidate, focus_phrases) == 0:
                return "distinctive_query_terms_missing"

        if self._looks_under_specific(candidate, results) and not (
            is_command_query
            or is_definition_query
            or has_large_number_coverage
            or has_formula_coverage
            or has_pipeline_coverage
        ):
            return "under_specific_candidate"

        word_count = len(re.findall(r"\b\w+\b", candidate))
        if is_definition_query:
            if 8 <= word_count <= 95:
                return ""
            return "definition_length_out_of_bounds"
        if self._is_list_question(query):
            if len(citation_numbers) >= 1 and word_count >= 14:
                return ""
            return "list_answer_too_short"
        if self._is_explanation_question(query) or query.lower().startswith("how"):
            if word_count >= 18:
                return ""
            return "explanation_answer_too_short"
        if word_count >= 8:
            return ""
        return "answer_too_short"

    def _has_competing_focus_topic(self, query: str, candidate: str) -> bool:
        q = query.lower()
        if not any(
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
        ):
            return False
        focus_phrases = set(self._focus_phrases(query))
        focus_entity = self._focus_entity_display(query)
        if focus_entity:
            focus_phrases.add(focus_entity.lower())
        if not focus_phrases:
            return False
        return self._mentions_competing_named_topic(candidate, focus_phrases)

    def _contains_unrequested_code(self, candidate: str, query: str) -> bool:
        if self._should_keep_code_fact(query, candidate):
            return False
        for sentence in self._split_sentences(candidate):
            if self._looks_like_code_or_metadata_fact(sentence) and not self._should_keep_code_fact(query, sentence):
                return True
        code_markers = [
            "import ",
            "plt.",
            "np.",
            "sklearn",
            "random_state",
            "fit_predict",
            "xlabel",
            "ylabel",
            "show()",
        ]
        candidate_lower = candidate.lower()
        return sum(1 for marker in code_markers if marker in candidate_lower) >= 2

    def _has_low_value_candidate_items(self, candidate: str) -> bool:
        parts = re.split(r"\s+-\s+", candidate)
        if len(parts) <= 1:
            return False
        low_value_markers = [
            "follow publication",
            "published in",
            "followers",
            "clap",
            "comment below",
            "share this",
            "subscribe",
            "thanks for reading",
        ]
        for raw_part in parts[1:]:
            item = re.sub(r"\[\d+\]", "", raw_part)
            item = re.sub(r"\s+", " ", item).strip(" .:-")
            if not item:
                return True
            item_lower = item.lower()
            if any(marker in item_lower for marker in low_value_markers):
                return True
            if self._has_article_metadata_separator(item) or "!!" in item:
                return True
            answer_markers = [
                " is ",
                " are ",
                "used",
                "useful",
                "feature",
                "strength",
                "because",
                "allows",
                "helps",
                "supports",
                "enables",
                "detect",
                "monitor",
                "update",
                "load",
                "generate",
                "create",
                "export",
                "render",
                "download",
                "preview",
                "process",
                "input",
                "output",
                "convert",
                "model",
                "document",
            ]
            if len(item.split()) < 6 and not any(marker in item_lower for marker in answer_markers):
                return True
            if self._is_low_value_fact(item):
                return True
        return False

    def _has_article_metadata_separator(self, item: str) -> bool:
        if "\u00b7" not in item and "\u00c2\u00b7" not in item:
            return False
        item_lower = item.lower()
        metadata_markers = [
            "followers",
            "published",
            "publication",
            "min read",
            "read more",
            "clap",
        ]
        return any(marker in item_lower for marker in metadata_markers) or bool(
            re.search(r"\b\d+(?:\.\d+)?k?\s+following\b", item_lower)
        )

    def _has_definition_answer_coverage(self, query: str, candidate: str) -> bool:
        entity = self._definition_query_entity(query)
        entity_terms = self._entity_terms(entity)
        candidate_lower = candidate.lower()
        relation_markers = [
            " is ",
            " are ",
            "refers to",
            "means",
            "called",
            "known as",
        ]
        return (
            bool(entity_terms)
            and self._matches_entity_terms(candidate_lower, entity_terms)
            and any(marker in candidate_lower for marker in relation_markers)
        )

    def _has_large_number_answer_coverage(self, query: str, candidate: str) -> bool:
        query_lower = query.lower()
        if not (
            ("large" in query_lower and ("number" in query_lower or "integer" in query_lower))
            or "very large" in query_lower
            or "big number" in query_lower
        ):
            return False

        candidate_lower = candidate.lower()
        coverage_groups = [
            ["large integer", "large number", "big number", "very large"],
            ["automatically manages", "automatically handle", "handles automatically"],
            ["special data type", "int or long", "separate int", "separate long"],
            ["dynamic memory", "dynamically allocates", "allocates memory"],
            ["10**", "100 digits", "digits"],
            ["use numbers normally", "numbers normally"],
        ]
        matched_groups = sum(
            1
            for markers in coverage_groups
            if any(marker in candidate_lower for marker in markers)
        )
        return matched_groups >= 4

    def _has_formula_answer_coverage(self, query: str, candidate: str) -> bool:
        query_lower = query.lower()
        if not any(phrase in query_lower for phrase in ["formula", "part formula", "three-part", "three part"]):
            return False

        candidate_lower = candidate.lower()
        has_formula_frame = "formula" in candidate_lower or re.search(r"\b\d{1,2}\.\s+\w+", candidate)
        component_markers = [
            "hook",
            "highlight",
            "handoff",
            "part",
            "step",
            "component",
            "framework",
        ]
        marker_hits = sum(1 for marker in component_markers if marker in candidate_lower)
        numbered_parts = len(re.findall(r"\b\d{1,2}\.\s+", candidate))
        return has_formula_frame and (marker_hits >= 2 or numbered_parts >= 2)

    def _has_pipeline_answer_coverage(self, query: str, candidate: str) -> bool:
        query_lower = query.lower()
        if not any(phrase in query_lower for phrase in ["pipeline", "workflow", "processing app", "app flow"]):
            return False

        candidate_lower = candidate.lower()
        coverage_groups = [
            ["pdf", "image", "file", "url", "upload", "input"],
            ["load", "model"],
            ["generate", "process", "output", "doctags", "markup"],
            ["document", "doclingdocument", "doctagsdocument"],
            ["markdown", "html", "json", "export", "format"],
            ["preview", "download", "ui", "interface", "gradio"],
        ]
        matched_groups = sum(
            1
            for markers in coverage_groups
            if any(marker in candidate_lower for marker in markers)
        )
        return matched_groups >= 4

    def _is_command_or_server_query(self, query: str) -> bool:
        q = query.lower()
        command_patterns = [
            r"\bcommands?\b",
            r"\bsetup\b",
            r"\binstall(?:ation)?\b",
            r"\brun(?:ning)?\b",
            r"\bserver\b",
            r"\bhow\s+(?:do|can|to)\s+(?:i\s+)?(?:start|run|install|set\s+up)\b",
            r"\bstart(?:s|ed|ing)?\s+(?:the\s+)?(?:server|app|application|container|service|tool)\b",
        ]
        return any(re.search(pattern, q) for pattern in command_patterns)

    def _has_command_answer_coverage(self, candidate: str) -> bool:
        candidate_lower = candidate.lower()
        has_command = bool(
            re.search(
                r"\b(?:python\s+-m\s+[-\w.]+(?:\s+\d+)?|docker\s+run\b|pip\s+install\b|uv\s+run\b|npm\s+install\b|brew\s+install\b)",
                candidate,
                flags=re.IGNORECASE,
            )
        )
        utility_markers = [
            "useful",
            "test",
            "web application",
            "web server",
            "http server",
            "share",
            "local network",
            "browser",
            "localhost",
        ]
        return has_command and sum(1 for marker in utility_markers if marker in candidate_lower) >= 2
    def _is_practice_challenge_query(self, query: str) -> bool:
        return bool(
            re.search(
                r"\b\d+\s*[- ]?\s*day\s+[^?]*challenge\b|\bpractice\w*\s+[^?]*challenge\b",
                query.lower(),
            )
        )
    def _has_practice_challenge_coverage(self, candidate: str) -> bool:
        candidate_lower = candidate.lower()
        has_day_steps = bool(re.search(r"\bday(?:s)?\s+\d", candidate_lower))
        practice_markers = [
            "practice",
            "mirror",
            "friend",
            "feedback",
            "real life",
        ]
        marker_hits = sum(1 for marker in practice_markers if marker in candidate_lower)
        return has_day_steps and marker_hits >= 2
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
