import json
from datetime import UTC, datetime

from app.domain.models import Event
from app.services.ag_ui_events import encode_ag_ui_sse, project_event_to_ag_ui


def persisted_event() -> Event:
    return Event(
        id="event-1",
        project_id="project-1",
        sequence=17,
        event_type="artifact.created",
        payload={"artifact_id": "artifact-1"},
        created_at=datetime(2026, 8, 23, tzinfo=UTC),
    )


def test_persisted_project_event_uses_ag_ui_custom_envelope() -> None:
    envelope = project_event_to_ag_ui(persisted_event())

    assert envelope["type"] == "CUSTOM"
    assert envelope["name"] == "artifact.created"
    assert envelope["value"]["sequence"] == 17
    assert envelope["value"]["id"] == "event-1"


def test_sse_id_is_the_persisted_sequence_for_resume() -> None:
    encoded = encode_ag_ui_sse(persisted_event())
    data_line = next(line for line in encoded.splitlines() if line.startswith("data: "))

    assert encoded.startswith("id: 17\nevent: ag-ui\n")
    assert json.loads(data_line.removeprefix("data: "))["value"]["sequence"] == 17
