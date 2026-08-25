import hashlib
import json
from pathlib import Path

import pytest
from app.adapters.codex_cli import (
    build_workspace_manifest,
    execute_codex_cli,
    resolve_project_workspace,
    smoke_codex_cli,
)
from app.core.config import Settings
from app.services.artifact_store import ArtifactStoreError, read_verified_artifact
from app.services.builder_runtime import BuilderRuntimeError, BuilderRuntimeService


def make_settings(tmp_path: Path, codex_path: Path) -> Settings:
    artifact_root = tmp_path / "artifacts"
    workspace_root = tmp_path / "workspaces"
    artifact_root.mkdir()
    workspace_root.mkdir()
    return Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg://user:password@127.0.0.1:5432/database",
        ARTIFACT_ROOT=artifact_root,
        WORKSPACE_ROOT=workspace_root,
        CODEX_CLI_PATH=codex_path,
    )


def test_codex_smoke_is_read_only_and_returns_version(tmp_path: Path) -> None:
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\nprintf 'codex-cli 1.2.3\\n'\n", encoding="utf-8")
    codex.chmod(0o700)

    result = smoke_codex_cli(make_settings(tmp_path, codex))

    assert result.executable is True
    assert result.exit_code == 0
    assert result.version == "codex-cli 1.2.3"


def test_codex_smoke_reports_builder_policy_disabled(tmp_path: Path) -> None:
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    codex.chmod(0o700)
    settings = make_settings(tmp_path, codex)
    settings.BUILDER_ENABLED = False

    result = smoke_codex_cli(settings)

    assert result.configured is False
    assert result.executable is False
    assert result.exit_code is None
    assert result.error == "Builder is disabled by installation policy"


def test_builder_runtime_fails_closed_before_database_access(tmp_path: Path) -> None:
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    codex.chmod(0o700)
    settings = make_settings(tmp_path, codex)
    settings.BUILDER_ENABLED = False

    with pytest.raises(BuilderRuntimeError) as error:
        BuilderRuntimeService(settings).start(
            project_id="2a3c38e1-9704-4f83-a096-84cb5a5025e7",
            task_id="task",
            context_pack_id="context",
            expected_context_version=1,
            idempotency_key="builder-disabled-test",
        )

    assert error.value.code == "BUILDER_DISABLED"


def test_codex_execution_is_scoped_hashed_and_does_not_inherit_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex = tmp_path / "codex"
    codex.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

if os.getenv("DEEPSEEK_API_KEY"):
    raise SystemExit(9)
Path("app.py").write_text("print('ok')\\n", encoding="utf-8")
message = json.dumps({
    "message": "后端切片完成",
    "technical_decisions": [],
    "tool_requests": [],
    "artifact_proposals": [],
    "test_results": [],
    "known_issues": [],
    "gate_request": None,
    "transition_proposal": None,
}, ensure_ascii=False)
print(json.dumps({
    "type": "item.completed",
    "item": {"type": "agent_message", "text": message},
}, ensure_ascii=False))
""",
        encoding="utf-8",
    )
    codex.chmod(0o700)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-reach-builder")
    settings = make_settings(tmp_path, codex)
    project_id = "2a3c38e1-9704-4f83-a096-84cb5a5025e7"
    workspace = resolve_project_workspace(settings, project_id)
    schema = workspace / "builder-output.schema.json"
    schema.write_text("{}", encoding="utf-8")

    result = execute_codex_cli(
        settings,
        project_id=project_id,
        prompt="Implement the approved backend task.",
        output_schema=schema,
        timeout_seconds=5,
    )

    assert result.succeeded is True
    assert result.exit_code == 0
    assert result.event_count == 1
    assert json.loads(result.final_message or "{}")["message"] == "后端切片完成"
    assert result.workspace_manifest.file_count == 2
    assert len(result.workspace_manifest.digest) == 64


def test_workspace_manifest_rejects_secret_files_and_local_paths(tmp_path: Path) -> None:
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    codex.chmod(0o700)
    settings = make_settings(tmp_path, codex)
    workspace = resolve_project_workspace(
        settings, "2a3c38e1-9704-4f83-a096-84cb5a5025e7"
    )
    (workspace / ".env").write_text("SAFE_PLACEHOLDER=1\n", encoding="utf-8")
    (workspace / "leak.txt").write_text(
        f"path={settings.WORKSPACE_ROOT}\n", encoding="utf-8"
    )

    manifest = build_workspace_manifest(settings, workspace)

    assert "secret-file:.env" in manifest.violations
    assert "local-path:leak.txt" in manifest.violations


def test_workspace_manifest_allows_server_env_reference_and_ignores_pnpm_cache(
    tmp_path: Path,
) -> None:
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    codex.chmod(0o700)
    settings = make_settings(tmp_path, codex)
    workspace = resolve_project_workspace(
        settings, "2a3c38e1-9704-4f83-a096-84cb5a5025e7"
    )
    route = workspace / "route.ts"
    route.write_text(
        "const token = process.env.SALES_REVIEW_API_TOKEN;\n", encoding="utf-8"
    )
    cache = workspace / ".pnpm-store" / "v11" / "projects"
    cache.mkdir(parents=True)
    (cache / "workspace-link").symlink_to(workspace, target_is_directory=True)

    manifest = build_workspace_manifest(settings, workspace)

    assert manifest.violations == ()
    assert manifest.file_count == 1


def test_workspace_manifest_still_rejects_literal_token_assignment(tmp_path: Path) -> None:
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    codex.chmod(0o700)
    settings = make_settings(tmp_path, codex)
    workspace = resolve_project_workspace(
        settings, "2a3c38e1-9704-4f83-a096-84cb5a5025e7"
    )
    (workspace / "leak.ts").write_text(
        'const token = "literal-production-token-123456";\n', encoding="utf-8"
    )

    manifest = build_workspace_manifest(settings, workspace)

    assert "secret-pattern:leak.ts" in manifest.violations


def test_artifact_store_rejects_escape_and_hash_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    content = root / "brief.md"
    content.write_text("# Brief", encoding="utf-8")

    path, text = read_verified_artifact(
        root,
        "brief.md",
        hashlib.sha256(b"# Brief").hexdigest(),
    )
    assert path == content
    assert text == "# Brief"

    with pytest.raises(ArtifactStoreError, match="escapes"):
        read_verified_artifact(root, "../outside.md", "0" * 64)
    with pytest.raises(ArtifactStoreError, match="hash"):
        read_verified_artifact(root, "brief.md", "0" * 64)
