from __future__ import annotations

from typing import Any

from agent.schemas import AgentAction, GuardrailDecision


class GuardrailPolicy:
    """Policy checks for actions that can execute tools."""

    policy_name = "tool_call_guardrails_v1"

    def evaluate_tool_call(self, action: AgentAction, tool_registry: Any) -> GuardrailDecision:
        tool_name = self._tool_name(action)
        if action.action_type != "tool_call":
            return GuardrailDecision(
                status="deny",
                reason="Guardrail policy only allows tool_call actions in this path.",
                action_type=action.action_type,
                tool_name=tool_name,
                policy_name=self.policy_name,
            )

        if not action.tool_call or not tool_name:
            return GuardrailDecision(
                status="deny",
                reason="Tool action is missing a tool call.",
                action_type=action.action_type,
                tool_name=tool_name,
                policy_name=self.policy_name,
            )

        tool_spec = tool_registry.get_tool_spec(tool_name)
        if tool_spec is None:
            return GuardrailDecision(
                status="deny",
                reason=f"Tool '{tool_name}' is not registered.",
                action_type=action.action_type,
                tool_name=tool_name,
                policy_name=self.policy_name,
            )

        if tool_spec.requires_approval:
            return GuardrailDecision(
                status="needs_approval",
                reason=f"Tool '{tool_name}' requires approval before execution.",
                action_type=action.action_type,
                tool_name=tool_name,
                requires_approval=True,
                policy_name=self.policy_name,
            )

        return GuardrailDecision(
            status="allow",
            reason=f"Tool '{tool_name}' is registered and does not require approval.",
            action_type=action.action_type,
            tool_name=tool_name,
            requires_approval=False,
            policy_name=self.policy_name,
        )

    def _tool_name(self, action: AgentAction) -> str | None:
        tool_call = action.tool_call
        if tool_call is None:
            return None
        if hasattr(tool_call, "name"):
            return tool_call.name
        return tool_call.get("name")
