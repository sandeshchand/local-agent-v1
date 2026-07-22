from __future__ import annotations

from typing import Any


class CrossEncoderReranker:
    def __init__(
        self,
        model_name: str,
        top_n: int = 3,
        batch_size: int = 3,
        max_length: int = 512,
    ) -> None:
        self.model_name = model_name
        self.top_n = top_n
        self.batch_size = batch_size
        self.max_length = max_length
        self._model = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            import os

            # Suppress HuggingFace warnings and weight loading bars
            os.environ["TRANSFORMERS_VERBOSITY"] = "error"
            os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                self.model_name,
                max_length=self.max_length,
            )
        return self._model

    def warm_up(self) -> None:
        model = self._ensure_model()
        model.predict(
            [["retrieval warmup query", "retrieval warmup document"]],
            batch_size=1,
            show_progress_bar=False,
        )

    def rerank(self, query: str, items: list[str]) -> list[dict]:
        if not items:
            return []

        model = self._ensure_model()

        pairs = []
        for item in items:
            text = (item.get("text") or "").strip()
            if text:
                pairs.append([query, text])
        scores = model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )

        reranked: list[dict] = []
        for item, score in zip(items, scores):
            enriched = dict(item)
            enriched["hybrid_score"] = float(item.get("score", 0.0))
            enriched["reranker_score"] = float(score)
            reranked.append(enriched)

        reranked.sort(key=lambda x: x["reranker_score"], reverse=True)
        return reranked[:self.top_n]
