from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.agents.context import ApprovedContextPack
from app.agents.policy import ToolRequest, evaluate_tool_policy
from app.agents.prd_contracts import (
    PrdArtifactRefRead,
    PrdReviewCreate,
    PrdReviewerInputRead,
    PrdReviewRead,
    PrdSubmissionCreate,
    PrdSubmissionRead,
)
from app.domain.models import (
    AgentMembership,
    AgentRun,
    AgentTask,
    Artifact,
    ArtifactEdge,
    ArtifactVersion,
    ContextPack,
    ContextVersion,
    Event,
    Gate,
    IdempotencyRecord,
    Project,
    RunStep,
    ToolRun,
)
from app.domain.schemas import (
    ContextPackRead,
    ContextResourceRef,
    GateRead,
    KnownIssueRead,
)
from app.services.artifact_store import (
    ArtifactStoreError,
    read_verified_artifact,
    write_immutable_artifact,
)


class PrdDefinitionError(RuntimeError):
    def __init__(self, code: str, message: str, http_status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def stable_hash(value: Any) -> str:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def lock_prd_scope(session: Session, project_id: str, idempotency_key: str) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"prd:{project_id}:{idempotency_key}"},
    )


def submit_prd(
    session: Session,
    *,
    artifact_root: Path,
    project_id: str,
    idempotency_key: str,
    body: PrdSubmissionCreate,
) -> PrdSubmissionRead:
    project = _require_project(session, project_id)
    body_hash = stable_hash(body)
    existing = _idempotency(session, f"prd.submission:{project_id}", idempotency_key)
    if existing is not None:
        if existing.input_hash != body_hash:
            raise PrdDefinitionError(
                "IDEMPOTENCY_CONFLICT", "同一幂等键不能提交不同的 PRD。"
            )
        version = session.get(ArtifactVersion, existing.resource_id)
        if version is None:
            raise PrdDefinitionError("IDEMPOTENCY_ORPHAN", "PRD 幂等记录失效。", 500)
        return _submission_read(session, project, version, idempotent=True)

    if project.state != "prd":
        raise PrdDefinitionError("PRD_STAGE_INVALID", "PRD 只能在 PRD 阶段提交。")
    if project.context_version != body.expected_context_version:
        raise PrdDefinitionError("STALE_CONTEXT", "PRD 基于旧 Context，禁止合并。")
    pack = _require_pack(
        session,
        project=project,
        pack_id=body.context_pack_id,
        agent_id="ai-pm",
        input_contract=None,
    )
    if "CAP-04" not in set(pack.policy.get("allowed_capability_ids") or []):
        raise PrdDefinitionError("CAPABILITY_NOT_ALLOWED", "PRD Context 未授权 CAP-04。")
    run, task = _require_run(
        session,
        project=project,
        run_id=body.source_run_id,
        pack=pack,
        agent_id="ai-pm",
    )
    policy = _authorize_artifact_store(pack, agent_id="ai-pm")
    _reject_secret_like_text(body.artifact_proposal.content)
    allowed_refs, source_artifacts = _approved_pack_refs(
        session,
        artifact_root=artifact_root,
        project=project,
        pack=pack,
    )
    proposed_refs = set(body.artifact_proposal.evidence_refs)
    if not proposed_refs.issubset(allowed_refs):
        raise PrdDefinitionError(
            "PRD_EVIDENCE_REF_INVALID",
            "PRD 引用了 Context Pack 之外的 EvidenceRef。",
        )

    _tool_started(
        session,
        project_id=project.id,
        run=run,
        task=task,
        capability_id="CAP-04",
        input_hash=body_hash,
        idempotency_key=f"artifact_store:prd:{run.id}",
        policy_outcome=policy.outcome,
    )
    artifact, version = _persist_artifact(
        session,
        artifact_root=artifact_root,
        project=project,
        proposal=body.artifact_proposal,
        kind="prd",
        owner_agent="ai-pm",
        summary=(
            f"PRD；引用 {len(body.artifact_proposal.evidence_refs)} 条；"
            f"假设 {len(body.artifact_proposal.assumptions)} 条。"
        ),
    )
    for source in source_artifacts:
        _ensure_edge(session, project.id, source.id, artifact.id, "supports")
    reviewer_pack = _create_reviewer_pack(
        session,
        project=project,
        source_pack=pack,
        prd=artifact,
        version=version,
        source_run_id=run.id,
        evidence_refs=body.artifact_proposal.evidence_refs,
    )
    _tool_completed(
        session,
        project_id=project.id,
        run=run,
        task=task,
        capability_id="CAP-04",
        input_hash=body_hash,
        idempotency_key=f"artifact_store:prd:{run.id}",
        result_ref=f"artifact:{artifact.id}:v{version.version}",
        policy_outcome=policy.outcome,
    )
    session.add(
        IdempotencyRecord(
            scope=f"prd.submission:{project_id}",
            key=idempotency_key,
            resource_id=version.id,
            input_hash=body_hash,
        )
    )
    _append_event(
        session,
        project.id,
        "prd.submitted",
        {
            "submission_id": version.id,
            "source_run_id": run.id,
            "context_pack_id": pack.id,
            "reviewer_context_pack_id": reviewer_pack.id,
            "artifact_id": artifact.id,
            "version": version.version,
            "content_hash": version.content_hash,
        },
    )
    return _submission_read(session, project, version, idempotent=False)


