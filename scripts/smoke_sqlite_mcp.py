from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from local_agent.agent.guardrails import GuardrailPolicy
from local_agent.agent.planner import Planner
from local_agent.agent.schemas import AgentAction
from local_agent.app.mcp_adapter import MCPToolAdapter
from local_agent.app.sqlite_mcp import ReadOnlySQLiteMCPClient
from local_agent.app.tool_registry import ToolRegistry
from local_agent.retrieval.answer_service import AnswerService
from local_agent.storage.sqlite_store import SQLiteStore


class ChatClientStub:
    def generate(self, prompt: str) -> str:
        raise AssertionError("Structured SQLite MCP output should not call the LLM.")


def guardrail_status(registry: ToolRegistry, tool_name: str) -> str:
    return GuardrailPolicy().evaluate_tool_call(
        AgentAction(action_type="tool_call", tool_call={"name": tool_name, "args": {}}),
        registry,
    ).status


def main() -> None:
    with TemporaryDirectory() as tmp:
        store = SQLiteStore(Path(tmp) / "app.db")
        try:
            store.initialize()
            trace_id = store.insert_trace(
                session_id="sqlite-mcp",
                query="What is SQLite MCP?",
                top_k=3,
                retrieved_json="{}",
                final_answer="A read-only SQLite inspection tool.",
                verification_json='{"status": "verified"}',
            )
            store.upsert_answer_feedback(trace_id=trace_id, rating="dislike", issue_type="weak_answer")

            registry = ToolRegistry()
            registered = MCPToolAdapter(
                "sqlite",
                ReadOnlySQLiteMCPClient(store),
            ).register_tools(registry)
            names = {tool.name for tool in registered}

            list_tool = "mcp.sqlite.list_tables"
            preview_tool = "mcp.sqlite.preview_table"
            traces_tool = "mcp.sqlite.recent_traces"
            feedback_tool = "mcp.sqlite.feedback_summary"

            assert {list_tool, preview_tool, traces_tool, feedback_tool}.issubset(names)
            assert registry.get_tool_spec(list_tool).requires_approval is False  # type: ignore[union-attr]
            assert guardrail_status(registry, list_tool) == "allow"

            tables_result = registry.execute(list_tool)
            tables_payload = json.loads(tables_result.output or "{}")
            table_names = {table["name"] for table in tables_payload["result"]["tables"]}
            assert "traces" in table_names
            assert "answer_feedback" in table_names

            preview_result = registry.execute(preview_tool, table="traces", limit=2)
            preview_payload = json.loads(preview_result.output or "{}")
            assert preview_payload["result"]["table"] == "traces"
            assert preview_payload["result"]["rows"][0]["query"] == "What is SQLite MCP?"

            bad_preview = registry.execute(preview_tool, table="missing_table")
            bad_payload = json.loads(bad_preview.output or "{}")
            assert bad_payload["result"]["success"] is False
            assert "Unknown table" in bad_payload["result"]["error"]

            traces_result = registry.execute(traces_tool, limit=5)
            traces_payload = json.loads(traces_result.output or "{}")
            assert traces_payload["result"]["traces"][0]["trace_id"] == trace_id

            feedback_result = registry.execute(feedback_tool)
            feedback_payload = json.loads(feedback_result.output or "{}")
            assert feedback_payload["result"]["dislike_count"] == 1
            assert feedback_payload["result"]["issue_counts"]["weak_answer"] == 1

            planner = Planner(chat_client=ChatClientStub())
            tables_plan = planner.plan("List database tables")
            assert tables_plan.mode == "tool_only"
            assert tables_plan.tool_name == list_tool

            typo_tables_plan = planner.plan("List databse tables")
            assert typo_tables_plan.mode == "tool_only"
            assert typo_tables_plan.tool_name == list_tool

            feedback_plan = planner.plan("Show feedback summary")
            assert feedback_plan.mode == "tool_only"
            assert feedback_plan.tool_name == feedback_tool

            traces_plan = planner.plan("Show recent traces from database")
            assert traces_plan.mode == "tool_only"
            assert traces_plan.tool_name == traces_tool

            preview_plan = planner.plan("Preview table traces limit 2")
            assert preview_plan.mode == "tool_only"
            assert preview_plan.tool_name == preview_tool
            assert preview_plan.tool_args["table"] == "traces"
            assert preview_plan.tool_args["limit"] == 2

            answer_service = AnswerService(chat_client=ChatClientStub())
            tables_answer = answer_service.answer_from_tool_result(
                query="List database tables",
                tool_context=tables_result.output or "",
            )
            assert "SQLite tables:" in tables_answer
            assert "traces" in tables_answer

            feedback_answer = answer_service.answer_from_tool_result(
                query="Show feedback summary",
                tool_context=feedback_result.output or "",
            )
            assert "Feedback summary" in feedback_answer
            assert "1 disliked" in feedback_answer
        finally:
            store.close()

    print("SQLite MCP smoke test passed.")


if __name__ == "__main__":
    main()
