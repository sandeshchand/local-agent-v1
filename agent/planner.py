from __future__ import annotations

import re

from agent.schemas import PlanDecision
from app.ollama_client import OllamaChatClient


class Planner:
    def __init__(self, chat_client: OllamaChatClient) -> None:
        self.chat_client = chat_client

    def plan(self, query: str) -> PlanDecision:
        q = query.strip().lower()

        casual_patterns = {
            "hi",
            "hello",
            "hey",
            "hola",
            "bonjour",
            "guten tag",
            "namaste",
            "namaskar",
            "how are you",
            "how are you doing",
            "how are you today",
            "what's up",
            "thanks",
            "thank you",
            "thank you so much",
            "bye",
            "goodbye",
            "see you",
            "see you later",
            "lol",
            "haha",
            "hehe",
            "what is your name",
            "who are you",
            "what can you do",
            "what can you do for me",
            "are you a bot",
            "are you an ai",
            "good morning",
            "good afternoon",
            "good evening",
        }

        if q in casual_patterns:
            return PlanDecision(
                mode="direct_answer",
                reasoning="Detected casual conversation or greeting.",
            )

        if self._is_current_weather_query(q):
            location = self._weather_location(query)
            return PlanDecision(
                mode="tool_only",
                reasoning="Detected current weather request.",
                tool_name="get_current_weather",
                tool_args={"location": location},
            )

        return PlanDecision(
            mode="retrieve_only",
            reasoning="Defaulting to retrieval for non-casual queries.",
            retrieve_query=query,
        )

    def _is_current_weather_query(self, query_lower: str) -> bool:
        if "weather" in query_lower:
            return True
        if "temperature" in query_lower and (
            any(term in query_lower for term in ["current", "now", "today", "outside", "forecast"])
            or any(marker in query_lower for marker in [" in ", " for ", " at ", " near "])
        ):
            return True
        return False

    def _weather_location(self, query: str) -> str:
        cleaned = query.strip().strip("?.! ")
        for pattern in [
            r"\b(?:in|for|at|near)\s+(.+)$",
            r"\bweather\s+(.+)$",
            r"\btemperature\s+(.+)$",
        ]:
            match = re.search(pattern, cleaned, flags=re.IGNORECASE)
            if match:
                location = match.group(1).strip(" ?.!")
                location = re.sub(
                    r"\b(?:right now|now|today|currently|outside|please)\b",
                    "",
                    location,
                    flags=re.IGNORECASE,
                )
                return re.sub(r"\s+", " ", location).strip()
        return ""
