import pytest
from app.services.control_plane import (
    ControlPlaneError,
    permission_policy,
    validate_gate_artifact_kinds,
    validate_gate_open,
    validate_task_dependency,
    validate_transition,
)


def test_gate_required_for_business_transition() -> None:
    with pytest.raises(ControlPlaneError, match="G0"):
        validate_transition("alignment", "mrd")

    validate_transition("alignment", "mrd", "G0")


def test_illegal_stage_skip_is_rejected() -> None:
    with pytest.raises(ControlPlaneError) as error:
        validate_transition("alignment", "development_backend", "G4")
    assert error.value.code == "INVALID_STATE_TRANSITION"


def test_development_is_backend_then_frontend() -> None:
    validate_transition("tech_stack_confirmation", "development_backend", "G4")
    validate_transition("development_backend", "development_frontend")
    validate_transition("development_frontend", "mvp")

    with pytest.raises(ControlPlaneError):
        validate_transition("development_backend", "mvp")


def test_feedback_starts_a_new_iteration_at_alignment() -> None:
    validate_transition("feedback", "alignment")


@pytest.mark.parametrize(
    ("risk", "stage_allowed", "expected"),
    [
        ("low", True, "allow"),
        ("medium", True, "ask"),
        ("high", True, "ask"),
        ("critical", True, "deny"),
        ("low", False, "deny"),
    ],
)
def test_permission_policy_is_deterministic(risk: str, stage_allowed: bool, expected: str) -> None:
    assert permission_policy(risk, stage_allowed) == expected


def test_task_self_dependency_is_rejected() -> None:
    with pytest.raises(ControlPlaneError) as error:
        validate_task_dependency([], "a", "a")
    assert error.value.code == "TASK_SELF_DEPENDENCY"


def test_task_dependency_cycle_is_rejected() -> None:
    edges = [("b", "a"), ("c", "b")]
    with pytest.raises(ControlPlaneError) as error:
        validate_task_dependency(edges, "a", "c")
    assert error.value.code == "TASK_DEPENDENCY_CYCLE"


def test_acyclic_task_dependency_is_allowed() -> None:
    validate_task_dependency([("b", "a")], "c", "b")


def test_g0_g1_gate_source_target_and_context_are_deterministic() -> None:
    validate_gate_open(
        current_state="alignment",
        gate_type="G0",
        target_state="mrd",
        context_matches=True,
    )
    validate_gate_open(
        current_state="mrd",
        gate_type="G1",
        target_state="prd",
        context_matches=True,
    )
    with pytest.raises(ControlPlaneError) as error:
        validate_gate_open(
            current_state="mrd",
            gate_type="G1",
            target_state="solution_confirmation",
            context_matches=True,
        )
    assert error.value.code == "GATE_TARGET_STATE_MISMATCH"
    with pytest.raises(ControlPlaneError) as error:
        validate_gate_open(
            current_state="mrd",
            gate_type="G1",
            target_state="prd",
            context_matches=False,
        )
    assert error.value.code == "STALE_CONTEXT"


def test_g1_requires_evidence_mrd_and_red_team_review() -> None:
    validate_gate_artifact_kinds("G1", {"evidence_index", "mrd", "red_team_review"})
    with pytest.raises(ControlPlaneError) as error:
        validate_gate_artifact_kinds("G1", {"evidence_index", "mrd"})
    assert error.value.code == "GATE_EVIDENCE_MISSING"
