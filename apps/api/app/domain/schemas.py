import hashlib
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    owner_user_id: str = Field(default="local-admin", min_length=1, max_length=64)


class ProjectRead(ApiModel):
    id: str
    owner_user_id: str
    name: str
    state: str
    context_version: int
    paused_from_state: str | None
    created_at: datetime
    updated_at: datetime


class MessageCreate(ApiModel):
    client_message_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=50_000)
    actor_id: str = Field(default="local-admin", max_length=64)


class MessageRead(ApiModel):
    id: str
    project_id: str
    client_message_id: str
    actor_type: str
    actor_id: str
    content: str
    created_at: datetime


class EventRead(ApiModel):
    id: str
    project_id: str
    sequence: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class ClarificationCreate(ApiModel):
    client_clarification_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=10_000)
    answer: str | None = Field(default=None, max_length=50_000)
    scope_impact: Literal["scope", "user", "timeline", "success", "none"]
    expected_context_version: int = Field(ge=1)
    created_by: str = Field(default="factory-lead", min_length=1, max_length=64)


class ClarificationRead(ApiModel):
    id: str
    project_id: str
    client_clarification_id: str
    question: str
    answer: str | None
    scope_impact: str
    context_version: int
    created_by: str
    created_at: datetime


class ProjectBriefCreate(ApiModel):
    expected_context_version: int = Field(ge=1)
    expected_previous_version: int = Field(default=0, ge=0)
    objective: str = Field(min_length=1, max_length=20_000)
    target_users: list[str] = Field(min_length=1, max_length=20)
    success_criteria: list[str] = Field(min_length=1, max_length=30)
    in_scope: list[str] = Field(min_length=1, max_length=50)
    out_of_scope: list[str] = Field(min_length=1, max_length=50)
    timeline: str = Field(min_length=1, max_length=5_000)
    open_questions: list[str] = Field(default_factory=list, max_length=20)
    source_clarification_ids: list[str] = Field(default_factory=list, max_length=20)
    created_by: str = Field(default="factory-lead", min_length=1, max_length=64)


class ProjectBriefVersionRead(ApiModel):
    id: str
    brief_id: str
    project_id: str
    version: int
    context_version: int
    approval_status: str
    objective: str
    target_users: list[str]
    success_criteria: list[str]
    in_scope: list[str]
    out_of_scope: list[str]
    timeline: str
    open_questions: list[str]
    source_clarification_ids: list[str]
    created_by: str
    created_at: datetime


class ProjectBriefCreateResult(ApiModel):
    brief: ProjectBriefVersionRead
    gate: "GateRead"
    idempotent: bool


class ContextVersionRead(ApiModel):
    id: str
    project_id: str
    version: int
    stage: str
    approval_status: str
    change_reason: str
    gate_decision_id: str | None
    summary: str
    created_at: datetime


class ContextResourceRef(ApiModel):
    resource_type: Literal["context_version", "project_brief", "artifact"]
    resource_id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)
    approval_status: Literal["approved"] = "approved"


class ContextPackCreate(ApiModel):
    context_version: int = Field(ge=1)
    stage: str = Field(min_length=1, max_length=64)
    recipient_agent_id: Literal["factory-lead", "ai-pm", "builder", "reviewer"]
    primary_resource: ContextResourceRef
    required_resources: list[ContextResourceRef] = Field(default_factory=list, max_length=50)
    task: str = Field(min_length=1, max_length=20_000)
    policy: dict[str, Any] = Field(default_factory=dict)


class ContextPackRead(ApiModel):
    id: str
    project_id: str
    context_version: int
    stage: str
    approval_status: str
    recipient_agent_id: str
    primary_resource: ContextResourceRef
    required_resources: list[ContextResourceRef]
    task: str
    policy: dict[str, Any]
    created_at: datetime


class GateRead(ApiModel):
    id: str
    project_id: str
    gate_type: str
    context_version: int
    status: str
    target_state: str | None
    reason: str
    impacted_artifact_refs: list[dict[str, Any]]
    opened_at: datetime


class ArtifactGateRef(ApiModel):
    artifact_id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)


class GateOpenCreate(ApiModel):
    gate_type: Literal["G0", "G1"]
    context_version: int = Field(ge=1)
    target_state: Literal["mrd", "prd"]
    reason: str = Field(min_length=1, max_length=10_000)
    impacted_artifact_refs: list[ArtifactGateRef] = Field(default_factory=list, max_length=20)


class GateDecisionCreate(ApiModel):
    decision: Literal["approve", "changes", "pause", "kill"]
    context_version: int = Field(ge=1)
    comment: str = Field(default="", max_length=10_000)
    decided_by: str = Field(default="local-admin", max_length=64)


class ClarificationAnswerInput(ApiModel):
    clarification_id: str = Field(min_length=1, max_length=36)
    answer: str = Field(min_length=1, max_length=50_000)


class FactoryLeadAlignmentCreate(ApiModel):
    expected_context_version: int = Field(ge=1)
    expected_previous_brief_version: int = Field(default=0, ge=0)
    client_message_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=50_000)
    clarification_answers: list[ClarificationAnswerInput] = Field(
        default_factory=list, max_length=3
    )


class FactoryLeadAlignmentRead(ApiModel):
    invocation_id: str
    idempotent: bool
    state: Literal["running", "clarification_required", "waiting_g0", "failed"]
    context_version: int
    context_pack_id: str
    run_id: str | None = None
    task_id: str | None = None
    message_id: str | None = None
    message: str = ""
    clarification_ids: list[str] = Field(default_factory=list)
    brief: ProjectBriefVersionRead | None = None
    gate: GateRead | None = None
    turns_used: int = 0
    retries_used: int = 0
    requested_model: str
    observed_model: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    checkpoint_hash: str | None = None
    error_code: str | None = None


class PermissionDecisionCreate(ApiModel):
    decision: Literal["allow", "deny"]
    input_hash: str = Field(min_length=64, max_length=64)
    decided_by: str = Field(default="local-admin", max_length=64)


class PermissionRequestRead(ApiModel):
    id: str
    project_id: str
    task_id: str
    run_id: str
    tool_name: str
    input_hash: str
    risk_level: str
    context_version: int
    status: str
    expires_at: datetime | None
    created_at: datetime


class GraphNode(ApiModel):
    id: str
    title: str
    kind: str
    stage: str
    status: str
    latest_version: int


class GraphEdge(ApiModel):
    id: str
    source_id: str
    target_id: str
    relation: str


class GraphRead(ApiModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class TaskRead(ApiModel):
    id: str
    project_id: str
    assigned_agent: str
    title: str
    state: str
    context_version: int
    claimed_by: str | None
    created_at: datetime


class TaskClaimCreate(ApiModel):
    worker_id: str = Field(min_length=1, max_length=100)


class RunStepRead(ApiModel):
    id: str
    run_id: str
    step_index: int
    step_type: str
    state: str
    idempotency_key: str | None
    input_hash: str
    output_ref: str | None
    external_effect_confirmed: bool
    created_at: datetime


class RunRead(ApiModel):
    id: str
    task_id: str
    project_id: str
    attempt: int
    state: str
    input_hash: str
    resume_token: str
    turns_used: int
    retries_used: int
    started_at: datetime | None
    completed_at: datetime | None
    steps: list[RunStepRead]


class RunResumeCreate(ApiModel):
    resume_token: str = Field(min_length=1, max_length=100)
    input_hash: str = Field(min_length=64, max_length=64)


class ArtifactVersionRead(ApiModel):
    artifact_id: str
    version: int
    context_version: int
    approval_status: str
    content_hash: str
    summary: str
    created_at: datetime


class ArtifactContentRead(ApiModel):
    artifact_id: str
    version: int
    title: str
    filename: str
    content_type: str
    content: str


class RuntimeStatusRead(ApiModel):
    database: str
    artifact_root_configured: bool
    workspace_root_configured: bool
    model_provider: str
    model_configured: bool
    event_transport: Literal["sse_cursor"]
    short_polling_degraded: bool
    codex: dict[str, object]


class AgentControlInput(ApiModel):
    """Stable input boundary: Agent runtimes call services with this, never mutate state."""

    project_id: str
    stage: str
    context_version: int = Field(ge=1)
    context_pack_id: str
    task_id: str | None = None


class AgentArtifactProposal(ApiModel):
    """Untrusted Agent output; deterministic services still validate versions and Gates."""

    project_id: str
    context_version: int = Field(ge=1)
    artifact_id: str | None = Field(default=None, max_length=36)
    expected_previous_version: int = Field(default=0, ge=0)
    artifact_kind: Literal["evidence_index", "mrd", "red_team_review"]
    title: str = Field(min_length=1, max_length=240)
    content_ref: str = Field(min_length=1, max_length=500)
    content_hash: str = Field(min_length=64, max_length=64)
    summary: str = Field(default="", max_length=20_000)


class WebResearchEvidenceItem(ApiModel):
    evidence_ref: str = Field(pattern=r"^bocha:web:[0-9a-f]{64}$")
    title: str = Field(min_length=1, max_length=1_000)
    url: str = Field(min_length=1, max_length=8_000)
    site_name: str | None = Field(default=None, max_length=1_000)
    snippet: str | None = Field(default=None, max_length=50_000)
    summary: str | None = Field(default=None, max_length=100_000)
    date_published: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def evidence_ref_matches_url(self) -> "WebResearchEvidenceItem":
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Web research evidence URL must be HTTP(S) with a host.")
        expected = f"bocha:web:{hashlib.sha256(self.url.encode()).hexdigest()}"
        if self.evidence_ref != expected:
            raise ValueError("Web research evidence_ref does not match its URL.")
        return self


class WebResearchEvidenceSet(ApiModel):
    provider: Literal["bocha"] = "bocha"
    provider_request_id: str | None = Field(default=None, max_length=200)
    query: str = Field(min_length=1, max_length=2_000)
    total_estimated_matches: int | None = Field(default=None, ge=0)
    results: list[WebResearchEvidenceItem] = Field(min_length=1, max_length=50)


class DefinitionArtifactProposal(ApiModel):
    artifact_id: str | None = Field(default=None, max_length=36)
    expected_previous_version: int = Field(default=0, ge=0)
    kind: Literal["evidence_index", "mrd"]
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=200_000)
    evidence_refs: list[str] = Field(
        min_length=1,
        max_length=100,
    )
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    status: Literal["waiting_review"] = "waiting_review"


