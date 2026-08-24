from __future__ import annotations

from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.agents.solution_contracts import (
    SolutionArtifactRefRead,
    SolutionReviewCreate,
    SolutionReviewerInputRead,
    SolutionReviewRead,
    SolutionSubmissionCreate,
    SolutionSubmissionRead,
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
)
from app.domain.schemas import GateRead, KnownIssueRead
from app.services.artifact_store import ArtifactStoreError, read_verified_artifact
from app.services.control_plane import (
    ControlPlaneError,
    validate_gate_artifact_kinds,
    validate_gate_open,
)
from app.services.prd_definition import (
    PrdDefinitionError,
    _append_event,
    _authorize_artifact_store,
    _ensure_edge,
    _idempotency,
    _persist_artifact,
    _reject_secret_like_text,
    _tool_completed,
    _tool_started,
    stable_hash,
)

SolutionDefinitionError = PrdDefinitionError


def lock_solution_scope(session: Session, project_id: str, idempotency_key: str) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"solution:{project_id}:{idempotency_key}"},
    )


def submit_solution(
    session: Session,
    *,
    artifact_root: Path,
    project_id: str,
    idempotency_key: str,
    body: SolutionSubmissionCreate,
) -> SolutionSubmissionRead:
    project = _require_project(session, project_id)
    body_hash = stable_hash(body)
    existing = _idempotency(session, f"solution.submission:{project_id}", idempotency_key)
    if existing is not None:
        if existing.input_hash != body_hash:
            raise SolutionDefinitionError(
                "IDEMPOTENCY_CONFLICT", "同一幂等键不能提交不同的方案。"
            )
        design_version = session.get(ArtifactVersion, existing.resource_id)
        if design_version is None:
            raise SolutionDefinitionError("IDEMPOTENCY_ORPHAN", "方案幂等记录失效。", 500)
        return _submission_read(session, project, design_version, idempotent=True)

    if project.state != "solution_confirmation":
        raise SolutionDefinitionError("SOLUTION_STAGE_INVALID", "方案只能在方案确认阶段提交。")
    if project.context_version != body.expected_context_version:
        raise SolutionDefinitionError("STALE_CONTEXT", "方案基于旧 Context，禁止合并。")
    pack = _require_pack(
        session,
        project=project,
        pack_id=body.context_pack_id,
        agent_id="builder",
        input_contract=None,
    )
    if "CAP-07" not in set(pack.policy.get("allowed_capability_ids") or []):
        raise SolutionDefinitionError("CAPABILITY_NOT_ALLOWED", "方案 Context 未授权 CAP-07。")
    forbidden = set(pack.policy.get("forbidden_actions") or [])
    required_forbidden = {"codex_cli", "project_fs_write", "git_local", "test_runner"}
    if (
        not required_forbidden.issubset(forbidden)
        or pack.policy.get("mode") != "solution_document_only"
    ):
        raise SolutionDefinitionError(
            "SOLUTION_POLICY_INVALID", "G3 前 Builder 必须处于只写方案、禁止代码的模式。"
        )
    run, task = _require_run(
        session,
        project=project,
        run_id=body.source_run_id,
        pack=pack,
        agent_id="builder",
    )
    policy = _authorize_artifact_store(pack, agent_id="builder")
    allowed_refs, source_artifacts = _approved_pack_refs(
        session,
        artifact_root=artifact_root,
        project=project,
        pack=pack,
    )
    primary_ref = f"artifact:{pack.primary_resource_id}:v{pack.primary_resource_version}"
    for proposal in body.artifact_proposals:
        _reject_secret_like_text(proposal.content)
        proposed_refs = set(proposal.evidence_refs)
        if primary_ref not in proposed_refs or not proposed_refs.issubset(allowed_refs):
            raise SolutionDefinitionError(
                "SOLUTION_EVIDENCE_INVALID",
                "User Flow 和方案说明必须引用已批准 PRD，且不能引用 Context 外材料。",
            )

    _tool_started(
        session,
        project_id=project.id,
        run=run,
        task=task,
        capability_id="CAP-07",
        input_hash=body_hash,
        idempotency_key=f"artifact_store:solution:{run.id}",
        policy_outcome=policy.outcome,
    )
    persisted: dict[str, tuple[Artifact, ArtifactVersion]] = {}
    for proposal in body.artifact_proposals:
        persisted[proposal.kind] = _persist_artifact(
            session,
            artifact_root=artifact_root,
            project=project,
            proposal=proposal,
            kind=proposal.kind,
            owner_agent="builder",
            summary=(
                f"{proposal.title}；引用 {len(proposal.evidence_refs)} 条；"
                f"假设 {len(proposal.assumptions)} 条。"
            ),
            stage="solution_confirmation",
        )
    user_flow, user_flow_version = persisted["user_flow"]
    solution, solution_version = persisted["solution_design"]
    for source in source_artifacts:
        _ensure_edge(session, project.id, source.id, user_flow.id, "supports")
        _ensure_edge(session, project.id, source.id, solution.id, "supports")
    _ensure_edge(session, project.id, user_flow.id, solution.id, "explains")
    reviewer_pack = _create_reviewer_pack(
        session,
        project=project,
        source_pack=pack,
        source_run_id=run.id,
        candidates=[
            (user_flow, user_flow_version),
            (solution, solution_version),
        ],
        evidence_refs={
            proposal.kind: proposal.evidence_refs for proposal in body.artifact_proposals
        },
    )
    result_ref = (
        f"artifact-pair:{user_flow.id}:v{user_flow_version.version},"
        f"{solution.id}:v{solution_version.version}"
    )
    _tool_completed(
        session,
        project_id=project.id,
        run=run,
        task=task,
        capability_id="CAP-07",
        input_hash=body_hash,
        idempotency_key=f"artifact_store:solution:{run.id}",
        result_ref=result_ref,
        policy_outcome=policy.outcome,
    )
    session.add(
        IdempotencyRecord(
            scope=f"solution.submission:{project_id}",
            key=idempotency_key,
            resource_id=solution_version.id,
            input_hash=body_hash,
        )
    )
    _append_event(
        session,
        project.id,
        "solution.submitted",
        {
            "submission_id": solution_version.id,
            "source_run_id": run.id,
            "context_pack_id": pack.id,
            "reviewer_context_pack_id": reviewer_pack.id,
            "artifact_refs": [
                f"artifact:{user_flow.id}:v{user_flow_version.version}",
                f"artifact:{solution.id}:v{solution_version.version}",
            ],
        },
    )
    return _submission_read(session, project, solution_version, idempotent=False)


