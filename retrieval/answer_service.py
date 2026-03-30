from __future__ import annotations

from app.ollama_client import  OllamaChatClient
from retrieval.citations import format_citations
from retrieval.context_builder import build_context

class AnswerService:
    def __init__(self, chat_client: OllamaChatClient) -> None:
        self.chat_client = chat_client

    def build_prompt(self, query:str, results: list[dict]) -> str:
        context = build_context(results)
        return f"""
        You are answering only from the retrieved context below.
        
        Rules:
        - Use only the provided context.
        - If the context is insufficient, say that clearly.
        - Cite supporting evidence using [1], [2], [3] style.
        - Do not invent facts that are not in the context.
        
        Question:
        {query}
        
        Context:
        {context}
        
        Answer:
        """.strip()

    def answer(self, query:str, results:list[dict]) ->str:
        prompt = self.build_prompt(query,results)
        answer= self.chat_client.generate(prompt).strip()
        citations = format_citations(results)
        return f"{answer}\n\nSources:\n{citations}"
