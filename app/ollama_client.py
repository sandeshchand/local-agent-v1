from __future__ import annotations

from typing import Any

import requests

class OllamaError(Exception):
    pass

class OllamaChatClient:
    def __init__(self, base_url: str, model_name: str, timeout: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

    def generate(self, prompt:str) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
        }

        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaError(f"Chat request failed: {exc}" ) from exc

        data = response.json()
        text = data.get("response","")
        if not text:
            raise OllamaError("Chat response was empty.")
        return text.strip()

class OllamaEmbeddingClient:
    def __init__(self, base_url:str, model_name:str, time_out: int= 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.time_out = time_out

    def embed(self, text: str) -> list[float]:
        vectors = self.embed_many([text])
        if not vectors or not vectors[0]:
            raise OllamaError("Embedding response was empty.")
        return vectors[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        url = f"{self.base_url}/api/embed"
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": texts,
        }

        try:
            response = requests.post(url, json=payload, timeout= self.time_out)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaError(f"Embedding request failed:{exc}") from exc

        data = response.json()
        embeddings = data.get("embeddings", [])
        if not embeddings:
            raise OllamaError("No embeddings returned from Ollama.")
        return embeddings