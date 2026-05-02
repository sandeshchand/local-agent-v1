from __future__ import annotations

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

        return f"""
        You are a precise and grounded AI assistant.

        Your task is to answer the user's question using ONLY the approved evidence context.

        Rules:
        1. Answer the exact question directly.
        2. Use ONLY the approved evidence context.
        3. Do not add unrelated background.
        4. Do not invent facts or fill gaps with outside knowledge.
        5. If the approved context contains multiple claims about the same topic, distinguish between:
        - core/main answer
        - supporting detail
        - speculative or secondary interpretation
        6. Prefer definitive statements over speculative statements.
        7. Do not present speculative phrases such as "we speculate", "may", "might", or "likely" as confirmed facts.
        8. If the approved context does not directly answer the question, respond exactly:
        "The retrieved context does not directly answer this."
        9. Use citation markers like [1], [2] only for statements supported by the approved context.
        10. Keep the answer concise.

        {memory_context}

        [APPROVED EVIDENCE CONTEXT]
        {context}

        [TOOL RESULTS]
        {tool_context}

        Question:
        {query}

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
    - Prefer definitive statements over speculative statements. Do not treat speculative phrases such as 
    "we speculate", "may", "likely", or "reverse engineering" as confirmed facts.

    {memory_context}

    [TOOL OUTPUT]
    {tool_context}

    Question:
    {query}

    Answer:
    """.strip()

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

        return "I’m here and ready to help. Could you rephrase your question?"

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
            return "The retrieved context does not directly answer this."

        return answer

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