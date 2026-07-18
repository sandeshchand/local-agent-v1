# Answer Service Implementation

This document explains the answer service implementation.

The implementation lives in:

```text
src/local_agent/answering/
```

`AnswerService` is the final answer layer of the RAG system. It receives the user query and the retrieved/evidence-selected chunks, then returns a grounded answer with citations.

The design goal is general-purpose quality across unseen PDFs. The code must not rely on document-specific keyword hacks for one PDF, one author, or one benchmark item.

## Responsibilities

`AnswerService` handles five main responsibilities:

1. Build prompts for retrieval, direct answers, and tool answers.
2. Ask the local chat model for an answer when the evidence is good enough.
3. Repair or replace weak LLM output with generic extractive answers.
4. Clean citations, remove raw context leakage, and enforce focus.
5. Provide deterministic fallbacks for common document-question shapes.

It does not retrieve chunks. Retrieval is handled by `RetrievalService`, document routing by `DocumentRouter`, and evidence filtering by `EvidenceJudge`.

## Module Layout

The public API remains:

```python
from local_agent.answering import AnswerService
```

The implementation is split by responsibility:

```text
src/local_agent/answering/
  service.py          public AnswerService orchestration and answer priority flow
  prompts.py          retrieval, direct-answer, and tool-answer prompts
  tool_outputs.py     structured weather, file MCP, and SQLite MCP formatting
  source_windows.py   focused source-window extraction around high-signal text
  evidence_facts.py   evidence fact extraction and generic fallback facts
  extractors.py       combines deterministic answer-shape extractor mixins
  extractive/         focused extractor groups by answer shape
  query_intent.py     query focus, answer-shape, and quality heuristics
  cleaning.py         final cleanup, citation normalization, and leakage removal
```

The split uses mixins. This keeps the behavior stable while making each group easier to test and maintain. `AnswerService` still exposes the same methods used by the orchestrator:

- `answer_from_context()`
- `repair_answer()`
- `answer_direct()`
- `answer_from_tool_result()`

This package sits outside `retrieval` because it is not only a retrieval component. It also handles direct answers, tool answers, answer repair, and final response cleanup.

## Main Entry Points

### `answer_from_context()`

This is the main RAG answer path.

Flow:

```text
retrieved results
-> single-source filtering when needed
-> deterministic evidence facts
-> build retrieval prompt
-> ask local LLM
-> remove mixed abstention
-> focused rewrite only when the first answer is weak, unfocused, under-specific, or citation-unsafe
-> run generic extractive answer candidates
-> choose a better candidate when LLM answer is weak or incomplete
-> citation cleanup
-> focus-entity cleanup
-> final answer
```

The method intentionally combines LLM output with deterministic extractive repair. This is because local LLM answers can vary between runs and can miss small required facts even when retrieval found them.

For performance, the answer path avoids unnecessary LLM calls:

- deterministic evidence facts are built before the prompt,
- LLM fact extraction is used only when deterministic facts are empty or insufficient,
- focused rewrite is skipped when the first answer is already cited, focused, specific enough, and free of raw context leakage.

### `repair_answer()`

This is called by the orchestrator when the verifier says an answer has a problem.

It repairs:

- raw chunk/context leakage
- invalid or missing citations
- unsupported drift
- missing directness
- weak focus on the user query

If the LLM repair fails, it falls back to deterministic repair through `_deterministic_repair_answer()`.

### `answer_direct()`

This handles non-RAG direct responses, such as greetings and casual questions. It can receive memory context, but it must not pretend to have retrieved document evidence.

### `answer_from_tool_result()`

This handles tool output. It uses only the tool output and memory guidance. It should not add outside facts.

## Prompt Construction

### `build_retrieval_prompt()`

Builds the RAG prompt with:

- grounding rules
- citation rules
- memory guidance
- answer shape
- question-specific constraints
- generic facet checklist
- evidence facts
- retrieved context

Important rule:

```text
Use memory only for user preferences and project/process constraints. Do not use memory as document evidence.
```

That means memory can remind the agent of project policy, but PDF facts must still come from retrieved chunks.

### Evidence Facts

Before answering, the service first builds deterministic facts:

```python
_build_evidence_fact_list()
```

If deterministic facts are empty or insufficient, it falls back to:

```python
_extract_evidence_facts_with_llm()
```

This gives the answer prompt a compact fact list before the full context while avoiding a separate LLM call when the deterministic evidence is already strong.

The deterministic fact builder also gives extra weight to concrete example sentences such as `including`, `such as`, `for example`, `e.g.`, or `like ...` when those sentences match the query intent. This protects exact fact coverage for future PDFs where an important named example appears after a broader capability sentence.

## Candidate Answer Priority

After the first LLM answer, `answer_from_context()` computes many generic candidate answers.

Important candidates include:

- `_best_practices_extractive_answer`
- `_capability_extractive_answer`
- `_limitation_extractive_answer`
- `_definition_extractive_answer`
- `_used_for_extractive_answer`
- `_config_file_purpose_answer`
- `_meaning_extractive_answer`
- `_pipeline_extractive_answer`
- `_challenge_steps_answer`
- `_command_usefulness_answer`
- `_example_extractive_answer`
- `_why_extractive_answer`
- `_list_extractive_answer`
- `_mechanism_extractive_answer`
- `_focused_entity_extractive_answer`
- `_source_window_answer`

