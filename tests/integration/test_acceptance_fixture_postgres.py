from __future__ import annotations

import os

import pytest
from app.agents.acceptance_fixture import FIXTURE_PROJECT_ID, reseed_fixture
from app.main import app
from fastapi.testclient import TestClient

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
        reason="set RUN_POSTGRES_INTEGRATION=1 to use the configured PostgreSQL database",
    ),
]


def test_gate_permission_fixture_is_reseedable_and_frontend_readable() -> None:
    first = reseed_fixture()
    second = reseed_fixture()
    assert first["project_id"] == second["project_id"] == FIXTURE_PROJECT_ID
    assert first["gate"]["id"] != second["gate"]["id"]
    assert first["permission"]["id"] != second["permission"]["id"]
    with TestClient(app) as client:
        gates = client.get(
            f"/api/v1/projects/{FIXTURE_PROJECT_ID}/gates?status=open"
        )
        permissions = client.get(
            f"/api/v1/projects/{FIXTURE_PROJECT_ID}/permissions?status=open"
        )
        events = client.get(
            f"/api/v1/projects/{FIXTURE_PROJECT_ID}/events?cursor=0"
        )
        execution = client.get(
            f"/api/v1/projects/{FIXTURE_PROJECT_ID}/execution"
        )
    assert gates.status_code == permissions.status_code == events.status_code == 200
    assert len(gates.json()) == 1
    assert len(permissions.json()) == 1
    assert permissions.json()[0]["redacted_parameters"]["fixture"] is True
    event_types = [event["event_type"] for event in events.json()]
    assert "run.waiting" in event_types
    assert "run.resumed" in event_types
    assert "tool_run.started" in event_types
    assert "tool_run.completed" in event_types
    assert not [
        task
        for task in execution.json()["tasks"]
        if task["assigned_agent"] == "builder"
    ]

