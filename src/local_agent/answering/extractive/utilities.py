from __future__ import annotations

import re


class ExtractorUtilityMixin:
    def _select_category_facts(
        self,
        facts: list[str],
        category_markers: list[tuple[str, list[str]]],
        max_items: int,
    ) -> list[str]:
        selected: list[str] = []
        seen: set[str] = set()
        for _, markers in category_markers:
            best: tuple[int, int, str] | None = None
            for index, fact in enumerate(facts):
                fact_text = re.sub(r"\[\d+\]", "", fact)
                fact_lower = fact_text.lower()
                if self._looks_like_code_or_metadata_fact(fact_text) and not any(marker in fact_lower for marker in markers):
                    continue
                score = sum(3 for marker in markers if marker in fact_lower)
                if score <= 0:
                    continue
                if self._is_low_value_fact(fact_text):
                    score -= 4
                candidate = (score, -index, fact)
                if best is None or candidate > best:
                    best = candidate
            if best is None:
                continue
            fact = self._shorten_fact(best[2], max_words=36)
            normalized = re.sub(r"\W+", " ", fact.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append(f"- {fact}")
            if len(selected) >= max_items:
                break
        return selected
    def _shorten_fact(self, fact: str, max_words: int = 38) -> str:
        citation_match = re.search(r"\s*\[(\d+)\]\s*$", fact)
        citation = f" [{citation_match.group(1)}]" if citation_match else ""
        body = re.sub(r"\s*\[\d+\]\s*$", "", fact).strip()
        words = body.split()
        if len(words) > max_words:
            body = " ".join(words[:max_words]).rstrip(" ,;:")
        return f"{body}.{citation}" if citation and not body.endswith((".", "!", "?")) else f"{body}{citation}"
    def _phrase_acronym(self, phrase: str) -> str:
        tokens = re.findall(r"\b[A-Za-z][A-Za-z0-9-]*\b", phrase)
        if len(tokens) < 2:
            return ""
        return "".join(token[0] for token in tokens).lower()
    def _compress_list_fact(self, query: str, fact: str) -> str:
        q = query.lower()
        fact_lower = fact.lower()
        citation_match = re.search(r"\[(\d+)\]\s*$", fact)
        citation = f" [{citation_match.group(1)}]" if citation_match else ""

        if "pipeline" in q or "processing app" in q:
            parts: list[str] = []
            if "file" in fact_lower and ("url" in fact_lower or "upload" in fact_lower):
                parts.append("accepts a local file upload or URL")
            if "load" in fact_lower and "model" in fact_lower:
                parts.append("loads the model")
            if "generate" in fact_lower or "output" in fact_lower or "stream" in fact_lower:
                parts.append("generates the structured intermediate output")
            class_names = self._class_like_identifiers(fact)
            if class_names:
                parts.append(f"creates or uses {', '.join(class_names[:4])}")
            formats = [
                name.upper() if name in {"html", "json"} else name.title()
                for name in ["markdown", "html", "json"]
                if name in fact_lower
            ]
            if len(formats) >= 2:
                parts.append(f"exports {', '.join(formats)}")
            if "download" in fact_lower or "preview" in fact_lower:
                parts.append("prepares downloads and previews")
            if "ui" in fact_lower or "interface" in fact_lower or re.search(r"\bwith\s+[a-z]{1,4}\.", fact_lower):
                parts.append("renders the workflow in a user interface")
            if parts:
                return f"{'; '.join(dict.fromkeys(parts))}.{citation}"

        if "number" in q:
            expression_match = re.search(r"\b\d+\s*\*\*\s*\d+\b", fact)
            digit_match = re.search(r"\b\d+\s+digits?\b", fact_lower)
            if expression_match or digit_match:
                details = []
                if expression_match:
                    details.append(f"uses `{expression_match.group(0).replace(' ', '')}`")
                if digit_match:
                    details.append(f"prints {digit_match.group(0)}")
                return f"The example {' and '.join(details)}.{citation}"

        return fact
    def _class_like_identifiers(self, text: str) -> list[str]:
        identifiers: list[str] = []
        for match in re.findall(r"\b[A-Z][A-Za-z0-9_]{3,}\b", text):
            if match.lower() in {"Figure", "Table", "Section", "Page"}:
                continue
            if re.search(r"(Document|Model|Config|Settings|Field|Choice|Choices|Tag|Tags)$", match):
                identifiers.append(match)
        return list(dict.fromkeys(identifiers))
