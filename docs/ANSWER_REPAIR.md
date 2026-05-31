# Answer Repair

Answer repair is the recovery step after verification finds a problem with a generated answer.

The implementation is in:

```text
src/local_agent/agent/orchestrator.py
src/local_agent/agent/verifier.py
src/local_agent/retrieval/answer_service.py
```

## Purpose

Local LLM answers can sometimes:

- miss citations,
- cite unavailable evidence,
- leak raw chunk metadata,
- answer too broadly,
- drift into another document/topic,
- ignore the retrieved evidence,
- fail to answer the exact user question.

Answer repair tries to fix these issues using only the retrieved evidence.

## When Repair Runs

The orchestrator verifies every final answer.

For retrieved PDF answers, repair runs when:

```text
used_citations exist
and
verification.status != "verified"
```

The flow is:

```text
generate answer
-> verify
-> if failed, repair answer
-> verify repaired answer
-> accept repaired answer only if verified
```

Tool-only and direct answers can be verified, but repair is only useful when retrieved evidence exists.

## Verifier Issues That Trigger Repair

Repair may run for issues such as:

- missing citation markers,
- invalid citation numbers,
- raw retrieval/chunk metadata leakage,
- answer drift,
- wrong prominent entity,
- wrong answer shape for the question,
- low overlap with retrieved evidence.

These issues come from:

```text
src/local_agent/agent/verifier.py
```

## LLM Repair Prompt

`AnswerService.repair_answer()` builds a repair prompt with:

- the original user question,
- the original answer,
- verifier issues,
- evidence facts extracted from retrieved chunks,
- retrieved context.

The repair prompt tells the model to:

- answer only the exact question,
- use only retrieved evidence,
- fix unsupported drift and raw context leakage,
- keep the answer concise,
- cite each sentence or bullet,
- avoid neighboring topics unless the user asks for them.

If the evidence does not answer the question, the repair prompt asks for:

```text
The provided context does not contain enough information.
```

## Deterministic Repair Fallback

If LLM repair is weak, empty, insufficient, unfocused, or still leaks raw context, the answer service falls back to deterministic repair.

The deterministic repair path tries multiple extractive builders, including:

- source-window answer,
- limitation answer,
- definition answer,
- used-for answer,
- config-file purpose answer,
- meaning answer,
- pipeline answer,
- command usefulness answer,
- example answer,
- why answer,
- list answer,
- mechanism answer,
- focused-entity answer,
- generic extractive fallback.

The first clean candidate with valid citations is returned.

## Raw Context Leakage Shortcut

If verifier issues mention raw retrieval or chunk metadata, repair immediately prefers deterministic repair.

This avoids asking the LLM to clean up a badly leaked answer when a safer extractive answer can be built directly from evidence.

## Accepting Or Rejecting Repair

After repair, the orchestrator verifies the repaired answer again.

The repaired answer replaces the original only when:

```text
repaired_verification.status == "verified"
```

If the repaired answer still fails, the original answer and original verification remain unless a later retrieval retry improves the result.

## Retrieval Retry After Repair

If repair does not produce a verified answer, the orchestrator may retry retrieval once.

Retry happens when:

- no citable evidence was found, or
- verification still failed,
- and the max retrieval attempts has not been reached.

The retry broadens document scope to all documents.

The retry result is accepted when it has:

- verified status with citations, or
- citations when the first attempt had none, or
- fewer verifier issues than the first attempt.

## Trace Visibility

The trace records:

```text
type: "verify"
type: "answer_repair"
type: "retrieval_retry_decision"
```

The `answer_repair` step includes:

- original verification issues,
- whether the answer changed,
- verification result after repair.

In the UI:

```text
Workspace -> Trace -> Timeline
```

Use this to see whether a bad answer failed because of:

- answer generation,
- verifier rejection,
- repair failure,
- retrieval failure.

## What Repair Does Not Do

Repair does not:

- retrieve new evidence by itself,
- use memory as PDF evidence,
- use MCP or tool output as PDF citations,
- guarantee factual correctness beyond retrieved evidence,
- hardcode fixes for one document.

Repair is a grounding and focus recovery layer, not a replacement for good retrieval and gold QA evaluation.

## How To Evaluate Repair

Use targeted eval after changing repair logic:

```cmd
venv\Scripts\python.exe scripts\eval_rag_quality.py --ids docker_watchtower_features,sora_world_simulator
```

Then run:

```cmd
venv\Scripts\python.exe scripts\run_regression.py
```

Useful report fields:

- `verification`
- `verifier_score`
- `missing_must_have`
- `triggered_must_not_have`
- `answer`

