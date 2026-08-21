import hashlib
from pathlib import Path

import pytest
from app.adapters.codex_cli import smoke_codex_cli
from app.core.config import Settings
from app.services.artifact_store import ArtifactStoreError, read_verified_artifact


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
