from __future__ import annotations

from local_agent.answering import AnswerService


class CountingChatClient:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        return (
            "LazyDocker is a terminal UI for Docker and Docker Compose. "
            "It shows container status, logs, metrics, and supports quick container actions. [1]"
        )


def main() -> None:
    chat_client = CountingChatClient()
    service = AnswerService(chat_client=chat_client)
    results = [
        {
            "chunk_id": "docker-lazydocker",
            "title": "Stop Managing Docker",
            "section_title": "LazyDocker",
            "page_number": 1,
            "text": (
                "LazyDocker is a terminal UI for Docker and Docker Compose. "
                "Key features include viewing container status, logs, and metrics at a glance, "
                "restarting, removing, and rebuilding containers, monitoring resource usage, "
                "attaching to container shells, pruning unused resources, and mouse support."
            ),
        }
    ]

    answer_result = service.answer_from_context_result(
        "Summarize this Docker document.",
        results,
    )
    answer = answer_result.answer

    assert chat_client.calls == 1
    assert answer_result.trace["used_llm_generation"] is True
    assert answer_result.trace["used_answer_fast_path"] is False
    assert answer_result.trace["fast_path"]["reason"] == "unsupported_query_shape"
    assert "LazyDocker" in answer
    assert "terminal UI" in answer
    assert "logs" in answer
    assert "[1]" in answer

    fast_chat_client = CountingChatClient()
    fast_service = AnswerService(chat_client=fast_chat_client)
    fast_result = fast_service.answer_from_context_result(
        "What are the key features of LazyDocker?",
        results,
    )
    fast_answer = fast_result.answer

    assert fast_chat_client.calls == 0
    assert fast_result.trace["used_answer_fast_path"] is True
    assert fast_result.trace["fast_path"]["used"] is True
    assert fast_result.trace["fast_path"]["accepted_candidate_source"]
    assert "LazyDocker" in fast_answer
    assert "logs" in fast_answer
    assert "[1]" in fast_answer

    print("Answer generation budget smoke test passed.")


if __name__ == "__main__":
    main()
