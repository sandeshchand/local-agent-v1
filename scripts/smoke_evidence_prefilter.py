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

    formula_chat_client = CountingChatClient()
    formula_judge = EvidenceJudge(formula_chat_client, max_llm_judgments=6)
    formula_results = [
        make_item(1, "General background about communication and short presentations."),
        make_item(
            2,
            (
                "The article gives a three-part formula for memorable introductions: "
                "1. The Hook starts with a story. "
                "2. The Highlight adds a surprising detail. "
                "3. The Handoff makes the ending about the other person."
            ),
        ),
        make_item(3, "Unrelated publication metadata and follow-up links."),
    ]

    formula_selected, _, formula_trace = formula_judge.select_evidence_with_trace(
        "What is the article's three-part formula for a memorable one-minute introduction?",
        formula_results,
        max_items=3,
    )

    assert formula_chat_client.calls == 0
    assert formula_trace["path"] == "deterministic_fast_path"
    assert formula_trace["fast_path_shape"] == "list"
    assert any("The Hook" in item["text"] for item in formula_selected)

    env_chat_client = CountingChatClient()
    env_judge = EvidenceJudge(env_chat_client, max_llm_judgments=6)
    env_results = [
        make_item(1, "General background about application configuration."),
        make_item(
            2,
            (
                "For local development, declaring environment variables on the machine is "
                "inconvenient, slow, and messy. A .env file stores environment variables "
                "such as API keys, database URLs, and tokens in key : value format."
            ),
        ),
        make_item(3, "Unrelated documentation about deployment pipelines."),
    ]

    env_selected, _, env_trace = env_judge.select_evidence_with_trace(
        "Why does the article recommend using a .env file during local development?",
        env_results,
        max_items=3,
    )

    assert env_chat_client.calls == 0
    assert env_trace["path"] == "deterministic_fast_path"
    assert env_trace["fast_path_shape"] == "explanation"
    assert any("slow" in item["text"] and "API keys" in item["text"] for item in env_selected)

    steps_chat_client = CountingChatClient()
    steps_judge = EvidenceJudge(steps_chat_client, max_llm_judgments=6)
    steps_results = [
        make_item(1, "General motivation about earning side income with new tools."),
        make_item(
            2,
            (
                "Want to start? Do this first: "
                "1. Pick one skill you already have. "
                "2. Ask AI tools to help you draft, research, or brainstorm faster. "
                "3. Package the skill as a service. "
                "4. Go where people already need help. "
                "5. Do it messy, do it fast, and do not overthink it."
            ),
        ),
        make_item(3, "Unrelated author biography and publication links."),
    ]

    steps_selected, _, steps_trace = steps_judge.select_evidence_with_trace(
        "What first steps does the article recommend for starting a side hustle?",
        steps_results,
        max_items=3,
    )

    assert steps_chat_client.calls == 0
    assert steps_trace["path"] == "deterministic_fast_path"
    assert steps_trace["fast_path_shape"] == "list"
    assert any("Pick one skill" in item["text"] for item in steps_selected)

    command_chat_client = CountingChatClient()
    command_judge = EvidenceJudge(command_chat_client, max_llm_judgments=6)
    command_results = [
        make_item(1, "General background about local developer tools."),
        make_item(
            2,
            (
                "The tool has a built-in web server. You can start it with a single command: "
                "tool serve 8000."
            ),
        ),
        make_item(
            3,
            (
                "Why is this useful? You can quickly test web applications, serve files in a "
                "browser, share files over a local network, and avoid third-party tools."
            ),
        ),
    ]

    command_selected, _, command_trace = command_judge.select_evidence_with_trace(
        "What built-in server command does the article provide and why is it useful?",
        command_results,
        max_items=3,
    )

    assert command_chat_client.calls == 0
    assert command_trace["path"] == "deterministic_fast_path"
    assert command_trace["fast_path_shape"] == "usage"
    assert any("single command" in item["text"] for item in command_selected)
    assert any("local network" in item["text"] for item in command_selected)

    technical_usage_chat_client = CountingChatClient()
    technical_usage_judge = EvidenceJudge(technical_usage_chat_client, max_llm_judgments=6)
    technical_usage_results = [
        make_item(1, "General background about sequence models and classifiers."),
        make_item(
            2,
            (
                "Conditional Random Fields (CRFs) are probabilistic models used for "
                "structured prediction. Unlike traditional classifiers that make independent "
                "predictions, CRFs take context into account, making them useful for sequential "
                "data. A simplified NER-like format is shown as an example dataset."
            ),
        ),
        make_item(3, "Unrelated information about recommendation systems and advertising."),
    ]

    technical_usage_selected, _, technical_usage_trace = technical_usage_judge.select_evidence_with_trace(
        "What are Conditional Random Fields used for?",
        technical_usage_results,
        max_items=3,
    )

    assert technical_usage_chat_client.calls == 0
    assert technical_usage_trace["path"] == "deterministic_fast_path"
    assert technical_usage_trace["fast_path_shape"] == "usage"
    assert any("structured prediction" in item["text"] for item in technical_usage_selected)
    assert any("NER-like format" in item["text"] for item in technical_usage_selected)

    pipeline_chat_client = CountingChatClient()
    pipeline_judge = EvidenceJudge(pipeline_chat_client, max_llm_judgments=6)
    pipeline_results = [
        make_item(1, "General background about document understanding tools."),
        make_item(
            2,
            (
                "The app workflow starts by loading PDFs or images from an upload, local file, "
                "or URL. It then loads the model and generates DocTags output for each page."
            ),
        ),
        make_item(
            3,
            (
                "The process creates a DocTagsDocument and a DoclingDocument, then exports "
                "Markdown, HTML, or JSON."
            ),
        ),
        make_item(
            4,
            "The Gradio UI renders a preview and provides download controls for the result.",
        ),
    ]

    pipeline_selected, _, pipeline_trace = pipeline_judge.select_evidence_with_trace(
        "What is the main pipeline of the document processing app?",
        pipeline_results,
        max_items=4,
    )

    assert pipeline_chat_client.calls == 0
    assert pipeline_trace["path"] == "deterministic_fast_path"
    assert pipeline_trace["fast_path_shape"] == "pipeline"
    assert any("PDFs or images" in item["text"] for item in pipeline_selected)
    assert any("DocTagsDocument" in item["text"] for item in pipeline_selected)
    assert any("Gradio UI" in item["text"] for item in pipeline_selected)

    print("Evidence prefilter smoke test passed.")


if __name__ == "__main__":
    main()
