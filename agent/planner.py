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

        file_tool_plan = self._file_tool_plan(query)
        if file_tool_plan is not None:
            return file_tool_plan

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
            or any(marker in query_lower for marker in [" in ", " for ", " at ", " near ", " of "])
        ):
            return True
        return False

    def _weather_location(self, query: str) -> str:
        cleaned = query.strip().strip("?.! ")
        for pattern in [
            r"\b(?:in|for|at|near|of)\s+(.+)$",
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
                location = re.sub(
                    r"^(?:of|in|for|at|near)\s+",
                    "",
                    location,
                    flags=re.IGNORECASE,
                )
                return re.sub(r"\s+", " ", location).strip()
        return ""

    def _file_tool_plan(self, query: str) -> PlanDecision | None:
        q = query.strip()
        q_lower = q.lower()
        path = self._file_path_from_query(q)

        if self._is_file_list_query(q_lower):
            return PlanDecision(
                mode="tool_only",
                reasoning="Detected read-only file listing request.",
                tool_name="mcp.local_files.list_directory",
                tool_args={"path": path, "max_entries": 100},
            )

        if path and self._is_file_info_query(q_lower):
            return PlanDecision(
                mode="tool_only",
                reasoning="Detected read-only file metadata request.",
                tool_name="mcp.local_files.file_info",
                tool_args={"path": path},
            )

        if path and self._is_file_read_query(q_lower):
            return PlanDecision(
                mode="tool_only",
                reasoning="Detected read-only file read request.",
                tool_name="mcp.local_files.read_text_file",
                tool_args={"path": path, "max_bytes": 20000},
            )

        return None

    def _is_file_list_query(self, query_lower: str) -> bool:
        has_list_verb = any(term in query_lower for term in ["list", "show", "what files", "which files"])
        has_file_target = any(term in query_lower for term in ["files", "directory", "folder"])
        return has_list_verb and has_file_target

    def _is_file_read_query(self, query_lower: str) -> bool:
        has_read_verb = any(term in query_lower for term in ["read", "show", "open", "display"])
        has_file_hint = any(term in query_lower for term in [" file", " mcp", " docs/", " data/", " test/"])
        return has_read_verb and has_file_hint

    def _is_file_info_query(self, query_lower: str) -> bool:
        has_info_verb = any(term in query_lower for term in ["info", "metadata", "size", "details"])
        return has_info_verb and any(term in query_lower for term in [" file", " directory", " folder", " mcp"])

    def _file_path_from_query(self, query: str) -> str:
        quoted = re.search(r"[`'\"]([^`'\"]+)[`'\"]", query)
        if quoted:
            return self._clean_file_path(quoted.group(1))

        file_patterns = [
            r"((?:[\w.-]+[\\/])+\.[\w.-]+)\b",
            r"((?:[\w.-]+[\\/])+[^?*!:;\r\n]*?\.(?:key|pem|p12|pfx))\b",
            r"((?:[\w.-]+[\\/])+[^?*!:;\r\n]*?\.(?:cfg|csv|ini|json|log|md|py|ps1|toml|txt|yaml|yml))\b",
            r"\b([\w.-]+\.(?:cfg|csv|ini|json|log|md|py|ps1|toml|txt|yaml|yml))\b",
        ]
        for pattern in file_patterns:
            path_match = re.search(pattern, query, flags=re.IGNORECASE)
            if path_match:
                return self._clean_file_path(path_match.group(1))

        folder_match = re.search(
            r"\b(?:in|inside|under|from|of|directory|folder)\s+([A-Za-z0-9_.\\/\- ]+)",
            query,
            flags=re.IGNORECASE,
        )
        if folder_match:
            return self._clean_file_path(folder_match.group(1))

        return ""

    def _clean_file_path(self, path: str) -> str:
        cleaned = path.strip().strip("`'\" ?.!,:;")
        cleaned = re.sub(r"^(?:file|folder|directory)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"\s+\b(?:please|now|today|kindly|using|with|through|via)\b.*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+\bfor\s+me\b.*$", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip("`'\" ?.!,:;")