def prd_reviewer_input(
    session: Session,
    *,
    project_id: str,
    submission_id: str,
) -> PrdReviewerInputRead:
    project = _require_project(session, project_id)
    version = session.get(ArtifactVersion, submission_id)
    artifact = session.get(Artifact, version.artifact_id) if version else None
    if (
        version is None
        or artifact is None
        or artifact.project_id != project.id
        or artifact.kind != "prd"
        or artifact.stage != "prd"
        or version.context_version != project.context_version
        or version.approval_status != "draft"
    ):
        raise PrdDefinitionError("PRD_SUBMISSION_NOT_FOUND", "PRD 提交不存在或已过期。", 404)
    pack = _reviewer_pack_for_version(session, project.id, version.id)
    if pack is None:
        raise PrdDefinitionError("PRD_REVIEW_PACK_NOT_FOUND", "PRD Reviewer Context 不存在。")
    return PrdReviewerInputRead(
        submission_id=version.id,
        project_id=project.id,
        context_version=project.context_version,
        reviewer_context_pack_id=pack.id,
        artifact_ref=f"artifact:{artifact.id}:v{version.version}",
        title=artifact.title,
        content_hash=version.content_hash,
        task=(
            "对已绑定 PRD 做 clean-review：检查核心闭环、三项以内 V1 范围、做/不做、"
            "状态边界、可操作验收、北极星/反指标、AI 评测与失败兜底；保留 G1 两项 P2。"
            "只提交 PRD Review，不批准 G2，不推进项目状态。"
        ),
        forbidden_actions=[
            "advance_project_state",
            "approve_gate",
            "modify_prd_candidate",
            "start_builder",
            "read_secret_values",
        ],
    )


