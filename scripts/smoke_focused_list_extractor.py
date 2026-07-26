from __future__ import annotations

from local_agent.agent.verifier import Verifier
from local_agent.answering import AnswerService


class _NoLlmClient:
    def generate(self, prompt: str) -> str:
        raise RuntimeError("LLM should not be used by this smoke test")


def main() -> None:
    _assert_multiword_focus_list()
    _assert_single_entity_focus_list()
    print("focused list extractor smoke passed")


def _assert_multiword_focus_list() -> None:
    query = "What are the key strengths of Atlas Machines?"
    results = [
        {
            "title": "Synthetic ML Notes",
            "section_title": "Atlas Machines",
            "text": (
                "3. Atlas Machines The Atlas Machine (AM) algorithm is introduced here. "
                "One of the key strengths of AMs is their low memory footprint and high learning speed, "
                "making them efficient while delivering competitive performance. "
                "Unlike traditional models, it uses propositional logic and a reward-and-penalty mechanism. "
                "Key Features - Requires significantly less computation than deep learning models. "
                "Additionally, their simplicity enables implementation on low-power hardware. "
                "Random Kitchen Sinks (RKS) Kernel methods like Support Vector Machines (SVMs) "
                "and Gaussian Processes are powerful, but they struggle with large datasets. "
                "Symbolic Regression discovers mathematical expressions with genetic programming."
            ),
        }
    ]

    answer_service = AnswerService(_NoLlmClient())
    result = answer_service.answer_from_context_result(query=query, results=results)

    assert result.trace["path"] == "extractive_fast_path", result.trace
    assert "Atlas Machines" in result.answer, result.answer
    assert "low memory footprint" in result.answer, result.answer
    assert "reward-and-penalty" in result.answer, result.answer
    assert "less computation" in result.answer, result.answer
    assert "Random Kitchen Sinks" not in result.answer, result.answer
    assert "Symbolic Regression" not in result.answer, result.answer

    verification = Verifier().verify(result.answer, results, query)
    assert verification.status == "verified", verification.model_dump()


def _assert_single_entity_focus_list() -> None:
    query = "What are the key features of AtlasTool?"
    results = [
        {
            "title": "Synthetic Tool Notes",
            "section_title": "AtlasTool",
            "text": (
                "AtlasTool monitors running jobs and shows status, logs, and metrics in one view. "
                "Monitoring: Constantly watches jobs for version changes and health issues. "
                "Detecting: Prompts alerts when new versions are available. "
                "Updating: Fetches and applies safe updates to running jobs. "
                "OtherTool: Opens interactive shells and inspects unrelated images. "
                "Dive: Analyzes unrelated container layers."
            ),
        }
    ]

    answer_service = AnswerService(_NoLlmClient())
    result = answer_service.answer_from_context_result(query=query, results=results)

    assert result.trace["path"] == "extractive_fast_path", result.trace
    assert "AtlasTool" in result.answer, result.answer
    assert "monitors running jobs" in result.answer, result.answer
    assert "watches jobs" in result.answer, result.answer
    assert "new versions" in result.answer, result.answer
    assert "OtherTool" not in result.answer, result.answer
    assert "Dive" not in result.answer, result.answer

    verification = Verifier().verify(result.answer, results, query)
    assert verification.status == "verified", verification.model_dump()


if __name__ == "__main__":
    main()
