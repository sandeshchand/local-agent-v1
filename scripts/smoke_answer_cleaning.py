from __future__ import annotations

from local_agent.answering import AnswerService


class ChatClientStub:
    def generate(self, prompt: str) -> str:
        raise AssertionError("Answer cleaning smoke should not call the LLM.")


def main() -> None:
    service = AnswerService(chat_client=ChatClientStub())
    messy = (
        "The main message is: Let\u00e2\u20ac\u2122s kill a myth real quick. "
        "You don\u00e2\u20ac\u2122t need to burn the boats "
        "You don\u00e2\u20ac\u2122t need to burn the boats. [1]"
    )

    cleaned = service._clean_final_answer(messy, max_citation=1)

    assert "Let\u00e2" not in cleaned
    assert "don\u00e2" not in cleaned
    assert "Let's" in cleaned
    assert "don't" in cleaned
    assert cleaned.count("You don't need to burn the boats") == 1
    assert "[1]" in cleaned

    evidence_text = service._clean_text("It\u00e2\u20ac\u2122s useful because it saves time.")
    assert evidence_text == "It's useful because it saves time."

    print("Answer cleaning smoke test passed.")


if __name__ == "__main__":
    main()
