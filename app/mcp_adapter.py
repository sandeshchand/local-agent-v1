from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Protocol

from agent.schemas import ToolSpec
from app.tool_registry import ToolRegistry


class MCPClientProtocol(Protocol):
    """Small protocol for MCP-like clients without binding to one SDK yet."""

    def list_tools(self) -> Any:
        ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        ...


@dataclass(frozen=True)
class MCPToolDefinition:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    annotations: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = True


class MCPToolAdapter:
    """Register MCP-discovered tools inside the existing guarded tool registry."""

    def __init__(
        self,
        server_name: str,
        client: MCPClientProtocol,
        *,
        default_requires_approval: bool = True,
        registry_prefix: str = "mcp",
    ) -> None:
        self.server_name = _safe_name(server_name) or "server"
        self.client = client
        self.default_requires_approval = default_requires_approval
        self.registry_prefix = _safe_name(registry_prefix) or "mcp"
        self._registry_to_mcp: dict[str, str] = {}

    def discover_tools(self) -> list[MCPToolDefinition]:
        payload = self.client.list_tools()
        raw_tools = _extract_tool_list(payload)
        return [self._tool_definition(raw_tool) for raw_tool in raw_tools]

    def register_tools(self, registry: ToolRegistry) -> list[ToolSpec]:
        registered: list[ToolSpec] = []
        used_names = {tool.name for tool in registry.list_tools()}

        for definition in self.discover_tools():
            if not definition.name:
                continue
            registry_name = self._registry_tool_name(definition.name, used_names)
            used_names.add(registry_name)
            self._registry_to_mcp[registry_name] = definition.name

            spec = ToolSpec(
                name=registry_name,
                description=definition.description or f"MCP tool {definition.name}",
                requires_approval=definition.requires_approval,
                source="mcp",
                metadata={
                    "server_name": self.server_name,
                    "mcp_tool_name": definition.name,
                    "input_schema": definition.input_schema,
                    "annotations": definition.annotations,
                },
            )
            registry.register(spec, self._callable_for(registry_name))
            registered.append(spec)

        return registered

    def _tool_definition(self, raw_tool: Any) -> MCPToolDefinition:
        payload = _as_dict(raw_tool)
        annotations = _as_dict(payload.get("annotations") or {})
        requires_approval = self._requires_approval(payload, annotations)
        input_schema = payload.get("inputSchema") or payload.get("input_schema") or {}

        return MCPToolDefinition(
            name=str(payload.get("name") or "").strip(),
            description=str(payload.get("description") or "").strip(),
            input_schema=_as_dict(input_schema),
            annotations=annotations,
            requires_approval=requires_approval,
        )

    def _requires_approval(self, payload: dict[str, Any], annotations: dict[str, Any]) -> bool:
        if "requires_approval" in payload:
            return bool(payload["requires_approval"])
        if "requiresApproval" in payload:
            return bool(payload["requiresApproval"])
        if payload.get("read_only") is True or payload.get("readOnly") is True:
            return False
        if annotations.get("readOnlyHint") is True or annotations.get("read_only") is True:
            return False
        return self.default_requires_approval

    def _registry_tool_name(self, mcp_tool_name: str, used_names: set[str]) -> str:
        safe_tool = _safe_name(mcp_tool_name) or "tool"
        base_name = f"{self.registry_prefix}.{self.server_name}.{safe_tool}"
        candidate = base_name
        index = 2
        while candidate in used_names:
            candidate = f"{base_name}_{index}"
            index += 1
        return candidate

    def _callable_for(self, registry_name: str):
        def call_mcp_tool(**kwargs: Any) -> str:
            mcp_tool_name = self._registry_to_mcp[registry_name]
            result = self.client.call_tool(mcp_tool_name, kwargs)
            return json.dumps(
                {
                    "source": "mcp",
                    "server_name": self.server_name,
                    "tool_name": mcp_tool_name,
                    "arguments": kwargs,
                    "result": _json_safe(result),
                },
                ensure_ascii=True,
            )

        return call_mcp_tool


def _extract_tool_list(payload: Any) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    payload_dict = _as_dict(payload)
    tools = payload_dict.get("tools") or payload_dict.get("items") or []
    return tools if isinstance(tools, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return dict(value.model_dump())
    if hasattr(value, "dict"):
        return dict(value.dict())
    result: dict[str, Any] = {}
    for key in ("name", "description", "inputSchema", "input_schema", "annotations"):
        if hasattr(value, key):
            result[key] = getattr(value, key)
    return result


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    return str(value)


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned.lower()
