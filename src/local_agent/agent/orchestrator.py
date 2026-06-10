from __future__ import annotations

import time
from typing import Any

from local_agent.agent.guardrails import GuardrailPolicy
from local_agent.agent.memory_manager import MemoryManager
from local_agent.agent.planner import Planner
from local_agent.agent.schemas import AgentAction, AgentState, GuardrailDecision, VerificationResult
from local_agent.agent.tool_router import ToolRouter
from local_agent.agent.verifier import Verifier
from local_agent.tools import ToolRegistry
from local_agent.observability.traces import save_trace
from local_agent.answering import AnswerService
from local_agent.retrieval.doc_router import DocumentRouter
from local_agent.retrieval.evidence_checker import EvidenceChecker
from local_agent.retrieval.evidence_judge import EvidenceJudge
from local_agent.retrieval.query_rewriter import QueryRewriter
from local_agent.retrieval.search import RetrievalService
from local_agent.storage.sqlite_store import SQLiteStore


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
        total_started_at = time.perf_counter()
        timings_ms: dict[str, float] = {}

        memory_started_at = time.perf_counter()
        self.memory_manager.save_user_turn(session_id, query)
        captured_memory = self.memory_manager.capture_long_term_memory(session_id, query)
        memory = self.memory_manager.load_memory_for_query(session_id, query)
        memory_context = self.memory_manager.format_memory_context(memory)
        timings_ms["memory_load_ms"] = self._elapsed_ms(memory_started_at)

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

        planning_started_at = time.perf_counter()
        state.plan = self.planner.plan(query)
        timings_ms["planning_ms"] = self._elapsed_ms(planning_started_at)
        state.steps.append(
            {
                "step": 1,
                "type": "plan",
                "plan": state.plan.model_dump(),
            }
        )

        used_citations: list[dict] = []
        verification: VerificationResult | None = None

        action_started_at = time.perf_counter()
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

        timings_ms["action_ms"] = self._elapsed_ms(action_started_at)

        if verification is None:
            verification_started_at = time.perf_counter()
            verification = self._verify_and_maybe_repair(query, used_citations, state)
            timings_ms["fallback_verification_ms"] = self._elapsed_ms(verification_started_at)

        assistant_memory_started_at = time.perf_counter()
        self.memory_manager.save_assistant_turn(
            session_id=session_id,
            content=state.final_answer,
        )
        timings_ms["memory_save_ms"] = self._elapsed_ms(assistant_memory_started_at)

        grounded_citations: list[dict] = []
        if verification.grounded and used_citations:
            grounded_citations = used_citations

        performance_step = self._append_performance_step(
            state=state,
            timings_ms=timings_ms,
            total_started_at=total_started_at,
            citation_count=len(grounded_citations or used_citations),
        )

        trace_started_at = time.perf_counter()
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
        performance_summary = {
            **performance_step,
            "trace_save_ms": self._elapsed_ms(trace_started_at),
            "total_ms": self._elapsed_ms(total_started_at),
        }
        state.steps[-1].update(performance_summary)

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
            "performance": performance_summary,
        }

    def _handle_direct_answer(
        self,
        query: str,
        memory_context: str,
        state: AgentState,
        action: AgentAction,
        step_no: int,
    ) -> tuple[list[dict], VerificationResult]:
        started_at = time.perf_counter()
        state.final_answer = self.answer_service.answer_direct(
            query,
            memory_context=memory_context,
        )
        answer_generation_ms = self._elapsed_ms(started_at)
        state.done = True
        state.steps.append(
            {
                "step": step_no,
                "type": "direct_answer",
                "notes": action.notes,
                "answer_generation_ms": answer_generation_ms,
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
        guardrail_started_at = time.perf_counter()
        guardrail_decision = self.guardrail_policy.evaluate_tool_call(
            action,
            self.tool_registry,
            approved_tools=approved_tools,
        )
        guardrail_ms = self._elapsed_ms(guardrail_started_at)
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
                "duration_ms": guardrail_ms,
            }
        )

        if guardrail_decision.status != "allow":
            state.final_answer = self._guardrail_blocked_answer(guardrail_decision)
            state.done = True
            return [], self._verify_and_maybe_repair(query, [], state)

        tool_name, tool_args = self._tool_call_name_args(action)
        tool_spec = self.tool_registry.get_tool_spec(tool_name)
        tool_started_at = time.perf_counter()
        tool_result = self.tool_registry.execute(tool_name, **tool_args)
        tool_duration_ms = self._elapsed_ms(tool_started_at)
        state.tool_results.append(tool_result)

        answer_generation_ms = 0.0
        if tool_result.success:
            answer_started_at = time.perf_counter()
            state.final_answer = self.answer_service.answer_from_tool_result(
                query=query,
                tool_context=str(tool_result.output),
                memory_context=memory_context,
            )
            answer_generation_ms = self._elapsed_ms(answer_started_at)
        else:
            state.final_answer = "I could not get the result from the tool."

        state.steps.append(
            {
                "step": step_no,
                "type": "tool_call",
                "tool_name": tool_name,
                "tool_source": tool_spec.source if tool_spec else "unknown",
                "tool_metadata": tool_spec.metadata if tool_spec else {},
                "success": tool_result.success,
                "tool_duration_ms": tool_duration_ms,
                "answer_generation_ms": answer_generation_ms,
                "notes": action.notes,
            }
        )

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
        attempt_started_at = time.perf_counter()
        candidate_doc_ids: list[str] | None = None
        routed_docs: list[dict] = []
        candidate_scope = "all_documents"
        doc_routing_ms = 0.0

        if self.doc_router is not None:
            doc_routing_started_at = time.perf_counter()
            routed_docs = self.doc_router.route(retrieval_query, top_n=3)
            doc_routing_ms = self._elapsed_ms(doc_routing_started_at)
            if broaden_doc_scope:
                candidate_doc_ids = None
                candidate_scope = "all_documents_retry"
            else:
                candidate_doc_ids = self._candidate_doc_ids(routed_docs)
                candidate_scope = "routed_documents" if candidate_doc_ids else "all_documents"

        search_started_at = time.perf_counter()
        results = self.retrieval_service.search(
            query=retrieval_query,
            candidate_doc_ids=candidate_doc_ids,
        )
        retrieval_search_ms = self._elapsed_ms(search_started_at)
        evidence_started_at = time.perf_counter()
        selected_results, judgments = self.evidence_judge.select_evidence(
            query,
            results,
            max_items=10 if broaden_doc_scope else 8,
        )
        evidence_selection_ms = self._elapsed_ms(evidence_started_at)
        context_started_at = time.perf_counter()
        answer_results = self._merge_answer_context(
            selected_results,
            results,
            max_items=10 if broaden_doc_scope else 8,
        )
        context_merge_ms = self._elapsed_ms(context_started_at)

        if answer_results:
            answer_started_at = time.perf_counter()
            state.retrieved_items = answer_results
            state.final_answer = self.answer_service.answer_from_context(
                query=query,
                results=answer_results,
                memory_context=memory_context,
                tool_context="",
            )
            answer_generation_ms = self._elapsed_ms(answer_started_at)
            state.steps.append(
                self._retrieval_step(
                    step_no=step_no,
                    attempt=attempt,
                    retry_reason=retry_reason,
                    broaden_doc_scope=broaden_doc_scope,
                    retrieval_query=retrieval_query,
                    candidate_scope=candidate_scope,
                    candidate_doc_count=len(candidate_doc_ids or []),
                    routed_docs=routed_docs,
                    result_count=len(results),
                    selected_count=len(selected_results),
                    answer_context_count=len(answer_results),
                    judgments=judgments,
                    notes=action.notes,
                    doc_routing_ms=doc_routing_ms,
                    retrieval_search_ms=retrieval_search_ms,
                    evidence_selection_ms=evidence_selection_ms,
                    context_merge_ms=context_merge_ms,
                    answer_generation_ms=answer_generation_ms,
                    duration_ms=self._elapsed_ms(attempt_started_at),
                )
            )
            return answer_results[:]

        state.retrieved_items = []
        state.final_answer = "Unable to find relevant information in the indexed documents."
        state.steps.append(
            self._retrieval_step(
                step_no=step_no,
                attempt=attempt,
                retry_reason=retry_reason,
                broaden_doc_scope=broaden_doc_scope,
                retrieval_query=retrieval_query,
                candidate_scope=candidate_scope,
                candidate_doc_count=len(candidate_doc_ids or []),
                routed_docs=routed_docs,
                result_count=len(results),
                selected_count=len(selected_results),
                answer_context_count=len(answer_results),
                judgments=judgments,
                notes=action.notes,
                doc_routing_ms=doc_routing_ms,
                retrieval_search_ms=retrieval_search_ms,
                evidence_selection_ms=evidence_selection_ms,
                context_merge_ms=context_merge_ms,
                answer_generation_ms=0.0,
                duration_ms=self._elapsed_ms(attempt_started_at),
            )
        )
        return []

    def _verify_and_maybe_repair(
        self,
        query: str,
        used_citations: list[dict],
        state: AgentState,
    ) -> VerificationResult:
        verification_started_at = time.perf_counter()
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
                "duration_ms": self._elapsed_ms(verification_started_at),
            }
        )

        if used_citations and verification.status != "verified":
            repair_started_at = time.perf_counter()
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
                    "duration_ms": self._elapsed_ms(repair_started_at),
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

    def _retrieval_step(
        self,
        *,
        step_no: int,
        attempt: int,
        retry_reason: str,
        broaden_doc_scope: bool,
        retrieval_query: str,
        candidate_scope: str,
        candidate_doc_count: int,
        routed_docs: list[dict],
        result_count: int,
        selected_count: int,
        answer_context_count: int,
        judgments: list[Any],
        notes: str,
        doc_routing_ms: float,
        retrieval_search_ms: float,
        evidence_selection_ms: float,
        context_merge_ms: float,
        answer_generation_ms: float,
        duration_ms: float,
    ) -> dict:
        return {
            "step": step_no,
            "type": "retrieve",
            "attempt": attempt,
            "retry": attempt > 1,
            "retry_reason": retry_reason,
            "broaden_doc_scope": broaden_doc_scope,
            "retrieval_query": retrieval_query,
            "candidate_scope": candidate_scope,
            "candidate_doc_count": candidate_doc_count,
            "routed_docs": [
                {
                    "doc_id": doc["doc_id"],
                    "title": doc["title"],
                    "routing_score": doc.get("routing_score", 0.0),
                }
                for doc in routed_docs
            ],
            "result_count": result_count,
            "selected_count": selected_count,
            "answer_context_count": answer_context_count,
            "evidence_judgements": [
                {
                    "label": judgment.label,
                    "reason": judgment.reason,
                    "chunk_id": judgment.item.get("chunk_id"),
                    "page_number": judgment.item.get("page_number"),
                }
                for judgment in judgments
            ],
            "timings_ms": {
                "doc_routing_ms": doc_routing_ms,
                "retrieval_search_ms": retrieval_search_ms,
                "evidence_selection_ms": evidence_selection_ms,
                "context_merge_ms": context_merge_ms,
                "answer_generation_ms": answer_generation_ms,
            },
            "duration_ms": duration_ms,
            "notes": notes,
        }

    def _append_performance_step(
        self,
        *,
        state: AgentState,
        timings_ms: dict[str, float],
        total_started_at: float,
        citation_count: int,
    ) -> dict:
        step_counts: dict[str, int] = {}
        for step in state.steps:
            step_type = str(step.get("type", "unknown"))
            step_counts[step_type] = step_counts.get(step_type, 0) + 1

        performance_step = {
            "type": "performance",
            "total_before_trace_save_ms": self._elapsed_ms(total_started_at),
            "timings_ms": timings_ms,
            "step_counts": step_counts,
            "retrieval_attempts": step_counts.get("retrieve", 0),
            "tool_calls": len(state.tool_results),
            "citation_count": citation_count,
        }
        state.steps.append(performance_step)
        return performance_step

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

    def _elapsed_ms(self, started_at: float) -> float:
        return round((time.perf_counter() - started_at) * 1000, 2)
