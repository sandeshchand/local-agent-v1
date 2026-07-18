from __future__ import annotations

import re

from local_agent.retrieval.context_builder import build_context


class AnswerPromptMixin:
    def build_retrieval_prompt(
        self,
        query: str,
        results: list[dict],
        memory_context: str = "",
        tool_context: str = "",
    ) -> str:
        context = build_context(results, max_chars_per_chunk=1400)
        evidence_facts = self._build_evidence_fact_list(query, results)
        if self._facts_need_llm_help(evidence_facts):
            llm_facts = self._extract_evidence_facts_with_llm(query, context)
            if not self._facts_need_llm_help(llm_facts):
                evidence_facts = llm_facts
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
    def _facts_need_llm_help(self, evidence_facts: str) -> bool:
        normalized = evidence_facts.strip().lower()
        return (
            not normalized
            or "no directly matching facts" in normalized
            or self._is_insufficient_answer(evidence_facts)
        )
