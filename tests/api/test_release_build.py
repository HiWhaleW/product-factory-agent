from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "release" / "build_release.py"
SPEC = importlib.util.spec_from_file_location("product_factory_release_build", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
release_build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_build)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fake_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    _write(source / "apps/api/app/main.py", "APP = 'release fixture'\n")
    _write(source / "apps/api/alembic/env.py", "# migration fixture\n")
    _write(
        source / "apps/api/alembic/versions/20260823_0010_project_soft_deletion.py",
        'revision = "20260823_0010"\n',
    )
    _write(source / "apps/api/alembic.ini", "[alembic]\nscript_location = apps/api/alembic\n")
    _write(
        source / "apps/web/.next/standalone/server.js",
        f"// standalone server built from {source}\n",
    )
    _write(
        source / "apps/web/.next/standalone/.next/required-server-files.json",
        json.dumps({"appDir": f"{source}/apps/web"}),
    )
    _write(
        source / "apps/web/.next/static/chunks/app.js",
        'const key = "product-factory:onboarding:v2:";\n',
    )
    _write(source / "apps/web/.next/cache/stale.txt", "must not ship\n")
    _write(source / "apps/web/.next/dev/stale.js.map", "must not ship\n")
    _write(source / "apps/web/public/favicon.ico", "fixture\n")
    for filename in release_build.EXPECTED_PROMPT_SHA256:
        source_prompt = ROOT / "产品工厂Agent" / "spec" / "prompts" / filename
        destination = source / "产品工厂Agent" / "spec" / "prompts" / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_prompt.read_bytes())
    for relative in [
        "package.json",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "pyproject.toml",
        "uv.lock",
        "apps/web/package.json",
    ]:
        _write(source / relative, f"fixture for {relative}\n")
    return source


def test_package_release_is_portable_complete_and_verifiable(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    release = tmp_path / "release"

    release_build.package_release(source, release, "20260824T120000Z")
    release_build.verify_release(release)

    assert (release / "apps/web/server.js").is_file()
    assert (release / "apps/web/.next/static/chunks/app.js").is_file()
    assert not (release / "apps/web/.next/cache").exists()
    assert not (release / "apps/web/.next/dev").exists()
    for path in release.rglob("*"):
        if path.is_symlink():
            assert not Path(path.readlink()).is_absolute()
            path.resolve().relative_to(release)
    assert str(source).encode() not in (release / "apps/web/server.js").read_bytes()
    assert release_build.SANITIZED_BUILD_ROOT in (release / "apps/web/server.js").read_bytes()
    assert (release / "apps/api/alembic.ini").is_file()
    assert (release / "产品工厂Agent/spec/prompts/reviewer.prompt.md").is_file()
    metadata = json.loads((release / release_build.METADATA_NAME).read_text(encoding="utf-8"))
    assert metadata["web_output"] == "standalone"
    assert metadata["alembic_head"] == "20260823_0010"


def test_verify_release_rejects_tampering(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    release = tmp_path / "release"
    release_build.package_release(source, release, "20260824T120001Z")
    (release / "apps/api/app/main.py").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(release_build.ReleaseBuildError, match="manifest does not match"):
        release_build.verify_release(release)


def test_package_release_rejects_changed_frozen_prompt(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    prompt = source / "产品工厂Agent/spec/prompts/factory-lead.prompt.md"
    prompt.write_text(prompt.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")

    with pytest.raises(release_build.ReleaseBuildError, match="prompt hash changed"):
        release_build.package_release(source, tmp_path / "release", "20260824T120002Z")


def test_package_release_rejects_onboarding_v1_bundle(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    bundle = source / "apps/web/.next/static/chunks/app.js"
    bundle.write_text('const key = "product-factory:onboarding:v1";\n', encoding="utf-8")

    with pytest.raises(release_build.ReleaseBuildError, match="onboarding v1"):
        release_build.package_release(source, tmp_path / "release", "20260824T120003Z")


def _run_release_shell(*arguments: str) -> subprocess.CompletedProcess[str]:
    script = 'source "$1"; shift; "$@"'
    return subprocess.run(
        ["bash", "-c", script, "bash", str(ROOT / "scripts/release/lib.sh"), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_controlled_release_resolution_accepts_only_canonical_roots(tmp_path: Path) -> None:
    internal_root = tmp_path / "seed/releases"
    user_root = tmp_path / "user/releases"
    internal_release = internal_root / "internal-v1"
    user_release = user_root / "user-v1"
    outside_release = tmp_path / "outside/v1"
    for path in [internal_release, user_release, outside_release]:
        path.mkdir(parents=True)

    for target in [internal_release, user_release]:
        result = _run_release_shell(
            "release_resolve_controlled_dir",
            str(target),
            str(internal_root),
            str(user_root),
        )
        assert result.returncode == 0
        assert Path(result.stdout.strip()) == target.resolve()

    rejected = _run_release_shell(
        "release_resolve_controlled_dir",
        str(outside_release),
        str(internal_root),
        str(user_root),
    )
    assert rejected.returncode != 0


def test_web_server_resolution_rejects_parent_traversal(tmp_path: Path) -> None:
    release = tmp_path / "release"
    _write(release / "apps/web/server.js", "// server\n")
    _write(release / "apps/web/WEB_SERVER_PATH", "server.js\n")
    valid = _run_release_shell("release_web_server_path", str(release))
    assert valid.returncode == 0
    assert Path(valid.stdout.strip()) == (release / "apps/web/server.js").resolve()

    _write(release / "apps/web/WEB_SERVER_PATH", "../outside/server.js\n")
    rejected = _run_release_shell("release_web_server_path", str(release))
    assert rejected.returncode != 0


def test_release_api_entrypoints_disable_python_bytecode_writes() -> None:
    entrypoints = [
        ROOT / "scripts/seed-beta/start.sh",
        ROOT / "scripts/seed-beta/supervise.sh",
        ROOT / "scripts/user-beta/start.sh",
        ROOT / "scripts/user-beta/supervise.sh",
    ]

    for entrypoint in entrypoints:
        content = entrypoint.read_text(encoding="utf-8")
        assert "PYTHONDONTWRITEBYTECODE=1" in content, entrypoint
