from __future__ import annotations

import re

from agent.schemas import VerificationResult

class Verifier:
    def verify(
        self,
        answer: str,
        retrieved_items: list[dict],
        query: str = "",
    ) -> VerificationResult:
        issues: list[str] =[]

        grounded = True
        if retrieved_items and "[" not in answer:
            grounded = False
            issues.append("Retrieved Answer has no citation markers.")
        
        if not answer.strip():
            grounded = False
            issues.append("Answer is empty.")

        if self._has_raw_context_leak(answer):
            grounded = False
            issues.append("Answer contains raw retrieval or chunk metadata.")

        if retrieved_items:
            citation_issues = self._citation_issues(answer, len(retrieved_items))
            if citation_issues:
                grounded = False
                issues.extend(citation_issues)

        if query and answer.strip():
            if self._looks_unfocused(query, answer):
                issues.append("Answer appears to drift away from the user's exact question.")
            if self._misses_intent_shape(query, answer):
                issues.append("Answer does not match the question intent.")
            if self._entity_drift(query, answer):
                issues.append("Answer discusses a different prominent entity than the one asked about.")
            if retrieved_items and self._low_evidence_overlap(query, answer, retrieved_items):
                issues.append("Answer has low overlap with the most relevant retrieved evidence.")

        status = "verified" 
        if issues:
            status = "needs_more_info"

        return VerificationResult(
            status=status,
            issues=issues,
            grounded=grounded,
        )

    def _citation_issues(self, answer: str, retrieved_count: int) -> list[str]:
        issues: list[str] = []
        citation_numbers = [int(match) for match in re.findall(r"\[(\d+)\]", answer)]
        if not citation_numbers:
            return issues
        invalid = sorted({number for number in citation_numbers if number < 1 or number > retrieved_count})
        if invalid:
            issues.append(f"Answer cites unavailable evidence numbers: {invalid}.")
        return issues

    def _has_raw_context_leak(self, answer: str) -> bool:
        markers = [
            "[child chunk",
            "Title:",
            "Section:",
            "Page:",
            "Score:",
            "Retrieved chunk:",
            "chunk_id",
            "hybrid_score",
            "reranker_score",
            "Follow publication",
            "Get an email whenever",
            "By signing up",
        ]
        answer_lower = answer.lower()
        if any(marker.lower() in answer_lower for marker in markers):
            return True
        return False

    def _looks_unfocused(self, query: str, answer: str) -> bool:
        query_lower = query.lower()
        answer_lower = answer.lower()
        broad_markers = [
            "### overview",
            "### introduction",
            "### applications",
            "### conclusion",
            "summary of",
        ]
        if any(marker in answer_lower for marker in broad_markers):
            return True
        if "application" not in query_lower and re.search(r"\bapplications?:", answer_lower):
            return True
        if (query_lower.startswith("what is") or "what type of" in query_lower) and len(answer.split()) > 120:
            return True
        return False

    def _misses_intent_shape(self, query: str, answer: str) -> bool:
        query_lower = query.lower()
        answer_lower = answer.lower()
        first_40 = " ".join(answer_lower.split()[:40])

        if "what type of input" in query_lower:
            return not any(term in first_40 for term in ["input", "prompt", "instruction", "text", "natural language"])
        if any(term in query_lower for term in ["architecture", "framework", "components"]):
            return not any(term in answer_lower for term in ["architecture", "framework", "component", "part", "module", "model"])
        if any(term in query_lower for term in ["represent", "representation", "before feeding", "model input"]):
            return not any(term in answer_lower for term in ["representation", "represent", "latent", "token", "patch", "compress"])
        if any(term in query_lower for term in ["limitations", "limitation", "challenges"]):
            return not any(term in answer_lower for term in ["limitation", "challenge", "constraint", "failure", "issue"])
        if query_lower.startswith("why"):
            return not any(term in answer_lower for term in ["because", "helps", "allows", "enables", "so that", "due to", "reason"])
        return False

    def _entity_drift(self, query: str, answer: str) -> bool:
        focus_entities = self._focus_entities(query)
        if not focus_entities:
            return False
        answer_lower = answer.lower()
        focus_phrases = self._focus_phrases(query)
        query_lower = query.lower()
        if focus_phrases and any(phrase in answer_lower for phrase in focus_phrases) and len(answer.split()) < 160:
            return False
        if not any(entity in answer_lower for entity in focus_entities):
            return True
        if len(answer.split()) < 180 and any(entity in answer_lower for entity in focus_entities):
            return False
        if any(
            term in query_lower
            for term in ["limitation", "challenge", "feature", "capability", "component", "architecture", "how"]
        ) and any(entity in answer_lower for entity in focus_entities):
            return False

        allowed = focus_entities | {
            token.lower()
            for token in re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,}\b", query)
        }
        allowed.update(self._focus_acronyms(query))
        generic_entities = {
            "docker",
            "pdf",
            "api",
            "ai",
            "ml",
            "rag",
            "url",
            "http",
            "https",
            "monitoring",
            "detecting",
            "updating",
            "updates",
            "containers",
            "security",
            "stability",
            "overhead",
            "this",
            "these",
            "that",
            "those",
            "there",
            "their",
            "they",
            "development",
            "optimize",
            "configure",
            "wisely",
            "keep",
            "create",
            "start",
            "implement",
            "schedule",
            "use",
            "run",
            "set",
            "limitations",
            "limitation",
            "challenges",
            "challenge",
            "features",
            "feature",
            "capabilities",
            "capability",
            "applications",
            "application",
            "architecture",
            "framework",
            "components",
            "component",
            "physical",
            "digital",
            "visual",
            "language",
            "interaction",
            "human-computer",
            "openai",
        }
        answer_for_entities = self._strip_inline_labels(answer)
        drift_entities: list[str] = []
        for entity in re.findall(r"\b[A-Z][A-Za-z0-9_-]{3,}\b", answer_for_entities):
            entity_lower = entity.lower()
            if entity_lower in allowed or entity_lower in generic_entities:
                continue
            if entity_lower in query_lower:
                continue
            occurrences = len(re.findall(rf"\b{re.escape(entity_lower)}\b", answer_lower))
            if occurrences >= 2 or self._appears_as_answer_subject(entity, answer_for_entities):
                drift_entities.append(entity_lower)
        return bool(drift_entities)

    def _focus_phrases(self, query: str) -> set[str]:
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
            tokens = [
                token
                for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_-]*\b", match.group(0))
                if token.lower() not in generic_terms
            ]
            if len(tokens) >= 2:
                phrase = " ".join(token.lower() for token in tokens)
                phrases.add(phrase)
                last = tokens[-1]
                if last.lower().endswith("s") and len(last) > 4:
                    phrases.add(" ".join([*(token.lower() for token in tokens[:-1]), last[:-1].lower()]))
        return phrases

    def _focus_acronyms(self, query: str) -> set[str]:
        acronyms: set[str] = set()
        for phrase in self._focus_phrases(query):
            acronym = "".join(token[0] for token in phrase.split() if token)
            if len(acronym) >= 2:
                acronyms.add(acronym.lower())
                acronyms.add(f"{acronym.lower()}s")
        return acronyms

    def _strip_inline_labels(self, answer: str) -> str:
        text = re.sub(r"\[\d+\]", " ", answer)
        text = re.sub(
            r"(?:^|[\n.;]\s*|\s+-\s+)[A-Z][A-Za-z0-9 _/&-]{1,48}:\s*",
            " ",
            text,
        )
        return text

    def _appears_as_answer_subject(self, entity: str, answer: str) -> bool:
        escaped = re.escape(entity)
        subject_pattern = rf"\b{escaped}\b\s+(?:is|are|was|were|can|helps|allows|provides|offers|includes|include|monitors|detects)\b"
        target_pattern = rf"\b(?:features|benefits|limitations|capabilities|components|architecture)\s+of\s+{escaped}\b"
        return bool(
            re.search(subject_pattern, answer)
            or re.search(target_pattern, answer, flags=re.IGNORECASE)
        )

    def _low_evidence_overlap(self, query: str, answer: str, retrieved_items: list[dict]) -> bool:
        query_terms = self._query_terms(query)
        if not query_terms:
            return False

        answer_terms = self._content_terms(answer)
        all_evidence_terms = self._content_terms(
            " ".join(self._clean_text(item.get("text") or "") for item in retrieved_items[:8])
        )
        grounded_answer_terms = answer_terms & all_evidence_terms
        if len(grounded_answer_terms) >= min(4, max(2, len(answer_terms) // 3)):
            return False

        evidence_sentences = self._top_evidence_sentences(query_terms, retrieved_items)
        if not evidence_sentences:
            return False

        evidence_terms = self._content_terms(" ".join(evidence_sentences))
        evidence_terms = {term for term in evidence_terms if term not in query_terms}
        if len(evidence_terms) < 5:
            return False

        overlap = len(evidence_terms & answer_terms)
        return overlap < min(3, max(1, len(evidence_terms) // 8))

    def _top_evidence_sentences(self, query_terms: set[str], retrieved_items: list[dict]) -> list[str]:
        scored: list[tuple[int, str]] = []
        for item in retrieved_items[:8]:
            text = self._clean_text(item.get("text") or "")
            for sentence in self._split_sentences(text):
                sentence_lower = sentence.lower()
                if any(
                    marker in sentence_lower
                    for marker in [
                        "follow publication",
                        "published in",
                        "get an email",
                        "by signing up",
                    ]
                ):
                    continue
                score = sum(1 for term in query_terms if term in sentence.lower())
                if score > 0:
                    scored.append((score, sentence))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [sentence for _, sentence in scored[:6]]

    def _query_terms(self, query: str) -> set[str]:
        return {
            token
            for token in re.findall(r"\b[a-zA-Z][a-zA-Z0-9\-]{2,}\b", query.lower())
            if token not in self._stop_words()
        }

    def _focus_entities(self, query: str) -> set[str]:
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
        }
        entities: set[str] = set()
        for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_-]{3,}\b", query):
            lower = token.lower()
            if lower in generic_terms:
                continue
            if token[:1].isupper() or any(char.isupper() for char in token[1:]):
                entities.add(lower)
        return entities

    def _content_terms(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"\b[a-zA-Z][a-zA-Z0-9\-]{3,}\b", text.lower())
            if token not in self._stop_words()
        }

    def _stop_words(self) -> set[str]:
        return {
            "what",
            "which",
            "are",
            "does",
            "do",
            "did",
            "how",
            "why",
            "this",
            "that",
            "the",
            "and",
            "for",
            "from",
            "into",
            "with",
            "about",
            "according",
            "paper",
            "document",
            "article",
            "review",
            "describe",
            "discuss",
            "main",
            "some",
            "type",
            "uses",
            "used",
            "using",
            "make",
            "makes",
            "say",
            "user",
            "answer",
            "context",
            "retrieved",
            "section",
            "page",
        }

    def _split_sentences(self, text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        parts = re.split(r"(?<=[.!?])\s+", normalized)
        return [part.strip() for part in parts if len(part.strip()) > 40]

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\[child chunk \d+ \| page [^\]]+\]\s*", " ", text)
        return re.sub(r"\s+", " ", text).strip()
