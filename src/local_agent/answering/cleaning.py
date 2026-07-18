from __future__ import annotations

import re


class AnswerCleaningMixin:
    def _clean_final_answer(self, answer: str, max_citation: int | None = None) -> str:
        answer = self._repair_mojibake(answer)
        answer = re.sub(r"\[child chunk \d+ \| page [^\]]+\]\s*", "", answer)
        answer = re.sub(r"\b\d+\s+(?=\[child chunk)", "", answer)
        answer = self._strip_context_leakage(answer)
        answer = re.sub(
            r"^\s*Based on (?:the )?(?:provided )?(?:context|evidence|retrieved evidence)(?: provided)?[:,]?\s*",
            "",
            answer,
            flags=re.IGNORECASE,
        )
        answer = re.sub(
            r"(\[\d+\])\s+[A-Z][^.\n]{10,}\|\s*by\s+[^.\n]+$",
            r"\1",
            answer,
            flags=re.IGNORECASE,
        )
        answer = re.sub(r"\s+-\s+(?=[A-Z][A-Za-z0-9 /&-]{0,48}:)", "\n- ", answer)
        answer = re.sub(
            r"(?:^|\n)-?\s*Some (?:of )?the key features(?: of [^:]+)? include:\s*",
            "\n",
            answer,
            flags=re.IGNORECASE,
        )
        answer = re.sub(r"\s+Citations:\s+\[\d+\].*$", "", answer, flags=re.IGNORECASE | re.DOTALL)
        answer = answer.replace("simu- late", "simulate")
        answer = answer.replace("signif- icantly", "significantly")
        answer = answer.replace("gener- ation", "generation")
        answer = answer.replace("remain- ing", "remaining")
        answer = re.sub(r"\bAbstract\b\s*", "", answer, flags=re.IGNORECASE)
        answer = self._normalize_answer_citations(answer, max_citation=max_citation)
        answer = self._dedupe_repeated_spans(answer)
        answer = re.sub(r"\s+", " ", answer)
        return answer.strip()
    def _repair_mojibake(self, text: str) -> str:
        if not text:
            return text

        best = self._replace_common_mojibake(text)
        if not self._looks_like_mojibake(best):
            return best

        for encoding in ["cp1252", "latin-1"]:
            try:
                candidate = text.encode(encoding).decode("utf-8")
            except UnicodeError:
                continue
            candidate = self._replace_common_mojibake(candidate)
            if self._mojibake_score(candidate) < self._mojibake_score(best):
                best = candidate
        return best
    def _replace_common_mojibake(self, text: str) -> str:
        replacements = {
            "\u00e2\u20ac\u2122": "'",
            "\u00e2\u0080\u0099": "'",
            "\u00e2\u20ac\u02dc": "'",
            "\u00e2\u0080\u0098": "'",
            "\u00e2\u20ac\u0153": '"',
            "\u00e2\u0080\u009c": '"',
            "\u00e2\u20ac\ufffd": '"',
            "\u00e2\u0080\u009d": '"',
            "\u00e2\u20ac\u201c": "-",
            "\u00e2\u0080\u0093": "-",
            "\u00e2\u20ac\u201d": "-",
            "\u00e2\u0080\u0094": "-",
            "\u00e2\u20ac\u00a6": "...",
            "\u00e2\u0080\u00a6": "...",
            "\u00c2\u00b0": "\u00b0",
            "\u00c2\u00b7": "-",
            "\u00c2\u00a0": " ",
            "\u00c2": "",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text
    def _looks_like_mojibake(self, text: str) -> bool:
        return self._mojibake_score(text) > 0
    def _mojibake_score(self, text: str) -> int:
        markers = [
            "\u00e2",
            "\u00c2",
            "\u00c3",
            "\u0080",
            "\u0098",
            "\u0099",
            "\u009c",
            "\u009d",
        ]
        return sum(text.count(marker) for marker in markers)
    def _dedupe_repeated_spans(self, answer: str) -> str:
        previous = None
        while previous != answer:
            previous = answer
            answer = re.sub(
                r"\b((?:[A-Za-z0-9][A-Za-z0-9'\u2019.-]*\s+){3,}[A-Za-z0-9][A-Za-z0-9'\u2019.-]*)(?:\s+\1\b)+",
                r"\1",
                answer,
                flags=re.IGNORECASE,
            )

        sentences = re.split(r"(?<=[.!?])\s+", answer)
        deduped: list[str] = []
        previous_key = ""
        for sentence in sentences:
            key = re.sub(r"\[\d+\]", "", sentence).strip().lower()
            key = re.sub(r"\W+", " ", key).strip()
            if key and key == previous_key:
                continue
            deduped.append(sentence)
            previous_key = key
        return " ".join(deduped)
    def _strip_context_leakage(self, answer: str) -> str:
        answer = re.sub(r"(?im)^\s*(?:Title|Section|Page|Score|Text)\s*:\s*.*$", "", answer)
        answer = re.sub(
            r"\b(?:Follow publication|Published in|Get an email whenever|By signing up)[^.!?]{0,180}",
            "",
            answer,
            flags=re.IGNORECASE,
        )
        answer = re.sub(
            r"\b(?:\d+(?:\.\d+)?K\s+)?Followers?\s*(?:·\s*\d+\s+Following)?[^.!?]{0,120}",
            "",
            answer,
            flags=re.IGNORECASE,
        )
        return answer
    def _has_raw_context_leak(self, answer: str) -> bool:
        answer_lower = answer.lower()
        raw_markers = [
            "[child chunk",
            "retrieved chunk",
            "chunk_id",
            "hybrid_score",
            "reranker_score",
            "title:",
            "section:",
            "score:",
            "text:",
            "follow publication",
            "get an email whenever",
            "by signing up",
        ]
        if any(marker in answer_lower for marker in raw_markers):
            return True
        return False
    def _normalize_answer_citations(self, answer: str, max_citation: int | None = None) -> str:
        def replace_multi(match: re.Match[str]) -> str:
            numbers = [int(number) for number in re.findall(r"\d+", match.group(1))]
            valid_numbers = [
                number
                for number in numbers
                if number >= 1 and (max_citation is None or number <= max_citation)
            ]
            if not valid_numbers:
                return ""
            return " ".join(f"[{number}]" for number in dict.fromkeys(valid_numbers))

        answer = re.sub(r"\[((?:\d+\s*,\s*)+\d+)\]", replace_multi, answer)

        if max_citation is not None:
            answer = re.sub(
                r"\[(\d+)\]",
                lambda match: match.group(0)
                if 1 <= int(match.group(1)) <= max_citation
                else "",
                answer,
            )

        answer = re.sub(r"(?:^|\s)-\s*(?:\[\d+\]\s*)+(?=$|\s+-)", " ", answer)
        return re.sub(r"\s+([,.])", r"\1", answer)
    def _remove_mixed_abstention(self, answer: str) -> str:
        lines = [
            line
            for line in answer.splitlines()
            if "provided context does not contain enough information" not in line.lower()
            and "does not contain enough information" not in line.lower()
        ]
        cleaned = "\n".join(lines).strip()
        return cleaned or answer
    def _is_insufficient_answer(self, answer: str) -> bool:
        normalized = answer.strip().lower()
        return (
            "does not contain enough information" in normalized
            or "not enough information" in normalized
            or "retrieved context does not directly answer" in normalized
        )
    def _direct_fallback(self, query: str) -> str:
        q = query.strip().lower()

        greeting_map = {
            "hi": "Hello! How can I help you today?",
            "hello": "Hello! How can I help you today?",
            "hey": "Hey! How can I help you today?",
            "namaste": "Namaste! How can I help you today?",
            "namaskar": "Namaskar! How can I help you today?",
            "good morning": "Good morning! How can I help you today?",
            "good afternoon": "Good afternoon! How can I help you today?",
            "good evening": "Good evening! How can I help you today?",
        }

        if q in greeting_map:
            return greeting_map[q]

        return "I'm here and ready to help. Could you rephrase your question?"
