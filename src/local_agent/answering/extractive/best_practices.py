from __future__ import annotations

import re


class BestPracticeExtractorMixin:
    def _best_practices_extractive_answer(self, query: str, results: list[dict]) -> str:
        if "best practice" not in query.lower():
            return ""

        action_patterns = [
            r"Use\s+[A-Z][A-Za-z0-9_-]+\s+for\s+Development",
            r"Optimize\s+with\s+[A-Z][A-Za-z0-9_-]+",
            r"Configure\s+[A-Z][A-Za-z0-9_-]+\s+Wisely",
            r"Keep it open[^.]+?(?:management|access|workflow)",
            r"Create custom keybindings[^.]+?(?:operations|actions|tasks)",
            r"Run\s+[A-Z][A-Za-z0-9_-]+\s+analysis[^.]+?(?:production|deployment)",
            r"Set\s+[^.]+?thresholds[^.]+?(?:pipelines|builds|checks)",
            r"Use multi-stage builds[^.]+?(?:feedback|optimization|images)",
            r"Start with monitoring[^.]+?(?:containers|services|targets)",
            r"Implement proper notification systems",
            r"Schedule updates[^.]+?(?:periods|windows|traffic)",
        ]

        selected: list[str] = []
        seen: set[str] = set()
        citation_index = 1
        for index, item in enumerate(results, start=1):
            text = self._clean_text(item.get("text") or "")
            lower = text.lower()
            if "best practices" not in lower and "best practice" not in lower:
                continue
            start = min(
                position
                for position in [lower.find("best practices"), lower.find("best practice")]
                if position >= 0
            )
            end_candidates = [
                lower.find("why these tools matter", start),
                lower.find("conclusion", start),
                lower.find("let's connect", start),
            ]
            end_candidates = [position for position in end_candidates if position > start]
            end = min(end_candidates) if end_candidates else min(len(text), start + 1800)
            excerpt = text[start:end]
            citation_index = index
            for pattern in action_patterns:
                for match in re.finditer(pattern, excerpt, flags=re.IGNORECASE):
                    action = re.sub(r"\s+", " ", match.group(0)).strip(" .:-")
                    if len(action.split()) < 3:
                        continue
                    action_lower = action.lower()
                    if action_lower in seen:
                        continue
                    seen.add(action_lower)
                    selected.append(action)
            if selected:
                break

        if not selected:
            generic_selected: list[tuple[str, int]] = []
            for index, item in enumerate(results, start=1):
                text = self._clean_text(item.get("text") or "")
                for action in self._generic_best_practice_actions(text):
                    action_lower = action.lower()
                    if action_lower in seen:
                        continue
                    seen.add(action_lower)
                    generic_selected.append((action, index))
                if len(generic_selected) >= 8:
                    break

            if not generic_selected:
                return ""
            return self._clean_final_answer(
                "Best practices include: "
                + " ".join(f"- {action}. [{index}]" for action, index in generic_selected[:8])
            )

        return self._clean_final_answer(
            "Best practices include: "
            + " ".join(f"- {action}. [{citation_index}]" for action in selected[:12])
        )
    def _generic_best_practice_actions(self, text: str) -> list[str]:
        lower = text.lower()
        if not any(marker in lower for marker in ["best practice", "effective practice", "code quality", "quality"]):
            return []

        actions: list[str] = []

        def add(action: str) -> None:
            action = re.sub(r"\s+", " ", action).strip(" .:-")
            if len(action.split()) < 3:
                return
            if action.lower() not in {existing.lower() for existing in actions}:
                actions.append(action)

        prompt_match = re.search(
            r"(?i)effective practices include:\s*(.+?)(?=developers who|to maintain|although|ai-generated|best practices|$)",
            text,
        )
        if prompt_match:
            prompt_block = prompt_match.group(1)
            prompt_parts = [
                re.sub(r"\s+", " ", part).strip(" .:-")
                for part in re.split(
                    r"(?=\b(?:Providing|Including|Specifying|Referencing|Using|Configuring|Applying|Keeping|Running|Maintaining|Writing|Documenting|Reviewing)\b)",
                    prompt_block,
                )
                if len(part.split()) >= 3
            ]
            if any("specific prompting" in lower or "detailed specification" in part.lower() for part in prompt_parts):
                add(
                    "Use clear and specific prompting with detailed specifications, examples, constraints, and existing codebase patterns"
                )
            else:
                for part in prompt_parts[:4]:
                    add(part)

        if any(marker in lower for marker in ["coding standards", "style guides", "formatters", "linters"]):
            standards_bits = []
            if "coding standards" in lower or "internal standards" in lower:
                standards_bits.append("coding standards")
            if "style guide" in lower:
                standards_bits.append("style guides")
            action = "Align generated code with " + " and ".join(standards_bits or ["team standards"])
            if "formatter" in lower or "linter" in lower:
                action += ", and apply automatic formatters and linters after generation"
            add(action)

        if any(marker in lower for marker in ["human review", "human oversight", "trust but verify"]):
            add("Keep human oversight and do not let AI-generated code bypass human review")

        if any(marker in lower for marker in ["unit tests", "integration tests", "security tests", "test suites"]):
            test_types = []
            for label, pattern in [
                ("unit tests", "unit tests"),
                ("integration tests", "integration tests"),
                ("end-to-end tests", "end-to-end tests"),
                ("stress tests", "stress tests"),
                ("security tests", "security tests"),
            ]:
                if pattern in lower:
                    test_types.append(label)
            if test_types:
                add("Run comprehensive tests, including " + ", ".join(test_types))
            else:
                add("Run comprehensive test suites for generated code")

        if any(marker in lower for marker in ["documentation", "readme", "claude.md"]):
            doc_bits = []
            if "readme" in lower:
                doc_bits.append("a well-documented README")
            if "claude.md" in lower:
                doc_bits.append("tool-specific guidance such as CLAUDE.md")
            add("Maintain documentation" + (", including " + " and ".join(doc_bits) if doc_bits else ""))

        return actions
