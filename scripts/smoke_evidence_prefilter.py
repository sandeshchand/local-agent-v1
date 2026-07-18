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
    judge = EvidenceJudge(chat_client, max_llm_judgments=6)
    results = [
        make_item(index, f"General background about video generation item {index}.")
        for index in range(12)
    ]
    results[10] = make_item(
        10,
        "The review highlights Sora spatial reasoning limitations, cause-and-effect failures, and issues with interactions.",
    )

    selected, judgments = judge.select_evidence(
        "What limitations of Sora does the review highlight?",
        results,
        max_items=4,
    )

    judged_ids = {judgment.item["chunk_id"] for judgment in judgments}
    selected_ids = {item["chunk_id"] for item in selected}

    assert chat_client.calls == 6
    assert len(judgments) == 6
    assert "chunk-10" in judged_ids
    assert "chunk-10" in selected_ids

    print("Evidence prefilter smoke test passed.")


if __name__ == "__main__":
    main()
