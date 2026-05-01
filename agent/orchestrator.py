 
from __future__ import annotations

from agent.memory_manager import MemoryManager
from agent.schemas import AgentState
from agent.tool_router import ToolRouter
from agent.verifier import Verifier
from agent.planner import Planner
from app.tool_registry import ToolRegistry
from observability.traces import save_trace
from retrieval.answer_service import AnswerService
from retrieval.evidence_checker import EvidenceChecker
from retrieval.query_rewriter import QueryRewriter
from retrieval.search import RetrievalService
from storage.sqlite_store import SQLiteStore

class Orchestrator:
    def __init__(self, 
                planner: Planner, 
                retrieval_service: RetrievalService, 
                answer_service: AnswerService,
                tool_registry: ToolRegistry,
                memory_manager: MemoryManager,
                verifier: Verifier,
                sqlite_store: SQLiteStore,
                max_steps: int = 3,       
              
            ) -> None:
        self.planner = planner
        self.retrieval_service = retrieval_service
        self.answer_service = answer_service
        self.tool_registry = tool_registry
        self.memory_manager = memory_manager
        self.verifier = verifier
        self.sqlite_store = sqlite_store
        self.tool_router = ToolRouter()
        self.max_steps = max_steps

        self.evidence_checker = EvidenceChecker()
        self.query_rewriter = QueryRewriter()

    def handle_query(self, query: str, session_id: str= "default") -> dict:
        self.memory_manager.save_user_turn(session_id, query)
        memory = self.memory_manager.load_sesssion_memory(session_id)

        state = AgentState(
            user_query=query,
            session_id=session_id,
            memory=memory,
        )

        state.plan = self.planner.plan(query)
        state.steps.append({
            "step": 1,
            "type": "plan",
            "plan": state.plan.model_dump(),
        })
        used_citations: list[dict] = []

        for step_no in range(2,self.max_steps+ 2):
            action = self.tool_router.next_action(state)

            if action.action_type == "direct_answer":
                answer = self.answer_service.answer_direct(query)
                state.final_answer = answer
                state.done = True
                state.steps.append({
                    "step": step_no,
                    "type": "direct_answer",
                    "notes": action.notes,
                })
                break

            if action.action_type == "retrieve":
                retrieval_query = action.retrieve_query or query
                current_query = self.query_rewriter.rewrite(
                    query=retrieval_query, session_memory=memory)
                best_results:list[dict]=[]
                best_evidence = None
                max_retrieval_attempts = 3

                for attempt in range(1,max_retrieval_attempts +1):
                    results = self.retrieval_service.search(current_query)
                    evidence = self.evidence_checker.evaluate(query,results)
                    state.steps.append({
                        "step": step_no,
                        "type": "retrieve_attempt",
                        "attempt":attempt,
                        "retrieval_query": current_query,
                        "result_count": len(results),
                        "evidence_sufficient": evidence.sufficient,
                        "need_retry":evidence.need_retry,
                        "quality_score":evidence.quality_score,
                        "reason":evidence.reason,
                    })

                    if best_evidence is None or evidence.quality_score > best_evidence.quality_score:
                        best_evidence= evidence
                        best_results = results
                        

                    if evidence.sufficient  and not evidence.need_retry:
                        best_results = results
                        best_evidence=evidence
                        break
                    
                    current_query=self.query_rewriter.rewrite_for_retry(
                        original_query=query,
                        previous_query=current_query,
                        missing_terms=evidence.missing_terms,
                        suggested_terms=evidence.suggested_terms,
                        failure_reason=evidence.reason,
                    )
                    
                    state.retrieved_items = best_results
                   
                    if not best_results and attempt == max_retrieval_attempts:
                       state.final_answer = (
                            "I could not find any relevant information in the indexed documents"
                            "for that question.")
                       state.done = True
                       break

                    if best_evidence is not None and not best_evidence.sufficient:
                        # If retrieval returned chunks , still allow grounded answering.
                        # The answer prompt will say insufficient context if it cannot answer.
                        if best_results:
                            answer = self.answer_service.answer_from_context(
                                query= query, 
                                results=best_results[: self.retrieval_service.final_context_limit],
                                memory_context = self.memory_manager.format_memory_context(memory),
                                tool_context="",
                            )
                            state.final_answer = answer 

                        else:
                            state.final_answer = (
                                "The retrieved documents are not relevant to the question.")
                        state.done = True
                        break

            if action.action_type == "tool_call" and action.tool_call:
                tool_name = action.tool_call["name"]
                tool_args = action.tool_call["args"]
                tool_result = self.tool_registry.execute(tool_name, **tool_args)
                state.tool_results.append(tool_result)
                state.steps.append({
                    "step": step_no,
                    "type": "tool_call",
                    "tool_name":tool_name,
                    "success": tool_result.success,
                    "notes": action.notes,
                })

                if tool_result.success:
                    tool_text = str(tool_result.output)
                    state.final_answer = self.answer_service.answer_from_tool_result(
                        query=query,
                        tool_context=tool_text,
                        memory_context=self.memory_manager.format_memory_context(memory),
                    )
                else:
                    state.final_answer = "I could not get the result from the tool."
                state.done = True
                break
            state.steps.append(
                {
                    "step": step_no,
                    "type": "finalize",
                    "notes": action.notes,
                }
            )
            break

        verification = self.verifier.verify(
            answer=state.final_answer,
            retrieved_items=used_citations,
        
        )

        self.memory_manager.save_assistant_turn(
            session_id=session_id,
            content=state.final_answer,
        )

        grounded_citations:list[dict] = []
        if verification.grounded and used_citations:
            grounded_citations = used_citations
        trace_id = save_trace(
            sqlite_store=self.sqlite_store,
            query=query,
            top_k=self.retrieval_service.top_k,
            retrieved_items=used_citations,
            final_answer=state.final_answer,
            plan=state.plan.model_dump() if state.plan else {},
            session_id=session_id,
            steps=state.steps,
            tool_results=[r.model_dump() for r in state.tool_results],
            verification=verification.model_dump(),
        )

        return {
            "session_id": session_id,
            "trace_id": trace_id,
            "mode": state.plan.mode if state.plan else "unknown",
            "reason":state.plan.reasoning if state.plan else "",
            "answer":state.final_answer,
            "citations":state.retrieved_items,
            "plan": state.plan.model_dump() if state.plan else {},
            "steps":state.steps,
            "tool_results": [r.model_dump() for r in state.tool_results],
            "verification": verification.model_dump(),
        }   

  

       