from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

BochaEvidenceRef = Annotated[
    str,
    StringConstraints(pattern=r"^bocha:web:[0-9a-f]{64}$"),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactProposal(StrictModel):
    kind: str
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=200_000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    status: Literal["draft", "waiting_review"] = "waiting_review"


class ToolRequestOutput(StrictModel):
    tool_id: str
    reason: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    side_effect: Literal["none", "reversible", "external-write", "destructive", "billable"]


class ClarificationProposal(StrictModel):
    question: str = Field(min_length=1, max_length=10_000)
    scope_impact: Literal["scope", "user", "timeline", "success", "none"]


class ProjectBriefProposal(StrictModel):
    objective: str = Field(min_length=1, max_length=20_000)
    target_users: list[str] = Field(min_length=1, max_length=20)
    success_criteria: list[str] = Field(min_length=1, max_length=30)
    in_scope: list[str] = Field(min_length=1, max_length=50)
    out_of_scope: list[str] = Field(min_length=1, max_length=50)
    timeline: str = Field(min_length=1, max_length=5_000)
    open_questions: list[str] = Field(default_factory=list, max_length=20)


class GateRequestOutput(StrictModel):
    gate_type: Literal["G0"]
    context_version: int = Field(ge=1)
    target_state: Literal["mrd"]
    reason: str = Field(min_length=1, max_length=10_000)


class TransitionProposalOutput(StrictModel):
    from_state: Literal["alignment"]
    target_state: Literal["mrd"]
    context_version: int = Field(ge=1)
    required_gate: Literal["G0"]


class FactoryLeadOutput(StrictModel):
    message: str
    identity_event: dict[str, Any] | None = None
    tool_request: ToolRequestOutput | None = None
    artifact_proposals: list[ArtifactProposal] = Field(default_factory=list)
    clarification_proposals: list[ClarificationProposal] = Field(default_factory=list, max_length=3)
    project_brief: ProjectBriefProposal | None = None
    gate_request: GateRequestOutput | None = None
    transition_proposal: TransitionProposalOutput | None = None
    open_questions: list[str] = Field(default_factory=list, max_length=3)


class AiPmOutput(StrictModel):
    message: str
    artifact_proposals: list[ArtifactProposal] = Field(default_factory=list)
    verified_fact_proposals: list[dict[str, Any]] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    transition_proposal: dict[str, Any] | None = None

    @model_validator(mode="after")
    def evidence_is_required_for_mrd_claims(self) -> AiPmOutput:
        for artifact in self.artifact_proposals:
            if artifact.kind in {"evidence_index", "mrd"} and not artifact.evidence_refs:
                raise ValueError("Evidence Index and MRD proposals require EvidenceRef values.")
        return self


class AiPmMrdArtifactProposal(ArtifactProposal):
    kind: Literal["evidence_index", "mrd"]
    content: str = Field(
        min_length=1,
        max_length=200_000,
        description=(
            "Markdown content. Every value in evidence_refs must appear verbatim next to the "
            "claim it supports; never replace it with E1/E2 aliases."
        ),
    )
    evidence_refs: list[BochaEvidenceRef] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def evidence_refs_are_unique(self) -> AiPmMrdArtifactProposal:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("MRD artifact EvidenceRef values must be unique.")
        missing = [ref for ref in self.evidence_refs if ref not in self.content]
        if missing:
            raise ValueError(
                "Every declared EvidenceRef must appear verbatim in the artifact content."
            )
        return self


class AiPmMrdOutput(AiPmOutput):
    artifact_proposals: list[AiPmMrdArtifactProposal] = Field(min_length=2)

    @model_validator(mode="after")
    def requires_evidence_index_and_mrd(self) -> AiPmMrdOutput:
        kinds = {artifact.kind for artifact in self.artifact_proposals}
        if len(self.artifact_proposals) != 2 or kinds != {"evidence_index", "mrd"}:
            raise ValueError(
                "MRD stage requires exactly one Evidence Index and one MRD proposal."
            )
        return self


class AiPmPrdArtifactProposal(ArtifactProposal):
    kind: Literal["prd"]
    evidence_refs: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def evidence_refs_are_inline(self) -> AiPmPrdArtifactProposal:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("PRD EvidenceRef values must be unique.")
        missing = [ref for ref in self.evidence_refs if ref not in self.content]
        if missing:
            raise ValueError(
                "Every declared PRD EvidenceRef must appear verbatim in the PRD content."
            )
        return self


class AiPmPrdOutput(AiPmOutput):
    artifact_proposals: list[AiPmPrdArtifactProposal] = Field(
        min_length=1,
        max_length=1,
    )
    transition_proposal: None = None


class BuilderOutput(StrictModel):
    message: str
    technical_decisions: list[dict[str, Any]] = Field(default_factory=list)
    tool_requests: list[ToolRequestOutput] = Field(default_factory=list)
    artifact_proposals: list[ArtifactProposal] = Field(default_factory=list)
    test_results: list[dict[str, Any]] = Field(default_factory=list)
    known_issues: list[dict[str, Any]] = Field(default_factory=list)
    gate_request: dict[str, Any] | None = None
    transition_proposal: dict[str, Any] | None = None


class ReviewerFinding(StrictModel):
    severity: Literal["P0", "P1", "P2"]
    title: str
    evidence_refs: list[str] = Field(default_factory=list)
    reproduction: list[str] = Field(default_factory=list)
    impact: str
    recommended_fix: str


class ReviewerMrdFinding(ReviewerFinding):
    evidence_refs: list[BochaEvidenceRef] = Field(min_length=1, max_length=100)


class ReviewerOutput(StrictModel):
    message: str
    verdict: Literal["pass", "pass_with_known_issues", "reject"]
    findings: list[ReviewerFinding] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    artifact_proposals: list[ArtifactProposal] = Field(default_factory=list)
    transition_proposal: dict[str, Any] | None = None


class ReviewerMrdArtifactProposal(ArtifactProposal):
    kind: Literal["red_team_review"]
    content: str = Field(
        min_length=1,
        max_length=200_000,
        description=(
            "Markdown review. Every value in evidence_refs must appear verbatim next to the "
            "finding or conclusion it supports."
        ),
    )
    evidence_refs: list[BochaEvidenceRef] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def evidence_refs_are_inline(self) -> ReviewerMrdArtifactProposal:
        missing = [ref for ref in self.evidence_refs if ref not in self.content]
        if missing:
            raise ValueError(
                "Every declared EvidenceRef must appear verbatim in the review content."
            )
        return self


class ReviewerMrdOutput(ReviewerOutput):
    findings: list[ReviewerMrdFinding] = Field(default_factory=list)
    evidence_refs: list[BochaEvidenceRef] = Field(min_length=1, max_length=100)
    artifact_proposals: list[ReviewerMrdArtifactProposal] = Field(
        min_length=1,
        max_length=1,
    )

    @model_validator(mode="after")
    def evidence_refs_are_unique(self) -> ReviewerMrdOutput:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("Reviewer EvidenceRef values must be unique.")
        return self


class ReviewerPrdArtifactProposal(ArtifactProposal):
    kind: Literal["prd_review"]
    evidence_refs: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def evidence_refs_are_inline(self) -> ReviewerPrdArtifactProposal:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("PRD Review EvidenceRef values must be unique.")
        missing = [ref for ref in self.evidence_refs if ref not in self.content]
        if missing:
            raise ValueError(
                "Every declared review EvidenceRef must appear verbatim in review content."
            )
        return self


class ReviewerPrdOutput(ReviewerOutput):
    evidence_refs: list[str] = Field(min_length=1, max_length=100)
    artifact_proposals: list[ReviewerPrdArtifactProposal] = Field(
        min_length=1,
        max_length=1,
    )
    transition_proposal: None = None

    @model_validator(mode="after")
    def evidence_refs_are_unique(self) -> ReviewerPrdOutput:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("Reviewer PRD EvidenceRef values must be unique.")
        return self


OUTPUT_MODELS = {
    "factory-lead": FactoryLeadOutput,
    "ai-pm": AiPmOutput,
    "builder": BuilderOutput,
    "reviewer": ReviewerOutput,
}


def output_model_for(agent_id: str, stage: str) -> type[BaseModel]:
    if agent_id == "ai-pm" and stage == "mrd":
        return AiPmMrdOutput
    if agent_id == "reviewer" and stage == "mrd":
        return ReviewerMrdOutput
    if agent_id == "ai-pm" and stage == "prd":
        return AiPmPrdOutput
    if agent_id == "reviewer" and stage == "prd":
        return ReviewerPrdOutput
    return OUTPUT_MODELS[agent_id]
