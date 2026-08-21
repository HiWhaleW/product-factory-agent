from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.schemas import ContextPackRead, ContextResourceRef


class ContextBoundaryError(ValueError):
    pass


class RuntimeBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_turns: int = Field(default=12, ge=1, le=50)
    max_retries: int = Field(default=2, ge=0, le=5)
    timeout_seconds: int = Field(default=300, ge=5, le=1800)
    max_tool_calls: int = Field(default=10, ge=0, le=30)


class ApprovedContextPack(BaseModel):
    """Runtime view of a deterministic, approved ContextPack record."""

    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    context_version: int = Field(ge=1)
    stage: str
    approval_status: str
    recipient_agent_id: str
    primary_resource: ContextResourceRef
    required_resources: list[ContextResourceRef]
    task: str = Field(min_length=1, max_length=20_000)
    allowed_capability_ids: list[str] = Field(default_factory=list, max_length=20)
    forbidden_actions: list[str] = Field(default_factory=list, max_length=50)
    secret_refs: list[str] = Field(default_factory=list, max_length=20)
    budget: RuntimeBudget = Field(default_factory=RuntimeBudget)

    @model_validator(mode="after")
    def enforce_minimum_approved_context(self) -> ApprovedContextPack:
        if self.approval_status != "approved":
            raise ContextBoundaryError("Runtime accepts only approved Context Packs.")
        refs = [self.primary_resource, *self.required_resources]
        if any(ref.approval_status != "approved" for ref in refs):
            raise ContextBoundaryError("Runtime accepts only approved resource versions.")
        if len({(ref.resource_type, ref.resource_id, ref.version) for ref in refs}) != len(refs):
            raise ContextBoundaryError("Context Pack contains duplicate resource references.")
        if any(not re.fullmatch(r"[A-Z][A-Z0-9_]{1,127}", ref) for ref in self.secret_refs):
            raise ContextBoundaryError("Context Pack secret_refs must contain names, never values.")
        return self

    @classmethod
    def from_control_plane(cls, pack: ContextPackRead) -> ApprovedContextPack:
        _reject_sensitive_policy(pack.policy)
        budget_body = pack.policy.get("budget") or {}
        return cls(
            id=pack.id,
            project_id=pack.project_id,
            context_version=pack.context_version,
            stage=pack.stage,
            approval_status=pack.approval_status,
            recipient_agent_id=pack.recipient_agent_id,
            primary_resource=pack.primary_resource,
            required_resources=pack.required_resources,
            task=pack.task,
            allowed_capability_ids=list(pack.policy.get("allowed_capability_ids") or []),
            forbidden_actions=list(pack.policy.get("forbidden_actions") or []),
            secret_refs=list(pack.policy.get("secret_refs") or []),
            budget=RuntimeBudget.model_validate(budget_body),
        )

    def model_payload(self) -> dict[str, Any]:
        """Minimal payload: refs and task only, never resource bodies or secret values."""
        return self.model_dump(mode="json")


def _reject_sensitive_policy(value: Any, path: tuple[str, ...] = ()) -> None:
    forbidden_keys = {
        "api_key",
        "secret_value",
        "password",
        "access_token",
        "refresh_token",
        "conversation",
        "chat_history",
        "hidden_reasoning",
        "chain_of_thought",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in forbidden_keys:
                raise ContextBoundaryError(
                    f"Context policy contains forbidden field at {'.'.join((*path, normalized))}."
                )
            _reject_sensitive_policy(child, (*path, normalized))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_policy(child, (*path, str(index)))
