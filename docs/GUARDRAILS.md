# Guardrails

Guardrails protect actions that can execute tools. Version 1 focuses only on tool calls; it does not block normal RAG retrieval, PDF answering, memory loading, or answer verification.

## Current Scope

Guardrails v1 checks tool calls before execution.

It decides:

- `allow`: the tool is registered and does not require approval.
- `deny`: the tool call is missing or the tool is not registered.
- `needs_approval`: the tool is registered, requires approval, and was not approved for this request.

MCP tools and file-operation guardrails will build on this layer later.

## Flow

```text
Planner
-> ToolRouter
-> AgentAction(action_type="tool_call")
-> GuardrailPolicy.evaluate_tool_call
   -> allow: execute tool
   -> deny: block execution
   -> needs_approval: block unless the caller approves the tool for this request
-> trace guardrail decision
-> final answer
```

## Policy Rules

The policy lives in `agent/guardrails.py`.

For a tool call:

- missing tool call: `deny`
- unknown tool name: `deny`
- registered tool with `requires_approval=True`: `needs_approval`
- registered tool with `requires_approval=True` and request-scoped approval: `allow`
- registered tool with `requires_approval=False`: `allow`

The first registered tool, `list_documents`, remains allowed because it is read-only and registered with `requires_approval=False`.

The `get_current_weather` tool is also allowed by default because it is a narrow read-only current-info tool. Broad web search should use stricter approval.

## Request-Scoped Approval

Approval is explicit and request-scoped. It is not stored in memory and does not approve future requests.

Python callers can pass approved tool names to the orchestrator:

```python
deps.orchestrator.handle_query(
    "Run the approved tool",
    approved_tools=["tool_name"],
)
```

Command-line callers can approve a tool for one `ask` command:

```cmd
venv\Scripts\python.exe app\main.py ask --query "Run the approved tool" --approve-tool tool_name
```

API callers can include approved tool names in the chat payload:

```json
{
  "query": "Run the approved tool",
  "approved_tools": ["tool_name"]
}
```

## Trace Step

Every tool action now records a `guardrail` step before execution.

Useful fields:

- `status`
- `reason`
- `action_type`
- `tool_name`
- `requires_approval`
- `approved`
- `policy_name`

Blocked tools are not executed and do not create a `tool_result`.

## Design Rules

Do:

- keep guardrails generic and independent of PDF content,
- check guardrails before tool execution,
- record every guardrail decision in traces,
- use `ToolSpec.requires_approval` for tool-level approval requirements.

Do not:

- use guardrails to optimize retrieval answers,
- treat tool output as PDF citation evidence,
- add document-specific allow/deny rules,
- persist approval from one request into another request.

## Verification

Run:

```cmd
venv\Scripts\python.exe -m py_compile agent\orchestrator.py agent\guardrails.py agent\schemas.py app\tool_registry.py
venv\Scripts\python.exe scripts\smoke_guardrails.py
venv\Scripts\python.exe scripts\smoke_memory.py
```

Run targeted RAG eval after wiring changes:

```cmd
venv\Scripts\python.exe scripts\eval_rag_quality.py --ids docker_lazydocker_features,docker_watchtower_features,ml_crfs,sora_world_simulator --output eval\rag_quality_guardrails_report.json --fail-under-average 8 --fail-under-item 7
```

## Next Improvements

1. Add file-operation categories before write/delete tools are introduced.
2. Add path allowlists before wiring writable File MCP tools.
3. Show approval-required tool prompts in the UI.