def solution_reviewer_input(
    session: Session,
    *,
    project_id: str,
    submission_id: str,
) -> SolutionReviewerInputRead:
    project = _require_project(session, project_id)
    design_version = session.get(ArtifactVersion, submission_id)
    user_flow, user_flow_version, solution, solution_version, pack = _solution_bundle(
        session,
        project=project,
        design_version=design_version,
    )
    return SolutionReviewerInputRead(
        submission_id=solution_version.id,
        project_id=project.id,
        context_version=project.context_version,
        reviewer_context_pack_id=pack.id,
        artifact_refs=[
            f"artifact:{user_flow.id}:v{user_flow_version.version}",
            f"artifact:{solution.id}:v{solution_version.version}",
        ],
        task=(
            "对绑定的 User Flow 与方案说明做 clean-review：检查是否严格继承已批准 PRD、"
            "是否保持前端固定、关键路径/状态/异常/可访问性/取舍是否完整。"
            "只提交 Solution Review，不批准 G3，不推进状态，不要求写代码。"
        ),
        forbidden_actions=[
            "advance_project_state",
            "approve_gate",
            "modify_solution_candidates",
            "codex_cli",
            "project_fs_write",
            "read_secret_values",
        ],
    )


def submit_solution_review(
    session: Session,
    *,
    artifact_root: Path,
    project_id: str,
    submission_id: str,
    idempotency_key: str,
    body: SolutionReviewCreate,
) -> SolutionReviewRead:
    project = _require_project(session, project_id)
    body_hash = stable_hash(body)
    existing = _idempotency(session, f"solution.review:{submission_id}", idempotency_key)
    if existing is not None:
        if existing.input_hash != body_hash:
            raise SolutionDefinitionError(
                "IDEMPOTENCY_CONFLICT", "同一幂等键不能提交不同的方案审核。"
            )
        return _review_read(session, project, submission_id, idempotent=True)
    if (
        project.state != "solution_confirmation"
        or project.context_version != body.expected_context_version
    ):
        raise SolutionDefinitionError("STALE_CONTEXT", "方案审核基于旧 Context，禁止合并。")

    design_version = session.get(ArtifactVersion, submission_id)
    user_flow, user_flow_version, solution, solution_version, pack = _solution_bundle(
        session,
        project=project,
        design_version=design_version,
    )
    if body.context_pack_id != pack.id:
        raise SolutionDefinitionError(
            "SOLUTION_REVIEW_CONTEXT_MISMATCH", "Reviewer 未绑定当前方案。"
        )
    run, task = _require_run(
        session,
        project=project,
        run_id=body.source_run_id,
        pack=pack,
        agent_id="reviewer",
    )
    policy = _authorize_artifact_store(pack, agent_id="reviewer")
    _reject_secret_like_text(body.review_artifact.content)
    candidate_refs = {
        f"artifact:{user_flow.id}:v{user_flow_version.version}",
        f"artifact:{solution.id}:v{solution_version.version}",
    }
    proposed_refs = set(body.review_artifact.evidence_refs) | {
        ref for finding in body.findings for ref in finding.evidence_refs
    }
    if (
        not candidate_refs.issubset(set(body.review_artifact.evidence_refs))
        or not proposed_refs.issubset(candidate_refs)
    ):
        raise SolutionDefinitionError(
            "SOLUTION_REVIEW_EVIDENCE_INVALID",
            "方案审核必须引用两个绑定候选，且不能引用未绑定材料。",
        )
    blocking = [finding for finding in body.findings if finding.severity in {"P0", "P1"}]
    if body.verdict != "reject" and blocking:
        raise SolutionDefinitionError(
            "SOLUTION_REVIEW_VERDICT_INVALID", "存在 P0/P1 时 Reviewer 必须 reject。"
        )

    _tool_started(
        session,
        project_id=project.id,
        run=run,
        task=task,
        capability_id="CAP-10",
        input_hash=body_hash,
        idempotency_key=f"artifact_store:solution-review:{run.id}",
        policy_outcome=policy.outcome,
    )
    review, review_version = _persist_artifact(
        session,
        artifact_root=artifact_root,
        project=project,
        proposal=body.review_artifact,
        kind="solution_review",
        owner_agent="reviewer",
        summary=f"方案审核：{body.verdict}；发现 {len(body.findings)} 项。",
        stage="solution_confirmation",
    )
    _ensure_edge(session, project.id, user_flow.id, review.id, "reviewed_by")
    _ensure_edge(session, project.id, solution.id, review.id, "reviewed_by")
    _tool_completed(
        session,
        project_id=project.id,
        run=run,
        task=task,
        capability_id="CAP-10",
        input_hash=body_hash,
        idempotency_key=f"artifact_store:solution-review:{run.id}",
        result_ref=f"artifact:{review.id}:v{review_version.version}",
        policy_outcome=policy.outcome,
    )
    known_issues = _known_issues(session, project, body)
    gate = None
    if body.verdict in {"pass", "pass_with_known_issues"}:
        for artifact, version in [
            (user_flow, user_flow_version),
            (solution, solution_version),
            (review, review_version),
        ]:
            artifact.status = "waiting_gate"
            version.approval_status = "waiting_gate"
        gate = _open_g3(
            session,
            project=project,
            user_flow=user_flow,
            user_flow_version=user_flow_version,
            solution=solution,
            solution_version=solution_version,
            review=review,
            review_version=review_version,
            known_issues=known_issues,
        )
        status = "waiting_g3"
    else:
        for artifact, version in [
            (user_flow, user_flow_version),
            (solution, solution_version),
            (review, review_version),
        ]:
            artifact.status = "changes_requested"
            version.approval_status = "changes_requested"
        status = "changes_requested"
    session.add(
        IdempotencyRecord(
            scope=f"solution.review:{submission_id}",
            key=idempotency_key,
            resource_id=review_version.id,
            input_hash=body_hash,
        )
    )
    _append_event(
        session,
        project.id,
        "solution.reviewed",
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
    return SolutionReviewRead(
        submission_id=submission_id,
        project_id=project.id,
        context_version=project.context_version,
        verdict=body.verdict,
        status=status,
        user_flow=_artifact_ref(user_flow, user_flow_version),
        solution_design=_artifact_ref(solution, solution_version),
        solution_review=_artifact_ref(review, review_version),
        known_issues=known_issues,
        gate=GateRead.model_validate(gate) if gate else None,
        idempotent=False,
    )


def _require_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise SolutionDefinitionError("PROJECT_NOT_FOUND", "项目不存在。", 404)
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
        or pack.stage != "solution_confirmation"
        or pack.context_version != project.context_version
        or pack.approval_status != "approved"
    ):
        raise SolutionDefinitionError("SOLUTION_CONTEXT_INVALID", "方案 Context 不存在或已过期。")
    if input_contract is not None and pack.policy.get("input_contract") != input_contract:
        raise SolutionDefinitionError("SOLUTION_CONTEXT_INVALID", "方案审核输入契约不匹配。")
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
        raise SolutionDefinitionError(
            "SOLUTION_SOURCE_RUN_INVALID", "仅接受当前 Context 的成功 Agent Run。"
        )
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
        raise SolutionDefinitionError("SOLUTION_SOURCE_RUN_INVALID", "Run 未绑定指定 Context。")
    return run, task


