from __future__ import annotations

from local_agent.answering.extractive import (
    BestPracticeExtractorMixin,
    CapabilityExtractorMixin,
    DefinitionUsageExtractorMixin,
    ExplanationExtractorMixin,
    ExtractorUtilityMixin,
    LimitationExtractorMixin,
    ListExtractorMixin,
    ProcessExtractorMixin,
)


class ExtractiveAnswerMixin(
    CapabilityExtractorMixin,
    ListExtractorMixin,
    ProcessExtractorMixin,
    DefinitionUsageExtractorMixin,
    ExtractorUtilityMixin,
    ExplanationExtractorMixin,
    BestPracticeExtractorMixin,
    LimitationExtractorMixin,
):
    """Combine deterministic answer-shape extractors for AnswerService."""
