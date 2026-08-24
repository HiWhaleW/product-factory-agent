from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

EXPECTED_ALEMBIC_HEAD = "20260823_0010"
EXPECTED_PROMPT_SHA256 = {
    "ai-pm.prompt.md": "8386405a7f02361ae679f3eb3bab610f9b38f2d1151f9f4fe96e7088138b211f",
    "builder.prompt.md": "ddba17ecf8f2ae91d9bcb11a6f230b458d489ece1f1e623c29da2d8e3d3b05e9",
    "factory-lead.prompt.md": "5ca89c671e8fc479e3dd926e194735ec02aa6cf082f72e9d1d0a2cfa26d8dee4",
    "reviewer.prompt.md": "fe0d315a93a74a23807e80be64691cc52abf9cefb2c16ffe3abd457b3c2a16be",
}
MANIFEST_NAME = "RELEASE-MANIFEST.sha256"
METADATA_NAME = "RELEASE-METADATA.json"
WEB_SERVER_PATH_NAME = "WEB_SERVER_PATH"
ONBOARDING_V1_MARKER = b"product-factory:onboarding:v1"
ONBOARDING_V2_MARKER = b"product-factory:onboarding:v2:"
SANITIZED_BUILD_ROOT = b"/workspace/product-factory"
SANITIZED_HOME = b"/workspace"


class ReleaseBuildError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_manifest_path(path: Path) -> str:
    if path.is_symlink():
        return hashlib.sha256(os.readlink(path).encode()).hexdigest()
    return sha256_file(path)


def _copy_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = {
        name
        for name in names
        if name in {"__pycache__", ".DS_Store"}
        or name.endswith((".pyc", ".pyo", ".map"))
    }
    if Path(directory).name == ".next":
        ignored.update(name for name in names if name in {"cache", "dev"})
    return ignored


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise ReleaseBuildError(f"Required source directory is unavailable: {source.name}")
    shutil.copytree(source, destination, symlinks=True, ignore=_copy_ignore)


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise ReleaseBuildError(f"Required source file is unavailable: {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _relative_files(release_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in release_dir.rglob("*"):
        relative = path.relative_to(release_dir)
        if "\n" in relative.as_posix():
            raise ReleaseBuildError("Release contains a filename with a newline.")
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo", ".map"}:
            raise ReleaseBuildError(f"Release contains a forbidden generated file: {relative}")
        for index, part in enumerate(relative.parts[:-1]):
            if part == ".next" and relative.parts[index + 1] in {"cache", "dev"}:
                raise ReleaseBuildError(
                    f"Release contains a forbidden Next.js directory: {relative}"
                )
        if path.is_symlink():
            link_target = Path(os.readlink(path))
            if link_target.is_absolute():
                raise ReleaseBuildError(f"Release contains an absolute symlink: {relative}")
            resolved_target = (path.parent / link_target).resolve(strict=False)
            try:
                resolved_target.relative_to(release_dir)
            except ValueError as exc:
                raise ReleaseBuildError(f"Release symlink escapes its root: {relative}") from exc
            if not resolved_target.exists():
                raise ReleaseBuildError(f"Release contains a broken symlink: {relative}")
            files.append(path)
            continue
        if not path.is_file() or relative.as_posix() == MANIFEST_NAME:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(release_dir).as_posix())


def _contains_marker(paths: list[Path], marker: bytes) -> bool:
    for path in paths:
        if path.is_symlink():
            continue
        if path.suffix not in {".js", ".json", ".html", ".txt"}:
            continue
        if marker in path.read_bytes():
            return True
    return False


def _verify_prompts(release_dir: Path) -> None:
    prompt_dir = release_dir / "产品工厂Agent" / "spec" / "prompts"
    actual_names = {path.name for path in prompt_dir.glob("*.prompt.md") if path.is_file()}
    if actual_names != set(EXPECTED_PROMPT_SHA256):
        raise ReleaseBuildError("Release must contain exactly the four frozen Agent prompts.")
    for filename, expected_hash in EXPECTED_PROMPT_SHA256.items():
        if sha256_file(prompt_dir / filename) != expected_hash:
            raise ReleaseBuildError(f"Frozen Agent prompt hash changed: {filename}")


