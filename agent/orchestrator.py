from __future__ import annotations

from typing import Any

from agent.guardrails import GuardrailPolicy
from agent.memory_manager import MemoryManager
from agent.planner import Planner
from agent.schemas import AgentAction, AgentState, GuardrailDecision, VerificationResult
from agent.tool_router import ToolRouter
from agent.verifier import Verifier
from app.tool_registry import ToolRegistry
from observability.traces import save_trace
from retrieval.answer_service import AnswerService
from retrieval.doc_router import DocumentRouter
from retrieval.evidence_checker import EvidenceChecker
from retrieval.evidence_judge import EvidenceJudge
from retrieval.query_rewriter import QueryRewriter
from retrieval.search import RetrievalService
from storage.sqlite_store import SQLiteStore


class Orchestrator:
    """Coordinate memory, planning, retrieval, evidence, answer generation, and verification."""

    def __init__(
        self,
        planner: Planner,
        retrieval_service: RetrievalService,
        answer_service: AnswerService,
        tool_registry: ToolRegistry,
        memory_manager: MemoryManager,
        verifier: Verifier,
        sqlite_store: SQLiteStore,
        doc_router: DocumentRouter | None = None,
        max_steps: int = 3,
        max_retrieval_attempts: int = 2,
        guardrail_policy: GuardrailPolicy | None = None,
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
        self.max_retrieval_attempts = max(1, max_retrieval_attempts)
        self.guardrail_policy = guardrail_policy or GuardrailPolicy()
        self.doc_router = doc_router

        self.evidence_checker = EvidenceChecker()
        self.query_rewriter = QueryRewriter()
        self.evidence_judge = EvidenceJudge(self.answer_service.chat_client)

    def handle_query(
        self,
        query: str,
        session_id: str = "default",
        approved_tools: list[str] | None = None,
    ) -> dict:
        self.memory_manager.save_user_turn(session_id, query)
        captured_memory = self.memory_manager.capture_long_term_memory(session_id, query)
        memory = self.memory_manager.load_memory_for_query(session_id, query)
        memory_context = self.memory_manager.format_memory_context(memory)

        state = AgentState(
            user_query=query,
            session_id=session_id,
            memory=memory,
        )
        state.steps.append(
            {
                "step": 0,
                "type": "memory",
                "captured_count": len(captured_memory),
                "loaded_count": len(memory),
                "loaded_kinds": [item.kind for item in memory],
            }
        )

        state.plan = self.planner.plan(query)
        state.steps.append(
            {
                "step": 1,
                "type": "plan",
                "plan": state.plan.model_dump(),
            }
        )

        used_citations: list[dict] = []
        verification: VerificationResult | None = None

        for step_no in range(2, self.max_steps + 2):
            action = self.tool_router.next_action(state)

            if action.action_type == "direct_answer":
                used_citations, verification = self._handle_direct_answer(
                    query=query,
                    memory_context=memory_context,
                    state=state,
                    action=action,
                    step_no=step_no,
                )
                break

            if action.action_type == "retrieve":
                used_citations, verification = self._handle_retrieval_action(
                    query=query,
                    memory_context=memory_context,
                    state=state,
                    action=action,
                    step_no=step_no,
                )
                break

            if action.action_type == "tool_call" and action.tool_call:
                used_citations, verification = self._handle_tool_action(
                    query=query,
                    memory_context=memory_context,
                    state=state,
                    action=action,
                    step_no=step_no,
                    approved_tools=approved_tools,
                )
                break

            state.steps.append(
                {
                    "step": step_no,
                    "type": "finalize",
                    "notes": action.notes,
                }
            )
            verification = self._verify_and_maybe_repair(query, used_citations, state)
            break

        if verification is None:
            verification = self._verify_and_maybe_repair(query, used_citations, state)

        self.memory_manager.save_assistant_turn(
            session_id=session_id,
            content=state.final_answer,
        )

        grounded_citations: list[dict] = []
        if verification.grounded and used_citations:
            grounded_citations = used_citations

        trace_id = save_trace(
            sqlite_store=self.sqlite_store,
            query=query,
            top_k=self.retrieval_service.top_k,
            retrieved_items=grounded_citations or used_citations,
            final_answer=state.final_answer,
            plan=state.plan.model_dump() if state.plan else {},
            session_id=session_id,
            steps=state.steps,
            tool_results=[result.model_dump() for result in state.tool_results],
            verification=verification.model_dump(),
        )

        return {
            "session_id": session_id,
            "trace_id": trace_id,
            "mode": state.plan.mode if state.plan else "unknown",
            "reason": state.plan.reasoning if state.plan else "",
            "answer": state.final_answer,
            "citations": state.retrieved_items,
            "plan": state.plan.model_dump() if state.plan else {},
            "steps": state.steps,
            "tool_results": [result.model_dump() for result in state.tool_results],
            "verification": verification.model_dump(),
        }

    def _handle_direct_answer(
        self,
        query: str,
        memory_context: str,
        state: AgentState,
        action: AgentAction,
        step_no: int,
    ) -> tuple[list[dict], VerificationResult]:
        state.final_answer = self.answer_service.answer_direct(
            query,
            memory_context=memory_context,
        )
        state.done = True
        state.steps.append(
            {
                "step": step_no,
                "type": "direct_answer",
                "notes": action.notes,
            }
        )
        return [], self._verify_and_maybe_repair(query, [], state)

    def _handle_retrieval_action(
        self,
        query: str,
        memory_context: str,
        state: AgentState,
        action: AgentAction,
        step_no: int,
    ) -> tuple[list[dict], VerificationResult]:
        retrieval_query = self.query_rewriter.rewrite(action.retrieve_query or query)
        used_citations = self._run_retrieval_attempt(
            query=query,
            retrieval_query=retrieval_query,
            memory_context=memory_context,
            state=state,
            action=action,
            step_no=step_no,
            attempt=1,
        )
        verification = self._verify_and_maybe_repair(query, used_citations, state)

        if self._should_retry_retrieval(verification, used_citations, attempt=1):
            previous_answer = state.final_answer
            previous_citations = used_citations[:]
            previous_verification = verification
            retry_reason = self._verification_summary(verification, used_citations)
            retry_query = self.query_rewriter.rewrite_for_retry(
                original_query=query,
                previous_query=retrieval_query,
                failure_reason=retry_reason,
            )
            retry_citations = self._run_retrieval_attempt(
                query=query,
                retrieval_query=retry_query,
                memory_context=memory_context,
                state=state,
                action=action,
                step_no=step_no + 1,
                attempt=2,
                broaden_doc_scope=True,
                retry_reason=retry_reason,
            )
            retry_verification = self._verify_and_maybe_repair(query, retry_citations, state)
            accepted = self._retry_is_better(
                previous_citations=previous_citations,
                previous_verification=previous_verification,
                retry_citations=retry_citations,
                retry_verification=retry_verification,
            )
            state.steps.append(
                {
                    "type": "retrieval_retry_decision",
                    "accepted": accepted,
                    "reason": retry_reason,
                    "first_verification": previous_verification.model_dump(),
                    "retry_verification": retry_verification.model_dump(),
                }
            )
            if accepted:
                used_citations = retry_citations
                verification = retry_verification
            else:
                state.final_answer = previous_answer
                state.retrieved_items = previous_citations
                used_citations = previous_citations
                verification = previous_verification

        state.done = True
        return used_citations, verification

    def _handle_tool_action(
        self,
        query: str,
        memory_context: str,
        state: AgentState,
        action: AgentAction,
        step_no: int,
        approved_tools: list[str] | None = None,
    ) -> tuple[list[dict], VerificationResult]:
        guardrail_decision = self.guardrail_policy.evaluate_tool_call(
            action,
            self.tool_registry,
            approved_tools=approved_tools,
        )
        state.steps.append(
            {
                "step": step_no,
                "type": "guardrail",
                "status": guardrail_decision.status,
                "reason": guardrail_decision.reason,
                "action_type": guardrail_decision.action_type,
                "tool_name": guardrail_decision.tool_name,
                "requires_approval": guardrail_decision.requires_approval,
                "approved": guardrail_decision.approved,
                "policy_name": guardrail_decision.policy_name,
            }
        )

        if guardrail_decision.status != "allow":
            state.final_answer = self._guardrail_blocked_answer(guardrail_decision)
            state.done = True
            return [], self._verify_and_maybe_repair(query, [], state)

        tool_name, tool_args = self._tool_call_name_args(action)
        tool_spec = self.tool_registry.get_tool_spec(tool_name)
        tool_result = self.tool_registry.execute(tool_name, **tool_args)
        state.tool_results.append(tool_result)
        state.steps.append(
            {
                "step": step_no,
                "type": "tool_call",
                "tool_name": tool_name,
                "tool_source": tool_spec.source if tool_spec else "unknown",
                "tool_metadata": tool_spec.metadata if tool_spec else {},
                "success": tool_result.success,
                "notes": action.notes,
            }
        )

        if tool_result.success:
            state.final_answer = self.answer_service.answer_from_tool_result(
                query=query,
                tool_context=str(tool_result.output),
                memory_context=memory_context,
            )
        else:
            state.final_answer = "I could not get the result from the tool."

        state.done = True
        return [], self._verify_and_maybe_repair(query, [], state)

    def _guardrail_blocked_answer(self, decision: GuardrailDecision) -> str:
        if decision.status == "needs_approval":
            return "This action requires approval before execution."
        return "This tool action was blocked by guardrails."

    def _run_retrieval_attempt(
        self,
        query: str,
        retrieval_query: str,
        memory_context: str,
        state: AgentState,
        action: AgentAction,
        step_no: int,
        attempt: int,
        broaden_doc_scope: bool = False,
        retry_reason: str = "",
    ) -> list[dict]:
        candidate_doc_ids: list[str] | None = None
        routed_docs: list[dict] = []
        candidate_scope = "all_documents"

        if self.doc_router is not None:
            routed_docs = self.doc_router.route(retrieval_query, top_n=3)
            if broaden_doc_scope:
                candidate_doc_ids = None
                candidate_scope = "all_documents_retry"
            else:
                candidate_doc_ids = self._candidate_doc_ids(routed_docs)
                candidate_scope = "routed_documents" if candidate_doc_ids else "all_documents"

        results = self.retrieval_service.search(
            query=retrieval_query,
            candidate_doc_ids=candidate_doc_ids,
        )
        selected_results, judgments = self.evidence_judge.select_evidence(
            query,
            results,
            max_items=10 if broaden_doc_scope else 8,
        )
        answer_results = self._merge_answer_context(
            selected_results,
            results,
            max_items=10 if broaden_doc_scope else 8,
        )

        state.steps.append(
            {
                "step": step_no,
                "type": "retrieve",
                "attempt": attempt,
                "retry": attempt > 1,
                "retry_reason": retry_reason,
                "broaden_doc_scope": broaden_doc_scope,
                "retrieval_query": retrieval_query,
                "candidate_scope": candidate_scope,
                "candidate_doc_count": len(candidate_doc_ids or []),
                "routed_docs": [
                    {
                        "doc_id": doc["doc_id"],
                        "title": doc["title"],
                        "routing_score": doc.get("routing_score", 0.0),
                    }
                    for doc in routed_docs
                ],
                "result_count": len(results),
                "selected_count": len(selected_results),
                "answer_context_count": len(answer_results),
                "evidence_judgements": [
                    {
                        "label": judgment.label,
                        "reason": judgment.reason,
                        "chunk_id": judgment.item.get("chunk_id"),
                        "page_number": judgment.item.get("page_number"),
                    }
                    for judgment in judgments
                ],
                "notes": action.notes,
            }
        )

        if answer_results:
            state.retrieved_items = answer_results
            state.final_answer = self.answer_service.answer_from_context(
                query=query,
                results=answer_results,
                memory_context=memory_context,
                tool_context="",
            )
            return answer_results[:]

        state.retrieved_items = []
        state.final_answer = "Unable to find relevant information in the indexed documents."
        return []

    def _verify_and_maybe_repair(
        self,
        query: str,
        used_citations: list[dict],
        state: AgentState,
    ) -> VerificationResult:
        verification = self.verifier.verify(
            answer=state.final_answer,
            retrieved_items=used_citations,
            query=query,
        )
        state.steps.append(
            {
                "type": "verify",
                "status": verification.status,
                "issues": verification.issues,
                "grounded": verification.grounded,
            }
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

        return verification

    def _should_retry_retrieval(
        self,
        verification: VerificationResult,
        used_citations: list[dict],
        attempt: int,
    ) -> bool:
        if attempt >= self.max_retrieval_attempts:
            return False
        if not used_citations:
            return True
        return verification.status != "verified"

    def _retry_is_better(
        self,
        previous_citations: list[dict],
        previous_verification: VerificationResult,
        retry_citations: list[dict],
        retry_verification: VerificationResult,
    ) -> bool:
        if retry_verification.status == "verified" and retry_citations:
            return True
        if not previous_citations and retry_citations:
            return True
        if previous_verification.status != "verified" and retry_citations:
            return len(retry_verification.issues) < len(previous_verification.issues)
        return False

    def _verification_summary(
        self,
        verification: VerificationResult,
        used_citations: list[dict],
    ) -> str:
        if not used_citations:
            return "no citable evidence found"
        if verification.issues:
            return "; ".join(verification.issues)
        return verification.status

    def _tool_call_name_args(self, action: AgentAction) -> tuple[str, dict[str, Any]]:
        tool_call = action.tool_call
        if tool_call is None:
            return "", {}
        if hasattr(tool_call, "name"):
            return tool_call.name, tool_call.args or {}
        return tool_call.get("name", ""), tool_call.get("args", {})

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
