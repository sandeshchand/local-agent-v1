from __future__ import annotations

import re


class ProcessExtractorMixin:
    def _challenge_steps_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        if "challenge" not in q or not any(term in q for term in ["step", "steps", "day", "practice"]):
            return ""

        candidates: list[tuple[int, int, list[str]]] = []
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            lower = text.lower()
            challenge_pos = lower.find("challenge")
            if challenge_pos < 0:
                continue
            start = max(0, challenge_pos - 80)
            end = self._first_marker_after(
                lower,
                ["why this works", "brain science", "tag your", "follow for", "comment your", "drop your"],
                challenge_pos + 120,
            )
            if end < 0:
                end = min(len(text), challenge_pos + 900)
            excerpt = self._clean_text(text[start:end])
            steps = self._numbered_day_steps(excerpt)
            if len(steps) < 2:
                steps = self._numbered_steps_after_marker(excerpt, marker="challenge")
            if len(steps) < 2:
                continue
            joined = " ".join(steps).lower()
            score = len(steps) * 8
            score += sum(3 for marker in ["day", "hook", "practice", "mirror", "friend", "feedback", "real life"] if marker in joined)
            candidates.append((score, -index, steps))

        if not candidates:
            return ""
        candidates.sort(reverse=True)
        _, negative_index, steps = candidates[0]
        citation = -negative_index
        selected = [f"- {step}. [{citation}]" for step in steps[:7]]
        duration_match = re.search(r"\b\d+\s*[- ]?\s*day\b", q)
        challenge_label = "challenge"
        if duration_match:
            duration_label = re.sub(r"\s+", "-", duration_match.group(0))
            challenge_label = f"{duration_label} challenge"
        return self._clean_final_answer(f"The {challenge_label} steps are: " + " ".join(selected), max_citation=len(results))
    def _numbered_day_steps(self, text: str) -> list[str]:
        pattern = re.compile(
            r"(?:^|\s)(?:\d+[.)]\s*)?"
            r"((?:Day|Days)\s+\d+(?:\s*[-\u2013\u2014]\s*\d+)?\s*:\s*.*?)(?="
            r"\s+\d+[.)]\s*(?:Day|Days)\s+\d+|\s+Why\s+This\s+Works|\s+Brain\s+Science|$)",
            flags=re.IGNORECASE,
        )
        return self._clean_numbered_steps(match.group(1) for match in pattern.finditer(text))
    def _numbered_steps_after_marker(self, text: str, marker: str) -> list[str]:
        lower = text.lower()
        start = lower.find(marker)
        if start >= 0:
            text = text[start:]
        pattern = re.compile(
            r"(?:^|\s)\d+[.)]\s*(.*?)(?=\s+\d+[.)]\s+|\s+Why\s+This\s+Works|\s+Brain\s+Science|$)",
            flags=re.IGNORECASE,
        )
        return self._clean_numbered_steps(match.group(1) for match in pattern.finditer(text))
    def _clean_numbered_steps(self, raw_steps) -> list[str]:
        steps: list[str] = []
        seen: set[str] = set()
        for raw in raw_steps:
            step = re.sub(r"\s+", " ", str(raw)).strip(" .:-")
            step = re.sub(r"\s*\([^)]{0,80}\)", lambda match: match.group(0), step).strip()
            if not step or len(step.split()) < 3:
                continue
            normalized = re.sub(r"\W+", " ", step.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            steps.append(step)
            if len(steps) >= 8:
                break
        return steps
    def _pipeline_extractive_answer(self, query: str, results: list[dict]) -> str:
        q = query.lower()
        if not any(term in q for term in ["pipeline", "workflow", "processing app", "app flow"]):
            return ""
        if not results:
            return ""

        combined = self._clean_text(" ".join((item.get("text") or "") for item in results))
        lower = combined.lower()
        pipeline_markers = [
            "load",
            "input",
            "file",
            "url",
            "image",
            "pdf",
            "model",
            "process",
            "generate",
            "output",
            "document",
            "export",
            "download",
            "preview",
            "interface",
            "ui",
        ]
        if sum(1 for marker in pipeline_markers if marker in lower) < 4:
            return ""

        focus = self._focus_entity_display(query)
        steps: list[str] = []

        def add_step(text: str, terms: list[str]) -> None:
            if any(self._similar_step(text, existing) for existing in steps):
                return
            citation = self._best_citation_for_terms(results, terms)
            steps.append(f"- {text}. [{citation}]")

        if any(term in lower for term in ["local", "upload", "file"]) and "url" in lower and any(term in lower for term in ["pdf", "image"]):
            add_step("Load PDFs or images from a local file/upload or a URL", ["local", "url", "pdf", "image"])

        if "load_model" in lower or ("load" in lower and "model" in lower):
            model_text = f"Load the {focus} model" if focus else "Load the model"
            add_step(model_text, ["load", "model"])

        generated_terms = self._pipeline_generated_terms(combined)
        if "generate" in lower or "stream" in lower or "output" in lower:
            generated_text = "Generate structured output for each page or image"
            if generated_terms:
                generated_text = f"Generate {', '.join(generated_terms[:2])} for each page or image"
            add_step(generated_text, ["generate", "output", "page", "image"])

        document_classes = self._pipeline_document_classes(combined)
        if document_classes:
            add_step(
                f"Create {' and '.join(document_classes[:3])} from the generated output",
                document_classes[:3],
            )

        formats = self._pipeline_export_formats(combined)
        if formats:
            add_step(f"Export the result as {', '.join(formats)}", formats)

        if any(term in lower for term in ["preview", "download", "interface", "ui", "gradio"]):
            ui_name = "Gradio UI" if "gradio" in lower else "UI"
            add_step(f"Render a preview and provide download controls in the {ui_name}", ["preview", "download", "ui", "interface"])

        if len(steps) < 3:
            extracted_steps = self._pipeline_comment_steps(results)
            for text, citation in extracted_steps:
                if any(self._similar_step(text, existing) for existing in steps):
                    continue
                steps.append(f"- {text}. [{citation}]")
                if len(steps) >= 6:
                    break

        if len(steps) < 3:
            return ""
        return self._clean_final_answer("The main pipeline is: " + " ".join(steps[:7]), max_citation=len(results))
    def _pipeline_generated_terms(self, text: str) -> list[str]:
        terms: list[str] = []
        for match in re.findall(r"\b[A-Z][A-Za-z0-9]*(?:Tags?|Markup|Output)\b", text):
            if match not in terms and len(match) > 3:
                terms.append(match)
        return terms
    def _pipeline_document_classes(self, text: str) -> list[str]:
        classes: list[str] = []
        code_like_matches = re.findall(r"\b([A-Z][A-Za-z0-9]*Document)\b(?=\s*(?:[.(]|=))", text)
        fallback_matches = re.findall(r"(?<![\"'])\b([A-Z][A-Za-z0-9]*Document)\b(?![\"'])", text)
        for match in [*code_like_matches, *fallback_matches]:
            if match not in classes:
                classes.append(match)
        return classes
    def _pipeline_export_formats(self, text: str) -> list[str]:
        formats: list[str] = []
        for match in re.findall(r"\b(?:Markdown|HTML|JSON|CSV|XML|TXT|PDF)\b", text):
            if match not in formats:
                formats.append(match)
        return formats
    def _pipeline_comment_steps(self, results: list[dict]) -> list[tuple[str, int]]:
        steps: list[tuple[str, int]] = []
        for index, item in enumerate(results, start=1):
            raw_text = (item.get("text") or "").replace("\r\n", "\n").replace("\r", "\n")
            for comment in re.findall(r"#\s*([^#\n]{8,120})", raw_text):
                cleaned = re.sub(r"\s+", " ", comment).strip(" .:-")
                if not cleaned:
                    continue
                if any(term in cleaned.lower() for term in ["load", "input", "process", "generate", "create", "export", "download", "preview"]):
                    steps.append((cleaned[0].upper() + cleaned[1:], index))
        return steps
    def _best_citation_for_terms(self, results: list[dict], terms: list[str]) -> int:
        scored: list[tuple[int, int]] = []
        normalized_terms = [term.lower() for term in terms if term]
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "").lower()
            score = sum(1 for term in normalized_terms if term.lower() in text)
            if score:
                scored.append((score, -index))
        if not scored:
            return 1
        scored.sort(reverse=True)
        return -scored[0][1]
    def _similar_step(self, text: str, existing: str) -> bool:
        text_terms = self._content_terms(text)
        existing_terms = self._content_terms(existing)
        if not text_terms or not existing_terms:
            return False
        overlap = len(text_terms & existing_terms)
        return overlap >= min(3, len(text_terms), len(existing_terms))
