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

    role_chat_client = CountingChatClient()
    role_service = AnswerService(chat_client=role_chat_client)
    role_result = role_service.answer_from_context_result(
        "What roles can specialized agents play in a multi-agent coding architecture?",
        [
            {
                "chunk_id": "agent-roles",
                "title": "From Code Assistants to Agents",
                "section_title": "Multi-agent architecture",
                "page_number": 1,
                "text": (
                    "Rather than relying on a single monolithic agent, these tools use "
                    "multi-agent architectures where specialized agents collaborate. "
                    "Different agents take on special roles like planning agents that break "
                    "down problems, coding agents that implement functionality, testing agents "
                    "that generate test cases, debugging agents that identify and fix issues, "
                    "and documentation agents that explain code."
                ),
            }
        ],
    )

    assert role_chat_client.calls == 0
    assert role_result.trace["used_answer_fast_path"] is True
    assert "The roles are:" in role_result.answer
    assert "planning agents" in role_result.answer.lower()
    assert "documentation agents" in role_result.answer.lower()
    assert "[1]" in role_result.answer

    strength_chat_client = CountingChatClient()
    strength_service = AnswerService(chat_client=strength_chat_client)
    strength_result = strength_service.answer_from_context_result(
        "What are the key strengths of BetaModel?",
        [
            {
                "chunk_id": "strengths",
                "title": "Model Notes",
                "section_title": "BetaModel",
                "page_number": 1,
                "text": (
                    "BetaModel has several key strengths. "
                    "One strength is low memory usage. "
                    "Another strength is high learning speed. "
                    "A further strength is competitive performance. "
                    "It also has the strength of efficient hardware deployment. "
                    "Its interpretable rules are another strength."
                ),
            }
        ],
    )

    assert strength_chat_client.calls == 0
    assert strength_result.trace["used_answer_fast_path"] is True
    assert "The strengths are:" in strength_result.answer
    assert "competitive performance" in strength_result.answer.lower()
    assert "interpretable" in strength_result.answer.lower()
    assert "[1]" in strength_result.answer

    large_number_chat_client = CountingChatClient()
    large_number_service = AnswerService(chat_client=large_number_chat_client)
    large_number_result = large_number_service.answer_from_context_result(
        "How does Python handle very large integers according to the article?",
        [
            {
                "chunk_id": "large-numbers",
                "title": "Python Facts",
                "section_title": "Large numbers",
                "page_number": 1,
                "text": (
                    "Python Handles Large Numbers Automatically. "
                    "In many languages, you need special data types to handle big numbers. "
                    "But Python automatically manages large integers. "
                    "big_num = 10**100. "
                    "No int or long types - just use numbers normally. "
                    "Python dynamically allocates memory."
                ),
            }
        ],
    )

    assert large_number_chat_client.calls == 0
    assert large_number_result.trace["used_answer_fast_path"] is True
    assert "automatically manages large integers" in large_number_result.answer.lower()
    assert "int or long" in large_number_result.answer.lower()
    assert "dynamically allocates memory" in large_number_result.answer.lower()
    assert "10**100" in large_number_result.answer
    assert "[1]" in large_number_result.answer

    formula_chat_client = CountingChatClient()
    formula_service = AnswerService(chat_client=formula_chat_client)
    formula_result = formula_service.answer_from_context_result(
        "What is the article's three-part formula for a memorable one-minute introduction?",
        [
            {
                "chunk_id": "intro-formula",
                "title": "One-Minute Introductions",
                "section_title": "The 3-Part Formula",
                "page_number": 1,
                "text": (
                    "The 3-Part Formula (Steal This!) "
                    "1. The Hook: Start With a Story, Not Your Name. "
                    "2. The Highlight: Add a WTF Detail. "
                    "3. The Handoff: Make It About Them."
                ),
            }
        ],
    )

    assert formula_chat_client.calls == 0
    assert formula_result.trace["used_answer_fast_path"] is True
    assert "The formula is:" in formula_result.answer
    assert "hook" in formula_result.answer.lower()
    assert "highlight" in formula_result.answer.lower()
    assert "handoff" in formula_result.answer.lower()
    assert "[1]" in formula_result.answer

    assert (
        fast_service._has_low_value_candidate_items(
            "Sora works this way: "
            "- DALL\u00b7E 3 addresses short prompts by using LLMs to rewrite them into detailed instructions. [1] "
            "- This prompt expansion helps improve prompt following. [1]"
        )
        is False
    )
    assert fast_service._is_low_value_fact("This prompt expansion helps improve prompt following.") is False
    assert fast_service._definition_query_entity("What are the key features of LazyDocker?") == ""
    assert fast_service._definition_query_entity("What are the key strengths of Tsetlin Machines?") == ""
    assert fast_service._definition_query_entity("What is the article's three-part formula for starting with AI?") == ""
    assert fast_service._definition_query_entity("What is Sora?") == "Sora"
    assert fast_service._is_command_or_server_query("What steps does the article suggest for starting with AI?") is False
    assert fast_service._is_command_or_server_query("What command starts the HTTP server?") is True
    assert (
        fast_service._has_low_value_candidate_items(
            "Because: - Follow publication for more posts. [1] - 10K Followers \u00b7 3 Following. [1]"
        )
        is True
    )

    print("Answer generation budget smoke test passed.")


if __name__ == "__main__":
    main()
