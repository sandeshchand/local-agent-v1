from __future__ import annotations
import json
import re

from agent.schemas import PlanDecision
from app.ollama_client import OllamaChatClient

class Planner:
    def __init__(self, chat_client: OllamaChatClient) -> None:
        self.chat_client = chat_client
      

    def plan(self, query:str) -> PlanDecision:
        q = query.strip().lower()
        casual_patterns = [
            "hi", "hello", "hey", "hola", "bonjour", "guten tag",
            "how are you", "how are you doing", "how are you today",
            "what's up",
            "thanks", "thank you", "thank you so much",
            "bye", "goodbye", "see you", "see you later",
            "lol", "haha", "hehe",
            "what is your name", "who are you",
            "what can you do", "what can you do for me",
            "are you a bot", "are you an ai",
            "good morning", "good afternoon", "good evening",
        ]

        if any(p ==q or p in q for p in casual_patterns):
            return PlanDecision(
                mode="direct_answer",
                reasoning="Detected casual conversation.",
             
            )
        
        return PlanDecision(
            mode="retrieve_only",
            reasoning="Defaulting to retrieval for all non-causal queries during milestone 4.5 debugging.",
            retrieve_query=query,
        )