def submit_prd_review(
    session: Session,
    *,
    artifact_root: Path,
    project_id: str,
    submission_id: str,
    idempotency_key: str,
    body: PrdReviewCreate,
) -> PrdReviewRead:
    project = _require_project(session, project_id)
    body_hash = stable_hash(body)
    existing = _idempotency(session, f"prd.review:{submission_id}", idempotency_key)
    if existing is not None:
        if existing.input_hash != body_hash:
            raise PrdDefinitionError(
                "IDEMPOTENCY_CONFLICT", "同一幂等键不能提交不同的 PRD Review。"
            )
        return _review_read(session, project, submission_id, idempotent=True)
    if project.state != "prd" or project.context_version != body.expected_context_version:
        raise PrdDefinitionError("STALE_CONTEXT", "PRD Review 基于旧 Context，禁止合并。")

    prd_version = session.get(ArtifactVersion, submission_id)
    prd = session.get(Artifact, prd_version.artifact_id) if prd_version else None
    if (
        prd_version is None
        or prd is None
        or prd.project_id != project.id
        or prd.kind != "prd"
        or prd_version.context_version != project.context_version
        or prd_version.approval_status != "draft"
    ):
        raise PrdDefinitionError("PRD_SUBMISSION_NOT_FOUND", "PRD 提交不存在或不可评审。", 404)
    pack = _require_pack(
        session,
        project=project,
        pack_id=body.context_pack_id,
        agent_id="reviewer",
        input_contract="prd-review/v1",
    )
    candidate = pack.policy.get("review_candidate") or {}
    if candidate.get("artifact_version_id") != prd_version.id:
        raise PrdDefinitionError("PRD_REVIEW_CONTEXT_MISMATCH", "Reviewer 未绑定当前 PRD。")
    run, task = _require_run(
        session,
        project=project,
        run_id=body.source_run_id,
        pack=pack,
        agent_id="reviewer",
    )
    policy = _authorize_artifact_store(pack, agent_id="reviewer")
    _reject_secret_like_text(body.review_artifact.content)
    allowed_refs = {
        str(candidate.get("artifact_ref")),
        *[str(ref) for ref in candidate.get("evidence_refs") or []],
    }
    proposed_refs = set(body.review_artifact.evidence_refs) | {
        ref for finding in body.findings for ref in finding.evidence_refs
    }
    if not proposed_refs or not proposed_refs.issubset(allowed_refs):
        raise PrdDefinitionError(
            "PRD_REVIEW_EVIDENCE_INVALID",
            "PRD Review 引用了未绑定的候选或证据。",
        )
    blocking = [finding for finding in body.findings if finding.severity in {"P0", "P1"}]
    if body.verdict != "reject" and blocking:
        raise PrdDefinitionError(
            "PRD_REVIEW_VERDICT_INVALID",
            "存在 P0/P1 时 Reviewer 必须 reject。",
        )

    _tool_started(
        session,
        project_id=project.id,
        run=run,
        task=task,
        capability_id="CAP-10",
        input_hash=body_hash,
        idempotency_key=f"artifact_store:prd-review:{run.id}",
        policy_outcome=policy.outcome,
    )
    review, review_version = _persist_artifact(
        session,
        artifact_root=artifact_root,
        project=project,
        proposal=body.review_artifact,
        kind="prd_review",
        owner_agent="reviewer",
        summary=f"PRD Review：{body.verdict}；发现 {len(body.findings)} 项。",
    )
    _ensure_edge(session, project.id, prd.id, review.id, "reviewed_by")
    _tool_completed(
        session,
        project_id=project.id,
        run=run,
        task=task,
        capability_id="CAP-10",
        input_hash=body_hash,
        idempotency_key=f"artifact_store:prd-review:{run.id}",
        result_ref=f"artifact:{review.id}:v{review_version.version}",
        policy_outcome=policy.outcome,
    )
    known_issues = _known_issues(session, project, body)
    gate = None
    if body.verdict in {"pass", "pass_with_known_issues"}:
        prd.status = "waiting_gate"
        prd_version.approval_status = "waiting_gate"
        review.status = "waiting_gate"
        review_version.approval_status = "waiting_gate"
        gate = _open_g2(
            session,
            project=project,
            prd=prd,
            prd_version=prd_version,
            review=review,
            review_version=review_version,
            known_issues=known_issues,
        )
        status = "waiting_g2"
    else:
        prd.status = "changes_requested"
        prd_version.approval_status = "changes_requested"
        review.status = "changes_requested"
        review_version.approval_status = "changes_requested"
        status = "changes_requested"
    session.add(
        IdempotencyRecord(
            scope=f"prd.review:{submission_id}",
            key=idempotency_key,
            resource_id=review_version.id,
            input_hash=body_hash,
        )
    )
    _append_event(
        session,
        project.id,
        "prd.reviewed",
        {
            "submission_id": submission_id,
            "source_run_id": run.id,
            "review_artifact_id": review.id,
            "review_version": review_version.version,
            "verdict": body.verdict,
            "status": status,
            "gate_id": gate.id if gate else None,
            "known_issue_count": len(known_issues),
        },
    )
    return PrdReviewRead(
        submission_id=submission_id,
        project_id=project.id,
        context_version=project.context_version,
        verdict=body.verdict,
        status=status,
        prd=_artifact_ref(prd, prd_version),
        prd_review=_artifact_ref(review, review_version),
        known_issues=known_issues,
        gate=GateRead.model_validate(gate) if gate else None,
        idempotent=False,
    )


