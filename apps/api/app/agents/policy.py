from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.agents.context import ApprovedContextPack
from app.agents.registry import CoreAgentId

PermissionOutcome = Literal["allow", "ask", "deny"]


@dataclass(frozen=True)
class ToolRequest:
    tool_id: str
    parameters: dict[str, Any]
    side_effect: Literal["none", "reversible", "external-write", "destructive", "billable"]


@dataclass(frozen=True)
class ToolPolicyDecision:
    outcome: PermissionOutcome
    code: str
    reason: str


HARD_DENY_TOOLS = {
    "git_push",
    "deploy_adapter",
    "workspace_delete",
    "read_secret_values",
    "database_state_write",
    "approve_gate",
    "advance_project_state",
}


def evaluate_tool_policy(
    *,
    agent_id: CoreAgentId,
    stage: str,
    context_pack: ApprovedContextPack,
    request: ToolRequest,
    tool_calls_used: int,
) -> ToolPolicyDecision:
    if request.tool_id in HARD_DENY_TOOLS or request.tool_id in context_pack.forbidden_actions:
        return ToolPolicyDecision("deny", "TOOL_HARD_DENY", "Tool is outside the V1 boundary.")
    if context_pack.stage != stage or context_pack.recipient_agent_id != agent_id:
        return ToolPolicyDecision("deny", "CONTEXT_SCOPE_MISMATCH", "Agent context is stale.")
    if tool_calls_used >= context_pack.budget.max_tool_calls:
        return ToolPolicyDecision("deny", "TOOL_BUDGET_EXCEEDED", "Tool-call budget is exhausted.")
    if request.tool_id == "web_research":
        if agent_id != "ai-pm" or stage not in {"mrd", "brd"}:
            return ToolPolicyDecision("deny", "TOOL_STAGE_DENY", "Research is not allowed here.")
        if not {"CAP-02", "CAP-12"}.intersection(context_pack.allowed_capability_ids):
            return ToolPolicyDecision("deny", "CAPABILITY_REQUIRED", "Research capability missing.")
    if request.side_effect in {"external-write", "destructive", "billable"}:
        if request.tool_id == "llm_call":
            return ToolPolicyDecision("allow", "PREAUTHORIZED_MODEL", "D5 model call is approved.")
        return ToolPolicyDecision("ask", "PERMISSION_REQUIRED", "Tool action requires permission.")
    return ToolPolicyDecision("allow", "POLICY_ALLOW", "Tool request is within the approved scope.")
