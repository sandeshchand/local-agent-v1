from __future__ import annotations

import json

from local_agent.retrieval.evidence_judge import EvidenceJudge


class CountingChatClient:
    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        if "spatial reasoning limitations" in prompt:
            return json.dumps(
                {
                    "label": "MAIN_ANSWER",
                    "reason": "The chunk directly names Sora limitations.",
                }
            )
        return json.dumps(
            {
                "label": "BACKGROUND",
                "reason": "The chunk is related background.",
            }
        )


def make_item(index: int, text: str) -> dict:
    return {
        "chunk_id": f"chunk-{index}",
        "section_title": "Sora review",
        "title": "SORA",
        "text": text,
        "source": "parent_context",
        "hybrid_score": 1.0 / (index + 1),
    }


def main() -> None:
    chat_client = CountingChatClient()
    judge = EvidenceJudge(chat_client, max_llm_judgments=6, enable_fast_path=False)
    results = [
        make_item(index, f"General background about video generation item {index}.")
        for index in range(12)
    ]
    results[10] = make_item(
        10,
        "The review highlights Sora spatial reasoning limitations, cause-and-effect failures, and issues with interactions.",
    )

    selected, judgments, trace = judge.select_evidence_with_trace(
        "What limitations of Sora does the review highlight?",
        results,
        max_items=4,
    )

    judged_ids = {judgment.item["chunk_id"] for judgment in judgments}
    selected_ids = {item["chunk_id"] for item in selected}

    assert chat_client.calls == 6
    assert len(judgments) == 6
    assert trace["path"] == "llm_judge"
    assert trace["used_evidence_fast_path"] is False
    assert trace["llm_judgment_count"] == 6
    assert "chunk-10" in judged_ids
    assert "chunk-10" in selected_ids

    fast_chat_client = CountingChatClient()
    fast_judge = EvidenceJudge(fast_chat_client, max_llm_judgments=6)
    fast_results = [
        make_item(1, "AlphaTool overview and related background."),
        make_item(
            2,
            "AlphaTool key features include monitoring pipelines, restarting jobs, and showing resource metrics.",
        ),
        make_item(
            3,
            "AlphaTool also helps teams inspect logs and review failed tasks from one interface.",
        ),
        make_item(4, "A general introduction to unrelated automation platforms."),
    ]

    fast_selected, fast_judgments, fast_trace = fast_judge.select_evidence_with_trace(
        "What are the key features of AlphaTool?",
        fast_results,
        max_items=3,
    )

    assert fast_chat_client.calls == 0
    assert fast_trace["path"] == "deterministic_fast_path"
    assert fast_trace["used_evidence_fast_path"] is True
    assert fast_trace["fast_path_shape"] == "list"
    assert fast_judgments
    assert any("fast path" in judgment.reason for judgment in fast_judgments)
    assert any("monitoring pipelines" in item["text"] for item in fast_selected)

    role_chat_client = CountingChatClient()
    role_judge = EvidenceJudge(role_chat_client, max_llm_judgments=6)
    role_results = [
        make_item(1, "General background about code assistant products."),
        make_item(
            2,
            (
                "Multi-agent coding architectures use specialized agents that collaborate. "
                "Roles include planning agents, coding agents, testing agents, debugging agents, "
                "and documentation agents."
            ),
        ),
        make_item(3, "Unrelated information about model pricing and release dates."),
    ]

    role_selected, _, role_trace = role_judge.select_evidence_with_trace(
        "What roles can specialized agents play in a multi-agent coding architecture?",
        role_results,
        max_items=3,
    )

    assert role_chat_client.calls == 0
    assert role_trace["path"] == "deterministic_fast_path"
    assert role_trace["fast_path_shape"] == "list"
    assert any("planning agents" in item["text"] for item in role_selected)

    strength_chat_client = CountingChatClient()
    strength_judge = EvidenceJudge(strength_chat_client, max_llm_judgments=6)
    strength_results = [
        make_item(1, "General background about machine learning models."),
        make_item(
            2,
            (
                "BetaModel key strengths include low memory usage, high learning speed, "
                "competitive performance, efficient hardware deployment, and interpretable rules."
            ),
        ),
        make_item(3, "Unrelated historical context about earlier algorithms."),
    ]

    strength_selected, _, strength_trace = strength_judge.select_evidence_with_trace(
        "What are the key strengths of BetaModel?",
        strength_results,
        max_items=3,
    )

    assert strength_chat_client.calls == 0
    assert strength_trace["path"] == "deterministic_fast_path"
    assert strength_trace["fast_path_shape"] == "list"
    assert any("low memory usage" in item["text"] for item in strength_selected)

    large_number_chat_client = CountingChatClient()
    large_number_judge = EvidenceJudge(large_number_chat_client, max_llm_judgments=6)
    large_number_results = [
        make_item(1, "General background about programming language syntax."),
        make_item(
            2,
            (
                "The language automatically manages large integers. "
                "There is no need for special data types or separate int or long types. "
                "A value like 10**100 works because memory is dynamically allocated."
            ),
        ),
        make_item(3, "Unrelated information about list indexing."),
    ]

    large_number_selected, _, large_number_trace = large_number_judge.select_evidence_with_trace(
        "How does the language handle very large integers?",
        large_number_results,
        max_items=3,
    )

    assert large_number_chat_client.calls == 0
    assert large_number_trace["path"] == "deterministic_fast_path"
    assert large_number_trace["fast_path_shape"] == "mechanism"
    assert any("10**100" in item["text"] for item in large_number_selected)

    print("Evidence prefilter smoke test passed.")


if __name__ == "__main__":
    main()
