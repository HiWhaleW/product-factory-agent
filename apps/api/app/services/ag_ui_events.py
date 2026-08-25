from __future__ import annotations

import json
from typing import Any

from app.domain.models import Event
from app.domain.schemas import EventRead


def project_event_to_ag_ui(event: Event) -> dict[str, Any]:
    """Wrap one persisted control-plane event in AG-UI's CUSTOM event contract."""
    persisted = EventRead.model_validate(event).model_dump(mode="json")
    return {
        "type": "CUSTOM",
        "timestamp": event.created_at.timestamp() * 1_000,
        "name": event.event_type,
        "value": persisted,
    }


def encode_ag_ui_sse(event: Event) -> str:
    payload = project_event_to_ag_ui(event)
    return (
        f"id: {event.sequence}\n"
        "event: ag-ui\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )
