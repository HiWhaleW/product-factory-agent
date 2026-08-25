from __future__ import annotations

from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.agents.technical_contracts import (
    TechnicalArtifactRefRead,
    TechnicalReviewCreate,
    TechnicalReviewerInputRead,
    TechnicalReviewRead,
    TechnicalSubmissionCreate,
    TechnicalSubmissionRead,
)
from app.domain.models import (
    AgentMembership,
    Artifact,
    ArtifactVersion,
    ContextPack,
    ContextVersion,
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
from app.services.solution_definition import _require_project, _require_run

TechnicalDefinitionError = PrdDefinitionError


def lock_technical_scope(session: Session, project_id: str, idempotency_key: str) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"technical:{project_id}:{idempotency_key}"},
    )


def submit_technical_definition(
    session: Session,
    *,
    artifact_root: Path,
    project_id: str,
    idempotency_key: str,
    body: TechnicalSubmissionCreate,
) -> TechnicalSubmissionRead:
    project = _require_project(session, project_id)
    body_hash = stable_hash(body)
    existing = _idempotency(session, f"technical.submission:{project_id}", idempotency_key)
    if existing is not None:
        if existing.input_hash != body_hash:
            raise TechnicalDefinitionError(
                "IDEMPOTENCY_CONFLICT", "同一幂等键不能提交不同的技术定义。"
            )
        api_version = session.get(ArtifactVersion, existing.resource_id)
        if api_version is None:
            raise TechnicalDefinitionError("IDEMPOTENCY_ORPHAN", "技术定义幂等记录失效。", 500)
        return _submission_read(session, project, api_version, idempotent=True)
    if project.state != "tech_stack_confirmation":
        raise TechnicalDefinitionError(
            "TECHNICAL_STAGE_INVALID", "技术定义只能在技术栈确认阶段提交。"
        )
    if project.context_version != body.expected_context_version:
        raise TechnicalDefinitionError("STALE_CONTEXT", "技术定义基于旧 Context，禁止合并。")
    pack = _require_technical_pack(session, project, body.context_pack_id, "builder", None)
    if (
        "CAP-07" not in set(pack.policy.get("allowed_capability_ids") or [])
        or pack.policy.get("mode") != "technical_document_only"
    ):
        raise TechnicalDefinitionError(
            "TECHNICAL_POLICY_INVALID", "G4 前 Builder 必须处于只写技术文档模式。"
        )
    forbidden = set(pack.policy.get("forbidden_actions") or [])
    if not {"codex_cli", "project_fs_write", "git_local", "test_runner"}.issubset(forbidden):
        raise TechnicalDefinitionError(
            "TECHNICAL_POLICY_INVALID", "G4 前必须禁止代码、Git 与测试。"
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
            raise TechnicalDefinitionError(
                "TECHNICAL_EVIDENCE_INVALID",
                "技术定义必须引用已批准方案说明，且不能引用 Context 外材料。",
            )
    _tool_started(
        session,
        project_id=project.id,
        run=run,
        task=task,
        capability_id="CAP-07",
        input_hash=body_hash,
        idempotency_key=f"artifact_store:technical:{run.id}",
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
            summary=f"{proposal.title}；引用 {len(proposal.evidence_refs)} 条。",
            stage="tech_stack_confirmation",
        )
    adaptation, adaptation_version = persisted["technical_adaptation"]
    api_contract, api_version = persisted["api_contract"]
    for source in source_artifacts:
        _ensure_edge(session, project.id, source.id, adaptation.id, "supports")
        _ensure_edge(session, project.id, source.id, api_contract.id, "supports")
    _ensure_edge(session, project.id, adaptation.id, api_contract.id, "defines")
    reviewer_pack = _create_reviewer_pack(
        session,
        project=project,
        source_pack=pack,
        source_run_id=run.id,
        candidates=[(adaptation, adaptation_version), (api_contract, api_version)],
        evidence_refs={
            proposal.kind: proposal.evidence_refs for proposal in body.artifact_proposals
        },
    )
    _tool_completed(
        session,
        project_id=project.id,
        run=run,
        task=task,
        capability_id="CAP-07",
        input_hash=body_hash,
        idempotency_key=f"artifact_store:technical:{run.id}",
        result_ref=(
            f"artifact-pair:{adaptation.id}:v{adaptation_version.version},"
            f"{api_contract.id}:v{api_version.version}"
        ),
        policy_outcome=policy.outcome,
    )
    session.add(
        IdempotencyRecord(
            scope=f"technical.submission:{project_id}",
            key=idempotency_key,
            resource_id=api_version.id,
            input_hash=body_hash,
        )
    )
    _append_event(
        session,
        project.id,
        "technical.submitted",
        {
            "submission_id": api_version.id,
            "source_run_id": run.id,
            "reviewer_context_pack_id": reviewer_pack.id,
        },
    )
    return _submission_read(session, project, api_version, idempotent=False)


def technical_reviewer_input(
    session: Session,
    *,
    project_id: str,
    submission_id: str,
) -> TechnicalReviewerInputRead:
    project = _require_project(session, project_id)
    api_version = session.get(ArtifactVersion, submission_id)
    adaptation, adaptation_version, api_contract, api_contract_version, pack = _technical_bundle(
        session, project=project, api_version=api_version
    )
    return TechnicalReviewerInputRead(
        submission_id=api_contract_version.id,
        project_id=project.id,
        context_version=project.context_version,
        reviewer_context_pack_id=pack.id,
        artifact_refs=[
            f"artifact:{adaptation.id}:v{adaptation_version.version}",
            f"artifact:{api_contract.id}:v{api_contract_version.version}",
        ],
        task=(
            "对绑定的 Technical Adaptation 与 API Contract 做 clean-review：检查冻结版本、"
            "Runtime/API/数据库边界、成本、安全、数据、迁移、可观测性、失败与回退是否完整。"
            "只提交 Technical Review，不批准 G4，不推进状态，不要求写代码。"
        ),
        forbidden_actions=[
            "advance_project_state",
            "approve_gate",
            "modify_technical_candidates",
            "codex_cli",
            "project_fs_write",
            "read_secret_values",
        ],
    )


def submit_technical_review(
    session: Session,
    *,
    artifact_root: Path,
    project_id: str,
    submission_id: str,
    idempotency_key: str,
    body: TechnicalReviewCreate,
) -> TechnicalReviewRead:
    project = _require_project(session, project_id)
    body_hash = stable_hash(body)
    existing = _idempotency(session, f"technical.review:{submission_id}", idempotency_key)
    if existing is not None:
        if existing.input_hash != body_hash:
            raise TechnicalDefinitionError(
                "IDEMPOTENCY_CONFLICT", "同一幂等键不能提交不同的技术审核。"
            )
        return _review_read(session, project, submission_id, idempotent=True)
    if (
        project.state != "tech_stack_confirmation"
        or project.context_version != body.expected_context_version
    ):
        raise TechnicalDefinitionError("STALE_CONTEXT", "技术审核基于旧 Context，禁止合并。")
    api_version = session.get(ArtifactVersion, submission_id)
    adaptation, adaptation_version, api_contract, api_contract_version, pack = _technical_bundle(
        session, project=project, api_version=api_version
    )
    if body.context_pack_id != pack.id:
        raise TechnicalDefinitionError(
            "TECHNICAL_REVIEW_CONTEXT_MISMATCH", "Reviewer 未绑定当前技术定义。"
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
        f"artifact:{adaptation.id}:v{adaptation_version.version}",
        f"artifact:{api_contract.id}:v{api_contract_version.version}",
    }
    proposed_refs = set(body.review_artifact.evidence_refs) | {
        ref for finding in body.findings for ref in finding.evidence_refs
    }
    if not candidate_refs.issubset(
        set(body.review_artifact.evidence_refs)
    ) or not proposed_refs.issubset(candidate_refs):
        raise TechnicalDefinitionError(
            "TECHNICAL_REVIEW_EVIDENCE_INVALID",
            "技术审核必须引用两个绑定候选，且不能引用未绑定材料。",
        )
    blocking = [finding for finding in body.findings if finding.severity in {"P0", "P1"}]
    if body.verdict != "reject" and blocking:
        raise TechnicalDefinitionError(
            "TECHNICAL_REVIEW_VERDICT_INVALID", "存在 P0/P1 时 Reviewer 必须 reject。"
        )
    _tool_started(
        session,
        project_id=project.id,
        run=run,
        task=task,
        capability_id="CAP-10",
        input_hash=body_hash,
        idempotency_key=f"artifact_store:technical-review:{run.id}",
        policy_outcome=policy.outcome,
    )
    review, review_version = _persist_artifact(
        session,
        artifact_root=artifact_root,
        project=project,
        proposal=body.review_artifact,
        kind="technical_review",
        owner_agent="reviewer",
        summary=f"技术审核：{body.verdict}；发现 {len(body.findings)} 项。",
        stage="tech_stack_confirmation",
    )
    _ensure_edge(session, project.id, adaptation.id, review.id, "reviewed_by")
    _ensure_edge(session, project.id, api_contract.id, review.id, "reviewed_by")
    _tool_completed(
        session,
        project_id=project.id,
        run=run,
        task=task,
        capability_id="CAP-10",
        input_hash=body_hash,
        idempotency_key=f"artifact_store:technical-review:{run.id}",
        result_ref=f"artifact:{review.id}:v{review_version.version}",
        policy_outcome=policy.outcome,
    )
    known_issues = _known_issues(session, project, body)
    gate = None
    bundle = [
        (adaptation, adaptation_version),
        (api_contract, api_contract_version),
        (review, review_version),
    ]
    if body.verdict in {"pass", "pass_with_known_issues"}:
        for artifact, version in bundle:
            artifact.status = "waiting_gate"
            version.approval_status = "waiting_gate"
        gate = _open_g4(
            session,
            project=project,
            adaptation=adaptation,
            adaptation_version=adaptation_version,
            api_contract=api_contract,
            api_contract_version=api_contract_version,
            review=review,
            review_version=review_version,
            known_issues=known_issues,
        )
        status = "waiting_g4"
    else:
        for artifact, version in bundle:
            artifact.status = "changes_requested"
            version.approval_status = "changes_requested"
        status = "changes_requested"
    session.add(
        IdempotencyRecord(
            scope=f"technical.review:{submission_id}",
            key=idempotency_key,
            resource_id=review_version.id,
            input_hash=body_hash,
        )
    )
    _append_event(
        session,
        project.id,
        "technical.reviewed",
        {
            "submission_id": submission_id,
            "source_run_id": run.id,
            "review_artifact_id": review.id,
            "verdict": body.verdict,
            "status": status,
            "gate_id": gate.id if gate else None,
        },
    )
    return TechnicalReviewRead(
        submission_id=submission_id,
        project_id=project.id,
        context_version=project.context_version,
        verdict=body.verdict,
        status=status,
        technical_adaptation=_artifact_ref(adaptation, adaptation_version),
        api_contract=_artifact_ref(api_contract, api_contract_version),
        technical_review=_artifact_ref(review, review_version),
        known_issues=known_issues,
        gate=GateRead.model_validate(gate) if gate else None,
        idempotent=False,
    )


def _require_technical_pack(
    session: Session,
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
        or pack.stage != "tech_stack_confirmation"
        or pack.context_version != project.context_version
        or pack.approval_status != "approved"
    ):
        raise TechnicalDefinitionError(
            "TECHNICAL_CONTEXT_INVALID", "技术定义 Context 不存在或已过期。"
        )
    if input_contract is not None and pack.policy.get("input_contract") != input_contract:
        raise TechnicalDefinitionError("TECHNICAL_CONTEXT_INVALID", "技术审核输入契约不匹配。")
    return pack


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
    expected = {"user_flow", "solution_design", "solution_review"}
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
            or artifact.kind not in expected
            or version.approval_status != "approved"
        ):
            raise TechnicalDefinitionError(
                "TECHNICAL_CONTEXT_INVALID", "技术定义只接受已批准方案产物。"
            )
        try:
            read_verified_artifact(artifact_root, version.content_ref, version.content_hash)
        except ArtifactStoreError as exc:
            raise TechnicalDefinitionError(
                "TECHNICAL_CONTEXT_INVALID", "技术定义输入 Artifact 校验失败。"
            ) from exc
        allowed.add(f"artifact:{artifact.id}:v{version.version}")
        artifacts.append(artifact)
    if {artifact.kind for artifact in artifacts} != expected:
        raise TechnicalDefinitionError(
            "TECHNICAL_CONTEXT_INVALID", "技术定义必须精确继承完整方案。"
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
        raise TechnicalDefinitionError("CONTEXT_VERSION_NOT_FOUND", "当前 Context 不存在。", 500)
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
        stage="tech_stack_confirmation",
        approval_status="approved",
        primary_resource_type=source_pack.primary_resource_type,
        primary_resource_id=source_pack.primary_resource_id,
        primary_resource_version=source_pack.primary_resource_version,
        agent_id="reviewer",
        task=(
            "使用 technical-review/v1 clean-review 审查 Technical Adaptation 与 "
            "API Contract；不得批准 G4。"
        ),
        references=list(source_pack.references or []),
        policy={
            "allowed_capability_ids": ["CAP-10"],
            "forbidden_actions": [
                "advance_project_state",
                "approve_gate",
                "modify_technical_candidates",
                "codex_cli",
                "project_fs_write",
                "read_secret_values",
            ],
            "input_contract": "technical-review/v1",
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
            "input_contract": "technical-review/v1",
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
    return pack


def _reviewer_pack_for_api(
    session: Session, project_id: str, api_version_id: str
) -> ContextPack | None:
    packs = session.scalars(
        select(ContextPack).where(
            ContextPack.project_id == project_id,
            ContextPack.stage == "tech_stack_confirmation",
            ContextPack.agent_id == "reviewer",
        )
    )
    for pack in packs:
        candidates = pack.policy.get("review_candidates") or []
        if any(item.get("artifact_version_id") == api_version_id for item in candidates):
            return pack
    return None


def _technical_bundle(
    session: Session,
    *,
    project: Project,
    api_version: ArtifactVersion | None,
) -> tuple[Artifact, ArtifactVersion, Artifact, ArtifactVersion, ContextPack]:
    api_contract = session.get(Artifact, api_version.artifact_id) if api_version else None
    if (
        api_version is None
        or api_contract is None
        or api_contract.project_id != project.id
        or api_contract.kind != "api_contract"
        or api_contract.stage != "tech_stack_confirmation"
        or api_version.context_version != project.context_version
        or api_version.approval_status not in {"draft", "waiting_gate"}
    ):
        raise TechnicalDefinitionError(
            "TECHNICAL_SUBMISSION_NOT_FOUND", "技术定义提交不存在或已过期。", 404
        )
    pack = _reviewer_pack_for_api(session, project.id, api_version.id)
    if pack is None:
        raise TechnicalDefinitionError(
            "TECHNICAL_REVIEW_PACK_NOT_FOUND", "技术 Reviewer Context 不存在。"
        )
    candidate = next(
        (
            item
            for item in pack.policy.get("review_candidates") or []
            if item.get("artifact_id") != api_contract.id
        ),
        None,
    )
    adaptation = session.get(Artifact, candidate.get("artifact_id")) if candidate else None
    adaptation_version = (
        session.get(ArtifactVersion, candidate.get("artifact_version_id")) if candidate else None
    )
    if (
        adaptation is None
        or adaptation_version is None
        or adaptation.kind != "technical_adaptation"
        or adaptation.project_id != project.id
        or adaptation_version.context_version != project.context_version
        or adaptation_version.approval_status not in {"draft", "waiting_gate"}
    ):
        raise TechnicalDefinitionError(
            "TECHNICAL_SUBMISSION_CORRUPT", "Technical Adaptation 绑定失效。", 500
        )
    return adaptation, adaptation_version, api_contract, api_version, pack


def _submission_read(
    session: Session,
    project: Project,
    api_version: ArtifactVersion,
    *,
    idempotent: bool,
) -> TechnicalSubmissionRead:
    adaptation, adaptation_version, api_contract, api_contract_version, pack = _technical_bundle(
        session, project=project, api_version=api_version
    )
    candidate = next(
        item
        for item in pack.policy["review_candidates"]
        if item.get("artifact_id") == api_contract.id
    )
    return TechnicalSubmissionRead(
        submission_id=api_contract_version.id,
        project_id=project.id,
        source_run_id=str(candidate.get("source_run_id")),
        context_pack_id=str(candidate.get("source_context_pack_id")),
        context_version=api_contract_version.context_version,
        status="waiting_reviewer",
        technical_adaptation=_artifact_ref(adaptation, adaptation_version),
        api_contract=_artifact_ref(api_contract, api_contract_version),
        reviewer_context_pack_id=pack.id,
        idempotent=idempotent,
        created_at=api_contract_version.created_at,
    )


def _review_read(
    session: Session,
    project: Project,
    submission_id: str,
    *,
    idempotent: bool,
) -> TechnicalReviewRead:
    api_version = session.get(ArtifactVersion, submission_id)
    adaptation, adaptation_version, api_contract, api_contract_version, _ = _technical_bundle(
        session, project=project, api_version=api_version
    )
    review = session.scalar(
        select(Artifact)
        .where(
            Artifact.project_id == project.id,
            Artifact.kind == "technical_review",
            Artifact.stage == "tech_stack_confirmation",
        )
        .order_by(Artifact.created_at.desc())
    )
    review_version = (
        session.scalar(
            select(ArtifactVersion)
            .where(
                ArtifactVersion.artifact_id == review.id,
                ArtifactVersion.context_version == project.context_version,
            )
            .order_by(ArtifactVersion.version.desc())
        )
        if review
        else None
    )
    if review is None or review_version is None:
        raise TechnicalDefinitionError("TECHNICAL_REVIEW_CORRUPT", "技术审核不存在。", 500)
    gate = session.scalar(
        select(Gate).where(
            Gate.project_id == project.id,
            Gate.gate_type == "G4",
            Gate.context_version == project.context_version,
        )
    )
    return TechnicalReviewRead(
        submission_id=submission_id,
        project_id=project.id,
        context_version=project.context_version,
        verdict="reject"
        if gate is None
        else ("pass_with_known_issues" if gate.known_issues else "pass"),
        status="changes_requested" if gate is None else "waiting_g4",
        technical_adaptation=_artifact_ref(adaptation, adaptation_version),
        api_contract=_artifact_ref(api_contract, api_contract_version),
        technical_review=_artifact_ref(review, review_version),
        known_issues=[
            KnownIssueRead.model_validate(item) for item in (gate.known_issues if gate else [])
        ],
        gate=GateRead.model_validate(gate) if gate else None,
        idempotent=idempotent,
    )


def _open_g4(
    session: Session,
    *,
    project: Project,
    adaptation: Artifact,
    adaptation_version: ArtifactVersion,
    api_contract: Artifact,
    api_contract_version: ArtifactVersion,
    review: Artifact,
    review_version: ArtifactVersion,
    known_issues: list[KnownIssueRead],
) -> Gate:
    existing = session.scalar(
        select(Gate).where(
            Gate.project_id == project.id,
            Gate.gate_type == "G4",
            Gate.context_version == project.context_version,
        )
    )
    if existing is not None:
        return existing
    try:
        validate_gate_open(
            current_state=project.state,
            gate_type="G4",
            target_state="development_backend",
            context_matches=True,
        )
        validate_gate_artifact_kinds("G4", {adaptation.kind, api_contract.kind, review.kind})
    except ControlPlaneError as exc:
        raise TechnicalDefinitionError(exc.code, exc.user_message) from exc
    refs = [
        {"artifact_id": adaptation.id, "version": adaptation_version.version},
        {"artifact_id": api_contract.id, "version": api_contract_version.version},
        {"artifact_id": review.id, "version": review_version.version},
    ]
    gate = Gate(
        project_id=project.id,
        gate_type="G4",
        context_version=project.context_version,
        status="open",
        target_state="development_backend",
        reason="Technical Adaptation、API Contract 与独立审核已完成，请用户确认技术栈。",
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
            "gate_type": "G4",
            "context_version": project.context_version,
            "target_state": "development_backend",
            "impacted_artifact_refs": refs,
            "known_issue_count": len(known_issues),
        },
    )
    return gate


def _known_issues(
    session: Session,
    project: Project,
    body: TechnicalReviewCreate,
) -> list[KnownIssueRead]:
    inherited = session.scalar(
        select(Gate)
        .where(Gate.project_id == project.id, Gate.gate_type == "G3")
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


def _artifact_ref(artifact: Artifact, version: ArtifactVersion) -> TechnicalArtifactRefRead:
    return TechnicalArtifactRefRead(
        artifact_id=artifact.id,
        version=version.version,
        kind=artifact.kind,
        context_version=version.context_version,
        approval_status=version.approval_status,
        content_hash=version.content_hash,
        artifact_ref=f"artifact:{artifact.id}:v{version.version}",
    )
