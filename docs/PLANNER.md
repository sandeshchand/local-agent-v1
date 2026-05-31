# Planner

The planner is the first routing decision layer for a user query.

The implementation is in:

```text
src/local_agent/agent/planner.py
src/local_agent/agent/tool_router.py
src/local_agent/agent/schemas.py
```

## Purpose

The planner decides what kind of work the agent should do before any retrieval or tool execution starts.

It produces a `PlanDecision` with:

- `mode`
- `reasoning`
- `retrieve_query`
- `tool_name`
- `tool_args`
- `confidence`

The planner does not execute anything. It only creates a plan. The `ToolRouter` converts that plan into an executable action.

## Current Plan Modes

Current modes are:

```text
direct_answer
retrieve_only
tool_only
retrieve_then_tool
```

Current implementation mainly uses:

- `direct_answer` for greetings and casual conversation,
- `tool_only` for weather, File MCP, and SQLite MCP inspection queries,
- `retrieve_only` for normal PDF/RAG questions.

`retrieve_then_tool` exists in the schema and tool router, but is not a major active path yet.

## Planner Flow

The planner checks the query in this order:

```text
casual conversation
-> current weather request
-> SQLite MCP inspection request
-> File MCP request
-> default PDF retrieval
```

This order matters. Tool and system-inspection queries should not be sent into PDF retrieval, while ordinary document questions should remain grounded in indexed PDF chunks.

## Direct Answer Path

Simple conversational inputs are routed to:

```text
mode = direct_answer
```

Examples:

- `hi`
- `hello`
- `thank you`
- `what can you do`

The orchestrator then calls `AnswerService.answer_direct()`.

Direct answers do not use PDF citations.

## Weather Tool Path

Current weather or current temperature questions route to:

```text
mode = tool_only
tool_name = get_current_weather
```

Examples:

- `What is the weather in Berlin?`
- `What is the current temperature of Stuttgart?`

The planner extracts the location from phrases like:

- `in`
- `for`
- `at`
- `near`
- `of`

Weather output is tool context, not PDF citation evidence.

## SQLite MCP Path

Local database inspection queries route to read-only SQLite MCP tools.

Examples:

```text
List database tables
Preview table traces limit 5
Show recent traces from database
Show feedback summary
```

These produce:

```text
mcp.sqlite.list_tables
mcp.sqlite.preview_table
mcp.sqlite.recent_traces
mcp.sqlite.feedback_summary
```

The planner normalizes a few control-query typos such as:

- `databse` -> `database`
- `datbase` -> `database`
- `sql lite` -> `sqlite`

This typo handling is only for tool-control intent, not document-specific PDF answers.

## File MCP Path

File inspection queries route to read-only File MCP tools.

Examples:

```text
List files in docs
Read file docs/MCP.md
Show metadata for file docs/MCP.md
```

These produce:

```text
mcp.local_files.list_directory
mcp.local_files.read_text_file
mcp.local_files.file_info
```

Actual path allowlists are enforced by File MCP and guardrails, not only by the planner.

## Default Retrieval Path

If no direct/tool route matches, the planner defaults to:

```text
mode = retrieve_only
retrieve_query = original query
```

This is the normal RAG path for PDF questions.

Examples:

- `What are the key features of WatchTower?`
- `Why does the paper describe Sora as a world simulator?`
- `What are Conditional Random Fields used for?`

## ToolRouter Role

`ToolRouter.next_action()` converts a plan into an `AgentAction`.

Examples:

- `direct_answer` -> `action_type = direct_answer`
- `retrieve_only` -> `action_type = retrieve`
- `tool_only` -> `action_type = tool_call`

The orchestrator then executes that action.

## Trace Visibility

Every request stores a plan step in the trace:

```text
type: "plan"
plan: {...}
```

In the UI, open the `Trace` workspace tab and inspect:

- selected mode,
- reasoning,
- tool name,
- tool args,
- retrieval query.

## Design Rules

- Keep planner routing general-purpose.
- Do not add PDF-specific hardcoded keywords.
- Prefer narrow tool intent detection over broad guessing.
- Tool execution must still pass guardrails.
- PDF facts must still come from retrieval and citations.