def _submission_read(
    session: Session,
    project: Project,
    version: ArtifactVersion,
    *,
    idempotent: bool,
) -> PrdSubmissionRead:
    artifact = session.get(Artifact, version.artifact_id)
    pack = _reviewer_pack_for_version(session, project.id, version.id)
    if artifact is None or pack is None:
        raise PrdDefinitionError("PRD_SUBMISSION_CORRUPT", "PRD 提交缺少确定性绑定。", 500)
    candidate = pack.policy.get("review_candidate") or {}
    return PrdSubmissionRead(
        submission_id=version.id,
        project_id=project.id,
        source_run_id=str(candidate.get("source_run_id")),
        context_pack_id=str(candidate.get("source_context_pack_id")),
        context_version=version.context_version,
        status="waiting_reviewer",
        prd=_artifact_ref(artifact, version),
        reviewer_context_pack_id=pack.id,
        idempotent=idempotent,
        created_at=version.created_at,
    )


def _review_read(
    session: Session,
    project: Project,
    submission_id: str,
    *,
    idempotent: bool,
) -> PrdReviewRead:
    prd_version = session.get(ArtifactVersion, submission_id)
    prd = session.get(Artifact, prd_version.artifact_id) if prd_version else None
    if prd is None or prd_version is None:
        raise PrdDefinitionError("PRD_SUBMISSION_CORRUPT", "PRD 提交不存在。", 500)
    edge_row = session.execute(
        select(ArtifactEdge, Artifact, ArtifactVersion)
        .join(Artifact, Artifact.id == ArtifactEdge.target_id)
        .join(ArtifactVersion, ArtifactVersion.artifact_id == Artifact.id)
        .where(
            ArtifactEdge.project_id == project.id,
            ArtifactEdge.source_id == prd.id,
            Artifact.kind == "prd_review",
            ArtifactVersion.context_version == project.context_version,
        )
        .order_by(ArtifactVersion.version.desc())
    ).first()
    if edge_row is None:
        raise PrdDefinitionError("PRD_REVIEW_CORRUPT", "PRD Review 不存在。", 500)
    _, review, review_version = edge_row
    gate = session.scalar(
        select(Gate).where(
            Gate.project_id == project.id,
            Gate.gate_type == "G2",
            Gate.context_version == project.context_version,
        )
    )
    verdict = "reject" if gate is None else (
        "pass_with_known_issues" if gate.known_issues else "pass"
    )
    return PrdReviewRead(
        submission_id=submission_id,
        project_id=project.id,
        context_version=project.context_version,
        verdict=verdict,
        status="changes_requested" if gate is None else "waiting_g2",
        prd=_artifact_ref(prd, prd_version),
        prd_review=_artifact_ref(review, review_version),
        known_issues=[
            KnownIssueRead.model_validate(item)
            for item in (gate.known_issues if gate else [])
        ],
        gate=GateRead.model_validate(gate) if gate else None,
        idempotent=idempotent,
    )


def _require_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise PrdDefinitionError("PROJECT_NOT_FOUND", "项目不存在。", 404)
    return project


