from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.guardrails import GuardrailPolicy
from agent.planner import Planner
from agent.schemas import AgentAction
from app.file_mcp import ReadOnlyFileMCPClient
from app.mcp_adapter import MCPToolAdapter
from app.tool_registry import ToolRegistry
from retrieval.answer_service import AnswerService


class ChatClientStub:
    def generate(self, prompt: str) -> str:
        raise AssertionError("Structured File MCP output should not call the LLM.")


def guardrail_status(registry: ToolRegistry, tool_name: str) -> str:
    return GuardrailPolicy().evaluate_tool_call(
        AgentAction(action_type="tool_call", tool_call={"name": tool_name, "args": {"path": "docs"}}),
        registry,
    ).status


def main() -> None:
    with TemporaryDirectory() as tmp:
        base_dir = Path(tmp)
        docs_dir = base_dir / "docs"
        data_dir = base_dir / "data"
        docs_dir.mkdir()
        data_dir.mkdir()
        (docs_dir / "MCP.md").write_text("# MCP\n\nRead-only file connector.", encoding="utf-8")
        (data_dir / "sample.json").write_text('{"ok": true}', encoding="utf-8")
        (data_dir / ".env").write_text("TOKEN=hidden", encoding="utf-8")
        (data_dir / ".env.example").write_text("TOKEN=example", encoding="utf-8")
        (data_dir / "secret.pem").write_text("private key", encoding="utf-8")
        (base_dir / "secret.env").write_text("TOKEN=hidden", encoding="utf-8")

        client = ReadOnlyFileMCPClient(
            allowed_roots=[docs_dir, data_dir],
            base_dir=base_dir,
        )
        registry = ToolRegistry()
        registered = MCPToolAdapter("local_files", client).register_tools(registry)
        names = {tool.name for tool in registered}

        read_tool = "mcp.local_files.read_text_file"
        list_tool = "mcp.local_files.list_directory"
        info_tool = "mcp.local_files.file_info"

        assert {read_tool, list_tool, info_tool}.issubset(names)
        assert registry.get_tool_spec(read_tool).requires_approval is False  # type: ignore[union-attr]
        assert guardrail_status(registry, read_tool) == "allow"

        list_result = registry.execute(list_tool, path="docs")
        list_payload = json.loads(list_result.output or "{}")
        assert list_payload["result"]["entries"][0]["path"] == "docs/MCP.md"

        read_result = registry.execute(read_tool, path="docs/MCP.md")
        read_payload = json.loads(read_result.output or "{}")
        assert read_payload["result"]["success"] is True
        assert "Read-only file connector" in read_payload["result"]["content"]

        denied_result = registry.execute(read_tool, path="secret.env")
        denied_payload = json.loads(denied_result.output or "{}")
        assert denied_payload["result"]["success"] is False
        assert "outside allowed" in denied_payload["result"]["error"]

        hidden_result = registry.execute(read_tool, path="data/.env")
        hidden_payload = json.loads(hidden_result.output or "{}")
        assert hidden_payload["result"]["success"] is False
        assert "sensitive" in hidden_payload["result"]["error"].lower()

        hidden_info = registry.execute(info_tool, path="data/.env")
        hidden_info_payload = json.loads(hidden_info.output or "{}")
        assert hidden_info_payload["result"]["success"] is False
        assert "sensitive" in hidden_info_payload["result"]["error"].lower()

        key_result = registry.execute(read_tool, path="data/secret.pem")
        key_payload = json.loads(key_result.output or "{}")
        assert key_payload["result"]["success"] is False
        assert "sensitive" in key_payload["result"]["error"].lower()

        example_result = registry.execute(read_tool, path="data/.env.example")
        example_payload = json.loads(example_result.output or "{}")
        assert example_payload["result"]["success"] is True
        assert "TOKEN=example" in example_payload["result"]["content"]

        planner = Planner(chat_client=ChatClientStub())
        read_plan = planner.plan("Read file docs/MCP.md")
        assert read_plan.mode == "tool_only"
        assert read_plan.tool_name == read_tool
        assert read_plan.tool_args["path"] == "docs/MCP.md"

        trailing_read_plan = planner.plan("Read file docs/MCP.md please")
        assert trailing_read_plan.mode == "tool_only"
        assert trailing_read_plan.tool_name == read_tool
        assert trailing_read_plan.tool_args["path"] == "docs/MCP.md"

        metadata_plan = planner.plan("Show metadata for file docs/MCP.md")
        assert metadata_plan.mode == "tool_only"
        assert metadata_plan.tool_name == info_tool
        assert metadata_plan.tool_args["path"] == "docs/MCP.md"

        hidden_plan = planner.plan("Read file data/.env")
        assert hidden_plan.mode == "tool_only"
        assert hidden_plan.tool_name == read_tool
        assert hidden_plan.tool_args["path"] == "data/.env"

        key_plan = planner.plan("Read file data/secret.pem")
        assert key_plan.mode == "tool_only"
        assert key_plan.tool_name == read_tool
        assert key_plan.tool_args["path"] == "data/secret.pem"

        list_plan = planner.plan("List files in docs")
        assert list_plan.mode == "tool_only"
        assert list_plan.tool_name == list_tool
        assert list_plan.tool_args["path"] == "docs"

        answer_service = AnswerService(chat_client=ChatClientStub())
        answer = answer_service.answer_from_tool_result(
            query="Read file docs/MCP.md",
            tool_context=read_result.output or "",
        )
        assert "Here is the content of docs/MCP.md" in answer
        assert "Read-only file connector" in answer

    print("File MCP smoke test passed.")


if __name__ == "__main__":
    main()
