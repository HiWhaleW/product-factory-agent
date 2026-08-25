from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.agents.outputs import AiPmMrdOutput, ReviewerMrdOutput
from app.domain.schemas import AgentArtifactProposal


class ProposalStagingError(RuntimeError):
    pass


class StagedArtifactSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_kind: Literal["evidence_index", "mrd", "red_team_review"]
    evidence_refs: list[str]
    idempotency_key: str
    body: AgentArtifactProposal


class ArtifactProposalStager:
    """Stages untrusted model proposals; deterministic APIs still own persistence."""

    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root.resolve(strict=True)
        if not self.artifact_root.is_dir():
            raise ProposalStagingError("Artifact root must be an existing directory.")

    def stage_ai_pm(
        self,
        *,
        project_id: str,
        context_version: int,
        run_id: str,
        output: dict[str, Any],
    ) -> list[StagedArtifactSubmission]:
        validated = AiPmMrdOutput.model_validate(output)
        return self._stage(
            project_id=project_id,
            context_version=context_version,
            run_id=run_id,
            proposals=[item.model_dump(mode="json") for item in validated.artifact_proposals],
        )

    def stage_reviewer(
        self,
        *,
        project_id: str,
        context_version: int,
        run_id: str,
        output: dict[str, Any],
    ) -> list[StagedArtifactSubmission]:
        validated = ReviewerMrdOutput.model_validate(output)
        return self._stage(
            project_id=project_id,
            context_version=context_version,
            run_id=run_id,
            proposals=[item.model_dump(mode="json") for item in validated.artifact_proposals],
        )

    def _stage(
        self,
        *,
        project_id: str,
        context_version: int,
        run_id: str,
        proposals: list[dict[str, Any]],
    ) -> list[StagedArtifactSubmission]:
        project_id = _safe_component(project_id, "project_id")
        run_id = _safe_component(run_id, "run_id")
        directory = self.artifact_root / "agent-proposals" / project_id / run_id
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        resolved_directory = directory.resolve(strict=True)
        if not resolved_directory.is_relative_to(self.artifact_root):
            raise ProposalStagingError("Proposal directory escapes ARTIFACT_ROOT.")
        staged: list[StagedArtifactSubmission] = []
        for proposal in proposals:
            kind = str(proposal["kind"])
            if kind not in {"evidence_index", "mrd", "red_team_review"}:
                raise ProposalStagingError("Unsupported D5 artifact kind.")
            content = _canonical_markdown(
                title=str(proposal["title"]),
                run_id=run_id,
                context_version=context_version,
                evidence_refs=list(proposal.get("evidence_refs") or []),
                assumptions=list(proposal.get("assumptions") or []),
                content=str(proposal["content"]),
            )
            _reject_sensitive_content(content)
            data = content.encode("utf-8")
            digest = hashlib.sha256(data).hexdigest()
            target = resolved_directory / f"{kind}.md"
            _write_once(target, data)
            relative_path = target.relative_to(self.artifact_root).as_posix()
            staged.append(
                StagedArtifactSubmission(
                    artifact_kind=kind,
                    evidence_refs=list(proposal.get("evidence_refs") or []),
                    idempotency_key=f"agent-proposal:{run_id}:{kind}",
                    body=AgentArtifactProposal(
                        project_id=project_id,
                        context_version=context_version,
                        expected_previous_version=0,
                        artifact_kind=kind,
                        title=str(proposal["title"]),
                        content_ref=relative_path,
                        content_hash=digest,
                        summary=f"Staged from Agent Run {run_id}; awaiting deterministic review.",
                    ),
                )
            )
        return staged


def _safe_component(value: str, name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,63}", value):
        raise ProposalStagingError(f"{name} is not a safe path component.")
    return value


def _canonical_markdown(
    *,
    title: str,
    run_id: str,
    context_version: int,
    evidence_refs: list[str],
    assumptions: list[str],
    content: str,
) -> str:
    evidence = "\n".join(f"- `{item}`" for item in evidence_refs)
    assumption_text = "\n".join(f"- {item}" for item in assumptions) or "- 无"
    return (
        f"# {title.strip()}\n\n"
        f"- Source Run: `{run_id}`\n"
        f"- Context Version: `{context_version}`\n\n"
        f"## Evidence Refs\n\n{evidence}\n\n"
        f"## Assumptions\n\n{assumption_text}\n\n"
        f"## Content\n\n{content.strip()}\n"
    )


def _reject_sensitive_content(value: str) -> None:
    markers = (
        r"\bsk-[A-Za-z0-9_-]{16,}\b",
        r"(?i)\b(api[_-]?key|access[_-]?token|password)\s*[:=]\s*\S+",
    )
    if any(re.search(pattern, value) for pattern in markers):
        raise ProposalStagingError("Proposal contains secret-like content.")


def _write_once(target: Path, data: bytes) -> None:
    temporary = target.with_name(f".{target.name}.tmp-{uuid4().hex}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            existing = target.read_bytes()
            if existing != data:
                raise ProposalStagingError(
                    "Staged proposal conflicts with immutable Run/kind content."
                ) from None
    finally:
        temporary.unlink(missing_ok=True)