def _require_pack(
    session: Session,
    *,
    project: Project,
    pack_id: str,
    agent_id: str,
    input_contract: str | None,
) -> ContextPack:
    pack = session.get(ContextPack, pack_id)
    if (
        pack is None
        or pack.project_id != project.id
        or pack.agent_id != agent_id
        or pack.stage != "prd"
        or pack.context_version != project.context_version
        or pack.approval_status != "approved"
    ):
        raise PrdDefinitionError("PRD_CONTEXT_INVALID", "PRD Context Pack 不存在或已过期。")
    if input_contract is not None and pack.policy.get("input_contract") != input_contract:
        raise PrdDefinitionError("PRD_CONTEXT_INVALID", "PRD Review 输入契约不匹配。")
    return pack


def _require_run(
    session: Session,
    *,
    project: Project,
    run_id: str,
    pack: ContextPack,
    agent_id: str,
) -> tuple[AgentRun, AgentTask]:
    run = session.get(AgentRun, run_id)
    task = session.get(AgentTask, run.task_id) if run else None
    if (
        run is None
        or task is None
        or task.project_id != project.id
        or task.assigned_agent != agent_id
        or task.context_version != project.context_version
        or run.state != "succeeded"
        or task.state != "completed"
    ):
        raise PrdDefinitionError("PRD_SOURCE_RUN_INVALID", "仅接受当前 Context 的成功 Agent Run。")
    started = next(
        (
            event
            for event in session.scalars(
                select(Event).where(
                    Event.project_id == project.id,
                    Event.event_type == "run.started",
                )
            )
            if event.payload.get("run_id") == run.id
            and event.payload.get("context_pack_id") == pack.id
        ),
        None,
    )
    if started is None:
        raise PrdDefinitionError("PRD_SOURCE_RUN_INVALID", "Run 未绑定指定 Context Pack。")
    return run, task


def _approved_pack_refs(
    session: Session,
    *,
    artifact_root: Path,
    project: Project,
    pack: ContextPack,
) -> tuple[set[str], list[Artifact]]:
    refs = [
        {
            "resource_type": pack.primary_resource_type,
            "resource_id": pack.primary_resource_id,
            "version": pack.primary_resource_version,
        },
        *list(pack.references or []),
    ]
    allowed: set[str] = set()
    artifacts: list[Artifact] = []
    for ref in refs:
        if ref.get("resource_type") != "artifact":
            raise PrdDefinitionError("PRD_CONTEXT_INVALID", "PRD 仅接收已批准 Artifact。")
        artifact = session.get(Artifact, ref.get("resource_id"))
        version = session.scalar(
            select(ArtifactVersion).where(
                ArtifactVersion.artifact_id == ref.get("resource_id"),
                ArtifactVersion.version == ref.get("version"),
            )
        )
        if (
            artifact is None
            or version is None
            or artifact.project_id != project.id
            or version.approval_status != "approved"
        ):
            raise PrdDefinitionError("PRD_CONTEXT_INVALID", "PRD 输入 Artifact 未批准。")
        try:
            _, content = read_verified_artifact(
                artifact_root,
                version.content_ref,
                version.content_hash,
            )
        except ArtifactStoreError as exc:
            raise PrdDefinitionError("PRD_CONTEXT_INVALID", "PRD 输入 Artifact 校验失败。") from exc
        artifact_ref = f"artifact:{artifact.id}:v{version.version}"
        allowed.add(artifact_ref)
        allowed.update(re.findall(r"bocha:web:[0-9a-f]{64}", content))
        artifacts.append(artifact)
    return allowed, artifacts


