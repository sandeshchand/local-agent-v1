from __future__ import annotations

import json

from local_agent.agent.guardrails import GuardrailPolicy
from local_agent.agent.schemas import AgentAction
from local_agent.tools import MCPToolAdapter, ToolRegistry


class FakeMCPClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self) -> dict:
        return {
            "tools": [
                {
                    "name": "read_note",
                    "description": "Read a note from a test MCP server.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    },
                    "annotations": {"readOnlyHint": True},
                },
                {
                    "name": "delete_note",
                    "description": "Delete a note from a test MCP server.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    },
                },
            ]
        }

    def call_tool(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))
        return {"ok": True, "name": name, "arguments": arguments}


def guardrail_status(registry: ToolRegistry, tool_name: str) -> str:
    decision = GuardrailPolicy().evaluate_tool_call(
        AgentAction(
            action_type="tool_call",
            tool_call={"name": tool_name, "args": {"name": "demo"}},
        ),
        registry,
    )
    return decision.status


def main() -> None:
    registry = ToolRegistry()
    client = FakeMCPClient()
    adapter = MCPToolAdapter("Test Server", client)

    registered = adapter.register_tools(registry)
    tool_names = {tool.name for tool in registered}

    read_tool = "mcp.test_server.read_note"
    delete_tool = "mcp.test_server.delete_note"

    assert read_tool in tool_names
    assert delete_tool in tool_names
    assert registry.get_tool_spec(read_tool).source == "mcp"  # type: ignore[union-attr]
    assert registry.get_tool_spec(read_tool).requires_approval is False  # type: ignore[union-attr]
    assert registry.get_tool_spec(delete_tool).requires_approval is True  # type: ignore[union-attr]

    assert guardrail_status(registry, read_tool) == "allow"
    assert guardrail_status(registry, delete_tool) == "needs_approval"

    result = registry.execute(read_tool, name="demo")
    payload = json.loads(result.output or "{}")

    assert result.success
    assert payload["source"] == "mcp"
    assert payload["server_name"] == "test_server"
    assert payload["tool_name"] == "read_note"
    assert payload["result"]["ok"] is True
    assert client.calls == [("read_note", {"name": "demo"})]

    print("MCP adapter smoke test passed.")


if __name__ == "__main__":
    main()
