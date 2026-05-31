
from __future__ import annotations

from local_agent.agent.schemas import AgentState, AgentAction


class ToolRouter:
    def next_action(self, state: AgentState) -> AgentAction:
        if state.plan is None:
            return AgentAction(
                action_type="finalize",
                notes="No plan available"
            )
        mode = state.plan.mode

        if mode =="direct_answer":
            return AgentAction(
                action_type="direct_answer",
                notes="Planner choose Direct answer"
            )
        
        if mode == "retrieve_only":
            return AgentAction(
                action_type="retrieve",
                retrieve_query=state.plan.retrieve_query or state.user_query,
                notes="Planner choose Retrieve only"
            )
        if mode == "tool_only"  and  state.plan.tool_name:
            return AgentAction(
                action_type="tool_call",
                tool_call={
                    "name": state.plan.tool_name,
                    "args": state.plan.tool_args or {},
                },
                notes="Planner choose tool call"
            )
        if mode == "retrieve_then_tool" :
            if not state.retrieved_items:
                return AgentAction(
                    action_type="retrieve",
                    retrieve_query=state.plan.retrieve_query or state.user_query,
                    notes="Retrieve before tool execution",
                )
            
            if state.plan.tool_name:
                return AgentAction(
                    action_type="tool_call",
                    tool_call={
                        "name": state.plan.tool_name,
                        "args": state.plan.tool_args or {},
                    },
                    notes="Tool call after retrieval",
                )
        return AgentAction(
            action_type="finalize",
            notes="No actionable route"
        )