class DefinitionSubmissionCreate(ApiModel):
    source_run_id: str = Field(min_length=1, max_length=36)
    context_pack_id: str = Field(min_length=1, max_length=36)
    expected_context_version: int = Field(ge=1)
    evidence_set_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    research_results: list[WebResearchEvidenceSet] = Field(min_length=1, max_length=3)
    artifact_proposals: list[DefinitionArtifactProposal] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def exact_artifacts_and_evidence(self) -> "DefinitionSubmissionCreate":
        if {item.kind for item in self.artifact_proposals} != {"evidence_index", "mrd"}:
            raise ValueError("Submission requires exactly one Evidence Index and one MRD.")
        research_refs = {
            item.evidence_ref
            for evidence_set in self.research_results
            for item in evidence_set.results
        }
        for proposal in self.artifact_proposals:
            if not set(proposal.evidence_refs).issubset(research_refs):
                raise ValueError("Artifact proposal cites evidence outside this Bocha result set.")
        return self


class DefinitionArtifactRefRead(ApiModel):
    artifact_id: str
    version: int
    kind: Literal["evidence_index", "mrd", "red_team_review"]
    context_version: int
    approval_status: str
    content_hash: str


class DefinitionSubmissionRead(ApiModel):
    id: str
    project_id: str
    source_run_id: str
    context_pack_id: str
    context_version: int
    evidence_set_hash: str
    status: str
    artifact_refs: list[DefinitionArtifactRefRead]
    reviewer_context_pack_id: str
    idempotent: bool
    created_at: datetime


class ReviewerArtifactSnapshot(ApiModel):
    artifact_id: str
    version: int
    kind: Literal["evidence_index", "mrd"]
    title: str
    content_hash: str
    content: str


class DefinitionReviewerInputRead(ApiModel):
    submission_id: str
    project_id: str
    context_version: int
    reviewer_context_pack_id: str
    artifacts: list[ReviewerArtifactSnapshot]
    evidence_refs: list[str]
    task: str
    forbidden_actions: list[str]


class DefinitionReviewFinding(ApiModel):
    severity: Literal["P0", "P1", "P2"]
    title: str = Field(min_length=1, max_length=500)
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    reproduction: list[str] = Field(default_factory=list, max_length=50)
    impact: str = Field(min_length=1, max_length=20_000)
    recommended_fix: str = Field(min_length=1, max_length=20_000)


class RedTeamReviewProposal(ApiModel):
    artifact_id: str | None = Field(default=None, max_length=36)
    expected_previous_version: int = Field(default=0, ge=0)
    kind: Literal["red_team_review"] = "red_team_review"
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=200_000)
    evidence_refs: list[str] = Field(min_length=1, max_length=100)


class DefinitionReviewCreate(ApiModel):
    source_run_id: str = Field(min_length=1, max_length=36)
    context_pack_id: str = Field(min_length=1, max_length=36)
    expected_context_version: int = Field(ge=1)
    verdict: Literal["pass", "pass_with_known_issues", "reject"]
    message: str = Field(min_length=1, max_length=20_000)
    findings: list[DefinitionReviewFinding] = Field(default_factory=list, max_length=100)
    red_team_review: RedTeamReviewProposal


class DefinitionReviewRead(ApiModel):
    review_id: str
    submission_id: str
    project_id: str
    context_version: int
    verdict: str
    status: str
    red_team_review: DefinitionArtifactRefRead
    gate: GateRead | None
    idempotent: bool


class ErrorBody(ApiModel):
    code: str
    message: str
    user_message: str
    retryable: bool
    request_id: str


class ErrorResponse(ApiModel):
    error: ErrorBody


ProjectBriefCreateResult.model_rebuild()
