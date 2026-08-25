from __future__ import annotations

import hashlib
import os
from pathlib import Path


class ArtifactStoreError(ValueError):
    pass


def resolve_artifact_file(root: Path, content_ref: str) -> Path:
    root = root.resolve(strict=True)
    reference = Path(content_ref)
    if reference.is_absolute():
        raise ArtifactStoreError("Artifact content_ref must be relative to ARTIFACT_ROOT")
    candidate = (root / reference).resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise ArtifactStoreError("Artifact content_ref escapes ARTIFACT_ROOT")
    try:
        candidate = candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise ArtifactStoreError("Artifact content file does not exist") from error
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ArtifactStoreError("Artifact content_ref escapes ARTIFACT_ROOT")
    return candidate


def read_verified_artifact(
    root: Path,
    content_ref: str,
    expected_hash: str,
    max_bytes: int = 2_000_000,
) -> tuple[Path, str]:
    path = resolve_artifact_file(root, content_ref)
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise ArtifactStoreError("Artifact content exceeds the preview size limit")
    actual_hash = hashlib.sha256(data).hexdigest()
    if actual_hash != expected_hash:
        raise ArtifactStoreError("Artifact content hash does not match its immutable version")
    try:
        return path, data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ArtifactStoreError("Artifact preview currently supports UTF-8 text only") from error


def write_immutable_artifact(
    root: Path,
    *,
    project_id: str,
    kind: str,
    content: str,
    max_bytes: int = 2_000_000,
) -> tuple[str, str]:
    """Write content once under ARTIFACT_ROOT and return a relative ref plus sha256."""
    root = root.resolve(strict=True)
    data = content.encode("utf-8")
    if not data or len(data) > max_bytes:
        raise ArtifactStoreError("Artifact content must contain between 1 and 2000000 bytes")
    safe_parts = (project_id, kind)
    if any(not part or part in {".", ".."} or "/" in part or "\\" in part for part in safe_parts):
        raise ArtifactStoreError("Artifact storage identity is invalid")
    digest = hashlib.sha256(data).hexdigest()
    directory = (root / "d5" / project_id / kind).resolve(strict=False)
    if not directory.is_relative_to(root):
        raise ArtifactStoreError("Artifact storage path escapes ARTIFACT_ROOT")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{digest}.md"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = path.read_bytes()
        if existing != data:
            raise ArtifactStoreError(
                "Immutable Artifact content hash collision"
            ) from None
    else:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    return path.relative_to(root).as_posix(), digest
