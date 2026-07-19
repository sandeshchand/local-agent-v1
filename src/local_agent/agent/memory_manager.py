from __future__ import annotations

import re
from typing import Any

from local_agent.agent.schemas import MemoryKind, MemoryRecord
from local_agent.storage.sqlite_store import SQLiteStore


class MemoryManager:
    """
    Stores short-term conversation turns and retrieves durable project memory.

    Short-term memory is the recent session transcript. Durable memory is made of
    explicit project rules, user preferences, task status, eval results, and known
    issues. Durable memories are intentionally small and inspectable.
    """

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        max_turns: int = 6,
        max_relevant_memories: int = 6,
    ) -> None:
        self.sqlite_store = sqlite_store
        self.max_turns = max_turns
        self.max_relevant_memories = max_relevant_memories

    def load_session_memory(self, session_id: str) -> list[MemoryRecord]:
        rows = self.sqlite_store.get_recent_conversations(session_id, limit=self.max_turns)
        return [
            MemoryRecord(
                role=row["role"],
                content=row["content"],
                kind="short_term",
                source="conversation",
                created_at=row.get("created_at"),
            )
            for row in rows
        ]

    def load_sesssion_memory(self, session_id: str) -> list[MemoryRecord]:
        """Backward-compatible alias for the earlier misspelled method name."""
        return self.load_session_memory(session_id)

    def load_relevant_memory(self, session_id: str, query: str) -> list[MemoryRecord]:
        rows = self.sqlite_store.list_memory_items(
            session_id=session_id,
            include_global=True,
            limit=200,
        )
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            score = self._score_memory(query, row)
            if score <= 0:
                continue
            scored.append((score, row))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[: self.max_relevant_memories]
        self.sqlite_store.touch_memory_items([int(row["memory_id"]) for _, row in selected])

        return [
            MemoryRecord(
                role="system",
                content=row["content"],
                kind=row["kind"],
                source=row["source"],
                importance=float(row["importance"]),
                score=round(score, 2),
                created_at=row.get("created_at"),
            )
            for score, row in selected
        ]

    def load_memory_for_query(self, session_id: str, query: str) -> list[MemoryRecord]:
        return [
            *self.load_relevant_memory(session_id, query),
            *self.load_session_memory(session_id),
        ]

    def save_user_turn(self, session_id: str, content: str) -> None:
        self.sqlite_store.insert_conversation_turn(
            session_id=session_id,
            role="user",
            content=self._redact_sensitive_text(content),
        )

    def save_assistant_turn(self, session_id: str, content: str) -> None:
        self.sqlite_store.insert_conversation_turn(
            session_id=session_id,
            role="assistant",
            content=self._redact_sensitive_text(content),
        )

    def remember(
        self,
        content: str,
        *,
        kind: MemoryKind = "project_decision",
        session_id: str = "global",
        scope: str = "global",
        source: str = "manual",
        importance: float = 1.0,
    ) -> int | None:
        cleaned = self._clean_memory_text(content)
        if not cleaned or self._is_sensitive(cleaned):
            return None
        return self.sqlite_store.insert_memory_item(
            content=cleaned,
            kind=kind,
            session_id=session_id if scope == "session" else "global",
            scope=scope,
            source=source,
            importance=importance,
        )

    def capture_long_term_memory(self, session_id: str, user_message: str) -> list[MemoryRecord]:
        captured: list[MemoryRecord] = []
        for candidate in self._extract_memory_candidates(user_message):
            memory_id = self.remember(
                candidate["content"],
                kind=candidate["kind"],
                session_id=session_id,
                scope=candidate["scope"],
                source="auto",
                importance=candidate["importance"],
            )
            if memory_id is None:
                continue
            captured.append(
                MemoryRecord(
                    role="system",
                    content=candidate["content"],
                    kind=candidate["kind"],
                    source="auto",
                    importance=candidate["importance"],
                    score=0.0,
                )
            )
        return captured

    def format_memory_context(self, memory: list[MemoryRecord]) -> str:
        if not memory:
            return "No relevant memory."

        durable = [item for item in memory if item.kind != "short_term"]
        recent = [item for item in memory if item.kind == "short_term"]
        lines: list[str] = []

        if durable:
            lines.append("[LONG-TERM MEMORY]")
            lines.append("Use these as project/user guidance. Do not treat them as PDF evidence.")
            for item in durable:
                lines.append(f"- {item.kind}: {item.content}")

        if recent:
            if lines:
                lines.append("")
            lines.append("[RECENT SESSION]")
            for item in recent:
                lines.append(f"{item.role}: {item.content}")

        return "\n".join(lines)

    def _extract_memory_candidates(self, text: str) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for sentence in self._memory_sentences(text):
            cleaned = self._clean_memory_text(sentence)
            if not cleaned or self._is_sensitive(cleaned):
                continue
            lower = cleaned.lower()
            if not self._has_memory_signal(lower):
                continue
            kind = self._classify_memory_kind(lower)
            importance = self._memory_importance(lower)
            candidates.append(
                {
                    "content": cleaned,
                    "kind": kind,
                    "scope": "global",
                    "importance": importance,
                }
            )
        return candidates

    def _memory_sentences(self, text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return []
        parts = re.split(r"(?<=[.!?])\s+|\n+", normalized)
        if len(parts) == 1 and len(normalized.split()) <= 80:
            return [normalized]
        return [part.strip() for part in parts if part.strip()]

    def _clean_memory_text(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip(" -")
        cleaned = re.sub(r"^(please|kindly)\s+", "", cleaned, flags=re.IGNORECASE)
        if len(cleaned.split()) > 80:
            return ""
        if len(cleaned) > 500:
            cleaned = cleaned[:500].rstrip()
        return cleaned

    def _has_memory_signal(self, lower: str) -> bool:
        signals = [
            "remember",
            "keep in mind",
            "do not",
            "don't",
            "dont",
            "never",
            "always",
            "we need",
            "we should",
            "target",
            "goal",
            "next step",
            "completed",
            "issue",
            "bug",
            "score",
            "eval",
            "benchmark",
        ]
        return any(signal in lower for signal in signals)

    def _classify_memory_kind(self, lower: str) -> MemoryKind:
        if any(term in lower for term in ["eval", "benchmark", "score", "pass", "failed"]):
            return "evaluation_result"
        if any(term in lower for term in ["next step", "todo", "remaining", "completed", "done"]):
            return "task_status"
        if any(term in lower for term in ["issue", "bug", "problem", "regression"]):
            return "known_issue"
        if any(term in lower for term in ["i prefer", "i want", "my preference"]):
            return "user_preference"
        return "project_decision"

    def _memory_importance(self, lower: str) -> float:
        importance = 1.0
        if any(term in lower for term in ["do not", "don't", "dont", "never", "always", "keep in mind"]):
            importance += 1.0
        if any(term in lower for term in ["target", "goal", "eval", "benchmark", "quality", "general purpose"]):
            importance += 0.5
        return min(3.0, importance)

    def _score_memory(self, query: str, row: dict[str, Any]) -> float:
        content = str(row["content"])
        query_terms = self._content_terms(query)
        memory_terms = self._content_terms(content)
        if not query_terms or not memory_terms:
            return 0.0

        overlap = len(query_terms & memory_terms)
        score = float(overlap * 2)
        query_lower = query.lower()
        content_lower = content.lower()
        for phrase in self._important_phrases(query_lower):
            if phrase in content_lower:
                score += 3.0

        kind = str(row["kind"])
        if kind in {"project_decision", "user_preference"}:
            score += 1.0
        if kind == "task_status" and any(term in query_lower for term in ["next", "todo", "remaining", "done"]):
            score += 3.0
        if kind == "evaluation_result" and any(term in query_lower for term in ["eval", "score", "benchmark", "quality"]):
            score += 3.0

        importance = float(row.get("importance") or 1.0)
        if importance >= 2.0 and any(
            term in query_lower
            for term in ["implement", "fix", "optimize", "quality", "rag", "general", "memory", "agent"]
        ):
            score += importance

        return score

    def _important_phrases(self, text: str) -> list[str]:
        words = [
            word
            for word in re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b", text)
            if word not in self._stop_words()
        ]
        phrases: list[str] = []
        for size in (3, 2):
            for index in range(0, max(0, len(words) - size + 1)):
                phrases.append(" ".join(words[index : index + size]))
        return phrases[:20]

    def _content_terms(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b", text.lower())
            if token not in self._stop_words()
        }

    def _stop_words(self) -> set[str]:
        return {
            "the",
            "and",
            "for",
            "with",
            "that",
            "this",
            "what",
            "how",
            "why",
            "are",
            "you",
            "your",
            "our",
            "from",
            "into",
            "about",
            "need",
            "should",
            "please",
            "kindly",
        }

    def _is_sensitive(self, text: str) -> bool:
        lower = text.lower()
        if any(term in lower for term in ["password", "secret", "api key", "apikey", "token", "private key"]):
            return True
        if re.search(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b", text):
            return True
        if re.search(r"\b(?:\+?\d[\s-]?){9,}\b", text):
            return True
        if re.search(r"\b(?:sk|pk|ghp|gho|hf)_[A-Za-z0-9_=-]{16,}\b", text):
            return True
        if re.search(r"\b[A-Fa-f0-9]{32,}\b", text):
            return True
        return False

    def _redact_sensitive_text(self, text: str) -> str:
        redacted = text
        redacted = re.sub(
            r"\b(?:sk|pk|ghp|gho|hf)_[A-Za-z0-9_=-]{8,}\b",
            "[REDACTED_SECRET]",
            redacted,
        )
        redacted = re.sub(
            r"(?i)\b(api key|apikey|token|password|secret|private key)\s*(?:is|=|:)\s*\S+",
            r"\1 is [REDACTED_SECRET]",
            redacted,
        )
        redacted = re.sub(
            r"\b[A-Fa-f0-9]{32,}\b",
            "[REDACTED_SECRET]",
            redacted,
        )
        redacted = re.sub(
            r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b",
            "[REDACTED_EMAIL]",
            redacted,
        )
        redacted = re.sub(
            r"\b(?:\+?\d[\s-]?){9,}\b",
            "[REDACTED_PHONE]",
            redacted,
        )
        return redacted
