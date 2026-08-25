from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from app.agents.artifact_proposals import ArtifactProposalStager, ProposalStagingError


def ai_pm_output(*, content: str = "市场证据与需求正文") -> dict:
    evidence_ref = f"bocha:web:{'a' * 64}"
    return {
        "message": "已形成 Evidence Index 和 MRD。",
        "artifact_proposals": [
            {
                "kind": kind,
                "title": title,
                "content": f"{content} {evidence_ref}",
                "evidence_refs": [evidence_ref],
                "assumptions": ["样本仅覆盖公开网页"],
                "status": "waiting_review",
            }
            for kind, title in (("evidence_index", "Evidence Index"), ("mrd", "MRD"))
        ],
        "verified_fact_proposals": [],
        "open_questions": [],
        "transition_proposal": None,
    }


def stager(root: Path) -> ArtifactProposalStager:
    root.mkdir()
    return ArtifactProposalStager(root)


def test_ai_pm_proposals_are_staged_as_hash_bound_immutable_markdown(tmp_path: Path) -> None:
    service = stager(tmp_path / "artifacts")
    staged = service.stage_ai_pm(
        project_id="project-1",
        context_version=2,
        run_id="run-1",
        output=ai_pm_output(),
    )

    assert [item.artifact_kind for item in staged] == ["evidence_index", "mrd"]
    for item in staged:
        path = service.artifact_root / item.body.content_ref
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == item.body.content_hash
        assert item.evidence_refs[0].encode() in data
        assert item.idempotency_key == f"agent-proposal:run-1:{item.artifact_kind}"
        assert path.stat().st_mode & 0o777 == 0o600


def test_staging_is_idempotent_and_conflicting_run_kind_fails_closed(
    tmp_path: Path,
) -> None:
    service = stager(tmp_path / "artifacts")
    arguments = {
        "project_id": "project-1",
        "context_version": 2,
        "run_id": "run-1",
    }
    first = service.stage_ai_pm(**arguments, output=ai_pm_output())
    repeated = service.stage_ai_pm(**arguments, output=ai_pm_output())
    assert repeated[0].body.content_hash == first[0].body.content_hash

    with pytest.raises(ProposalStagingError, match="conflicts"):
        service.stage_ai_pm(**arguments, output=ai_pm_output(content="changed"))


def test_staging_rejects_paths_secrets_and_invalid_artifact_schema(tmp_path: Path) -> None:
    service = stager(tmp_path / "artifacts")
    with pytest.raises(ProposalStagingError, match="safe path"):
        service.stage_ai_pm(
            project_id="../escape",
            context_version=2,
            run_id="run-1",
            output=ai_pm_output(),
        )
    with pytest.raises(ProposalStagingError, match="secret-like"):
        service.stage_ai_pm(
            project_id="project-1",
            context_version=2,
            run_id="run-secret",
            output=ai_pm_output(content="api_key=must-not-persist-123456789"),
        )
    invalid = ai_pm_output()
    invalid["artifact_proposals"] = invalid["artifact_proposals"][:1]
    with pytest.raises(ValueError):
        service.stage_ai_pm(
            project_id="project-1",
            context_version=2,
            run_id="run-invalid",
            output=invalid,
        )
