from __future__ import annotations

from agent.schemas import MemoryRecord
from storage.sqlite_store import SQLiteStore

class MemoryManager:
    def __init__(self, sqlite_store:SQLiteStore, max_turns: int = 6) -> None:
        self.sqlite_store = sqlite_store
        self.max_turns = max_turns
    
    def load_sesssion_memory(self, session_id: str) -> list[MemoryRecord]:
        rows = self.sqlite_store.get_recent_conversations(session_id, limit=self.max_turns)
        return [
            MemoryRecord(
                role=row["role"],
                content=row["content"],
                kind="short_term",
            )
            for row in rows
        ]

    def save_user_turn(self, session_id: str, content: str) -> None:
        self.sqlite_store.insert_conversation_turn(
            session_id=session_id,
            role="user",
            content=content,
        )
    def save_assistant_turn(self, session_id: str, content: str) -> None:
        self.sqlite_store.insert_conversation_turn(
            session_id=session_id,
            role="assistant",
            content=content,
        )
   
    def format_memory_context(self, memory:list[MemoryRecord]) -> str:
        if not memory:
            return "No previous conversation."
        
        lines = ["[SESSION MEMORY]"]
        for item in memory:
            lines.append(f"{item.role}: {item.content}")
        
        return "\n".join(lines)