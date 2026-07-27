from __future__ import annotations

from local_agent.answering import AnswerService


class DummyChatClient:
    def generate(self, prompt: str) -> str:
        raise AssertionError("extractive smoke tests should not call the chat model")


def build_service() -> AnswerService:
    return AnswerService(chat_client=DummyChatClient())  # type: ignore[arg-type]


def assert_recommended_items_answer() -> None:
    service = build_service()
    query = "Which three tools does the article recommend for better container management?"
    results = [
        {
            "title": "Example Tools Article",
            "section_title": "Overview",
            "page_number": 1,
            "text": (
                "Meet three amazing tools: LazyDocker, Dive, and WatchTower "
                "game changing tools that will save you time, reduce headaches, "
                "and boost productivity."
            ),
        }
    ]

    answer = service._recommended_items_answer(query, results)

    assert "LazyDocker" in answer
    assert "Dive" in answer
    assert "WatchTower" in answer
    assert "save time" in answer
    assert "[1]" in answer
    assert service._high_confidence_extractive_rejection_reason(
        query=query,
        candidate=answer,
        results=results,
    ) == ""


def assert_setup_command_sequence_answer() -> None:
    service = build_service()
    query = "What setup and run commands does the tutorial provide?"
    results = [
        {
            "title": "Setup Tutorial",
            "section_title": "Setup Instructions",
            "page_number": 1,
            "text": (
                "Setup Instructions (Mac M1/M2/M3/M4 Recommended). "
                "This tutorial uses MLX and Apple's Metal-accelerated backend. "
                "pip install uv "
                "uv venv smoldocling-env "
                "source smoldocling-env/bin/activate "
                "uv pip install gradio mlx-vlm docling-core pillow pdf2image requests "
                "brew install poppler"
            ),
        },
        {
            "title": "Setup Tutorial",
            "section_title": "Running the App",
            "page_number": 2,
            "text": 'if __name__ == "__main__": app.launch() Running the App uv run main.py',
        },
    ]

    answer = service._source_window_answer(query, results)

    for expected in [
        "pip install uv",
        "uv venv smoldocling-env",
        "source smoldocling-env/bin/activate",
        "uv pip install gradio mlx-vlm docling-core pillow pdf2image requests",
        "brew install poppler",
        "uv run main.py",
        "127.0.0.1:7860",
    ]:
        assert expected in answer
    assert service._high_confidence_extractive_rejection_reason(
        query=query,
        candidate=answer,
        results=results,
    ) == ""

    weak_answer = "The command is `uv run main.py`. [2]"
    assert service._high_confidence_extractive_rejection_reason(
        query=query,
        candidate=weak_answer,
        results=results,
    ) == "command_coverage_missing"


def main() -> None:
    assert_recommended_items_answer()
    assert_setup_command_sequence_answer()
    print("Answer sequence extractor smoke test passed.")


if __name__ == "__main__":
    main()
