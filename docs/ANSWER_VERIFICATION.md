# Answer Verification

Answer verification checks whether a generated answer is grounded, focused, and safe to return.

The main implementation is in:

```text
src/local_agent/agent/verifier.py
src/local_agent/agent/orchestrator.py
src/local_agent/answering/service.py
```

## Where Verification Runs

For document questions, the orchestrator runs this flow:

```text
retrieve evidence
-> generate answer
-> verify answer
-> repair if needed
-> verify repaired answer
-> optionally retry retrieval
-> save trace
```

The verifier result is stored in the trace as:

```text
verification
```

The trace step is:

```text
type: "verify"
```

If repair runs, the trace also includes:

```text
type: "answer_repair"
```

## Verification Result

The verifier returns:

```text
status
issues
grounded
```

Possible status values currently used:

- `verified`
- `needs_more_info`

`grounded` is false when the answer fails a grounding rule such as missing citations, invalid citations, empty answer, or raw context leakage.

Some focus/intent problems add issues but may not set `grounded` to false.

## Main Checks

The verifier checks:

- citation presence when retrieved evidence exists,
- empty answer,
- raw retrieval/chunk metadata leakage,
- citation numbers that do not exist in the retrieved evidence list,
- answer focus compared with the question,
- answer shape compared with user intent,
- prominent entity drift,
- low overlap with relevant retrieved evidence.

## Citation Checks

If retrieved evidence exists, the answer should include citation markers like:

```text
[1]
[2]
```

The verifier checks that cited numbers are valid for the current evidence list.

Example issue:

```text
Answer cites unavailable evidence numbers: [7].
```

## Raw Context Leakage

The verifier flags answers that expose internal retrieval metadata such as:

- `[child chunk ...]`
- `chunk_id`
- `hybrid_score`
- `reranker_score`
- `Title:`
- `Section:`
- `Page:`

This protects the user experience from raw chunk dumps.

## Focus And Intent Checks

The verifier checks whether the answer matches the query shape.

Examples:

- A `why` question should usually include causal language such as `because`, `helps`, `allows`, or `enables`.
- A limitation question should mention limitations, challenges, constraints, failures, or issues.
- A representation/model-input question should mention representation, latent space, token, patch, compression, or related terms.
- A simple `what is` answer should not become a long broad overview unless the user asked for one.

## Entity Drift

The verifier tries to identify the focus entity in the query.

If the user asks about WatchTower, the answer should not drift into Sora, LazyDocker, Tsetlin Machines, or another prominent entity.

This is general-purpose. It is not a hardcoded Sora/Docker rule. It uses query entities and answer entities to detect drift.

## Evidence Overlap

For retrieved answers, the verifier checks whether the answer shares enough content terms with the most relevant retrieved evidence.

This catches cases where:

- retrieval found relevant chunks,
- but the answer ignores them,
- or the answer invents unrelated content.

The overlap check uses content terms, removes stop words, and looks at top evidence sentences.

## Repair Behavior

If verification fails and there are retrieved citations, the orchestrator calls:

```text
AnswerService.repair_answer()
```

Repair receives:

- query,
- current answer,
- retrieved evidence,
- verifier issues.

It asks the answer service to fix:

- missing directness,
- unsupported drift,
- raw chunk leakage,
- invalid citations,
- missing grounding.

If LLM repair is weak or still leaks raw context, the answer service can fall back to deterministic extractive repair.

The repaired answer is accepted only if verification passes after repair.

## Retrieval Retry

The orchestrator can make one generic retrieval retry when:

- no citable evidence was found, or
- verification still failed.

The retry uses full-corpus retrieval as a recovery mechanism for routing misses and unseen PDFs.

The retry is kept only when it improves verification/citations.

## What Verification Is Not

Verification is not a complete factual oracle.

It does not prove every statement is true. It checks local grounding and quality signals:

- Does the answer cite available evidence?
- Does it avoid raw retrieval leakage?
- Does it answer the exact question?
- Does it stay on the right entity?
- Does it overlap with retrieved evidence?

For stronger quality, use verification together with eval reports from `docs/EVALUATION.md`.

## How To Inspect Verification

From the UI:

1. Ask a question.
2. Open the `Trace` tab in the Workspace.
3. Check the verifier status, issues, repair status, and final citations.

From eval reports:

```text
eval/rag_quality_report.json
eval/rag_quality_batch_1_report.json
```

Look at:

- `verification`
- `verifier_score`
- `missing_must_have`
- `triggered_must_not_have`
- `answer`

