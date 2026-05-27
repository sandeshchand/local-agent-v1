# Web Tools

The first web-based tool is a narrow current weather tool. It is intentionally not a broad web search tool.

## Current Weather

Tool name:

```text
get_current_weather
```

Purpose:

- answer current weather questions,
- fetch structured weather data for a named location,
- keep current-info tool output separate from PDF citation evidence.

Example questions:

- What is the current weather in Berlin?
- What is the current weather of Stuttgart?
- What is the temperature in Kathmandu now?
- How is the weather in New York today?

The tool uses Open-Meteo's geocoding and forecast APIs. It does not require an API key.

The planner accepts common phrasing such as `weather in`, `weather of`, and `temperature in`. The tool also makes one conservative retry with a shortened location token, which helps simple typos such as `stuttgat` resolve to `Stuttgart`.

## Planner Routing

The planner routes weather/current-temperature questions to `tool_only` mode.

The tool receives:

```json
{
  "location": "Berlin"
}
```

If no location is provided, the tool asks for a location instead of guessing.

## Guardrails

`get_current_weather` is registered as a read-only tool with:

```text
requires_approval=False
```

Reason:

- the user explicitly asks for current weather,
- the tool only reads public weather data,
- it does not write files, call shell commands, or mutate the project.

Future broad web search tools should be stricter and should usually require approval.

## Evidence Boundary

Weather tool output is tool context, not PDF evidence.

For document questions, answers must still come from retrieved PDF chunks and citations. Web tool output should not become citation evidence for RAG answers.

## Verification

Run:

```cmd
venv\Scripts\python.exe -m py_compile app\weather_tool.py agent\planner.py
venv\Scripts\python.exe scripts\smoke_weather_tool.py
```

Run targeted RAG eval after planner changes:

```cmd
venv\Scripts\python.exe scripts\eval_rag_quality.py --ids docker_lazydocker_features,docker_watchtower_features,ml_crfs,sora_world_simulator --output eval\rag_quality_weather_tool_report.json --fail-under-average 8 --fail-under-item 7
```

## Next Web/MCP Tools

Recommended order:

1. Add UI visibility for registered File MCP tools.
2. Web search with approval.
3. GitHub or repository tools with approval.
4. File-operation tools only after path guardrails are stronger.
