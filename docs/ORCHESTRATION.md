# Orchestration Layer

The orchestration layer lives in `agent/orchestrator.py`. Its job is to coordinate the full agentic RAG flow without adding document-specific logic.

The layer should stay generic. It must not contain hardcoded PDF names, author names, or topic-specific keyword hacks for Sora, Docker, machine-learning papers, or any future document source.

## Current Flow

For every query, the orchestrator runs this pipeline:

```text
User query
-> save user turn
-> capture explicit long-term memory
-> load relevant memory
-> plan
-> route action
-> guardrail check for tool calls
-> direct answer, retrieval, or tool call
-> verify answer
-> repair answer when grounded citations exist but verification fails
-> optionally retry retrieval once
-> save assistant turn
-> save trace
-> return answer, citations, steps, and verification
```

## Retrieval Flow

Document questions use this sequence:

1. Rewrite the user query with generic intent expansion.
2. Route across indexed documents with `DocumentRouter`.
3. Search the selected route using hybrid retrieval.
4. Select evidence with `EvidenceJudge`.
5. Merge top retrieval hits and judged evidence into the answer context.
6. Generate a grounded answer with `AnswerService`.
7. Verify the answer with `Verifier`.
8. Repair the answer if citations exist and verifier issues are fixable.

The answer context intentionally keeps both high-ranked retrieval results and judged evidence. This avoids over-trusting one component and helps with PDFs where section titles, OCR text, or chunk boundaries are imperfect.

## Retrieval Retry

The orchestrator can run one generic retrieval retry.

A retry is triggered when:

- no citable evidence is found, or
- the verifier still marks the answer as not verified after repair.

The retry:

- keeps the original user query as the source of truth,
- uses `QueryRewriter.rewrite_for_retry`,
- searches the full corpus instead of only the routed document subset,
- allows a slightly larger answer context,
- records the retry reason and acceptance decision in the trace.

The retry answer is accepted when it is clearly better:

- it is verified and has citations,
- the first attempt had no citations and the retry found citations, or
- the first attempt failed verification and the retry reduces verifier issues.

This is a general recovery mechanism for routing misses, sparse wording, noisy chunks, and unseen PDFs. It is not tuned for any one document.

## Verification And Repair

Verification checks:

- citation presence for retrieved answers,
- invalid citation references,
- raw chunk metadata leakage,
- query intent match,
- entity drift,
- evidence overlap.

When citations exist but verification fails, the orchestrator asks `AnswerService.repair_answer` to produce a more focused answer from the same evidence. The repaired answer is only accepted when the verifier marks it as verified.

## Trace Steps

Each response returns a `steps` list and stores it in SQLite traces.

Important step types:

- `memory`: memory capture/load counts.
- `plan`: planner decision.
- `retrieve`: retrieval attempt details.
- `verify`: verifier result.
- `answer_repair`: repair attempt and repair verification.
- `retrieval_retry_decision`: whether the retry answer replaced the first attempt.
- `guardrail`: tool-call allow, deny, needs-approval, or request-approved decision.
- `tool_call`: tool execution result.
- `direct_answer`: casual or non-document answer path.

For retrieval steps, useful fields include:

- `attempt`
- `retry`
- `retry_reason`
- `candidate_scope`
- `routed_docs`
- `result_count`
- `selected_count`
- `answer_context_count`
- `evidence_judgements`

These fields are useful when debugging why a query was answered poorly.

## Design Rules

Keep this layer responsible for coordination only.

Do:

- keep routing, retrieval, evidence selection, answer generation, and verification separate,
- use generic fallback behavior,
- check guardrails before tool execution,
- record decisions in trace steps,
- keep external response keys stable for CLI, API, and eval scripts,
- run targeted eval after changing orchestration.

Do not:

- hardcode document titles, source names, or PDF-specific keywords,
- silently accept an unverified repaired answer,
- let memory become citation evidence,
- hide retry behavior from traces,
- persist approval from one request into another request,
- make unlimited retrieval loops.

## Evaluation

Run focused checks after orchestration changes:

```cmd
venv\Scripts\python.exe -m py_compile agent\orchestrator.py
venv\Scripts\python.exe scripts\eval_rag_quality.py --ids docker_lazydocker_features,docker_watchtower_features,ml_crfs,sora_world_simulator,smoldocling_doctags,intro_seven_day_challenge,ai_money_no_quit_job --output eval\rag_quality_orchestration_report.json --fail-under-average 8 --fail-under-item 7
```

Run the full benchmark before a push:

```cmd
venv\Scripts\python.exe scripts\eval_rag_quality.py --eval-file test\eval_multi_doc_rag.json --output eval\rag_quality_report.json --fail-under-average 8 --fail-under-item 7
```

## Next Improvements

Good next orchestration improvements:

1. Add multi-step `retrieve_then_tool` tests.
2. Reuse the guardrail policy shape for MCP tools.
3. Add a route-confidence metric from document routing.
4. Add UI trace inspection so users can see routing, evidence, retry, guardrail, and verifier decisions.
