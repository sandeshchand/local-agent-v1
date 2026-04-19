from __future__ import annotations

from app.ollama_client import  OllamaChatClient
from retrieval.context_builder import build_context

class AnswerService:
    def __init__(self, chat_client: OllamaChatClient) -> None:
        self.chat_client = chat_client

    def build_retrieval_prompt(
        self,
        query:str, 
        results: list[dict],
        memory_context: str,
        tool_context: str) -> str:
        context = build_context(results)
        return f"""
        You are answering only from the retrieved context below.
        
        Rules:
        - Use only the provided context.
        - If the context is insufficient, say that clearly.
        - Cite supporting evidence using [1], [2], [3] style.
        - Do not invent facts that are not in the context.
        - Keep the answer clear and concise.

        {memory_context}

        [RETRIEVED DOCUMENT CONTEXT]
        {context}

        [TOOL RESULTS]
        {tool_context}

        
        Question:
        {query}
        
        
        Answer:
        """.strip()

    def build_direct_prompt(self, query: str) -> str:
        return f"""
    You are a helpful AI assistant
    
    Rules:
    - Answer clearly and concisely.
    - Use normal reasoning.
    - If the question requires specific document content that you don't have, say that clearly.
    - Do not claim you searched documents unless retrieval actually happened.
    - Do not invent facts
    
    User question:
    {query}
    
    Answer:
    """.strip()
    def build_tool_prompt(
        self,
        query:str,
        tool_context:str,
        memory_context: str = "",
    ) -> str:
        return f"""
    You are a helpful AI assistant using tool output.
    
    Rules:
    - Base your answer only on the tool output below.
    - If the tool output is insufficient, say that clearly.
    - Keep the answer concise and accurate.

    {memory_context}

    [TOOL OUTPUT]
    {tool_context}

    
    Question:
    {query}
    
    
    Answer:
    """.strip()

    def answer_from_context(self,
        query:str, 
        results:list[dict],
        memory_context: str = "",
        tool_context: str = "",
    ) ->str:
        prompt = self.build_retrieval_prompt(
            query,results,memory_context,tool_context)
        return self.chat_client.generate(prompt).strip()

    def answer_direct(self, query:str) ->str:
        prompt = self.build_direct_prompt(query)
        return self.chat_client.generate(prompt).strip()

    def answer_from_tool_result(
        self,
        query:str,
        tool_context:str,
        memory_context: str = "",
    ) -> str:
        prompt = self.build_tool_prompt(
            query,tool_context,memory_context
        )
        return self.chat_client.generate(prompt).strip()
