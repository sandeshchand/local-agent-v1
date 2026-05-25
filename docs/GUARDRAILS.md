# Guardrails

Guardrails protect actions that can execute tools. Version 1 focuses only on tool calls; it does not block normal RAG retrieval, PDF answering, memory loading, or answer verification.

## Current Scope

Guardrails v1 checks tool calls before execution.

It decides:

- `allow`: the tool is registered and does not require approval.
- `deny`: the tool call is missing or the tool is not registered.
- `needs_approval`: the tool is registered but its `ToolSpec.requires_approval` flag is true.

MCP tools and file-operation guardrails will build on this layer later.

## Flow

```text
Planner
-> ToolRouter
-> AgentAction(action_type="tool_call")
-> GuardrailPolicy.evaluate_tool_call
   -> allow: execute tool
   -> deny: block execution
   -> needs_approval: block until approval support exists
-> trace guardrail decision
-> final answer
```

## Policy Rules

The policy lives in `agent/guardrails.py`.

For a tool call:

- missing tool call: `deny`
- unknown tool name: `deny`
- registered tool with `requires_approval=True`: `needs_approval`
- registered tool with `requires_approval=False`: `allow`

The first registered tool, `list_documents`, remains allowed because it is read-only and registered with `requires_approval=False`.

## Trace Step

Every tool action now records a `guardrail` step before execution.

Useful fields:

- `status`
- `reason`
- `action_type`
- `tool_name`
- `requires_approval`
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
- execute approval-required tools before an approval flow exists.

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

1. Add an explicit approval flow for `needs_approval`.
2. Reuse the same policy shape for MCP tools.
3. Add file-operation categories before write/delete tools are introduced.
4. Show guardrail decisions in the UI trace view.
