from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BuilderContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BuilderTechnicalDecision(BuilderContractModel):
    decision: str = Field(min_length=1, max_length=2_000)
    reason: str = Field(min_length=1, max_length=5_000)


class BuilderTestResult(BuilderContractModel):
    command: str = Field(min_length=1, max_length=2_000)
    status: Literal["passed", "failed", "blocked", "not_run"]
    summary: str = Field(min_length=1, max_length=5_000)


class BuilderKnownIssue(BuilderContractModel):
    severity: Literal["P0", "P1", "P2"]
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=5_000)
    status: Literal["open", "resolved", "accepted"]


class BuilderCodexOutput(BuilderContractModel):
    """Provider-compatible strict output for the post-G4 Codex Builder."""

    message: str = Field(min_length=1, max_length=20_000)
    technical_decisions: list[BuilderTechnicalDecision] = Field(max_length=100)
    tool_requests: list[None] = Field(max_length=0)
    artifact_proposals: list[None] = Field(max_length=0)
    test_results: list[BuilderTestResult] = Field(max_length=100)
    known_issues: list[BuilderKnownIssue] = Field(max_length=100)
    gate_request: None
    transition_proposal: None
