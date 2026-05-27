from __future__ import annotations

from typing import Any, Callable

from agent.schemas import ToolSpec, ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolSpec, Callable[..., Any]]] = {}

    def register(self, tool: ToolSpec, fn: Callable[..., Any]) -> None:
        self._tools[tool.name] = (tool, fn)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def get_tool_spec(self, name: str) -> ToolSpec | None:
        tool = self._tools.get(name)
        if tool is None:
            return None
        spec, _ = tool
        return spec

    def list_tools(self) -> list[ToolSpec]:
        return [spec for spec, _ in self._tools.values()]

    def execute(self, tool_name: str, **kwargs: Any) -> ToolResult:
        if tool_name not in self._tools:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool '{tool_name}' not found",
            )
        spec, fn = self._tools[tool_name]
        try:
            result = fn(**kwargs)
            return ToolResult(
                tool_name=spec.name,
                success=True,
                output=result,
            )
        except Exception as exc:
            return ToolResult(
                tool_name=spec.name,
                success=False,
                error=str(exc),
            )
