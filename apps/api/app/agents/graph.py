from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any, Protocol, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel

from app.adapters.bocha import (
    BochaError,
    BochaRateLimitError,
    BochaSchemaError,
    BochaTimeoutError,
)
from app.adapters.deepseek import (
    DeepSeekError,
    DeepSeekMessage,
    DeepSeekRateLimitError,
    DeepSeekSchemaError,
    DeepSeekTimeoutError,
)
from app.agents.context import ApprovedContextPack
from app.agents.outputs import output_model_for
from app.agents.policy import ToolRequest, evaluate_tool_policy
from app.agents.registry import CoreAgentId, load_frozen_prompt, require_d5_agent


class ModelProvider(Protocol):
    async def complete(
        self,
        messages,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout_seconds: float | None = None,
        response_model: type[BaseModel] | None = None,
        tools=None,
        tool_choice=None,
        require_tool_call: bool = False,
    ): ...


class ResearchProvider(Protocol):
    async def search(
        self,
        query: str,
        *,
        count: int = 10,
        freshness: str = "noLimit",
        summary: bool = True,
        timeout_seconds: float | None = None,
    ): ...


class RuntimeGraphState(TypedDict, total=False):
    run_id: str
    agent_id: CoreAgentId
    stage: str
    context_pack: dict[str, Any]
    approved_materials: list[dict[str, Any]]
    review_candidates: list[dict[str, Any]]
    user_input: str
    turns_used: int
    retries_used: int
    tool_calls_used: int
    research_retries_used: int
    tool_results: list[dict[str, Any]]
    status: str
    output: dict[str, Any] | None
    observed_model: str | None
    usage: dict[str, Any]
    error_code: str | None
    error_retryable: bool
    permission_outcome: str | None
    permission_reason: str | None
    validation_feedback: str | None


