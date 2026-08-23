from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CoreAgentId = Literal["factory-lead", "ai-pm", "builder", "reviewer"]


@dataclass(frozen=True)
class AgentDefinition:
    id: CoreAgentId
    prompt_filename: str
    allowed_stages: frozenset[str]
    default_capability_ids: tuple[str, ...]
    context_policy: Literal["project-minimum", "stage-minimum", "clean-review"]
    d5_active: bool
    prompt_version: str = "v0.2"


ALL_STAGES = frozenset(
    {
        "alignment",
        "mrd",
        "prd",
        "solution_confirmation",
        "tech_stack_confirmation",
        "development_backend",
        "development_frontend",
        "mvp",
        "internal_acceptance",
        "seed_beta",
        "brd",
        "release_handoff",
        "feedback",
    }
)


AGENT_REGISTRY: dict[CoreAgentId, AgentDefinition] = {
    "factory-lead": AgentDefinition(
        id="factory-lead",
        prompt_filename="factory-lead.prompt.md",
        allowed_stages=ALL_STAGES,
        default_capability_ids=("CAP-01", "CAP-05", "CAP-06", "CAP-12"),
        context_policy="project-minimum",
        d5_active=True,
    ),
    "ai-pm": AgentDefinition(
        id="ai-pm",
        prompt_filename="ai-pm.prompt.md",
        allowed_stages=frozenset({"mrd", "prd", "seed_beta", "brd", "feedback"}),
        default_capability_ids=("CAP-02", "CAP-03", "CAP-04", "CAP-12"),
        context_policy="stage-minimum",
        d5_active=True,
    ),
    "builder": AgentDefinition(
        id="builder",
        prompt_filename="builder.prompt.md",
        allowed_stages=frozenset(
            {
                "solution_confirmation",
                "tech_stack_confirmation",
                "development_backend",
                "development_frontend",
                "mvp",
                "release_handoff",
            }
        ),
        default_capability_ids=("CAP-07", "CAP-08", "CAP-09"),
        context_policy="stage-minimum",
        d5_active=False,
    ),
    "reviewer": AgentDefinition(
        id="reviewer",
        prompt_filename="reviewer.prompt.md",
        allowed_stages=ALL_STAGES,
        default_capability_ids=("CAP-10", "CAP-11"),
        context_policy="clean-review",
        d5_active=True,
    ),
}


class AgentRegistryError(ValueError):
    pass


def prompt_directory() -> Path:
    return Path(__file__).resolve().parents[4] / "产品工厂Agent" / "spec" / "prompts"


def load_frozen_prompt(agent_id: CoreAgentId) -> tuple[str, str]:
    definition = AGENT_REGISTRY[agent_id]
    path = (prompt_directory() / definition.prompt_filename).resolve()
    if path.parent != prompt_directory().resolve() or not path.is_file():
        raise AgentRegistryError(f"Frozen prompt is unavailable for {agent_id}.")
    content = path.read_text(encoding="utf-8")
    return content, hashlib.sha256(content.encode()).hexdigest()


def require_d5_agent(agent_id: str, stage: str) -> AgentDefinition:
    if agent_id not in AGENT_REGISTRY:
        raise AgentRegistryError("Unknown core Agent.")
    definition = AGENT_REGISTRY[agent_id]  # type: ignore[index]
    if not definition.d5_active:
        raise AgentRegistryError("Builder is registered but cannot execute during D5.")
    if stage not in definition.allowed_stages:
        raise AgentRegistryError(f"Agent {agent_id} is not allowed in stage {stage}.")
    return definition


def require_runtime_agent(agent_id: str, stage: str) -> AgentDefinition:
    """Allow active agents plus Builder's document-only G2→G4 definition tasks."""
    if agent_id not in AGENT_REGISTRY:
        raise AgentRegistryError("Unknown core Agent.")
    definition = AGENT_REGISTRY[agent_id]  # type: ignore[index]
    if stage not in definition.allowed_stages:
        raise AgentRegistryError(f"Agent {agent_id} is not allowed in stage {stage}.")
    if definition.d5_active:
        return definition
    if definition.id == "builder" and stage in {
        "solution_confirmation",
        "tech_stack_confirmation",
    }:
        return definition
    raise AgentRegistryError(
        "Builder may prepare definition documents after G2, but cannot develop before G4."
    )
