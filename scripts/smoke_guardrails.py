from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from local_agent.agent.guardrails import GuardrailPolicy
from local_agent.agent.orchestrator import Orchestrator
from local_agent.agent.schemas import AgentAction, AgentState, ToolSpec, VerificationResult
from local_agent.tools import ToolRegistry


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


def path_policy_metadata(
    base_dir: Path,
    allowed_roots: list[Path],
    *,
    allow_empty_path: bool = False,
    category: str = "read_file",
    write_delete_policy: dict | None = None,
) -> dict:
    metadata = {
        "category": category,
        "path_policy": {
            "path_args": ["path"],
            "base_dir": str(base_dir),
            "allowed_roots": [str(root) for root in allowed_roots],
            "allow_empty_path": allow_empty_path,
            "block_sensitive": True,
        },
    }
    if write_delete_policy is not None:
        metadata["write_delete_policy"] = write_delete_policy
    return metadata


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


def run_tool_action(
    orchestrator: Orchestrator,
    tool_name: str,
    approved_tools: list[str] | None = None,
    tool_args: dict | None = None,
) -> AgentState:
    state = AgentState(session_id="guardrail-smoke", user_query=f"run {tool_name}")
    action = AgentAction(
        action_type="tool_call",
        tool_call={
            "name": tool_name,
            "args": tool_args or {},
        },
    )
    orchestrator._handle_tool_action(
        query=state.user_query,
        memory_context="",
        state=state,
        action=action,
        step_no=2,
        approved_tools=approved_tools,
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

    approved_decision = policy.evaluate_tool_call(
        AgentAction(action_type="tool_call", tool_call={"name": "approval_tool", "args": {}}),
        registry,
        approved_tools=["approval_tool"],
    )
    assert approved_decision.status == "allow"
    assert approved_decision.requires_approval
    assert approved_decision.approved

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

    approved_state = run_tool_action(orchestrator, "approval_tool", approved_tools=["approval_tool"])
    assert_guardrail_status(approved_state, "allow")
    guardrail_step = [step for step in approved_state.steps if step.get("type") == "guardrail"][-1]
    assert guardrail_step["requires_approval"]
    assert guardrail_step["approved"]
    assert calls.get("approval_tool") == 1
    assert approved_state.tool_results and approved_state.tool_results[0].success

    with TemporaryDirectory() as tmp:
        base_dir = Path(tmp)
        docs_dir = base_dir / "docs"
        data_dir = base_dir / "data"
        docs_dir.mkdir()
        data_dir.mkdir()
        registry.register(
            ToolSpec(
                name="file_read",
                description="Read a guarded file path",
                requires_approval=False,
                metadata=path_policy_metadata(base_dir, [docs_dir, data_dir]),
            ),
            lambda path: _record_call(calls, "file_read", path),
        )
        registry.register(
            ToolSpec(
                name="file_list",
                description="List guarded file roots",
                requires_approval=False,
                metadata=path_policy_metadata(base_dir, [docs_dir, data_dir], allow_empty_path=True),
            ),
            lambda path="": _record_call(calls, "file_list", path),
        )

        allowed_path = policy.evaluate_tool_call(
            AgentAction(action_type="tool_call", tool_call={"name": "file_read", "args": {"path": "docs"}}),
            registry,
        )
        assert allowed_path.status == "allow"

        outside_path = policy.evaluate_tool_call(
            AgentAction(
                action_type="tool_call",
                tool_call={"name": "file_read", "args": {"path": "secret.env"}},
            ),
            registry,
        )
        assert outside_path.status == "deny"
        assert "outside allowed roots" in outside_path.reason

        sensitive_path = policy.evaluate_tool_call(
            AgentAction(
                action_type="tool_call",
                tool_call={"name": "file_read", "args": {"path": "data/.env"}},
            ),
            registry,
        )
        assert sensitive_path.status == "deny"
        assert "sensitive" in sensitive_path.reason

        empty_listing = policy.evaluate_tool_call(
            AgentAction(action_type="tool_call", tool_call={"name": "file_list", "args": {}}),
            registry,
        )
        assert empty_listing.status == "allow"

        registry.register(
            ToolSpec(
                name="write_file",
                description="Future write tool without policy",
                requires_approval=False,
                metadata=path_policy_metadata(base_dir, [docs_dir], category="write_file"),
            ),
            lambda path: _record_call(calls, "write_file", path),
        )
        unconfigured_write = policy.evaluate_tool_call(
            AgentAction(
                action_type="tool_call",
                tool_call={"name": "write_file", "args": {"path": "docs/output.md"}},
            ),
            registry,
            approved_tools=["write_file"],
        )
        assert unconfigured_write.status == "deny"
        assert "write/delete tool execution is disabled" in unconfigured_write.reason

        blocked_write_state = run_tool_action(
            orchestrator,
            "write_file",
            approved_tools=["write_file"],
            tool_args={"path": "docs/output.md"},
        )
        assert_guardrail_status(blocked_write_state, "deny")
        assert calls.get("write_file", 0) == 0
        assert not blocked_write_state.tool_results

        registry.register(
            ToolSpec(
                name="configured_write_file",
                description="Future write tool with policy",
                requires_approval=False,
                metadata=path_policy_metadata(
                    base_dir,
                    [docs_dir],
                    category="write_file",
                    write_delete_policy={
                        "enabled": True,
                        "allowed_categories": ["write_file"],
                    },
                ),
            ),
            lambda path: _record_call(calls, "configured_write_file", path),
        )
        write_needs_approval = policy.evaluate_tool_call(
            AgentAction(
                action_type="tool_call",
                tool_call={"name": "configured_write_file", "args": {"path": "docs/output.md"}},
            ),
            registry,
        )
        assert write_needs_approval.status == "needs_approval"
        assert write_needs_approval.requires_approval

        approved_write = policy.evaluate_tool_call(
            AgentAction(
                action_type="tool_call",
                tool_call={"name": "configured_write_file", "args": {"path": "docs/output.md"}},
            ),
            registry,
            approved_tools=["configured_write_file"],
        )
        assert approved_write.status == "allow"
        assert approved_write.requires_approval
        assert approved_write.approved

        registry.register(
            ToolSpec(
                name="configured_delete_file",
                description="Future delete tool without delete flag",
                requires_approval=True,
                metadata=path_policy_metadata(
                    base_dir,
                    [docs_dir],
                    category="delete_file",
                    write_delete_policy={
                        "enabled": True,
                        "allowed_categories": ["delete_file"],
                    },
                ),
            ),
            lambda path: _record_call(calls, "configured_delete_file", path),
        )
        delete_without_flag = policy.evaluate_tool_call(
            AgentAction(
                action_type="tool_call",
                tool_call={"name": "configured_delete_file", "args": {"path": "docs/output.md"}},
            ),
            registry,
            approved_tools=["configured_delete_file"],
        )
        assert delete_without_flag.status == "deny"
        assert "not explicitly allowed to delete" in delete_without_flag.reason

        registry.register(
            ToolSpec(
                name="delete_file_enabled",
                description="Future delete tool with delete flag",
                requires_approval=True,
                metadata=path_policy_metadata(
                    base_dir,
                    [docs_dir],
                    category="delete_file",
                    write_delete_policy={
                        "enabled": True,
                        "allowed_categories": ["delete_file"],
                        "allow_delete": True,
                    },
                ),
            ),
            lambda path: _record_call(calls, "delete_file_enabled", path),
        )
        approved_delete = policy.evaluate_tool_call(
            AgentAction(
                action_type="tool_call",
                tool_call={"name": "delete_file_enabled", "args": {"path": "docs/output.md"}},
            ),
            registry,
            approved_tools=["delete_file_enabled"],
        )
        assert approved_delete.status == "allow"
        assert approved_delete.requires_approval
        assert approved_delete.approved

    print("Guardrails smoke test passed.")


if __name__ == "__main__":
    main()