def _verify_web_contract(release_dir: Path, files: list[Path]) -> None:
    if _contains_marker(files, ONBOARDING_V1_MARKER):
        raise ReleaseBuildError("Release still contains the retired global onboarding v1 marker.")
    if not _contains_marker(files, ONBOARDING_V2_MARKER):
        raise ReleaseBuildError("Release does not contain the per-user onboarding v2 marker.")
    server_path_file = release_dir / "apps" / "web" / WEB_SERVER_PATH_NAME
    if not server_path_file.is_file():
        raise ReleaseBuildError("Release is missing the standalone Web server path.")
    relative_server = Path(server_path_file.read_text(encoding="utf-8").strip())
    if relative_server.is_absolute() or ".." in relative_server.parts:
        raise ReleaseBuildError("Standalone Web server path escapes the release directory.")
    server_path = release_dir / "apps" / "web" / relative_server
    if not server_path.is_file() or server_path.name != "server.js":
        raise ReleaseBuildError("Standalone Web server is unavailable.")
    required_server_files = server_path.parent / ".next" / "required-server-files.json"
    if not required_server_files.is_file():
        raise ReleaseBuildError("Standalone Web required-server-files metadata is unavailable.")


def _sanitize_next_build_paths(
    release_dir: Path, source_root: Path, web_server_relative: Path
) -> None:
    server_path = release_dir / "apps" / "web" / web_server_relative
    metadata_path = server_path.parent / ".next" / "required-server-files.json"
    if not server_path.is_file() or not metadata_path.is_file():
        raise ReleaseBuildError("Next.js standalone metadata is incomplete.")
    replacements = [
        (str(source_root.resolve()).encode(), SANITIZED_BUILD_ROOT),
        (str(Path.home().resolve()).encode(), SANITIZED_HOME),
    ]
    web_root = release_dir / "apps" / "web"
    for path in web_root.rglob("*"):
        if (
            path.is_symlink()
            or not path.is_file()
            or path.suffix not in {".html", ".js", ".json", ".txt"}
        ):
            continue
        content = path.read_bytes()
        for original, replacement in replacements:
            content = content.replace(original, replacement)
        path.write_bytes(content)
    try:
        json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReleaseBuildError("Sanitized Next.js server metadata is invalid.") from exc


def _verify_migration(release_dir: Path) -> None:
    expected = release_dir / "apps" / "api" / "alembic" / "versions"
    matches = list(expected.glob(f"{EXPECTED_ALEMBIC_HEAD}_*.py"))
    if len(matches) != 1:
        raise ReleaseBuildError(f"Release must contain Alembic head {EXPECTED_ALEMBIC_HEAD}.")
    if not (release_dir / "apps" / "api" / "alembic.ini").is_file():
        raise ReleaseBuildError("Release is missing apps/api/alembic.ini.")


def _scan_for_local_paths(release_dir: Path, files: list[Path], source_root: Path) -> None:
    forbidden_values = {str(source_root.resolve()).encode(), str(Path.home().resolve()).encode()}
    for path in files:
        if path.is_symlink():
            continue
        content = path.read_bytes()
        if any(value and value in content for value in forbidden_values):
            relative = path.relative_to(release_dir)
            raise ReleaseBuildError(f"Release embeds a local machine path: {relative}")