def _persist_artifact(
    session: Session,
    *,
    artifact_root: Path,
    project: Project,
    proposal: Any,
    kind: str,
    owner_agent: str,
    summary: str,
) -> tuple[Artifact, ArtifactVersion]:
    artifact = session.get(Artifact, proposal.artifact_id) if proposal.artifact_id else None
    if proposal.artifact_id and artifact is None:
        raise PrdDefinitionError("ARTIFACT_NOT_FOUND", "指定 Artifact 不存在。", 404)
    if artifact is None:
        existing = session.scalar(
            select(Artifact).where(
                Artifact.project_id == project.id,
                Artifact.stage == "prd",
                Artifact.kind == kind,
            )
        )
        if existing is not None:
            raise PrdDefinitionError(
                "ARTIFACT_ID_REQUIRED", "该 PRD 产物已存在，修订时必须传 artifact_id。"
            )
        if proposal.expected_previous_version != 0:
            raise PrdDefinitionError("ARTIFACT_VERSION_CONFLICT", "新产物前置版本必须为 0。")
        artifact = Artifact(
            project_id=project.id,
            title=proposal.title,
            kind=kind,
            stage="prd",
            status="waiting_review",
            latest_version=0,
            owner_agent=owner_agent,
        )
        session.add(artifact)
        session.flush()
    elif (
        artifact.project_id != project.id
        or artifact.stage != "prd"
        or artifact.kind != kind
    ):
        raise PrdDefinitionError("ARTIFACT_BINDING_INVALID", "Artifact 身份或阶段不匹配。")
    if artifact.latest_version != proposal.expected_previous_version:
        raise PrdDefinitionError("ARTIFACT_VERSION_CONFLICT", "Artifact 前置版本已变化。")
    try:
        content_ref, content_hash = write_immutable_artifact(
            artifact_root,
            project_id=project.id,
            kind=kind,
            content=proposal.content,
        )
    except ArtifactStoreError as exc:
        raise PrdDefinitionError("ARTIFACT_CONTENT_INVALID", str(exc)) from exc
    version = ArtifactVersion(
        artifact_id=artifact.id,
        version=artifact.latest_version + 1,
        context_version=project.context_version,
        approval_status="draft",
        content_ref=content_ref,
        content_hash=content_hash,
        summary=summary,
        created_by=owner_agent,
    )
    artifact.latest_version = version.version
    artifact.title = proposal.title
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


def _create_reviewer_pack(
    session: Session,
    *,
    project: Project,
    source_pack: ContextPack,
    prd: Artifact,
    version: ArtifactVersion,
    source_run_id: str,
    evidence_refs: list[str],
) -> ContextPack:
    context = session.scalar(
        select(ContextVersion).where(
            ContextVersion.project_id == project.id,
            ContextVersion.version == project.context_version,
            ContextVersion.approval_status == "active",
        )
    )
    if context is None:
        raise PrdDefinitionError("CONTEXT_VERSION_NOT_FOUND", "当前 Context 不存在。", 500)
    pack = ContextPack(
        project_id=project.id,
        context_version_id=context.id,
        context_version=context.version,
        stage="prd",
        approval_status="approved",
        primary_resource_type=source_pack.primary_resource_type,
        primary_resource_id=source_pack.primary_resource_id,
        primary_resource_version=source_pack.primary_resource_version,
        agent_id="reviewer",
        task="使用 prd-review/v1 clean-review 输入审查 PRD；不得批准 G2。",
        references=list(source_pack.references or []),
        policy={
            "allowed_capability_ids": ["CAP-10"],
            "forbidden_actions": [
                "advance_project_state",
                "approve_gate",
                "modify_prd_candidate",
                "start_builder",
                "read_secret_values",
            ],
            "input_contract": "prd-review/v1",
            "review_candidate": {
                "artifact_id": prd.id,
                "artifact_version_id": version.id,
                "version": version.version,
                "content_hash": version.content_hash,
                "artifact_ref": f"artifact:{prd.id}:v{version.version}",
                "evidence_refs": list(evidence_refs),
                "source_run_id": source_run_id,
                "source_context_pack_id": source_pack.id,
            },
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
            "input_contract": "prd-review/v1",
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
                "responsibility": "clean-review PRD",
            },
        )
    return pack


