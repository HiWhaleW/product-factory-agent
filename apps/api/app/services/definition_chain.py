from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import (
    AgentMembership,
    AgentRun,
    AgentTask,
    Artifact,
    ArtifactEdge,
    ArtifactVersion,
    ContextPack,
    ContextVersion,
    DefinitionReview,
    DefinitionSubmission,
    Event,
    Gate,
    PermissionDecision,
    PermissionRequest,
    Project,
    ProjectBrief,
    ProjectBriefVersion,
    RunStep,
)
from app.domain.schemas import (
    DefinitionArtifactProposal,
    DefinitionArtifactRefRead,
    DefinitionReviewCreate,
    DefinitionReviewerInputRead,
    DefinitionReviewRead,
    DefinitionSubmissionCreate,
    DefinitionSubmissionRead,
    ReviewerArtifactSnapshot,
)
from app.services.artifact_store import (
    ArtifactStoreError,
    read_verified_artifact,
    write_immutable_artifact,
)


class DefinitionChainError(RuntimeError):
    def __init__(self, code: str, message: str, http_status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def stable_input_hash(value: Any) -> str:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def research_set_hash(body: DefinitionSubmissionCreate) -> str:
    payload = [item.model_dump(mode="json") for item in body.research_results]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def submit_definition(
    session: Session,
    *,
    artifact_root: Path,
    project_id: str,
    idempotency_key: str,
    body: DefinitionSubmissionCreate,
) -> DefinitionSubmissionRead:
    project = _require_project(session, project_id)
    body_hash = stable_input_hash(body)
    existing = session.scalar(
        select(DefinitionSubmission).where(
            DefinitionSubmission.project_id == project_id,
            DefinitionSubmission.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.input_hash != body_hash:
            raise DefinitionChainError(
                "IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同的 AI PM 提案。"
            )
        return definition_submission_read(session, existing, idempotent=True)
    existing_run = session.scalar(
        select(DefinitionSubmission).where(
            DefinitionSubmission.source_run_id == body.source_run_id
        )
    )
    if existing_run is not None:
        raise DefinitionChainError(
            "SOURCE_RUN_ALREADY_SUBMITTED", "该 AI PM Run 已经提交过确定性产物。"
        )

    if project.state != "mrd":
        raise DefinitionChainError("ARTIFACT_STAGE_INVALID", "AI PM 提案只能在 MRD 阶段提交。")
    if project.context_version != body.expected_context_version:
        raise DefinitionChainError("STALE_CONTEXT", "AI PM 提案基于旧 Context，禁止合并。")
    pack, run = _require_bound_run(
        session,
        project=project,
        context_pack_id=body.context_pack_id,
        run_id=body.source_run_id,
        agent_id="ai-pm",
    )
    if pack.stage != "mrd":
        raise DefinitionChainError("CONTEXT_STAGE_MISMATCH", "AI PM Context Pack 不是 MRD 阶段。")

    computed_evidence_hash = research_set_hash(body)
    if computed_evidence_hash != body.evidence_set_hash:
        raise DefinitionChainError(
            "EVIDENCE_SET_HASH_MISMATCH", "博查结果内容与提交的 evidence_set_hash 不一致。"
        )
    tool_step = session.scalar(
        select(RunStep)
        .where(
            RunStep.run_id == run.id,
            RunStep.step_type == "tool",
            RunStep.state == "completed",
            RunStep.external_effect_confirmed.is_(True),
        )
        .order_by(RunStep.step_index.desc())
    )
    if tool_step is None or tool_step.output_ref != f"evidence-set://{computed_evidence_hash}":
        raise DefinitionChainError(
            "EVIDENCE_SET_NOT_CONFIRMED", "AI PM Run 没有已确认且哈希一致的博查结果。"
        )
    _require_allowed_research_permission(session, run.id)

    by_kind = {item.kind: item for item in body.artifact_proposals}
    versions: dict[str, tuple[Artifact, ArtifactVersion]] = {}
    for kind in ("evidence_index", "mrd"):
        proposal = by_kind[kind]
        _reject_secret_like_text(proposal.content)
        versions[kind] = _persist_artifact(
            session,
            artifact_root=artifact_root,
            project=project,
            proposal=proposal,
        )

    evidence_artifact, evidence_version = versions["evidence_index"]
    mrd_artifact, mrd_version = versions["mrd"]
    edge = session.scalar(
        select(ArtifactEdge).where(
            ArtifactEdge.project_id == project.id,
            ArtifactEdge.source_id == evidence_artifact.id,
            ArtifactEdge.target_id == mrd_artifact.id,
        )
    )
    if edge is None:
        session.add(
            ArtifactEdge(
                project_id=project.id,
                source_id=evidence_artifact.id,
                target_id=mrd_artifact.id,
                relation="supports",
            )
        )

    reviewer_pack = _create_reviewer_pack(session, project)
    all_evidence_refs = sorted(
        {
            ref
            for proposal in body.artifact_proposals
            for ref in proposal.evidence_refs
        }
    )
    submission = DefinitionSubmission(
        project_id=project.id,
        source_run_id=run.id,
        context_pack_id=pack.id,
        context_version=project.context_version,
        idempotency_key=idempotency_key,
        input_hash=body_hash,
        evidence_set_hash=computed_evidence_hash,
        evidence_refs=all_evidence_refs,
        status="waiting_reviewer",
        evidence_artifact_id=evidence_artifact.id,
        evidence_artifact_version=evidence_version.version,
        mrd_artifact_id=mrd_artifact.id,
        mrd_artifact_version=mrd_version.version,
        reviewer_context_pack_id=reviewer_pack.id,
    )
    session.add(submission)
    session.flush()
    reviewer_pack.policy = {
        **reviewer_pack.policy,
        "definition_submission_id": submission.id,
    }
    _append_event(
        session,
        project.id,
        "definition.submitted",
        {
            "submission_id": submission.id,
            "source_run_id": run.id,
            "context_version": project.context_version,
            "reviewer_context_pack_id": reviewer_pack.id,
            "artifact_refs": [
                {"artifact_id": evidence_artifact.id, "version": evidence_version.version},
                {"artifact_id": mrd_artifact.id, "version": mrd_version.version},
            ],
        },
    )
    return definition_submission_read(session, submission, idempotent=False)


def definition_submission_read(
    session: Session, submission: DefinitionSubmission, *, idempotent: bool
) -> DefinitionSubmissionRead:
    refs = [
        _artifact_ref(
            session,
            submission.evidence_artifact_id,
            submission.evidence_artifact_version,
        ),
        _artifact_ref(session, submission.mrd_artifact_id, submission.mrd_artifact_version),
    ]
    return DefinitionSubmissionRead(
        id=submission.id,
        project_id=submission.project_id,
        source_run_id=submission.source_run_id,
        context_pack_id=submission.context_pack_id,
        context_version=submission.context_version,
        evidence_set_hash=submission.evidence_set_hash,
        status=submission.status,
        artifact_refs=refs,
        reviewer_context_pack_id=submission.reviewer_context_pack_id,
        idempotent=idempotent,
        created_at=submission.created_at,
    )


def reviewer_input(
    session: Session,
    *,
    artifact_root: Path,
    project_id: str,
    submission_id: str,
) -> DefinitionReviewerInputRead:
    project = _require_project(session, project_id)
    submission = session.get(DefinitionSubmission, submission_id)
    if submission is None or submission.project_id != project.id:
        raise DefinitionChainError("DEFINITION_SUBMISSION_NOT_FOUND", "AI PM 提交不存在。", 404)
    if project.state != "mrd" or project.context_version != submission.context_version:
        raise DefinitionChainError("STALE_CONTEXT", "Reviewer 输入已过期。")
    if submission.status != "waiting_reviewer":
        raise DefinitionChainError("DEFINITION_NOT_REVIEWABLE", "AI PM 提交当前不可审查。")
    snapshots = [
        _artifact_snapshot(
            session,
            artifact_root,
            submission.evidence_artifact_id,
            submission.evidence_artifact_version,
        ),
        _artifact_snapshot(
            session,
            artifact_root,
            submission.mrd_artifact_id,
            submission.mrd_artifact_version,
        ),
    ]
    return DefinitionReviewerInputRead(
        submission_id=submission.id,
        project_id=project.id,
        context_version=project.context_version,
        reviewer_context_pack_id=submission.reviewer_context_pack_id,
        artifacts=snapshots,
        evidence_refs=submission.evidence_refs,
        task="对 Evidence Index 与 MRD 做清洁上下文红队审查，并提交 Red Team Review。",
        forbidden_actions=[
            "advance_project_state",
            "approve_gate",
            "modify_ai_pm_artifacts",
            "read_secret_values",
        ],
    )


def submit_definition_review(
    session: Session,
    *,
    artifact_root: Path,
    project_id: str,
    submission_id: str,
    idempotency_key: str,
    body: DefinitionReviewCreate,
) -> DefinitionReviewRead:
    project = _require_project(session, project_id)
    submission = session.get(DefinitionSubmission, submission_id)
    if submission is None or submission.project_id != project.id:
        raise DefinitionChainError("DEFINITION_SUBMISSION_NOT_FOUND", "AI PM 提交不存在。", 404)
    body_hash = stable_input_hash(body)
    existing = session.scalar(
        select(DefinitionReview).where(DefinitionReview.submission_id == submission.id)
    )
    if existing is not None:
        if existing.input_hash != body_hash or existing.idempotency_key != idempotency_key:
            raise DefinitionChainError(
                "DEFINITION_REVIEW_CONFLICT", "该 AI PM 提交已有不同 Reviewer 结果。"
            )
        return definition_review_read(session, project, submission, existing, idempotent=True)
    if project.state != "mrd" or project.context_version != body.expected_context_version:
        raise DefinitionChainError("STALE_CONTEXT", "Reviewer 结果基于旧 Context，禁止合并。")
    if submission.context_version != project.context_version:
        raise DefinitionChainError("STALE_CONTEXT", "AI PM 提交已过期。")
    if body.context_pack_id != submission.reviewer_context_pack_id:
        raise DefinitionChainError(
            "REVIEW_CONTEXT_MISMATCH", "Reviewer 使用了错误的 Context Pack。"
        )
    _, review_run = _require_bound_run(
        session,
        project=project,
        context_pack_id=body.context_pack_id,
        run_id=body.source_run_id,
        agent_id="reviewer",
    )
    allowed_refs = set(submission.evidence_refs)
    cited_refs = set(body.red_team_review.evidence_refs)
    cited_refs.update(ref for finding in body.findings for ref in finding.evidence_refs)
    invalid_bocha_refs = {
        ref for ref in cited_refs if ref.startswith("bocha:web:") and ref not in allowed_refs
    }
    if invalid_bocha_refs:
        raise DefinitionChainError(
            "REVIEW_EVIDENCE_MISMATCH", "Reviewer 引用了本次搜索结果之外的博查证据。"
        )
    _reject_secret_like_text(body.red_team_review.content)
    red_team_artifact, red_team_version = _persist_red_team_artifact(
        session,
        artifact_root=artifact_root,
        project=project,
        proposal=body.red_team_review,
    )

    gate = None
    if body.verdict in {"pass", "pass_with_known_issues"}:
        gate = Gate(
            project_id=project.id,
            gate_type="G1",
            context_version=project.context_version,
            status="open",
            target_state="prd",
            reason="Evidence Index、MRD 与 Red Team Review 已完成，等待用户决定。",
            impacted_artifact_refs=[
                {
                    "artifact_id": submission.evidence_artifact_id,
                    "version": submission.evidence_artifact_version,
                },
                {
                    "artifact_id": submission.mrd_artifact_id,
                    "version": submission.mrd_artifact_version,
                },
                {"artifact_id": red_team_artifact.id, "version": red_team_version.version},
            ],
        )
        session.add(gate)
        session.flush()
        submission.status = "waiting_g1"
        _append_event(
            session,
            project.id,
            "gate.opened",
            {
                "gate_id": gate.id,
                "gate_type": "G1",
                "context_version": project.context_version,
                "target_state": "prd",
                "impacted_artifact_refs": gate.impacted_artifact_refs,
            },
        )
    else:
        submission.status = "changes_requested"
        for artifact_id in (
            submission.evidence_artifact_id,
            submission.mrd_artifact_id,
        ):
            artifact = session.get(Artifact, artifact_id)
            if artifact is not None:
                artifact.status = "changes_requested"

    review = DefinitionReview(
        submission_id=submission.id,
        source_run_id=review_run.id,
        context_pack_id=body.context_pack_id,
        idempotency_key=idempotency_key,
        input_hash=body_hash,
        verdict=body.verdict,
        red_team_artifact_id=red_team_artifact.id,
        red_team_artifact_version=red_team_version.version,
        gate_id=gate.id if gate else None,
    )
    session.add(review)
    session.flush()
    _append_event(
        session,
        project.id,
        "definition.reviewed",
        {
            "submission_id": submission.id,
            "review_id": review.id,
            "source_run_id": review_run.id,
            "verdict": body.verdict,
            "status": submission.status,
            "red_team_artifact_id": red_team_artifact.id,
            "red_team_artifact_version": red_team_version.version,
            "gate_id": gate.id if gate else None,
        },
    )
    return definition_review_read(session, project, submission, review, idempotent=False)


def definition_review_read(
    session: Session,
    project: Project,
    submission: DefinitionSubmission,
    review: DefinitionReview,
    *,
    idempotent: bool,
) -> DefinitionReviewRead:
    return DefinitionReviewRead(
        review_id=review.id,
        submission_id=submission.id,
        project_id=project.id,
        context_version=submission.context_version,
        verdict=review.verdict,
        status=submission.status,
        red_team_review=_artifact_ref(
            session, review.red_team_artifact_id, review.red_team_artifact_version
        ),
        gate=session.get(Gate, review.gate_id) if review.gate_id else None,
        idempotent=idempotent,
    )


def _require_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise DefinitionChainError("PROJECT_NOT_FOUND", "项目不存在。", 404)
    return project


def _require_bound_run(
    session: Session,
    *,
    project: Project,
    context_pack_id: str,
    run_id: str,
    agent_id: str,
) -> tuple[ContextPack, AgentRun]:
    pack = session.get(ContextPack, context_pack_id)
    run = session.get(AgentRun, run_id)
    task = session.get(AgentTask, run.task_id) if run else None
    if pack is None or pack.project_id != project.id:
        raise DefinitionChainError("CONTEXT_PACK_NOT_FOUND", "Context Pack 不存在。", 404)
    if (
        pack.approval_status != "approved"
        or pack.context_version != project.context_version
        or pack.stage != project.state
        or pack.agent_id != agent_id
    ):
        raise DefinitionChainError("STALE_CONTEXT", "Context Pack 与当前项目或 Agent 不匹配。")
    if (
        run is None
        or task is None
        or task.project_id != project.id
        or task.assigned_agent != agent_id
        or task.context_version != project.context_version
        or run.state != "succeeded"
    ):
        raise DefinitionChainError("SOURCE_RUN_INVALID", "来源 Agent Run 不存在或未成功完成。")
    candidates = session.scalars(
        select(Event)
        .where(Event.project_id == project.id, Event.event_type == "run.started")
        .order_by(Event.sequence.desc())
    )
    matched = next(
        (
            event
            for event in candidates
            if event.payload.get("run_id") == run.id
            and event.payload.get("context_pack_id") == pack.id
            and event.payload.get("agent_id") == agent_id
        ),
        None,
    )
    if matched is None:
        raise DefinitionChainError("RUN_CONTEXT_BINDING_INVALID", "Run 未精确绑定该 Context Pack。")
    model_step = session.scalar(
        select(RunStep)
        .where(
            RunStep.run_id == run.id,
            RunStep.step_type == "model",
            RunStep.state == "completed",
        )
        .order_by(RunStep.step_index.desc())
    )
    checkpoint_step = session.scalar(
        select(RunStep)
        .where(
            RunStep.run_id == run.id,
            RunStep.step_type == "checkpoint",
            RunStep.state == "completed",
            RunStep.external_effect_confirmed.is_(True),
        )
        .order_by(RunStep.step_index.desc())
    )
    if (
        model_step is None
        or not model_step.output_ref
        or not model_step.output_ref.startswith("model://")
        or checkpoint_step is None
        or not checkpoint_step.output_ref
        or checkpoint_step.idempotency_key != f"checkpoint:{checkpoint_step.input_hash}"
    ):
        raise DefinitionChainError(
            "SOURCE_RUN_JOURNAL_INVALID", "来源 Run 缺少完整的 model/checkpoint 记录。"
        )
    return pack, run


def _require_allowed_research_permission(session: Session, run_id: str) -> None:
    request = session.scalar(
        select(PermissionRequest)
        .where(PermissionRequest.run_id == run_id, PermissionRequest.tool_name == "web_research")
        .order_by(PermissionRequest.created_at.desc())
    )
    decision = (
        session.scalar(
            select(PermissionDecision).where(
                PermissionDecision.permission_request_id == request.id,
                PermissionDecision.decision == "allow",
                PermissionDecision.input_hash == request.input_hash,
            )
        )
        if request
        else None
    )
    if request is None or request.status != "decided" or decision is None:
        raise DefinitionChainError(
            "RESEARCH_PERMISSION_NOT_CONFIRMED", "博查调用没有独立且有效的一次性授权。"
        )


def _persist_artifact(
    session: Session,
    *,
    artifact_root: Path,
    project: Project,
    proposal: DefinitionArtifactProposal,
) -> tuple[Artifact, ArtifactVersion]:
    return _persist_artifact_values(
        session,
        artifact_root=artifact_root,
        project=project,
        artifact_id=proposal.artifact_id,
        expected_previous_version=proposal.expected_previous_version,
        kind=proposal.kind,
        title=proposal.title,
        content=proposal.content,
        summary=f"{proposal.kind}；证据 {len(proposal.evidence_refs)} 条；等待 Reviewer。",
    )


def _persist_red_team_artifact(
    session: Session, *, artifact_root: Path, project: Project, proposal: Any
) -> tuple[Artifact, ArtifactVersion]:
    return _persist_artifact_values(
        session,
        artifact_root=artifact_root,
        project=project,
        artifact_id=proposal.artifact_id,
        expected_previous_version=proposal.expected_previous_version,
        kind="red_team_review",
        title=proposal.title,
        content=proposal.content,
        summary=f"Red Team Review；证据引用 {len(proposal.evidence_refs)} 条。",
    )


def _persist_artifact_values(
    session: Session,
    *,
    artifact_root: Path,
    project: Project,
    artifact_id: str | None,
    expected_previous_version: int,
    kind: str,
    title: str,
    content: str,
    summary: str,
) -> tuple[Artifact, ArtifactVersion]:
    artifact = session.get(Artifact, artifact_id) if artifact_id else None
    if artifact_id and artifact is None:
        raise DefinitionChainError("ARTIFACT_NOT_FOUND", "指定的产物不存在。", 404)
    if artifact is None:
        existing = session.scalar(
            select(Artifact).where(
                Artifact.project_id == project.id,
                Artifact.stage == "mrd",
                Artifact.kind == kind,
            )
        )
        if existing is not None:
            raise DefinitionChainError(
                "ARTIFACT_ID_REQUIRED", "该类型产物已存在，创建新版本时必须传 artifact_id。"
            )
        if expected_previous_version != 0:
            raise DefinitionChainError("ARTIFACT_VERSION_CONFLICT", "新产物前置版本必须为 0。")
        artifact = Artifact(
            project_id=project.id,
            title=title,
            kind=kind,
            stage="mrd",
            status="waiting_review",
            latest_version=0,
        )
        session.add(artifact)
        session.flush()
    elif artifact.project_id != project.id or artifact.stage != "mrd" or artifact.kind != kind:
        raise DefinitionChainError("ARTIFACT_BINDING_INVALID", "产物身份、阶段或类型不匹配。")
    if artifact.latest_version != expected_previous_version:
        raise DefinitionChainError("ARTIFACT_VERSION_CONFLICT", "产物前置版本已经变化。")
    try:
        content_ref, content_hash = write_immutable_artifact(
            artifact_root,
            project_id=project.id,
            kind=kind,
            content=content,
        )
    except ArtifactStoreError as exc:
        raise DefinitionChainError("ARTIFACT_CONTENT_INVALID", str(exc)) from exc
    version = ArtifactVersion(
        artifact_id=artifact.id,
        version=artifact.latest_version + 1,
        context_version=project.context_version,
        approval_status="draft",
        content_ref=content_ref,
        content_hash=content_hash,
        summary=summary,
    )
    artifact.latest_version = version.version
    artifact.title = title
    artifact.status = "waiting_review"
    session.add(version)
    session.flush()
    _append_event(
        session,
        project.id,
        "artifact.created" if version.version == 1 else "artifact.versioned",
        {
            "artifact_id": artifact.id,
            "artifact_version_id": version.id,
            "kind": artifact.kind,
            "version": version.version,
            "context_version": version.context_version,
            "approval_status": version.approval_status,
        },
    )
    return artifact, version


def _create_reviewer_pack(session: Session, project: Project) -> ContextPack:
    context = session.scalar(
        select(ContextVersion).where(
            ContextVersion.project_id == project.id,
            ContextVersion.version == project.context_version,
            ContextVersion.approval_status == "active",
        )
    )
    if context is None:
        raise DefinitionChainError("CONTEXT_VERSION_NOT_FOUND", "当前 ContextVersion 不存在。", 500)
    brief_row = session.execute(
        select(ProjectBrief, ProjectBriefVersion)
        .join(ProjectBriefVersion, ProjectBriefVersion.brief_id == ProjectBrief.id)
        .where(
            ProjectBrief.project_id == project.id,
            ProjectBriefVersion.approval_status == "approved",
        )
        .order_by(ProjectBriefVersion.version.desc())
    ).first()
    if brief_row is None:
        raise DefinitionChainError(
            "APPROVED_BRIEF_NOT_FOUND", "Reviewer Context 缺少已批准 Project Brief。", 500
        )
    brief, brief_version = brief_row
    pack = ContextPack(
        project_id=project.id,
        context_version_id=context.id,
        context_version=context.version,
        stage="mrd",
        approval_status="approved",
        primary_resource_type="project_brief",
        primary_resource_id=brief.id,
        primary_resource_version=brief_version.version,
        agent_id="reviewer",
        task="通过 definition-review/v1 输入契约审查 Evidence Index 与 MRD。",
        references=[],
        policy={
            "input_contract": "definition-review/v1",
            "allowed_capability_ids": ["CAP-10"],
            "forbidden_actions": [
                "advance_project_state",
                "approve_gate",
                "modify_ai_pm_artifacts",
                "read_secret_values",
            ],
        },
    )
    session.add(pack)
    session.flush()
    _append_event(
        session,
        project.id,
        "context.pack_created",
        {
            "context_pack_id": pack.id,
            "context_version": pack.context_version,
            "stage": pack.stage,
            "recipient_agent_id": "reviewer",
            "input_contract": "definition-review/v1",
        },
    )
    membership = session.scalar(
        select(AgentMembership).where(
            AgentMembership.project_id == project.id,
            AgentMembership.agent_id == "reviewer",
        )
    )
    if membership is None:
        session.add(
            AgentMembership(
                project_id=project.id,
                agent_id="reviewer",
                joined_context_version=project.context_version,
            )
        )
        _append_event(
            session,
            project.id,
            "agent.joined",
            {
                "agent_id": "reviewer",
                "context_pack_id": pack.id,
                "context_version": project.context_version,
                "responsibility": "clean-review Evidence/MRD",
            },
        )
    return pack


def _artifact_ref(
    session: Session, artifact_id: str, version_number: int
) -> DefinitionArtifactRefRead:
    artifact = session.get(Artifact, artifact_id)
    version = session.scalar(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact_id,
            ArtifactVersion.version == version_number,
        )
    )
    if artifact is None or version is None:
        raise DefinitionChainError("ARTIFACT_NOT_FOUND", "定义产物版本不存在。", 500)
    return DefinitionArtifactRefRead(
        artifact_id=artifact.id,
        version=version.version,
        kind=artifact.kind,
        context_version=version.context_version,
        approval_status=version.approval_status,
        content_hash=version.content_hash,
    )


def _artifact_snapshot(
    session: Session, artifact_root: Path, artifact_id: str, version_number: int
) -> ReviewerArtifactSnapshot:
    artifact = session.get(Artifact, artifact_id)
    version = session.scalar(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact_id,
            ArtifactVersion.version == version_number,
        )
    )
    if artifact is None or version is None:
        raise DefinitionChainError("ARTIFACT_NOT_FOUND", "Reviewer 输入产物不存在。", 500)
    try:
        _, content = read_verified_artifact(
            artifact_root, version.content_ref, version.content_hash
        )
    except ArtifactStoreError as exc:
        raise DefinitionChainError("ARTIFACT_CONTENT_INVALID", str(exc)) from exc
    return ReviewerArtifactSnapshot(
        artifact_id=artifact.id,
        version=version.version,
        kind=artifact.kind,
        title=artifact.title,
        content_hash=version.content_hash,
        content=content,
    )


def _append_event(
    session: Session, project_id: str, event_type: str, payload: dict[str, Any]
) -> Event:
    sequence = session.scalar(
        select(func.max(Event.sequence)).where(Event.project_id == project_id)
    )
    event = Event(
        project_id=project_id,
        sequence=(sequence or 0) + 1,
        event_type=event_type,
        payload=payload,
    )
    session.add(event)
    session.flush()
    return event


def _reject_secret_like_text(content: str) -> None:
    markers = (
        r"\bsk-[A-Za-z0-9_-]{16,}\b",
        r"(?i)\b(api[_-]?key|access[_-]?token|password)\s*[:=]\s*\S+",
    )
    if any(re.search(pattern, content) for pattern in markers):
        raise DefinitionChainError(
            "SENSITIVE_INPUT_REJECTED", "产物中疑似包含密钥，请改为 SecretRef。"
        )