def _write_manifest(release_dir: Path, files: list[Path]) -> None:
    lines = [
        f"{sha256_manifest_path(path)}  {path.relative_to(release_dir).as_posix()}"
        for path in files
    ]
    (release_dir / MANIFEST_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_manifest(release_dir: Path) -> dict[str, str]:
    manifest = release_dir / MANIFEST_NAME
    if not manifest.is_file():
        raise ReleaseBuildError("Release integrity manifest is unavailable.")
    entries: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if separator != "  " or len(digest) != 64 or not relative:
            raise ReleaseBuildError("Release integrity manifest is malformed.")
        if relative in entries:
            raise ReleaseBuildError("Release integrity manifest contains duplicate paths.")
        entries[relative] = digest
    return entries


def verify_release(release_dir: Path) -> None:
    release_dir = release_dir.resolve()
    if not release_dir.is_dir():
        raise ReleaseBuildError("Release directory is unavailable.")
    files = _relative_files(release_dir)
    actual = {
        path.relative_to(release_dir).as_posix(): sha256_manifest_path(path) for path in files
    }
    expected = _read_manifest(release_dir)
    if actual != expected:
        raise ReleaseBuildError("Release integrity manifest does not match packaged files.")
    _verify_prompts(release_dir)
    _verify_web_contract(release_dir, files)
    _verify_migration(release_dir)
    metadata_path = release_dir / METADATA_NAME
    if not metadata_path.is_file():
        raise ReleaseBuildError("Release metadata is unavailable.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("alembic_head") != EXPECTED_ALEMBIC_HEAD:
        raise ReleaseBuildError("Release metadata has the wrong Alembic head.")
    if metadata.get("prompt_sha256") != EXPECTED_PROMPT_SHA256:
        raise ReleaseBuildError("Release metadata has the wrong frozen Prompt hashes.")


def package_release(source_root: Path, release_dir: Path, release_id: str) -> None:
    source_root = source_root.resolve()
    release_dir = release_dir.resolve()
    if not source_root.is_dir():
        raise ReleaseBuildError("Project source root is unavailable.")
    if release_dir.exists():
        raise ReleaseBuildError("Release staging directory already exists.")
    if not release_id.strip() or "/" in release_id or "\n" in release_id:
        raise ReleaseBuildError("Release ID is invalid.")

    web_standalone = source_root / "apps" / "web" / ".next" / "standalone"
    server_candidates = [
        web_standalone / "server.js",
        web_standalone / "apps" / "web" / "server.js",
    ]
    existing_servers = [candidate for candidate in server_candidates if candidate.is_file()]
    if len(existing_servers) != 1:
        raise ReleaseBuildError("Next.js standalone server output is unavailable or ambiguous.")
    web_server_relative = existing_servers[0].relative_to(web_standalone)

    release_dir.mkdir(parents=True)
    _copy_tree(source_root / "apps" / "api" / "app", release_dir / "apps" / "api" / "app")
    _copy_tree(
        source_root / "apps" / "api" / "alembic", release_dir / "apps" / "api" / "alembic"
    )
    _copy_file(
        source_root / "apps" / "api" / "alembic.ini",
        release_dir / "apps" / "api" / "alembic.ini",
    )
    _copy_tree(web_standalone, release_dir / "apps" / "web")

    web_runtime_root = release_dir / "apps" / "web" / web_server_relative.parent
    _copy_tree(
        source_root / "apps" / "web" / ".next" / "static",
        web_runtime_root / ".next" / "static",
    )
    _copy_tree(source_root / "apps" / "web" / "public", web_runtime_root / "public")
    (release_dir / "apps" / "web" / WEB_SERVER_PATH_NAME).write_text(
        web_server_relative.as_posix() + "\n", encoding="utf-8"
    )
    _sanitize_next_build_paths(release_dir, source_root, web_server_relative)

    _copy_tree(
        source_root / "产品工厂Agent" / "spec" / "prompts",
        release_dir / "产品工厂Agent" / "spec" / "prompts",
    )
    for relative in [
        Path("package.json"),
        Path("pnpm-lock.yaml"),
        Path("pnpm-workspace.yaml"),
        Path("pyproject.toml"),
        Path("uv.lock"),
        Path("apps/web/package.json"),
    ]:
        _copy_file(source_root / relative, release_dir / "source" / relative)

    (release_dir / "RELEASE_ID").write_text(release_id + "\n", encoding="utf-8")
    metadata = {
        "schema_version": 1,
        "release_id": release_id,
        "web_output": "standalone",
        "web_server_path": web_server_relative.as_posix(),
        "alembic_head": EXPECTED_ALEMBIC_HEAD,
        "prompt_sha256": EXPECTED_PROMPT_SHA256,
    }
    (release_dir / METADATA_NAME).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    files = _relative_files(release_dir)
    _verify_prompts(release_dir)
    _verify_web_contract(release_dir, files)
    _verify_migration(release_dir)
    _scan_for_local_paths(release_dir, files, source_root)
    _write_manifest(release_dir, files)
    verify_release(release_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or verify a portable Product Factory release."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    package_parser = subparsers.add_parser("package")
    package_parser.add_argument("--source-root", type=Path, required=True)
    package_parser.add_argument("--release-dir", type=Path, required=True)
    package_parser.add_argument("--release-id", required=True)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--release-dir", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "package":
        package_release(args.source_root, args.release_dir, args.release_id)
    else:
        verify_release(args.release_dir)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError, ReleaseBuildError) as exc:
        raise SystemExit(f"Release build failed: {exc}") from exc