These are ordered carefully. More specific answer shapes should usually beat broad list extraction. For example:

- limitation answers should not be overwritten by generic list answers
- challenge-step answers should not be treated as limitation answers
- meaning/definition answers should not be overwritten by weaker why/list answers
- feature answers may be augmented with a short definition sentence when the evidence supports it

This priority logic is why small changes in `answer_from_context()` should always be followed by targeted eval.

## Generic Source-Window Answers

The source-window path is:

```python
_source_window_answer()
```

It extracts a focused window around high-signal markers in the retrieved text.

It supports question shapes like:

- setup or command questions
- reason or brain-science questions
- formula questions
- example questions
- main-message questions
- feature or analysis questions
- generic window fallback

Source-window answers are useful for Medium-style PDFs where nearby headings and list text often contain the exact answer.

## Generic Extractive Answers

The extractive methods are deterministic. They score facts from retrieved evidence and build concise cited answers.

Examples:

### Feature Questions

```python
_feature_window_answer()
_augment_feature_answer_with_intro()
```

Used for questions asking about features, capabilities, or analysis functions.

The augmenter can prepend a short definition sentence when the answer lists features but does not explain what the tool/model/system is.

### Limitation Questions

```python
_limitation_extractive_answer()
```

Covers generic limitation facets:

- physical/cause-and-effect
- spatial
- temporal
- irrelevant entities
- human-computer interaction
- usage/access/safety

These facets are generic. They are not tied to one PDF.

### Used-For Questions

```python
_used_for_extractive_answer()
```

Handles “used for” and “useful for” questions. It supports acronym matching and category coverage so it can answer technical model questions more reliably.

### Pipeline Questions

```python
_pipeline_extractive_answer()
```

Builds step answers around generic pipeline concepts:

- input file or URL
- model loading
- output generation
- document object creation
- export formats
- preview/download UI

### Challenge Step Questions

```python
_challenge_steps_answer()
```

Handles numbered practice/challenge steps such as `Day 1`, `Day 2`, etc.

This exists because the word “challenge” can mean either a limitation or a practice exercise. The code must avoid treating practice challenges as technical limitations.

### Command Questions

```python
_command_usefulness_answer()
```

Extracts commands and their stated purpose, especially for local server or setup commands.

### Best Practice Questions

```python
_best_practices_extractive_answer()
```

Extracts generic action recommendations from best-practice sections, such as use/configure/optimize/schedule/run/set/implement actions.

## Repair And Fallback

### `_deterministic_repair_answer()`

Runs a list of deterministic extractors and returns the first valid candidate.

This is used when:

- the LLM call fails
- verifier repair fails
- the answer contains raw retrieval metadata
- the answer has invalid citations

### `_generic_extractive_fallback()`

Last resort. It selects the best evidence facts and returns them with citations.

## Cleaning And Guardrails

Key methods:

```python
_clean_final_answer()
_strip_context_leakage()
_normalize_answer_citations()
_has_raw_context_leak()
_remove_mixed_abstention()
_ensure_focus_entity_mentioned()
```

These methods prevent:

- raw chunk metadata in answers
- invalid citation numbers
- citation ranges that do not map to retrieved items
- “context does not contain enough information” mixed with real answer content
- answers that omit the focused entity

## Query Understanding Helpers

Important helpers:

```python
_query_terms()
_query_intent_terms()
_intent_terms_from_query_terms()
_focus_entity_display()
_focus_phrases()
_entity_terms()
_matches_entity_terms()
```

These helpers keep the answer logic generic. They infer focus and intent from the query rather than checking for a specific PDF name.

## What Not To Do

Do not add document-specific branches such as:

```python
if "sora" in query:
    ...
if "watchtower" in query:
    ...
```

Instead, add generic behavior:

- feature extraction
- definition extraction
- limitation facets
- pipeline steps
- command usefulness
- numbered challenge steps
- acronym/entity matching
- section-title matching

Any new extractor should work for future PDFs from Medium, arXiv, docs, blog posts, and papers.

## Evaluation Guidance

When changing the answer service, run at least targeted eval for the affected shape.

Useful examples:

```cmd
venv\Scripts\python.exe scripts\eval_rag_quality.py --ids docker_lazydocker_features,docker_watchtower_features
venv\Scripts\python.exe scripts\eval_rag_quality.py --ids sora_limitations,ml_crfs
venv\Scripts\python.exe scripts\eval_rag_quality.py --ids smoldocling_doctags,intro_seven_day_challenge
```

Before commit, run the full benchmark:

```cmd
venv\Scripts\python.exe scripts\eval_rag_quality.py --eval-file benchmarks\gold_qa\eval_multi_doc_rag.json --output eval\rag_quality_report.json
```

Or run it in batches if the full command is slow.

## Maintenance Notes

The old large answer-service implementation has been split, but the priority order in `service.py` is still important. Many extractors can produce valid-looking answers, so the ordering decides which candidate wins.

When adding or changing logic:

- Keep document-specific keyword hacks out of the codebase.
- Put prompt changes in `prompts.py`.
- Put output formatting for tools in `tool_outputs.py`.
- Put final answer cleaning in `cleaning.py`.
- Put query-shape and focus heuristics in `query_intent.py`.
- Put deterministic extraction logic in `extractive/` or `source_windows.py`.
- Update eval coverage before changing answer priority.
- Run regression before committing.
