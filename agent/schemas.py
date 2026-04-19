from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PlanMode = Literal[
    "direct_answer", 
    "retrieve_only",
    "tool_only",
    "retrieve_then_tool"
    ]


ActionType = Literal[
    "direct_answer",
    "retrieve",
    "tool_call",
    "finalize"
]

VerificationStatus = Literal[
    "verified",
    "needs_more_info",
    "contradictory"
]



class PlanDecision(BaseModel):
    mode: PlanMode
    reasoning: str = ""
    goal: str = ""
    retrieve_query: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    needs_memory: bool = False
    confidence: float = 0.0
    
class ToolSpec(BaseModel):
    name: str
    description: str
    requires_approval: bool = False

class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)

class ToolResult(BaseModel):
    tool_name: str
    success: bool
    output: str | None = None
    error: str | None = None

class AgentAction(BaseModel):
    action_type: ActionType
    tool_call: ToolCall | None = None
    retrieve_query: str | None = None
    notes: str= ""

class MemoryRecord(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    kind: Literal["short_term", "long_term", "summary"] = "short_term"
    
class AgentState(BaseModel):
    session_id: str
    user_query: str
    plan: PlanDecision | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    memory: list[MemoryRecord] = Field(default_factory=list)
    retrieved_items: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    final_answer: str = ""
    done: bool = False

class VerificationResult(BaseModel):
    status: VerificationStatus
    issues: list[str] = Field(default_factory=list)
    grounded: bool = True
    
    
    
    
    
    
    