def _approved_pack_refs(
    session: Session,
    *,
    artifact_root: Path,
    project: Project,
    pack: ContextPack,
) -> tuple[set[str], list[Artifact]]:
    raw_refs = [
        {
            "resource_type": pack.primary_resource_type,
            "resource_id": pack.primary_resource_id,
            "version": pack.primary_resource_version,
        },
        *list(pack.references or []),
    ]
    allowed: set[str] = set()
    artifacts: list[Artifact] = []
    for raw in raw_refs:
        artifact = session.get(Artifact, raw.get("resource_id"))
        version = session.scalar(
            select(ArtifactVersion).where(
                ArtifactVersion.artifact_id == raw.get("resource_id"),
                ArtifactVersion.version == raw.get("version"),
            )
        )
        if (
            raw.get("resource_type") != "artifact"
            or artifact is None
            or version is None
            or artifact.project_id != project.id
            or artifact.kind not in {"prd", "prd_review"}
            or version.approval_status != "approved"
        ):
            raise SolutionDefinitionError(
                "SOLUTION_CONTEXT_INVALID", "方案只接受已批准 PRD 与 PRD Review。"
            )
        try:
            read_verified_artifact(artifact_root, version.content_ref, version.content_hash)
        except ArtifactStoreError as exc:
            raise SolutionDefinitionError(
                "SOLUTION_CONTEXT_INVALID", "方案输入 Artifact 校验失败。"
            ) from exc
        allowed.add(f"artifact:{artifact.id}:v{version.version}")
        artifacts.append(artifact)
    if {artifact.kind for artifact in artifacts} != {"prd", "prd_review"}:
        raise SolutionDefinitionError(
            "SOLUTION_CONTEXT_INVALID", "方案必须精确继承 PRD 与 PRD Review。"
        )
    return allowed, artifacts


