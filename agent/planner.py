from __future__ import annotations

import json
import re

from agent.schemas import PlanDecision
from app.ollama_client import OllamaChatClient, OllamaError


class Planner:
    def __init__(self, chat_client: OllamaChatClient) -> None:
        self.chat_client = chat_client

    def plan(self, query: str) -> PlanDecision:
        prompt = self._build_prompt(query)

        try:
            raw = self.chat_client.generate(prompt)
            return self._parse_plan(raw, original_query=query)
        except Exception:
            return self._fallback_plan(query)

    def _build_prompt(self, query: str) -> str:
        return f"""
        You are a planner for a local PDF assistant.

        Your job is to decide how the assistant should respond.

        Available modes:
        - direct_answer: use general_reasoning or normal conversation without document retrieval.
        - retrieve_only: search indexed PDFs first, then answer from retrieved context.
        - tool_only: reserved for future tool-use scenarios.
        - retrieve_then_tool: reserved for future retrieve + tool flow.

        Important:
        - In this current build, prefer only:
            - direct answer
            -retrieve only
        -Use direct answer only for
            - greetings
            - casual conversation
            - simple non-document help
            - thanks / follow-up social messages
        -Use retrieve_onle for:
            - questions about indexed PDFs
            - factual/document-grounded queries
            - questions likely answered from stored documents
            - any technical or knowledge question when unsure
        
        Return JSON only
        no markdown.
        no explanation outside JSON.

        JSON format:
        {{
            "mode": "direct_answer" | "retrieve_only" | "tool_only" | "retrieve_then_tool",
            "reasoning": "short reasoning",
            "retrieve_query": "search query or null",
            "tool_name": null,
            "tool_args": null
        }}

        user query:
        {query}

        """.strip()

    def _parse_plan(self, raw: str, original_query: str) -> PlanDecision:
        raw = raw.strip()
        try:
            data = json.loads(raw)
            return PlanDecision.model_validate(data)
        except Exception:
            pass

        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                return PlanDecision.model_validate(data)
            except Exception:
                pass
        return self._fallback_plan(original_query)

    def _fallback_plan(self, query: str) -> PlanDecision:
        q = query.strip().lower()
        casual_patterns = [
            "hi", "hello", "hey", "hola", "bonjour", "guten tag",
            "how are you", "how are you doing", "how are you today",
            "what's up", "what is up",
            "thanks", "thank you", "thank you so much",
            "bye", "goodbye", "see you", "see you later",
            "lol", "haha", "hehe",
            "what is your name", "who are you",
            "what can you do", "what can you do for me",
            "are you a bot", "are you an ai",
            "good morning", "good afternoon", "good evening",
        ]

        if any(p in q for p in casual_patterns):
            return PlanDecision(
                mode="direct_answer",
                reasoning="Fallback planner detected casual conversation.",
                retrieve_query=None,
                tool_name=None,
                tool_args=None
            )
        
        return PlanDecision(
            mode="retrieve_only",
            reasoning="Fallback planner defaulted to retrieval for document-grounded answering.",
            retrieve_query=query,
            tool_name=None,
            tool_args=None
        )