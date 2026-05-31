# Feedback Analytics

Feedback analytics turns thumbs-up/thumbs-down clicks into a small review loop for RAG quality.

It is intentionally general-purpose. It does not contain document-specific keywords or PDF-specific rules.

## What It Adds

- `POST /api/feedback` stores or updates one rating per trace.
- `GET /api/feedback` lists recent feedback items, optionally filtered by `like` or `dislike`.
- `GET /api/feedback/summary` returns aggregate feedback counts and recent disliked traces.
- `POST /api/eval-candidates` converts a disliked trace into a draft eval candidate.
- `GET /api/eval-candidates` lists draft candidates for review.
- `PATCH /api/eval-candidates/{candidate_id}` updates reviewed fields.
- `POST /api/eval-candidates/{candidate_id}/promote` writes the reviewed item into the gold QA file.
- `POST /api/eval-candidates/{candidate_id}/run-eval` runs one promoted candidate and returns the score.
- The web UI shows summary tiles above the feedback review list.
- Disliked feedback items include a `Create eval` button.
- Disliked feedback items can be tagged with a failure reason.

## Summary Fields

`GET /api/feedback/summary` returns:

- `total_count`
- `like_count`
- `dislike_count`
- `dislike_rate`
- `issue_counts`
- `latest_feedback_at`
- `recent_dislikes`

`recent_dislikes` is the first review queue for weak answers. Each item links back to the full trace, where we can inspect:

- selected plan mode,
- routed documents,
- retrieved evidence,
- verifier result,
- final answer.

## How To Use

1. Ask questions in the web UI.
2. Mark answers with thumbs up or thumbs down.
3. Open the right-side Feedback panel.
4. Review the summary tiles and disliked answers.
5. Click a disliked item to inspect the trace.
6. Decide whether the problem is retrieval, routing, evidence selection, answer generation, or verification.
7. Click `Create eval` when the weak answer should become a repeatable test candidate.

Supported failure tags:

- `wrong_document`
- `bad_retrieval`
- `weak_answer`
- `missing_citation`
- `tool_issue`
- `other`

Draft candidates are written to:

```text
data/evals/feedback_eval_candidates.json
```

This file is local generated data. It is not the gold benchmark.

Reviewed candidates can be promoted into:

```text
benchmarks/gold_qa/eval_multi_doc_rag.json
```

## Evaluation Workflow

When a disliked answer reveals a repeatable issue:

1. Click `Create eval` in the Feedback panel.
2. Open `data/evals/feedback_eval_candidates.json`.
3. In the UI Eval Drafts panel, fill `expected_answer`, `must_have`, `should_have`, and `must_not_have`.
4. Click `Promote` to write the reviewed item into `benchmarks/gold_qa/eval_multi_doc_rag.json`.
5. Click `Run eval` to score that promoted item.
6. Fix the general system behavior.
7. Run regression before committing.

This prevents us from overfitting to one chat result while still learning from real user feedback.

The draft candidate stores:

- original query,
- predicted answer,
- feedback failure tag,
- suggested document title,
- compact retrieved evidence,
- verifier payload,
- trace id and feedback id.

## Verification

Run:

```cmd
venv\Scripts\python.exe scripts\smoke_feedback_analytics.py
venv\Scripts\python.exe scripts\smoke_feedback_issue_tags.py
venv\Scripts\python.exe scripts\smoke_eval_candidates.py
venv\Scripts\python.exe scripts\smoke_eval_candidate_review.py
venv\Scripts\python.exe scripts\smoke_eval_candidate_run.py
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```
