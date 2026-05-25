from __future__ import annotations

from agent.guardrails import GuardrailPolicy
from agent.orchestrator import Orchestrator
from agent.schemas import AgentAction, AgentState, ToolSpec, VerificationResult
from app.tool_registry import ToolRegistry


class VerifierStub:
    def verify(self, answer: str, retrieved_items: list[dict], query: str = "") -> VerificationResult:
        return VerificationResult(status="verified", issues=[], grounded=True)


class AnswerServiceStub:
    def answer_from_tool_result(
        self,
        query: str,
        tool_context: str,
        memory_context: str = "",
    ) -> str:
        return f"Tool result: {tool_context}"


def build_registry(calls: dict[str, int]) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="safe_tool",
            description="Safe read-only smoke tool",
            requires_approval=False,
        ),
        lambda: _record_call(calls, "safe_tool", "safe output"),
    )
    registry.register(
        ToolSpec(
            name="approval_tool",
            description="Approval-required smoke tool",
            requires_approval=True,
        ),
        lambda: _record_call(calls, "approval_tool", "approval output"),
    )
    return registry


def _record_call(calls: dict[str, int], name: str, output: str) -> str:
    calls[name] = calls.get(name, 0) + 1
    return output


def build_orchestrator(registry: ToolRegistry) -> Orchestrator:
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.tool_registry = registry
    orchestrator.guardrail_policy = GuardrailPolicy()
    orchestrator.verifier = VerifierStub()
    orchestrator.answer_service = AnswerServiceStub()
    return orchestrator


def run_tool_action(orchestrator: Orchestrator, tool_name: str) -> AgentState:
    state = AgentState(session_id="guardrail-smoke", user_query=f"run {tool_name}")
    action = AgentAction(
        action_type="tool_call",
        tool_call={
            "name": tool_name,
            "args": {},
        },
    )
    orchestrator._handle_tool_action(
        query=state.user_query,
        memory_context="",
        state=state,
        action=action,
        step_no=2,
    )
    return state


def assert_guardrail_status(state: AgentState, expected_status: str) -> None:
    guardrail_steps = [step for step in state.steps if step.get("type") == "guardrail"]
    assert guardrail_steps, "Expected a guardrail trace step."
    assert guardrail_steps[-1]["status"] == expected_status


def main() -> None:
    calls: dict[str, int] = {}
    registry = build_registry(calls)
    policy = GuardrailPolicy()

    safe_decision = policy.evaluate_tool_call(
        AgentAction(action_type="tool_call", tool_call={"name": "safe_tool", "args": {}}),
        registry,
    )
    assert safe_decision.status == "allow"

    unknown_decision = policy.evaluate_tool_call(
        AgentAction(action_type="tool_call", tool_call={"name": "missing_tool", "args": {}}),
        registry,
    )
    assert unknown_decision.status == "deny"

    approval_decision = policy.evaluate_tool_call(
        AgentAction(action_type="tool_call", tool_call={"name": "approval_tool", "args": {}}),
        registry,
    )
    assert approval_decision.status == "needs_approval"

    orchestrator = build_orchestrator(registry)

    safe_state = run_tool_action(orchestrator, "safe_tool")
    assert_guardrail_status(safe_state, "allow")
    assert calls.get("safe_tool") == 1
    assert safe_state.tool_results and safe_state.tool_results[0].success

    unknown_state = run_tool_action(orchestrator, "missing_tool")
    assert_guardrail_status(unknown_state, "deny")
    assert "blocked by guardrails" in unknown_state.final_answer
    assert calls.get("missing_tool", 0) == 0
    assert not unknown_state.tool_results

    approval_state = run_tool_action(orchestrator, "approval_tool")
    assert_guardrail_status(approval_state, "needs_approval")
    assert "requires approval" in approval_state.final_answer
    assert calls.get("approval_tool", 0) == 0
    assert not approval_state.tool_results

    print("Guardrails smoke test passed.")


if __name__ == "__main__":
    main()
