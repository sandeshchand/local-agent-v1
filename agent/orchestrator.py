 
from __future__ import annotations

from agent.memory_manager import MemoryManager
from agent.schemas import AgentState
from agent.tool_router import ToolRouter
from agent.verifier import Verifier
from agent.planner import Planner
from app.tool_registry import ToolRegistry
from observability.traces import save_trace
from retrieval.doc_router import DocumentRouter
from retrieval.answer_service import AnswerService
from retrieval.evidence_checker import EvidenceChecker
from retrieval.query_rewriter import QueryRewriter
from retrieval.search import RetrievalService
from storage.sqlite_store import SQLiteStore
from retrieval.evidence_judge import EvidenceJudge

class Orchestrator:
    def __init__(self, 
                planner: Planner, 
                retrieval_service: RetrievalService, 
                answer_service: AnswerService,
                tool_registry: ToolRegistry,
                memory_manager: MemoryManager,
                verifier: Verifier,
                sqlite_store: SQLiteStore,
                doc_router:DocumentRouter | None = None,
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
        self.doc_router = doc_router 

        self.evidence_checker = EvidenceChecker()
        self.query_rewriter = QueryRewriter()
        self.evidence_judge = EvidenceJudge(self.answer_service.chat_client)

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
                retrieval_query = self.query_rewriter.rewrite(action.retrieve_query or query)
                candidate_doc_ids:list[str] | None = None
                routed_docs:list[dict]  = []
                if self.doc_router is not None:
                    routed_docs = self.doc_router.route(retrieval_query, top_n=3)
                    candidate_doc_ids = self._candidate_doc_ids(routed_docs)

                results = self.retrieval_service.search(
                    query=retrieval_query,
                    candidate_doc_ids=candidate_doc_ids,
                )
                selected_results, judgments = self.evidence_judge.select_evidence(
                    query,
                    results,
                    max_items=8,
                    
                )
                answer_results = self._merge_answer_context(selected_results, results, max_items=8)
                state.steps.append({
                    "step": step_no,
                    "type": "retrieve",
                    "retrieval_query": retrieval_query,
                    "routed_docs":[
                        {
                            "doc_id":doc["doc_id"],
                            "title":doc["title"],
                            "routing_score":doc.get("routing_score",0.0)
                        }
                        for doc in routed_docs
                        ],
                    "result_count": len(results),
                    "selected_count": len(selected_results),
                    "answer_context_count": len(answer_results),
                    "evidence_judgements": [
                        {
                            "label":j.label,
                            "reason":j.reason,
                            "chunk_id":j.item.get("chunk_id"),
                            "page_number":j.item.get("page_number"),
                        }
                        for j in judgments
                    ],
                    "notes":action.notes,
                })
                
                if answer_results:
                    state.retrieved_items= answer_results
                    used_citations= answer_results[:]
                    
                    answer = self.answer_service.answer_from_context(
                        query= query, 
                        results=answer_results,
                        memory_context = self.memory_manager.format_memory_context(memory),
                        tool_context="",
                    )
                    state.final_answer = answer
                else:
                    state.retrieved_items=[]
                    used_citations=[]
                    state.final_answer="Unable to find relevant information in the indexed documents."
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
            query=query,
        
        )

        if used_citations and verification.status != "verified":
            repaired_answer = self.answer_service.repair_answer(
                query=query,
                answer=state.final_answer,
                results=used_citations,
                issues=verification.issues,
            )
            repaired_verification = self.verifier.verify(
                answer=repaired_answer,
                retrieved_items=used_citations,
                query=query,
            )
            state.steps.append(
                {
                    "type": "answer_repair",
                    "issues": verification.issues,
                    "repaired": repaired_answer != state.final_answer,
                    "verification_after_repair": repaired_verification.model_dump(),
                }
            )
            if repaired_verification.status == "verified":
                state.final_answer = repaired_answer
                verification = repaired_verification

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

    def _merge_answer_context(
        self,
        selected_results: list[dict],
        retrieved_results: list[dict],
        max_items: int,
    ) -> list[dict]:
        merged: list[dict] = []
        seen: set[str] = set()

        for item in [*retrieved_results[:3], *selected_results, *retrieved_results]:
            item_id = str(item.get("chunk_id") or item.get("id") or id(item))
            if item_id in seen:
                continue
            seen.add(item_id)
            merged.append(item)
            if len(merged) >= max_items:
                break

        return merged

    def _candidate_doc_ids(self, routed_docs: list[dict]) -> list[str]:
        if not routed_docs:
            return []
        if len(routed_docs) == 1:
            return [routed_docs[0]["doc_id"]]

        top_score = float(routed_docs[0].get("routing_score", 0.0))
        second_score = float(routed_docs[1].get("routing_score", 0.0))
        if top_score >= second_score * 1.05 or (top_score - second_score) >= 3.0:
            return [routed_docs[0]["doc_id"]]
        return [doc["doc_id"] for doc in routed_docs]


  

       
