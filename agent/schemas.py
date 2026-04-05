from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

PlanMode = Literal[
    "direct_answer", 
    "retrieve_only",
    "tool_only",
    "retrieve_then_tool"
    ]

class PlanDecision(BaseModel):
    mode: PlanMode
    reasoning: str = ""
    retrieve_query: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    
