# Feedback Analytics

Feedback analytics turns thumbs-up/thumbs-down clicks into a small review loop for RAG quality.

It is intentionally general-purpose. It does not contain document-specific keywords or PDF-specific rules.

## What It Adds

- `POST /api/feedback` stores or updates one rating per trace.
- `GET /api/feedback` lists recent feedback items, optionally filtered by `like` or `dislike`.
- `GET /api/feedback/summary` returns aggregate feedback counts and recent disliked traces.
- The web UI shows summary tiles above the feedback review list.

## Summary Fields

`GET /api/feedback/summary` returns:

- `total_count`
- `like_count`
- `dislike_count`
- `dislike_rate`
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

## Evaluation Workflow

When a disliked answer reveals a repeatable issue:

1. Add the query to `test/eval_multi_doc_rag.json`.
2. Add `must_have`, `should_have`, and `must_not_have` fields.
3. Run a targeted eval for that item.
4. Fix the general system behavior.
5. Run regression before committing.

This prevents us from overfitting to one chat result while still learning from real user feedback.

## Verification

Run:

```cmd
venv\Scripts\python.exe scripts\smoke_feedback_analytics.py
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```
