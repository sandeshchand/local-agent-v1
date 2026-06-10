from __future__ import annotations

import re

from local_agent.retrieval.context_builder import build_context


class QueryIntentMixin:
    def _is_explanation_question(self, query: str) -> bool:
        q = query.lower()
        return q.startswith("why") or (
            "article" in q and ("mean by" in q or (q.startswith("what does") and "mean" in q))
        )
    def _definition_query_entity(self, query: str) -> str:
        q = query.strip().strip("?!. ")
        patterns = [
            r"(?i)^what\s+do\s+you\s+mean\s+by\s+(.+)$",
            r"(?i)^what\s+is\s+(.+)$",
            r"(?i)^what\s+are\s+(.+)$",
            r"(?i)^define\s+(.+)$",
            r"(?i)^definition\s+of\s+(.+)$",
            r"(?i)^what\s+does\s+(.+?)\s+mean$",
        ]
        for pattern in patterns:
            match = re.search(pattern, q)
            if not match:
                continue
            entity = match.group(1).strip(" '\"“”‘’")
            if entity.lower() in {"the article", "article", "it", "this", "that"}:
                continue
            if pattern.startswith("(?i)^what\\s+is") or pattern.startswith("(?i)^what\\s+are"):
                if len(self._entity_terms(entity)) < 2:
                    continue
            return re.sub(r"\s+", " ", entity)
        return ""
    def _entity_terms(self, entity: str) -> list[str]:
        stop_words = {"a", "an", "the", "and", "or", "of", "for", "about", "by", "in", "on", "to"}
        return [
            token.lower()
            for token in re.findall(r"\b[a-zA-Z0-9][a-zA-Z0-9_-]*\b", entity)
            if token.lower() not in stop_words
        ]
    def _entity_anchor_positions(self, lower_text: str, entity_terms: list[str]) -> list[int]:
        positions: list[int] = []
        compact_entity = "".join(entity_terms)
        if compact_entity:
            compact_chars: list[str] = []
            raw_positions: list[int] = []
            for raw_position, char in enumerate(lower_text):
                if char.isalnum():
                    compact_chars.append(char)
                    raw_positions.append(raw_position)
            compact_text = "".join(compact_chars)
            for match in re.finditer(re.escape(compact_entity), compact_text):
                if match.start() < len(raw_positions):
                    positions.append(raw_positions[match.start()])
        if len(entity_terms) >= 2:
            flexible = r"\s*[-_]?\s*".join(re.escape(term) for term in entity_terms)
            positions.extend(match.start() for match in re.finditer(flexible, lower_text))
        if len(entity_terms) == 1:
            for term in entity_terms:
                positions.extend(match.start() for match in re.finditer(rf"\b{re.escape(term)}\b", lower_text))
        return sorted(set(position for position in positions if position >= 0))
    def _matches_entity_terms(self, lower_text: str, entity_terms: list[str]) -> bool:
        if not entity_terms:
            return False
        compact_text = re.sub(r"[^a-z0-9]+", "", lower_text)
        compact_entity = "".join(entity_terms)
        if compact_entity and compact_entity in compact_text:
            return True
        return all(re.search(rf"\b{re.escape(term)}\b", lower_text) for term in entity_terms)
    def _answer_misses_focus_phrase(self, query: str, answer: str) -> bool:
        focus_phrases = self._focus_phrases(query)
        if not focus_phrases:
            return False
        answer_lower = answer.lower()
        return not any(phrase in answer_lower for phrase in focus_phrases)
    def _prefer_focused_entity_answer(self, query: str, answer: str, focused_answer: str) -> bool:
        if not self._focus_phrases(query):
            return False
        q = query.lower()
        if not any(marker in q for marker in ["used for", "key strength", "key strengths", "how do", "how does", "what is"]):
            return False
        answer_terms = self._content_terms(answer)
        focused_terms = self._content_terms(focused_answer)
        return len(focused_terms) >= len(answer_terms) or len(focused_terms - answer_terms) >= 3
    def _prefer_mechanism_answer(self, query: str, answer: str, mechanism_answer: str) -> bool:
        q = query.lower()
        if not (q.startswith("how") or any(term in q for term in ["turn", "convert", "transform", "detect"])):
            return False
        answer_terms = self._content_terms(answer)
        mechanism_terms = self._content_terms(mechanism_answer)
        if len(mechanism_terms - answer_terms) >= 3:
            return True
        query_terms = self._query_terms(query)
        intent_terms = set(self._query_intent_terms(query) + self._intent_terms_from_query_terms(query_terms))
        answer_lower = answer.lower()
        mechanism_lower = mechanism_answer.lower()
        missed_intent_terms = [
            term
            for term in intent_terms
            if term in mechanism_lower and term not in answer_lower
        ]
        return len(missed_intent_terms) >= 2
    def _focused_rewrite(self, query: str, draft_answer: str, results: list[dict]) -> str:
        facts = self._build_evidence_fact_list(query, results, max_facts=16)
        context = build_context(results, max_chars_per_chunk=1200)
        prompt = f"""
Rewrite the draft into a focused RAG answer.

Rules:
- Answer only the user's exact question.
- Use only the evidence facts and context below.
- Remove broad introductions, applications, background history, and conclusions unless the question asks for them.
- Follow this question-specific constraint: {self._question_specific_constraint(query)}
- Include every distinct directly relevant item, component, step, limitation, reason, or category supported by the evidence.
- Keep the answer concise: one paragraph or 3-6 bullets.
- Cite every sentence or bullet with [1], [2], etc.
- Do not include document titles, author names, source names, URLs, or filler prefaces unless the question asks for them.
- If the evidence does not answer the question, say exactly: The provided context does not contain enough information.

Question:
{query}

Draft answer:
{draft_answer}

Evidence facts:
{facts}

Context:
{context}

Focused answer:
""".strip()
        try:
            rewritten = self.chat_client.generate(prompt).strip()
        except Exception:
            return draft_answer
        if not rewritten or self._is_insufficient_answer(rewritten):
            return draft_answer
        return self._ensure_focus_entity_mentioned(
            query,
            self._clean_final_answer(self._remove_mixed_abstention(rewritten)),
        )
    def _looks_under_specific(self, answer: str, results: list[dict]) -> bool:
        answer_lower = answer.lower()
        evidence_text = " ".join((item.get("text") or "") for item in results)
        source_terms = self._source_specific_terms(evidence_text)
        if len(source_terms) < 4:
            return False
        matched = sum(1 for term in source_terms if term.lower() in answer_lower)
        return matched < max(2, len(source_terms) // 5)
    def _looks_unfocused(self, query: str, answer: str) -> bool:
        answer_lower = answer.lower()
        broad_headings = [
            "### overview",
            "### introduction",
            "### applications",
            "### challenges",
            "### conclusion",
            "summary of",
        ]
        if any(heading in answer_lower for heading in broad_headings):
            return True
        if "application" not in query.lower() and re.search(r"\bapplications?:", answer_lower):
            return True
        if any(term in query.lower() for term in ["different", "earlier", "previous", "compared"]) and any(
            drift in answer_lower
            for drift in ["applications in various domains", "healthcare", "robotics", "marketing", "education sector"]
        ):
            return True
        if (query.lower().startswith("what is") or "what type of" in query.lower()) and len(answer.split()) > 90:
            return True
        if "key features:" in answer_lower and not any(term in query.lower() for term in ["feature", "features", "different"]):
            return True

        query_terms = self._query_terms(query)
        if not query_terms:
            return False
        first_120_words = " ".join(answer_lower.split()[:120])
        matched = sum(1 for term in query_terms if term in first_120_words)
        return matched == 0 and len(answer.split()) > 120
    def _misses_intent_shape(self, query: str, answer: str) -> bool:
        query_lower = query.lower()
        answer_lower = answer.lower()

        if "what type of input" in query_lower:
            first_30_words = " ".join(answer_lower.split()[:30])
            return not any(term in first_30_words for term in ["input", "prompt", "instruction", "text", "natural language"])

        if any(term in query_lower for term in ["architecture", "framework", "components"]):
            first_80_words = " ".join(answer_lower.split()[:80])
            return not any(term in first_80_words for term in ["architecture", "framework", "component", "part", "module"])

        if any(term in query_lower for term in ["represent", "representation", "before feeding", "model input"]):
            return not any(term in answer_lower for term in ["representation", "represent", "latent", "token", "patch", "compress"])

        if any(term in query_lower for term in ["limitations", "limitation", "challenges"]):
            return not any(term in answer_lower for term in ["limitation", "challenge", "constraint", "failure", "issue"])

        return False
    def _source_specific_terms(self, text: str) -> set[str]:
        terms: set[str] = set()
        for match in re.findall(r"\b[A-Z][A-Za-z0-9]*(?:[-·][A-Z]?[A-Za-z0-9]+)*\b", text):
            if len(match) >= 3 and match.lower() not in {"figure", "source", "section", "title", "page"}:
                terms.add(match)
        for match in re.findall(r"\b\d{4}\b|\b\d+\s*minute\b|\btext-to-[a-z-]+\b|\b[a-z]+-[a-z]+(?:-[a-z]+)?\b", text.lower()):
            terms.add(match)
        return set(list(terms)[:40])
    def _infer_answer_shape(self, query: str) -> str:
        q = query.lower()
        if self._is_list_question(query):
            return "Use concise bullets. Include each distinct item or category supported by the context."
        if q.startswith("why"):
            return "Explain the reason and include the main benefits or consequences supported by the context."
        if q.startswith("how"):
            return "Explain the process in order. Include all supported steps or mechanisms."
        if "architecture" in q or "components" in q:
            return "Name the core architecture and list the supported components."
        if "limitations" in q or "risks" in q or "challenges" in q:
            return "Group the answer by limitation or challenge category."
        return "Give a concise paragraph or short bullets covering all supported facts."
    def _question_specific_constraint(self, query: str) -> str:
        q = query.lower()
        if "feature" in q and not any(term in q for term in ["benefit", "advantage", "setup", "install", "best practice"]):
            return (
                "For feature questions, list only supported features, capabilities, or functions. "
                "Do not add benefits, setup steps, best practices, or neighboring tool details unless the question asks for them."
            )
        if any(term in q for term in ["simulator", "simulation", "simulate"]):
            return (
                "For simulation or capability questions, include the concrete abilities and examples named in the evidence. "
                "Prefer specific observed behaviors over a generic explanation."
            )
        return "No extra constraint beyond answering the exact question."
    def _generic_facet_checklist(self, query: str) -> str:
        q = query.lower()
        facets: list[str] = []
        if "feature" in q:
            facets.extend(["named features/capabilities/functions", "short role of each feature"])
        if q.startswith("what is") or "definition" in q:
            facets.extend(["definition/category", "creator/source/date if present", "main capability", "important scope or limit"])
        if "architecture" in q or "components" in q or "core model" in q:
            facets.extend(["core architecture name", "all listed components/parts", "conditioning/input mechanism if present"])
        if q.startswith("how"):
            facets.extend(["ordered steps", "mechanisms/methods", "inputs and outputs", "important caveats"])
        if q.startswith("why"):
            facets.extend(["main reason", "technical challenge", "benefits/consequences", "comparison if present"])
        if any(term in q for term in ["simulator", "simulation", "simulate"]):
            facets.extend(["concrete simulation abilities", "specific examples or environments named in context", "scope: physical and/or digital if present"])
        if any(word in q for word in ["approaches", "types", "kinds", "prompt", "capabilities", "limitations"]):
            facets.extend(["all categories/items named in context", "role of each item", "examples if present"])
        if not facets:
            facets.append("all distinct facts that directly answer the question")
        return "\n".join(f"- {facet}" for facet in dict.fromkeys(facets))
    def _is_list_question(self, query: str) -> bool:
        q = query.lower()
        return any(
            phrase in q
            for phrase in [
                "what are",
                "what types",
                "what kinds",
                "what limitations",
                "what capabilities",
                "what approaches",
                "what steps",
                "what first steps",
                "what three",
                "main pipeline",
                "pipeline",
                "formula",
                "setup",
                "commands",
                "which",
                "mentioned",
                "reasons",
                "list",
            ]
        )
    def _intent_terms_from_query_terms(self, query_terms: set[str]) -> list[str]:
        terms: list[str] = []
        if {"input", "prompt", "instruction"} & query_terms:
            terms.extend(["input", "prompt", "instruction", "user", "text", "natural language"])
        if {"application", "applications", "areas", "uses"} & query_terms:
            terms.extend(["application", "use", "domain", "area", "industry", "sector"])
        if {"architecture", "framework", "component", "components"} & query_terms:
            terms.extend(["architecture", "framework", "component", "module", "mechanism"])
        if {"represent", "representation", "model", "input"} & query_terms:
            terms.extend(["representation", "token", "patch", "latent", "compressed", "compressing", "input", "encoder", "model"])
        if {"kernel", "scalable", "scale", "methods"} & query_terms:
            terms.extend(["kernel", "scalable", "large datasets", "computation", "computational", "expensive", "approximating", "feature", "feature space", "memory", "cost"])
        if {"advancements", "agents", "assistants", "coding", "tools"} & query_terms:
            terms.extend(["language model", "foundation model", "multi-step reasoning", "reasoning", "integration", "development environment", "project structure", "codebase", "version control", "runtime information", "autonomy"])
        if {"pipeline", "processing", "app", "document"} & query_terms:
            terms.extend(["pipeline", "file", "url", "local", "load", "model", "generate", "output", "export", "format", "download", "preview", "interface"])
        if {"large", "numbers", "integer", "integers"} & query_terms:
            terms.extend(["large numbers", "large integers", "memory", "dynamic", "dynamically", "allocates"])
        if {"native", "sizes", "size", "resolution"} & query_terms:
            terms.extend(["native", "duration", "resolution", "aspect ratio", "composition", "framing", "crop", "resize"])
        if {"follow", "following", "instructions", "instruction", "detailed"} & query_terms:
            terms.extend(["instruction", "following", "caption", "description", "training", "prompt"])
        if {"limitations", "limitation", "challenge", "constraints"} & query_terms:
            terms.extend(["limitation", "challenge", "constraint", "failure", "risk", "issue", "accuracy", "usage"])
        if {"different", "earlier", "previous"} & query_terms:
            terms.extend(["different", "previous", "earlier", "unlike", "improvement"])
        if {"capabilities", "capability", "simulate", "simulation", "simulator", "world"} & query_terms:
            terms.extend(["capability", "ability", "simulate", "simulation", "environment", "world", "consistency", "coherence"])
        return list(dict.fromkeys(terms))
    def _query_intent_terms(self, query: str) -> list[str]:
        q = query.lower()
        terms: list[str] = []
        if "used for" in q or "useful" in q:
            terms.extend(["used", "useful", "prediction", "structured", "context", "sequential", "sequence", "independent", "probabilistic", "application", "example", "label", "labels"])
        if "best practice" in q:
            terms.extend(["practice", "development", "analysis", "threshold", "notification", "schedule", "low-traffic", "multi-stage"])
        if "indentation" in q or "braces" in q:
            terms.extend(["indentation", "enforces", "forces", "code block", "code blocks", "clean", "readable", "missing braces", "formatting", "readability"])
        if ("command" in q or "server" in q) and any(term in q for term in ["http", "web", "useful", "provide", "provides"]):
            terms.extend(["command", "http.server", "web server", "useful", "test", "web applications", "share files", "local network", "third-party", "browser", "localhost"])
        is_practice_challenge = bool(re.search(r"\b\d+\s*[- ]?\s*day\s+[^?]*challenge\b|\bpractice\w*\s+[^?]*challenge\b", q))
        if "limitation" in q or ("challenge" in q and not is_practice_challenge):
            terms.extend(["limitation", "challenge", "cause", "effect", "physical", "spatial", "placement", "arrangement", "temporal", "irrelevant", "interaction", "usage", "access", "safety"])
        if "detect" in q or "anomal" in q:
            terms.extend(["detect", "isolate", "isolates", "outlier", "random", "randomly", "partitioned", "labeled", "unlabeled", "unsupervised", "abnormal", "rare", "unusual"])
        if "strength" in q:
            terms.extend(["strength", "memory", "speed", "performance", "hardware", "logic", "reward", "penalty", "interpretable"])
        if "hardcod" in q or "secret" in q:
            terms.extend(["hardcode", "hardcoding", "secret", "secrets", "key", "keys", "database", "connection", "configuration", "settings", "structured", "safe"])
        if (".env" in q or "env file" in q) and ("local" in q or "development" in q or "recommend" in q):
            terms.extend([".env", "env file", "local development", "environment variables", "variables", "api keys", "tokens", "secrets", "database", "url", "key : value", "key-value", "slow", "messy", "inconvenient"])
        if "start" in q or "recommend" in q or "steps" in q:
            terms.extend(["skill", "tool", "tools", "faster", "draft", "research", "brainstorm", "package", "service", "client", "group", "fast", "try", "practice"])
        if "pipeline" in q or "processing app" in q:
            terms.extend(["local", "url", "load", "model", "generate", "output", "document", "export", "format", "download", "preview", "interface"])
        if "settings" in q and ("environment" in q or "variables" in q or "validate" in q or "map" in q):
            terms.extend(["settings", "class", "field", "default", "alias", "validation", "prefix", "validate", "environment variables"])
        if ".env.example" in q or "env.example" in q or "gitignore" in q:
            terms.extend(["private", "ignore", "never push", "repository", "developer", "placeholder", "placeholders", "keys"])
        if "markup" in q or "tag" in q or "tags" in q:
            terms.extend(["markup", "layout", "semantics", "reading order", "hierarchy", "parser", "heuristic", "downstream", "accuracy", "conversion"])
        if "forgettable" in q or "remember" in q or "memorable" in q or "introduction" in q or "intro" in q:
            terms.extend(["predictable", "tune out", "brain", "name", "job", "hobby", "effect", "impression", "seconds", "science", "story", "curiosity", "attention", "question", "engage", "remember", "memorable"])
        if "coding tools" in q or ("tools" in q and "strength" in q):
            terms.extend(["tool", "tools", "context", "codebase", "multi-agent", "multiple files", "project", "consistency"])
        if "multi-agent" in q or "multi agent" in q:
            terms.extend(["agent", "agents", "planning", "coding", "testing", "debugging", "documentation", "parallel processing", "specialization"])
        if ("brain" in q and "science" in q) or ("formula" in q and "works" in q):
            terms.extend(["brain", "science", "surprise", "story", "stories", "feel", "emotional", "memory", "question"])
        if "business" in q or "client" in q or "charge" in q:
            terms.extend(["hours", "content", "business", "businesses", "outline", "outlines", "post", "posts", "email", "client", "clients", "work", "personal touch", "charge"])
        if ("hold" in q or "holding" in q) and "back" in q:
            terms.extend(["fear", "failing", "looking", "wasting", "time", "stuck", "job", "trying", "try", "barrier", "obstacle"])
        if "replace" in q:
            terms.extend(["tool", "tools", "faster", "income", "side income", "background", "technical", "tech", "degree", "code", "no code", "product", "app", "save time", "make money", "learn", "need", "don't need", "don’t need", "didn't", "didn’t"])
        return list(dict.fromkeys(terms))
    def _query_terms(self, query: str) -> set[str]:
        stop_words = {
            "what",
            "which",
            "are",
            "does",
            "do",
            "did",
            "how",
            "why",
            "the",
            "and",
            "for",
            "with",
            "from",
            "into",
            "about",
            "according",
            "review",
            "paper",
            "document",
            "article",
            "discuss",
            "describe",
            "say",
            "use",
            "uses",
            "used",
            "make",
            "makes",
            "key",
            "feature",
            "features",
            "machine",
            "learning",
        }
        return {
            token
            for token in re.findall(r"\b[a-zA-Z][a-zA-Z0-9\-]{2,}\b", query.lower())
            if token not in stop_words
        }
    def _content_terms(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"\b[a-zA-Z][a-zA-Z0-9\-]{3,}\b", text.lower())
            if token not in {
                "what",
                "which",
                "does",
                "this",
                "that",
                "from",
                "with",
                "about",
                "paper",
                "document",
                "article",
                "answer",
                "context",
                "section",
                "page",
            }
        }
    def _contains_distinctive_identifier(self, text: str) -> bool:
        if self._class_like_identifiers(text):
            return True
        return bool(re.search(r"\b[A-Z][A-Za-z0-9_-]{2,}\b(?:\s+\b[A-Z][A-Za-z0-9_-]{2,}\b)+", text))
    def _ensure_focus_entity_mentioned(self, query: str, answer: str) -> str:
        if not answer or self._is_insufficient_answer(answer):
            return answer
        focus_entity = self._focus_entity_display(query)
        focus_terms = self._entity_terms(focus_entity)
        answer_lower = answer.lower()
        if (
            not focus_entity
            or focus_entity.lower() in answer_lower
            or (focus_terms and self._matches_entity_terms(answer_lower, focus_terms))
        ):
            return answer

        q = query.lower()
        if self._is_list_question(query):
            label = "key features" if "feature" in q else "main points"
            return f"{focus_entity}'s {label} are: {answer}"
        return f"{focus_entity}: {answer}"
    def _focus_entity_display(self, query: str) -> str:
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
        for pattern in [
            r"(?i)^\s*what\s+does\s+(.+?)\s+(?:help|support|provide|allow|enable|detect|analy[sz]e|monitor|update|show)\b",
            r"(?i)^\s*how\s+does\s+(.+?)\s+(?:help|work|support|provide|allow|enable|detect|analy[sz]e|monitor|update|show)\b",
        ]:
            match = re.search(pattern, query)
            if not match:
                continue
            candidate = re.sub(r"\s+", " ", match.group(1)).strip(" '\"“”‘’")
            candidate_terms = self._entity_terms(candidate)
            if candidate_terms and not all(term in generic_terms for term in candidate_terms):
                return candidate

        focus_phrases = self._focus_phrases(query, preserve_case=True)
        if focus_phrases:
            return sorted(focus_phrases, key=len, reverse=True)[0]

        candidates: list[str] = []
        for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_-]{3,}\b", query):
            lower = token.lower()
            if lower in generic_terms:
                continue
            if token[:1].isupper() or any(char.isupper() for char in token[1:]):
                candidates.append(token)
        return candidates[-1] if candidates else ""
    def _focus_phrases(self, query: str, preserve_case: bool = False) -> set[str]:
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
            current = [
                token
                for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_-]*\b", match.group(0))
                if token.lower() not in generic_terms
            ]
            if len(current) < 2:
                continue
            phrase_tokens = current if preserve_case else [token.lower() for token in current]
            phrase = " ".join(phrase_tokens)
            phrases.add(phrase)
            last = current[-1]
            if last.lower().endswith("s") and len(last) > 4:
                singular_tokens = list(current[:-1]) + [last[:-1]]
                if not preserve_case:
                    singular_tokens = [token.lower() for token in singular_tokens]
                phrases.add(" ".join(singular_tokens))
        return phrases
