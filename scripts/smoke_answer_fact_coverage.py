from __future__ import annotations

from local_agent.answering import AnswerService


class ChatClientStub:
    def generate(self, prompt: str) -> str:
        return "AlphaSim is described as a simulation platform because it models physical scenes. [1]"


def main() -> None:
    service = AnswerService(chat_client=ChatClientStub())
    results = [
        {
            "chunk_id": "alpha-sim-1",
            "title": "AlphaSim Technical Note",
            "section_title": "Capabilities",
            "page_number": 1,
            "text": (
                "AlphaSim trains at scale to simulate aspects of the physical world. "
                "It exhibits spatial consistency, camera coherence, and persistent objects. "
                "Moreover, AlphaSim simulates digital environments like BlockCraft while maintaining visual fidelity."
            ),
        }
    ]

    facts = service._build_evidence_fact_list(
        "Why is AlphaSim described as a world simulator?",
        results,
        max_facts=8,
    )
    answer = service.answer_from_context(
        "Why is AlphaSim described as a world simulator?",
        results,
    )

    assert "BlockCraft" in facts
    assert "BlockCraft" in answer
    assert "digital environments" in answer
    assert "[1]" in answer

    print("Answer fact coverage smoke test passed.")


if __name__ == "__main__":
    main()