def _create_reviewer_pack(
    session: Session,
    *,
    project: Project,
    source_pack: ContextPack,
    source_run_id: str,
    candidates: list[tuple[Artifact, ArtifactVersion]],
    evidence_refs: dict[str, list[str]],
) -> ContextPack:
    context = session.scalar(
        select(ContextVersion).where(
            ContextVersion.project_id == project.id,
            ContextVersion.version == project.context_version,
            ContextVersion.approval_status == "active",
        )
    )
    if context is None:
        raise SolutionDefinitionError("CONTEXT_VERSION_NOT_FOUND", "当前 Context 不存在。", 500)
    candidate_policy = [
        {
            "artifact_id": artifact.id,
            "artifact_version_id": version.id,
            "version": version.version,
            "content_hash": version.content_hash,
            "artifact_ref": f"artifact:{artifact.id}:v{version.version}",
            "evidence_refs": list(evidence_refs[artifact.kind]),
            "source_run_id": source_run_id,
            "source_context_pack_id": source_pack.id,
        }
        for artifact, version in candidates
    ]
    pack = ContextPack(
        project_id=project.id,
        context_version_id=context.id,
        context_version=context.version,
        stage="solution_confirmation",
        approval_status="approved",
        primary_resource_type=source_pack.primary_resource_type,
        primary_resource_id=source_pack.primary_resource_id,
        primary_resource_version=source_pack.primary_resource_version,
        agent_id="reviewer",
        task="使用 solution-review/v1 clean-review 审查 User Flow 与方案说明；不得批准 G3。",
        references=list(source_pack.references or []),
        policy={
            "allowed_capability_ids": ["CAP-10"],
            "forbidden_actions": [
                "advance_project_state",
                "approve_gate",
                "modify_solution_candidates",
                "codex_cli",
                "project_fs_write",
                "read_secret_values",
            ],
            "input_contract": "solution-review/v1",
            "review_candidates": candidate_policy,
            "budget": {
                "max_turns": 3,
                "max_retries": 2,
                "timeout_seconds": 300,
                "max_tool_calls": 1,
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
            "input_contract": "solution-review/v1",
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
                "responsibility": "clean-review solution documents",
            },
        )
    return pack


def _reviewer_pack_for_design(
    session: Session,
    project_id: str,
    design_version_id: str,
) -> ContextPack | None:
    packs = session.scalars(
        select(ContextPack).where(
            ContextPack.project_id == project_id,
            ContextPack.stage == "solution_confirmation",
            ContextPack.agent_id == "reviewer",
        )
    )
    for pack in packs:
        candidates = pack.policy.get("review_candidates") or []
        if any(item.get("artifact_version_id") == design_version_id for item in candidates):
            return pack
    return None


def _solution_bundle(
    session: Session,
    *,
    project: Project,
    design_version: ArtifactVersion | None,
) -> tuple[Artifact, ArtifactVersion, Artifact, ArtifactVersion, ContextPack]:
    solution = session.get(Artifact, design_version.artifact_id) if design_version else None
    if (
        design_version is None
        or solution is None
        or solution.project_id != project.id
        or solution.kind != "solution_design"
        or solution.stage != "solution_confirmation"
        or design_version.context_version != project.context_version
        or design_version.approval_status not in {"draft", "waiting_gate"}
    ):
        raise SolutionDefinitionError(
            "SOLUTION_SUBMISSION_NOT_FOUND", "方案提交不存在或已过期。", 404
        )
    pack = _reviewer_pack_for_design(session, project.id, design_version.id)
    if pack is None:
        raise SolutionDefinitionError(
            "SOLUTION_REVIEW_PACK_NOT_FOUND", "方案 Reviewer Context 不存在。"
        )
    candidates = pack.policy.get("review_candidates") or []
    flow_candidate = next(
        (item for item in candidates if item.get("artifact_id") != solution.id),
        None,
    )
    user_flow = (
        session.get(Artifact, flow_candidate.get("artifact_id")) if flow_candidate else None
    )
    user_flow_version = (
        session.scalar(
            select(ArtifactVersion).where(
                ArtifactVersion.id == flow_candidate.get("artifact_version_id")
            )
        )
        if flow_candidate
        else None
    )
    if (
        user_flow is None
        or user_flow_version is None
        or user_flow.kind != "user_flow"
        or user_flow.project_id != project.id
        or user_flow_version.context_version != project.context_version
        or user_flow_version.approval_status not in {"draft", "waiting_gate"}
    ):
        raise SolutionDefinitionError("SOLUTION_SUBMISSION_CORRUPT", "User Flow 绑定失效。", 500)
    return user_flow, user_flow_version, solution, design_version, pack


def _submission_read(
    session: Session,
    project: Project,
    design_version: ArtifactVersion,
    *,
    idempotent: bool,
) -> SolutionSubmissionRead:
    user_flow, user_flow_version, solution, solution_version, pack = _solution_bundle(
        session,
        project=project,
        design_version=design_version,
    )
    design_candidate = next(
        item
        for item in pack.policy["review_candidates"]
        if item.get("artifact_id") == solution.id
    )
    return SolutionSubmissionRead(
        submission_id=solution_version.id,
        project_id=project.id,
        source_run_id=str(design_candidate.get("source_run_id")),
        context_pack_id=str(design_candidate.get("source_context_pack_id")),
        context_version=solution_version.context_version,
        status="waiting_reviewer",
        user_flow=_artifact_ref(user_flow, user_flow_version),
        solution_design=_artifact_ref(solution, solution_version),
        reviewer_context_pack_id=pack.id,
        idempotent=idempotent,
        created_at=solution_version.created_at,
    )


def _review_read(
    session: Session,
    project: Project,
    submission_id: str,
    *,
    idempotent: bool,
) -> SolutionReviewRead:
    design_version = session.get(ArtifactVersion, submission_id)
    user_flow, user_flow_version, solution, solution_version, _ = _solution_bundle(
        session,
        project=project,
        design_version=design_version,
    )
    row = session.execute(
        select(ArtifactEdge, Artifact, ArtifactVersion)
        .join(Artifact, Artifact.id == ArtifactEdge.target_id)
        .join(ArtifactVersion, ArtifactVersion.artifact_id == Artifact.id)
        .where(
            ArtifactEdge.project_id == project.id,
            ArtifactEdge.source_id == solution.id,
            Artifact.kind == "solution_review",
            ArtifactVersion.context_version == project.context_version,
        )
        .order_by(ArtifactVersion.version.desc())
    ).first()
    if row is None:
        raise SolutionDefinitionError("SOLUTION_REVIEW_CORRUPT", "方案审核不存在。", 500)
    _, review, review_version = row
    gate = session.scalar(
        select(Gate).where(
            Gate.project_id == project.id,
            Gate.gate_type == "G3",
            Gate.context_version == project.context_version,
        )
    )
    verdict = "reject" if gate is None else (
        "pass_with_known_issues" if gate.known_issues else "pass"
    )
    return SolutionReviewRead(
        submission_id=submission_id,
        project_id=project.id,
        context_version=project.context_version,
        verdict=verdict,
        status="changes_requested" if gate is None else "waiting_g3",
        user_flow=_artifact_ref(user_flow, user_flow_version),
        solution_design=_artifact_ref(solution, solution_version),
        solution_review=_artifact_ref(review, review_version),
        known_issues=[
            KnownIssueRead.model_validate(item)
            for item in (gate.known_issues if gate else [])
        ],
        gate=GateRead.model_validate(gate) if gate else None,
        idempotent=idempotent,
    )


def _open_g3(
    session: Session,
    *,
    project: Project,
    user_flow: Artifact,
    user_flow_version: ArtifactVersion,
    solution: Artifact,
    solution_version: ArtifactVersion,
    review: Artifact,
    review_version: ArtifactVersion,
    known_issues: list[KnownIssueRead],
) -> Gate:
    existing = session.scalar(
        select(Gate).where(
            Gate.project_id == project.id,
            Gate.gate_type == "G3",
            Gate.context_version == project.context_version,
        )
    )
    if existing is not None:
        return existing
    try:
        validate_gate_open(
            current_state=project.state,
            gate_type="G3",
            target_state="tech_stack_confirmation",
            context_matches=True,
        )
        validate_gate_artifact_kinds(
            "G3", {user_flow.kind, solution.kind, review.kind}
        )
    except ControlPlaneError as exc:
        raise SolutionDefinitionError(exc.code, exc.user_message) from exc
    refs = [
        {"artifact_id": user_flow.id, "version": user_flow_version.version},
        {"artifact_id": solution.id, "version": solution_version.version},
        {"artifact_id": review.id, "version": review_version.version},
    ]
    gate = Gate(
        project_id=project.id,
        gate_type="G3",
        context_version=project.context_version,
        status="open",
        target_state="tech_stack_confirmation",
        reason="User Flow、方案说明与独立审核已完成，请用户确认方案。",
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
            "gate_type": "G3",
            "context_version": project.context_version,
            "target_state": "tech_stack_confirmation",
            "impacted_artifact_refs": refs,
            "known_issue_count": len(known_issues),
        },
    )
    return gate


def _known_issues(
    session: Session,
    project: Project,
    body: SolutionReviewCreate,
) -> list[KnownIssueRead]:
    inherited = session.scalar(
        select(Gate)
        .where(Gate.project_id == project.id, Gate.gate_type == "G2")
        .order_by(Gate.opened_at.desc())
    )
    raw = list(inherited.known_issues if inherited else [])
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


def _artifact_ref(
    artifact: Artifact,
    version: ArtifactVersion,
) -> SolutionArtifactRefRead:
    return SolutionArtifactRefRead(
        artifact_id=artifact.id,
        version=version.version,
        kind=artifact.kind,
        context_version=version.context_version,
        approval_status=version.approval_status,
        content_hash=version.content_hash,
        artifact_ref=f"artifact:{artifact.id}:v{version.version}",
    )