def build_agent_graph(
    provider: ModelProvider,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    research_provider: ResearchProvider | None = None,
):
    def prepare_node(state: RuntimeGraphState) -> RuntimeGraphState:
        return {"status": "prepared"}

    def after_prepare(state: RuntimeGraphState) -> str:
        pack = ApprovedContextPack.model_validate(state["context_pack"])
        requires_research = (
            state["agent_id"] == "ai-pm"
            and state["stage"] == "mrd"
            and "CAP-02" in pack.allowed_capability_ids
        )
        return "research_policy" if requires_research else "model"

    def research_policy_node(state: RuntimeGraphState) -> RuntimeGraphState:
        pack = ApprovedContextPack.model_validate(state["context_pack"])
        query = _research_query(state["user_input"])
        request = ToolRequest(
            tool_id="web_research",
            parameters={"query_sha256": _hash_text(query)},
            side_effect="billable",
        )
        decision = evaluate_tool_policy(
            agent_id=state["agent_id"],
            stage=state["stage"],
            context_pack=pack,
            request=request,
            tool_calls_used=state.get("tool_calls_used", 0),
        )
        if decision.outcome == "deny":
            return {
                "status": "failed",
                "permission_outcome": "deny",
                "permission_reason": decision.reason,
                "error_code": decision.code,
            }
        if decision.outcome == "ask":
            resumed = interrupt(
                {
                    "kind": "permission_request",
                    "tool_id": request.tool_id,
                    "reason": decision.reason,
                    "parameters": request.parameters,
                }
            )
            if not isinstance(resumed, dict) or resumed.get("decision") != "allow":
                return {
                    "status": "failed",
                    "permission_outcome": "deny",
                    "permission_reason": "Permission was denied or invalid.",
                    "error_code": "PERMISSION_DENIED",
                }
        if research_provider is None:
            return {
                "status": "failed",
                "permission_outcome": "allow",
                "permission_reason": "Bocha research Adapter is unavailable.",
                "error_code": "WEB_RESEARCH_ADAPTER_UNAVAILABLE",
            }
        return {
            "status": "research_allowed",
            "permission_outcome": decision.outcome,
            "permission_reason": decision.reason,
        }

    def after_research_policy(state: RuntimeGraphState) -> str:
        return "research" if state.get("status") == "research_allowed" else "finish"

    async def research_node(state: RuntimeGraphState) -> RuntimeGraphState:
        pack = ApprovedContextPack.model_validate(state["context_pack"])
        used = state.get("tool_calls_used", 0)
        if used >= pack.budget.max_tool_calls:
            return {
                "status": "waiting_human",
                "error_code": "TOOL_BUDGET_EXCEEDED",
            }
        if research_provider is None:
            return {
                "status": "waiting_human",
                "error_code": "WEB_RESEARCH_ADAPTER_UNAVAILABLE",
            }
        try:
            response = await research_provider.search(
                _research_query(state["user_input"]),
                count=10,
                freshness="noLimit",
                summary=True,
                timeout_seconds=pack.budget.timeout_seconds,
            )
        except (BochaSchemaError, BochaTimeoutError, BochaRateLimitError) as exc:
            retries = state.get("research_retries_used", 0) + 1
            can_retry = exc.retryable or isinstance(exc, BochaSchemaError)
            return {
                "tool_calls_used": used + 1,
                "research_retries_used": retries,
                "status": (
                    "research_retrying"
                    if can_retry
                    and retries <= pack.budget.max_retries
                    and used + 1 < pack.budget.max_tool_calls
                    else "waiting_human"
                ),
                "error_code": exc.code,
                "error_retryable": can_retry,
            }
        except BochaError as exc:
            return {
                "tool_calls_used": used + 1,
                "status": "waiting_human",
                "error_code": exc.code,
                "error_retryable": exc.retryable,
            }
        return {
            "tool_calls_used": used + 1,
            "status": "research_completed",
            "tool_results": [response.model_payload()],
            "error_code": None,
            "error_retryable": False,
        }

    def after_research(state: RuntimeGraphState) -> str:
        if state.get("status") == "research_retrying":
            return "research"
        if state.get("status") == "research_completed":
            return "model"
        return "finish"

    async def model_node(state: RuntimeGraphState) -> RuntimeGraphState:
        pack = ApprovedContextPack.model_validate(state["context_pack"])
        definition = require_d5_agent(state["agent_id"], state["stage"])
        turns = state.get("turns_used", 0)
        if turns >= pack.budget.max_turns:
            return {
                "status": "waiting_human",
                "error_code": "MAX_TURNS_EXCEEDED",
                "error_retryable": False,
            }
        prompt, prompt_hash = load_frozen_prompt(definition.id)
        output_model = output_model_for(definition.id, state["stage"])
        schema = json.dumps(output_model.model_json_schema(), ensure_ascii=False)
        system = (
            f"{prompt}\n\nRuntime contract: return only a JSON object matching this "
            f"schema: {schema}\n"
            f"Frozen prompt sha256: {prompt_hash}. Never output hidden reasoning or secret values."
        )
        if definition.id == "ai-pm" and state["stage"] == "mrd":
            system += (
                "\nEvidence contract: every declared EvidenceRef must appear verbatim in its "
                "artifact content adjacent to the supported claim. The Evidence Index must map "
                "each cited EvidenceRef to source title, URL, publisher/date when available, and "
                "the exact supported claim. Do not replace EvidenceRef values with E1/E2 aliases."
            )
        if definition.id == "reviewer" and state["stage"] == "mrd":
            system += (
                "\nReview evidence contract: cite only EvidenceRef values declared by the bound "
                "review candidates, and include every declared review EvidenceRef verbatim in "
                "the Red Team Review content adjacent to the relevant finding or conclusion."
            )
        user_payload = {
            "context_pack": pack.model_payload(),
            "approved_materials": state.get("approved_materials") or [],
            "review_candidates": state.get("review_candidates") or [],
            "tool_results": state.get("tool_results") or [],
            "current_user_input": state["user_input"],
            "retry_feedback": state.get("validation_feedback"),
        }
        try:
            response = await provider.complete(
                [
                    DeepSeekMessage(role="system", content=system),
                    DeepSeekMessage(
                        role="user",
                        content=json.dumps(user_payload, ensure_ascii=False),
                    ),
                ],
                max_tokens=(
                    8192
                    if state["stage"] == "mrd"
                    and definition.id in {"ai-pm", "reviewer"}
                    else 4096
                ),
                temperature=0,
                timeout_seconds=pack.budget.timeout_seconds,
                response_model=output_model,
            )
            _validate_evidence_provenance(
                agent_id=definition.id,
                stage=state["stage"],
                output=response.structured_output or {},
                tool_results=state.get("tool_results") or [],
                approved_materials=state.get("approved_materials") or [],
                review_candidates=state.get("review_candidates") or [],
            )
        except DeepSeekSchemaError as exc:
            retries = state.get("retries_used", 0) + 1
            return {
                "turns_used": turns + 1,
                "retries_used": retries,
                "status": (
                    "retrying"
                    if retries <= pack.budget.max_retries
                    else "waiting_human"
                ),
                "error_code": exc.code,
                "error_retryable": True,
                "validation_feedback": (
                    f"Safe validation errors: {str(exc)[:2000]}. "
                    "The previous JSON failed the runtime schema. Rebuild the complete response "
                    "from scratch. For MRD artifacts, include every declared EvidenceRef verbatim "
                    "inside that artifact's content; do not use E1/E2 aliases. For Red Team "
                    "Review, include every declared review EvidenceRef verbatim inside review "
                    "content."
                ),
            }
        except (DeepSeekTimeoutError, DeepSeekRateLimitError) as exc:
            retries = state.get("retries_used", 0) + 1
            return {
                "turns_used": turns + 1,
                "retries_used": retries,
                "status": (
                    "retrying"
                    if exc.retryable and retries <= pack.budget.max_retries
                    else "waiting_human"
                ),
                "error_code": exc.code,
                "error_retryable": exc.retryable,
            }
        except DeepSeekError as exc:
            return {
                "turns_used": turns + 1,
                "status": "waiting_human",
                "error_code": exc.code,
                "error_retryable": exc.retryable,
            }
        return {
            "turns_used": turns + 1,
            "status": "model_completed",
            "output": response.structured_output,
            "observed_model": response.model,
            "usage": response.usage.model_dump(mode="json"),
            "error_code": None,
            "error_retryable": False,
            "validation_feedback": None,
        }

    def after_model(state: RuntimeGraphState) -> str:
        if state.get("status") == "retrying":
            return "model"
        if state.get("status") != "model_completed":
            return "finish"
        output = state.get("output") or {}
        requests = []
        if output.get("tool_request"):
            requests.append(output["tool_request"])
        requests.extend(output.get("tool_requests") or [])
        return "policy" if requests else "finish"

    def policy_node(state: RuntimeGraphState) -> RuntimeGraphState:
        pack = ApprovedContextPack.model_validate(state["context_pack"])
        output = state.get("output") or {}
        raw_requests = []
        if output.get("tool_request"):
            raw_requests.append(output["tool_request"])
        raw_requests.extend(output.get("tool_requests") or [])
        for raw in raw_requests:
            request = ToolRequest(
                tool_id=raw["tool_id"],
                parameters=raw.get("parameters") or {},
                side_effect=raw["side_effect"],
            )
            decision = evaluate_tool_policy(
                agent_id=state["agent_id"],
                stage=state["stage"],
                context_pack=pack,
                request=request,
                tool_calls_used=state.get("tool_calls_used", 0),
            )
            if decision.outcome == "deny":
                return {
                    "status": "failed",
                    "permission_outcome": "deny",
                    "permission_reason": decision.reason,
                    "error_code": decision.code,
                }
            if decision.outcome == "ask":
                resumed = interrupt(
                    {
                        "kind": "permission_request",
                        "tool_id": request.tool_id,
                        "reason": decision.reason,
                        "parameters": request.parameters,
                    }
                )
                if not isinstance(resumed, dict) or resumed.get("decision") != "allow":
                    return {
                        "status": "failed",
                        "permission_outcome": "deny",
                        "permission_reason": "Permission was denied or invalid.",
                        "error_code": "PERMISSION_DENIED",
                    }
            # Tool execution is a separate adapter boundary. Unknown/unwired tools fail closed.
            return {
                "status": "failed",
                "permission_outcome": "allow",
                "permission_reason": (
                    "Policy allowed the tool but no runtime adapter is registered."
                ),
                "error_code": "TOOL_ADAPTER_UNAVAILABLE",
            }
        return {"status": "succeeded"}

    def finish_node(state: RuntimeGraphState) -> RuntimeGraphState:
        if state.get("status") == "model_completed":
            return {"status": "succeeded"}
        return {}

    builder = StateGraph(RuntimeGraphState)
    builder.add_node("prepare", prepare_node)
    builder.add_node("research_policy", research_policy_node)
    builder.add_node("research", research_node)
    builder.add_node("model", model_node)
    builder.add_node("policy", policy_node)
    builder.add_node("finish", finish_node)
    builder.add_edge(START, "prepare")
    builder.add_conditional_edges(
        "prepare",
        after_prepare,
        {"research_policy": "research_policy", "model": "model"},
    )
    builder.add_conditional_edges(
        "research_policy",
        after_research_policy,
        {"research": "research", "finish": "finish"},
    )
    builder.add_conditional_edges(
        "research",
        after_research,
        {"research": "research", "model": "model", "finish": "finish"},
    )
    builder.add_conditional_edges(
        "model",
        after_model,
        {"model": "model", "policy": "policy", "finish": "finish"},
    )
    builder.add_edge("policy", END)
    builder.add_edge("finish", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


GraphFactory = Callable[[ModelProvider, BaseCheckpointSaver | None], Any]


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _research_query(user_input: str) -> str:
    """Select an explicit public-search query without sending task instructions to search."""
    first_line, _, _ = user_input.partition("\n")
    prefix = "Research query:"
    if first_line.startswith(prefix):
        query = first_line.removeprefix(prefix).strip()
        if query:
            return query
    return user_input


def _validate_evidence_provenance(
    *,
    agent_id: str,
    stage: str,
    output: dict[str, Any],
    tool_results: list[dict[str, Any]],
    approved_materials: list[dict[str, Any]],
    review_candidates: list[dict[str, Any]],
) -> None:
    if stage != "mrd" or agent_id not in {"ai-pm", "reviewer"}:
        return
    if agent_id == "ai-pm":
        allowed = {
            str(result.get("evidence_ref"))
            for tool_result in tool_results
            for result in tool_result.get("results") or []
            if result.get("evidence_ref")
        }
    else:
        content_refs = {
            match
            for material in review_candidates
            for match in re.findall(
                r"bocha:web:[0-9a-f]{64}",
                str(material.get("content") or ""),
            )
        }
        declared_refs = {
            str(ref)
            for material in review_candidates
            for ref in material.get("evidence_refs") or []
        }
        allowed = content_refs | declared_refs
    proposed = set(output.get("evidence_refs") or [])
    for artifact in output.get("artifact_proposals") or []:
        proposed.update(artifact.get("evidence_refs") or [])
    for finding in output.get("findings") or []:
        proposed.update(finding.get("evidence_refs") or [])
    if not proposed or not proposed.issubset(allowed):
        raise DeepSeekSchemaError(
            "Agent output contains missing or unverified EvidenceRef values."
        )