def _reviewer_pack_for_version(
    session: Session,
    project_id: str,
    artifact_version_id: str,
) -> ContextPack | None:
    packs = session.scalars(
        select(ContextPack).where(
            ContextPack.project_id == project_id,
            ContextPack.agent_id == "reviewer",
            ContextPack.stage == "prd",
        ).order_by(ContextPack.created_at.desc())
    )
    return next(
        (
            pack
            for pack in packs
            if (pack.policy.get("review_candidate") or {}).get("artifact_version_id")
            == artifact_version_id
        ),
        None,
    )


def _open_g2(
    session: Session,
    *,
    project: Project,
    prd: Artifact,
    prd_version: ArtifactVersion,
    review: Artifact,
    review_version: ArtifactVersion,
    known_issues: list[KnownIssueRead],
) -> Gate:
    existing = session.scalar(
        select(Gate).where(
            Gate.project_id == project.id,
            Gate.gate_type == "G2",
            Gate.context_version == project.context_version,
        )
    )
    if existing is not None:
        return existing
    refs = [
        {"artifact_id": prd.id, "version": prd_version.version},
        {"artifact_id": review.id, "version": review_version.version},
    ]
    gate = Gate(
        project_id=project.id,
        gate_type="G2",
        context_version=project.context_version,
        status="open",
        target_state="solution_confirmation",
        reason="PRD 与独立 PRD Review 已完成，请用户决定是否冻结产品范围。",
        impacted_artifact_refs=refs,
        known_issues=[issue.model_dump(mode="json") for issue in known_issues],
    )
    session.add(gate)
    session.flush()
    _append_event(
        session,
        project.id,
        "gate.opened",
        {
            "gate_id": gate.id,
            "gate_type": "G2",
            "context_version": project.context_version,
            "target_state": "solution_confirmation",
            "impacted_artifact_refs": refs,
            "known_issue_count": len(known_issues),
        },
    )
    return gate


def _known_issues(
    session: Session,
    project: Project,
    body: PrdReviewCreate,
) -> list[KnownIssueRead]:
    inherited_gate = session.scalar(
        select(Gate)
        .where(Gate.project_id == project.id, Gate.gate_type == "G1")
        .order_by(Gate.opened_at.desc())
    )
    raw = list(inherited_gate.known_issues if inherited_gate else [])
    for finding in body.findings:
        if finding.severity == "P2":
            raw.append(
                {
                    "issue": finding.title,
                    "severity": "P2",
                    "evidence_refs": finding.evidence_refs,
                    "source_refs": [],
                    "status": "open",
                }
            )
    unique: dict[str, KnownIssueRead] = {}
    for item in raw:
        issue = KnownIssueRead.model_validate(item)
        unique.setdefault(issue.issue, issue)
    return list(unique.values())


def _tool_started(
    session: Session,
    *,
    project_id: str,
    run: AgentRun,
    task: AgentTask,
    capability_id: str,
    input_hash: str,
    idempotency_key: str,
    policy_outcome: str,
) -> None:
    existing = session.scalar(select(ToolRun).where(ToolRun.idempotency_key == idempotency_key))
    if existing is not None:
        return
    tool = ToolRun(
        task_id=task.id,
        run_id=run.id,
        capability_id=capability_id,
        tool_name="artifact_store",
        state="running",
        input_hash=input_hash,
        idempotency_key=idempotency_key,
    )
    session.add(tool)
    session.flush()
    _append_event(
        session,
        project_id,
        "tool_run.started",
        {
            "tool_run_id": tool.id,
            "run_id": run.id,
            "task_id": task.id,
            "tool_id": "artifact_store",
            "capability_id": capability_id,
            "policy_outcome": policy_outcome,
            "idempotency_key": idempotency_key,
        },
    )


