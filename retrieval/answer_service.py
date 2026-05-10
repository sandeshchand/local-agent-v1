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
1. Use only the provided context and evidence facts.
2. If the context supports only part of the answer, answer the supported part and do not fully abstain.
3. If no relevant evidence exists, say exactly:
   "The provided context does not contain enough information."
4. Preserve uncertainty from the source, such as "may", "likely", "speculates", or "reverse-engineered".
5. Cover all distinct relevant facts, not only the first fact.
6. Cite each sentence or bullet using citation markers like [1], [2].
7. Do not add unsupported background or outside knowledge.
8. Preserve important source terminology exactly when it appears in the context, including model names,
   dates, method names, numbered components, limitation names, and technical phrases.
9. If the context contains a numbered list or explicit categories/components, include all relevant items.

Answer shape:
{answer_shape}

Generic facet checklist:
{self._generic_facet_checklist(query)}

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
        if self._looks_under_specific(answer, results):
            return self._generic_extractive_fallback(query, results)
        if self._is_insufficient_answer(answer):
            return self._generic_extractive_fallback(query, results)

        return answer

    def _extract_evidence_facts_with_llm(self, query: str, context: str) -> str:
        prompt = f"""
Extract source-faithful answer facts from the retrieved context.

Rules:
- Use only the context.
- Preserve exact terminology, names, dates, method names, numbered components, and limitation names.
- Extract all distinct facts that help answer the question.
- Keep citation markers by citing each fact with [1], [2], etc. from the context.
- Do not summarize away technical terms.
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
        seen: set[str] = set()

        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            if not text:
                continue

            sentences = self._split_sentences(text)
            scored_sentences: list[tuple[int, str]] = []
            if index <= 4:
                for sentence in sentences[:5]:
                    if self._is_high_signal_sentence(sentence):
                        scored_sentences.append((7, sentence))
            for sentence in sentences:
                score = self._sentence_relevance_score(sentence, query_terms)
                if score > 0:
                    scored_sentences.append((score, sentence))
            for sentence in sentences[:2]:
                if self._is_high_signal_sentence(sentence):
                    scored_sentences.append((6, sentence))

            scored_sentences.sort(key=lambda pair: pair[0], reverse=True)
            for _, sentence in scored_sentences[:5]:
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
            return " ".join(clean_facts)

        return " ".join(clean_facts[:4])

    def _looks_under_specific(self, answer: str, results: list[dict]) -> bool:
        answer_lower = answer.lower()
        evidence_text = " ".join((item.get("text") or "") for item in results)
        source_terms = self._source_specific_terms(evidence_text)
        if len(source_terms) < 4:
            return False
        matched = sum(1 for term in source_terms if term.lower() in answer_lower)
        return matched < max(2, len(source_terms) // 5)

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

    def _generic_facet_checklist(self, query: str) -> str:
        q = query.lower()
        facets: list[str] = []
        if q.startswith("what is") or "definition" in q:
            facets.extend(["definition/category", "creator/source/date if present", "main capability", "important scope or limit"])
        if "architecture" in q or "components" in q or "core model" in q:
            facets.extend(["core architecture name", "all listed components/parts", "conditioning/input mechanism if present"])
        if q.startswith("how"):
            facets.extend(["ordered steps", "mechanisms/methods", "inputs and outputs", "important caveats"])
        if q.startswith("why"):
            facets.extend(["main reason", "technical challenge", "benefits/consequences", "comparison if present"])
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
        if any(marker in sentence_lower for marker in ["first", "second", "third", "finally", "include", "includes", "consists", "composed", "such as", "it has three parts", "(1)", "(2)", "(3)"]):
            score += 1
        if any(marker in sentence_lower for marker in ["limitation", "challenge", "benefit", "approach", "method", "architecture", "prompt", "compression", "released", "model", "called", "known as"]):
            score += 1
        return score

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
            "review",
            "paper",
            "document",
            "discuss",
            "describe",
            "say",
            "use",
            "uses",
        }
        return {
            token
            for token in re.findall(r"\b[a-zA-Z][a-zA-Z0-9\-]{2,}\b", query.lower())
            if token not in stop_words
        }

    def _split_sentences(self, text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        parts = re.split(r"(?<=[.!?])\s+", normalized)
        return [part.strip() for part in parts if len(part.strip()) > 40]

    def _clean_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

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
