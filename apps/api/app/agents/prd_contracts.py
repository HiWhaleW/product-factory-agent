from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.schemas import GateRead, KnownIssueRead


class PrdContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrdArtifactProposal(PrdContractModel):
    artifact_id: str | None = Field(default=None, max_length=36)
    expected_previous_version: int = Field(default=0, ge=0)
    kind: Literal["prd"] = "prd"
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=200_000)
    evidence_refs: list[str] = Field(min_length=1, max_length=100)
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    status: Literal["waiting_review"] = "waiting_review"

    @model_validator(mode="after")
    def refs_must_be_inline(self) -> PrdArtifactProposal:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("PRD evidence_refs must be unique.")
        if any(ref not in self.content for ref in self.evidence_refs):
            raise ValueError("Every PRD evidence_ref must appear inline in content.")
        return self


class PrdSubmissionCreate(PrdContractModel):
    source_run_id: str = Field(min_length=1, max_length=36)
    context_pack_id: str = Field(min_length=1, max_length=36)
    expected_context_version: int = Field(ge=1)
    artifact_proposal: PrdArtifactProposal


class PrdArtifactRefRead(PrdContractModel):
    artifact_id: str
    version: int
    kind: Literal["prd", "prd_review"]
    context_version: int
    approval_status: str
    content_hash: str
    artifact_ref: str


class PrdSubmissionRead(PrdContractModel):
    submission_id: str
    project_id: str
    source_run_id: str
    context_pack_id: str
    context_version: int
    status: str
    prd: PrdArtifactRefRead
    reviewer_context_pack_id: str
    idempotent: bool
    created_at: datetime


class PrdReviewerInputRead(PrdContractModel):
    submission_id: str
    project_id: str
    context_version: int
    reviewer_context_pack_id: str
    artifact_ref: str
    title: str
    content_hash: str
    task: str
    forbidden_actions: list[str]


class PrdReviewFinding(PrdContractModel):
    severity: Literal["P0", "P1", "P2"]
    title: str = Field(min_length=1, max_length=500)
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    reproduction: list[str] = Field(default_factory=list, max_length=50)
    impact: str = Field(min_length=1, max_length=20_000)
    recommended_fix: str = Field(min_length=1, max_length=20_000)


class PrdReviewArtifactProposal(PrdContractModel):
    artifact_id: str | None = Field(default=None, max_length=36)
    expected_previous_version: int = Field(default=0, ge=0)
    kind: Literal["prd_review"] = "prd_review"
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=200_000)
    evidence_refs: list[str] = Field(min_length=1, max_length=100)
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    status: Literal["waiting_review"] = "waiting_review"

    @model_validator(mode="after")
    def refs_must_be_inline(self) -> PrdReviewArtifactProposal:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("PRD Review evidence_refs must be unique.")
        if any(ref not in self.content for ref in self.evidence_refs):
            raise ValueError("Every PRD Review evidence_ref must appear inline in content.")
        return self


class PrdReviewCreate(PrdContractModel):
    source_run_id: str = Field(min_length=1, max_length=36)
    context_pack_id: str = Field(min_length=1, max_length=36)
    expected_context_version: int = Field(ge=1)
    verdict: Literal["pass", "pass_with_known_issues", "reject"]
    message: str = Field(min_length=1, max_length=20_000)
    findings: list[PrdReviewFinding] = Field(default_factory=list, max_length=100)
    review_artifact: PrdReviewArtifactProposal


class PrdReviewRead(PrdContractModel):
    submission_id: str
    project_id: str
    context_version: int
    verdict: str
    status: str
    prd: PrdArtifactRefRead
    prd_review: PrdArtifactRefRead
    known_issues: list[KnownIssueRead] = Field(default_factory=list)
    gate: GateRead | None
    idempotent: bool