def _tool_completed(
    session: Session,
    *,
    project_id: str,
    run: AgentRun,
    task: AgentTask,
    capability_id: str,
    input_hash: str,
    idempotency_key: str,
    result_ref: str,
    policy_outcome: str,
) -> None:
    tool = session.scalar(select(ToolRun).where(ToolRun.idempotency_key == idempotency_key))
    if tool is None:
        raise PrdDefinitionError("TOOL_RUN_MISSING", "Artifact Store ToolRun 不存在。", 500)
    tool.state = "completed"
    tool.result_ref = result_ref
    step_index = session.scalar(
        select(func.max(RunStep.step_index)).where(RunStep.run_id == run.id)
    )
    session.add(
        RunStep(
            run_id=run.id,
            step_index=(step_index if step_index is not None else -1) + 1,
            step_type="tool",
            state="completed",
            idempotency_key=idempotency_key,
            input_hash=input_hash,
            output_ref=result_ref,
            external_effect_confirmed=True,
        )
    )
    _append_event(
        session,
        project_id,
        "tool_run.completed",
        {
            "tool_run_id": tool.id,
            "run_id": run.id,
            "task_id": task.id,
            "tool_id": "artifact_store",
            "capability_id": capability_id,
            "state": "completed",
            "policy_outcome": policy_outcome,
            "idempotency_key": idempotency_key,
            "result_ref": result_ref,
        },
    )


def _ensure_edge(
    session: Session,
    project_id: str,
    source_id: str,
    target_id: str,
    relation: str,
) -> None:
    existing = session.scalar(
        select(ArtifactEdge).where(
            ArtifactEdge.project_id == project_id,
            ArtifactEdge.source_id == source_id,
            ArtifactEdge.target_id == target_id,
        )
    )
    if existing is None:
        session.add(
            ArtifactEdge(
                project_id=project_id,
                source_id=source_id,
                target_id=target_id,
                relation=relation,
            )
        )


def _authorize_artifact_store(pack: ContextPack, *, agent_id: str):
    runtime_pack = ApprovedContextPack.from_control_plane(
        ContextPackRead(
            id=pack.id,
            project_id=pack.project_id,
            context_version=pack.context_version,
            stage=pack.stage,
            approval_status=pack.approval_status,
            recipient_agent_id=pack.agent_id,
            primary_resource=ContextResourceRef(
                resource_type=pack.primary_resource_type,
                resource_id=pack.primary_resource_id,
                version=pack.primary_resource_version,
                approval_status="approved",
            ),
            required_resources=[
                ContextResourceRef.model_validate(ref) for ref in (pack.references or [])
            ],
            task=pack.task,
            policy=pack.policy,
            created_at=pack.created_at,
        )
    )
    decision = evaluate_tool_policy(
        agent_id=agent_id,
        stage="prd",
        context_pack=runtime_pack,
        request=ToolRequest(
            tool_id="artifact_store",
            parameters={"content": "redacted", "stage": "prd"},
            side_effect="reversible",
        ),
        tool_calls_used=0,
    )
    if decision.outcome != "allow":
        raise PrdDefinitionError(decision.code, decision.reason)
    return decision


def _artifact_ref(artifact: Artifact, version: ArtifactVersion) -> PrdArtifactRefRead:
    return PrdArtifactRefRead(
        artifact_id=artifact.id,
        version=version.version,
        kind=artifact.kind,
        context_version=version.context_version,
        approval_status=version.approval_status,
        content_hash=version.content_hash,
        artifact_ref=f"artifact:{artifact.id}:v{version.version}",
    )


def _idempotency(session: Session, scope: str, key: str) -> IdempotencyRecord | None:
    return session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key == key,
        )
    )


def _reject_secret_like_text(content: str) -> None:
    if re.search(r"\bsk-[A-Za-z0-9_-]{16,}\b", content) or re.search(
        r"(?i)\b(api[_-]?key|access[_-]?token|password)\s*[:=]\s*\S+",
        content,
    ):
        raise PrdDefinitionError("SENSITIVE_ARTIFACT_REJECTED", "PRD 产物疑似包含密钥。")


def _append_event(
    session: Session,
    project_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> Event:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"project:{project_id}"},
    )
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
