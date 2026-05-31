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

GuardrailStatus = Literal[
    "allow",
    "deny",
    "needs_approval",
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
    source: str = "local"
    metadata: dict[str, Any] = Field(default_factory=dict)

class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)

class ToolResult(BaseModel):
    tool_name: str
    success: bool
    output: Any | None = None
    error: str | None = None

class GuardrailDecision(BaseModel):
    status: GuardrailStatus
    reason: str
    action_type: ActionType
    tool_name: str | None = None
    requires_approval: bool = False
    approved: bool = False
    policy_name: str = "tool_call_guardrails_v1"

class AgentAction(BaseModel):
    action_type: ActionType
    tool_call: ToolCall | None = None
    retrieve_query: str | None = None
    notes: str= ""

MemoryKind = Literal[
    "short_term",
    "long_term",
    "summary",
    "user_preference",
    "project_decision",
    "task_status",
    "evaluation_result",
    "known_issue",
]


class MemoryRecord(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    kind: MemoryKind = "short_term"
    source: str = "conversation"
    importance: float = 1.0
    score: float = 0.0
    created_at: str | None = None
    
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
    
    
    
    
    
    
    
