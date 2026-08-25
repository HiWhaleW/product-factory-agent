from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver


class CheckpointArchiveError(RuntimeError):
    pass


def _encoded(serializer, value: Any) -> dict[str, str]:
    kind, payload = serializer.dumps_typed(value)
    return {"kind": kind, "payload": base64.b64encode(payload).decode("ascii")}


def _decoded(serializer, value: dict[str, str]) -> Any:
    return serializer.loads_typed(
        (value["kind"], base64.b64decode(value["payload"].encode("ascii")))
    )


class CheckpointArchive:
    """Durable content archive for the latest LangGraph checkpoint.

    Metadata is recorded by AgentRuntimeService in RunStep. This class stores only opaque,
    hashed checkpoint content under the approved Artifact root.
    """

    def __init__(self, root: Path) -> None:
        if not root.is_absolute() or not root.is_dir():
            raise CheckpointArchiveError("Checkpoint root must be an existing absolute directory.")
        self.root = root.resolve()

    def save(self, saver: BaseCheckpointSaver, config: dict[str, Any]) -> tuple[str, str]:
        checkpoint_tuple = saver.get_tuple(config)
        if checkpoint_tuple is None:
            raise CheckpointArchiveError("LangGraph did not produce a checkpoint.")
        thread_id = str(config["configurable"]["thread_id"])
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", thread_id):
            raise CheckpointArchiveError("Checkpoint thread_id is unsafe.")
        body = {
            "version": 1,
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_tuple.config["configurable"].get("checkpoint_ns", ""),
            "checkpoint": _encoded(saver.serde, checkpoint_tuple.checkpoint),
            "metadata": _encoded(saver.serde, checkpoint_tuple.metadata),
            "pending_writes": [
                {
                    "task_id": task_id,
                    "channel": channel,
                    "value": _encoded(saver.serde, value),
                }
                for task_id, channel, value in checkpoint_tuple.pending_writes
            ],
        }
        payload = json.dumps(body, ensure_ascii=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(payload).hexdigest()
        relative = Path(".runtime-checkpoints") / thread_id / f"{digest}.json"
        target = (self.root / relative).resolve()
        if self.root not in target.parents:
            raise CheckpointArchiveError("Checkpoint path escapes the approved root.")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(target)
        return relative.as_posix(), digest

    def restore(
        self,
        saver: BaseCheckpointSaver,
        config: dict[str, Any],
        *,
        relative_path: str,
        expected_hash: str,
    ) -> dict[str, Any]:
        target = (self.root / relative_path).resolve()
        if self.root not in target.parents or not target.is_file():
            raise CheckpointArchiveError("Checkpoint archive is unavailable.")
        payload = target.read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected_hash:
            raise CheckpointArchiveError("Checkpoint archive hash mismatch.")
        try:
            body = json.loads(payload)
            checkpoint = _decoded(saver.serde, body["checkpoint"])
            metadata = _decoded(saver.serde, body["metadata"])
        except (KeyError, ValueError, TypeError) as exc:
            raise CheckpointArchiveError("Checkpoint archive is malformed.") from exc
        configurable = config["configurable"]
        base_config = {
            "configurable": {
                "thread_id": configurable["thread_id"],
                "checkpoint_ns": body.get("checkpoint_ns", ""),
            }
        }
        restored_config = saver.put(
            base_config,
            checkpoint,
            metadata,
            checkpoint.get("channel_versions") or {},
        )
        grouped: dict[str, list[tuple[str, Any]]] = {}
        for item in body.get("pending_writes") or []:
            grouped.setdefault(item["task_id"], []).append(
                (item["channel"], _decoded(saver.serde, item["value"]))
            )
        for task_id, writes in grouped.items():
            saver.put_writes(restored_config, writes, task_id)
        return restored_config
