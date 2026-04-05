 
from __future__ import annotations

from agent.planner import Planner
from retrieval.answer_service import AnswerService
from retrieval.search import RetrievalService

class Orchestrator:
    def __init__(self, 
                planner: Planner, 
                retrieval_service: RetrievalService, 
                answer_service: AnswerService, 
            ) -> None:
        self.planner = planner
        self.retrieval_service = retrieval_service
        self.answer_service = answer_service

    def handle_query(self, query: str) -> str:
        plan = self.planner.plan(query)

        results: list[dict] = []
        answer = ""
        effective_mode = plan.mode

        if plan.mode == "direct_answer":
           answer = self.answer_service.answer_direct(query)
        
        elif plan.mode == "retrieve_only":
            retrieval_query = plan.retrieve_query or query
            results = self.retrieval_service.search(retrieval_query)

            if results:
                answer = self.answer_service.answer_from_context(query, results)
            else:
                answer = (
                    "I could not find relevant information in the indexed documents"
                    "for that question."
                )
        
        elif plan.mode == "tool_only":
            effective_mode = "direct_answer"
            answer = ("Tool routing is not enabled yet in this build."
            "I can currently answer directly or retrieve from documents.")
        
        elif plan.mode == "retrieve_then_tool":
            effective_mode = "retrieve_only"
            retrieval_query = plan.retrieve_query or query
            results = self.retrieval_service.search(retrieval_query)
            if results:
                answer = self.answer_service.answer_from_context(query, results)
            else:
                answer = (
                    "Retrieve-then-tool is not yet implemented yet, and no relevant document"
                    "context was found for this question."
                )
      
        return {
            "mode": effective_mode,
            "reason": plan.reasoning,
            "retrieval_query": plan.retrieve_query,
            "answer": answer,
            "citations": results,
            "plan": plan.model_dump(),
        }