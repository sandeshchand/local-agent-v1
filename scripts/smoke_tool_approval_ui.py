from __future__ import annotations

from local_agent.app.api_models import ChatResponse
from local_agent.app.web import approval_payload


def main() -> None:
    needs_approval = approval_payload(
        {
            "steps": [
                {
                    "type": "guardrail",
                    "status": "needs_approval",
                    "tool_name": "mcp.example.write_file",
                    "reason": "Approval-required smoke tool.",
                }
            ]
        }
    )
    assert needs_approval["needs_approval"] is True
    assert needs_approval["approval_tool_name"] == "mcp.example.write_file"
    assert "Approval-required" in needs_approval["approval_reason"]

    allowed = approval_payload(
        {
            "steps": [
                {
                    "type": "guardrail",
                    "status": "allow",
                    "tool_name": "mcp.example.read_file",
                }
            ]
        }
    )
    assert allowed["needs_approval"] is False
    assert allowed["approval_tool_name"] is None

    response = ChatResponse(
        answer="This action requires approval before execution.",
        trace_id=1,
        mode="tool_only",
        citations=[],
        **needs_approval,
    )
    assert response.needs_approval is True
    assert response.approval_tool_name == "mcp.example.write_file"

    print("Tool approval UI contract smoke passed.")


if __name__ == "__main__":
    main()
