from __future__ import annotations

import re


def tokenize(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def meaningful_query_terms(query: str) -> set[str]:
    stop_terms = {
        "what",
        "does",
        "review",
        "sora",
        "with",
        "from",
        "that",
        "this",
        "into",
        "their",
        "about",
        "core",
        "model",
        "use",
    }
    return {
        term
        for term in tokenize(query)
        if len(term) >= 4 and term not in stop_terms
    }


def focus_terms(query: str) -> set[str]:
    generic_terms = {
        "what",
        "which",
        "from",
        "paper",
        "document",
        "key",
        "feature",
        "features",
        "main",
        "some",
        "tell",
        "about",
        "explain",
        "describe",
        "according",
        "review",
        "use",
        "uses",
        "using",
        "docker",
    }
    original_tokens = re.findall(r"\b[A-Za-z][A-Za-z0-9_-]{3,}\b", query)
    terms: set[str] = set()
    for token in original_tokens:
        lower = token.lower()
        if lower in generic_terms:
            continue
        if any(char.isupper() for char in token[1:]) or token[:1].isupper():
            terms.add(lower)
        elif len(lower) >= 8:
            terms.add(lower)
    return terms


def focus_phrases(query: str) -> set[str]:
    generic_terms = {
        "what",
        "which",
        "from",
        "paper",
        "document",
        "article",
        "key",
        "features",
        "main",
        "some",
        "tell",
        "about",
        "explain",
        "describe",
        "according",
        "review",
        "how",
        "why",
        "does",
        "used",
    }
    phrases: set[str] = set()

    for match in re.finditer(
        r"\b[A-Z][A-Za-z0-9_-]*\b(?:\s+\b[A-Z][A-Za-z0-9_-]*\b)+",
        query,
    ):
        phrase_tokens = [
            token
            for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_-]*\b", match.group(0))
            if token.lower() not in generic_terms
        ]
        if len(phrase_tokens) < 2:
            continue
        phrase = " ".join(token.lower() for token in phrase_tokens)
        phrases.add(phrase)
        last = phrase_tokens[-1]
        if last.lower().endswith("s") and len(last) > 4:
            phrases.add(" ".join([*(token.lower() for token in phrase_tokens[:-1]), last[:-1].lower()]))
    return phrases


def focused_text(text: str, focus_units: set[str], radius: int = 2200) -> str:
    text_lower = text.lower()
    matches = [
        text_lower.find(term)
        for term in focus_units
        if text_lower.find(term) != -1
    ]
    matches = [match for match in matches if match >= 0]
    if not matches:
        return ""

    anchor = min(matches)
    start = max(0, anchor - radius // 3)
    end = min(len(text), anchor + radius)

    sentence_start = max(
        text.rfind(". ", 0, start),
        text.rfind("\n", 0, start),
    )
    if sentence_start >= 0:
        start = sentence_start + 1

    sentence_end_candidates = [
        text.find(". ", end),
        text.find("\n", end),
    ]
    sentence_end_candidates = [candidate for candidate in sentence_end_candidates if candidate != -1]
    if sentence_end_candidates:
        end = min(sentence_end_candidates) + 1

    return text[start:end].strip()
