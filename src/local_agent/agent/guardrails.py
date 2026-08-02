from __future__ import annotations

from pathlib import Path
from typing import Any

from local_agent.agent.schemas import AgentAction, GuardrailDecision

_SENSITIVE_FILE_NAMES = {
    ".env",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
}

_SENSITIVE_SUFFIXES = {
    ".key",
    ".p12",
    ".pem",
    ".pfx",
}


class GuardrailPolicy:
    """Policy checks for actions that can execute tools."""

    policy_name = "tool_call_guardrails_v1"

    def evaluate_tool_call(
        self,
        action: AgentAction,
        tool_registry: Any,
        approved_tools: list[str] | None = None,
    ) -> GuardrailDecision:
        tool_name = self._tool_name(action)
        approved_tool_names = set(approved_tools or [])
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

        path_decision = self._evaluate_path_policy(action, tool_spec)
        if path_decision is not None:
            return path_decision

        if tool_spec.requires_approval:
            if tool_name in approved_tool_names:
                return GuardrailDecision(
                    status="allow",
                    reason=f"Tool '{tool_name}' requires approval and was approved for this request.",
                    action_type=action.action_type,
                    tool_name=tool_name,
                    requires_approval=True,
                    approved=True,
                    policy_name=self.policy_name,
                )
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

    def _tool_args(self, action: AgentAction) -> dict[str, Any]:
        tool_call = action.tool_call
        if tool_call is None:
            return {}
        if hasattr(tool_call, "args"):
            return tool_call.args or {}
        return tool_call.get("args", {}) or {}

    def _evaluate_path_policy(self, action: AgentAction, tool_spec: Any) -> GuardrailDecision | None:
        policy = self._path_policy(tool_spec)
        if not policy:
            return None

        tool_name = self._tool_name(action)
        args = self._tool_args(action)
        path_args = policy.get("path_args") or policy.get("pathArgs") or ["path"]
        if isinstance(path_args, str):
            path_args = [path_args]
        allow_empty_path = bool(policy.get("allow_empty_path") or policy.get("allowEmptyPath"))

        base_dir = self._resolve_policy_root(policy.get("base_dir") or policy.get("baseDir"))
        allowed_roots = [
            self._resolve_policy_root(raw_root, base_dir=base_dir)
            for raw_root in (policy.get("allowed_roots") or policy.get("allowedRoots") or [])
            if str(raw_root or "").strip()
        ]
        if not allowed_roots:
            return self._deny_path_policy(
                action,
                tool_name,
                "Tool has a path policy but no allowed roots are configured.",
            )

        for path_arg in path_args:
            raw_path = args.get(str(path_arg))
            if raw_path is None or str(raw_path).strip() == "":
                if allow_empty_path:
                    continue
                return self._deny_path_policy(
                    action,
                    tool_name,
                    f"Tool requires path argument '{path_arg}' for guardrail path validation.",
                )

            resolved = self._resolve_tool_path(str(raw_path), base_dir)
            if resolved is None:
                return self._deny_path_policy(
                    action,
                    tool_name,
                    f"Tool path '{raw_path}' could not be resolved safely.",
                )

            if not self._is_allowed_path(resolved, allowed_roots):
                allowed_display = ", ".join(self._display_root(root, base_dir) for root in allowed_roots)
                return self._deny_path_policy(
                    action,
                    tool_name,
                    f"Tool path '{raw_path}' is outside allowed roots: {allowed_display}.",
                )

            if bool(policy.get("block_sensitive", True)) and self._is_sensitive_path(resolved, base_dir):
                return self._deny_path_policy(
                    action,
                    tool_name,
                    f"Tool path '{raw_path}' is hidden or sensitive and cannot be accessed.",
                )

        return None

    def _path_policy(self, tool_spec: Any) -> dict[str, Any] | None:
        metadata = getattr(tool_spec, "metadata", {}) or {}
        policy = metadata.get("path_policy")
        if isinstance(policy, dict):
            return policy
        annotations = metadata.get("annotations") or {}
        if isinstance(annotations, dict):
            nested_policy = annotations.get("localAgentPathPolicy")
            if isinstance(nested_policy, dict):
                return nested_policy
        return None

    def _deny_path_policy(
        self,
        action: AgentAction,
        tool_name: str | None,
        reason: str,
    ) -> GuardrailDecision:
        return GuardrailDecision(
            status="deny",
            reason=reason,
            action_type=action.action_type,
            tool_name=tool_name,
            policy_name=f"{self.policy_name}.path_policy",
        )

    def _resolve_policy_root(self, raw_path: Any, *, base_dir: Path | None = None) -> Path:
        path = Path(str(raw_path or ".")).expanduser()
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / path
        return path.resolve()

    def _resolve_tool_path(self, raw_path: str, base_dir: Path) -> Path | None:
        try:
            candidate = Path(raw_path.strip()).expanduser()
            if not candidate.is_absolute():
                candidate = base_dir / candidate
            return candidate.resolve()
        except (OSError, RuntimeError, ValueError):
            return None

    def _is_allowed_path(self, path: Path, allowed_roots: list[Path]) -> bool:
        for root in allowed_roots:
            if path == root:
                return True
            if root.exists() and root.is_dir() and root in path.parents:
                return True
        return False

    def _is_sensitive_path(self, path: Path, base_dir: Path) -> bool:
        lower_name = path.name.lower()
        if lower_name.endswith(".env.example"):
            return False
        if lower_name in _SENSITIVE_FILE_NAMES:
            return True
        if path.suffix.lower() in _SENSITIVE_SUFFIXES:
            return True
        try:
            parts = path.relative_to(base_dir).parts
        except ValueError:
            parts = path.parts
        return any(part.startswith(".") for part in parts)

    def _display_root(self, root: Path, base_dir: Path) -> str:
        try:
            return root.relative_to(base_dir).as_posix()
        except ValueError:
            return str(root)
