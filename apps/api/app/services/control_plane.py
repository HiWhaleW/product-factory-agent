from collections import defaultdict

PROJECT_TRANSITIONS: dict[str, set[str]] = {
    "alignment": {"mrd", "killed"},
    "mrd": {"prd", "alignment", "killed"},
    "prd": {"solution_confirmation", "mrd", "killed"},
    "solution_confirmation": {"tech_stack_confirmation", "prd", "killed"},
    "tech_stack_confirmation": {"development_backend", "solution_confirmation", "killed"},
    "development_backend": {"development_frontend", "tech_stack_confirmation"},
    "development_frontend": {"mvp", "development_backend"},
    "mvp": {"internal_acceptance", "development_frontend"},
    "internal_acceptance": {"seed_beta", "development_backend", "development_frontend"},
    "seed_beta": {"brd", "development_backend", "development_frontend", "killed"},
    "brd": {"release_handoff", "seed_beta", "killed"},
    "release_handoff": {"feedback", "development_backend", "development_frontend"},
    "feedback": {"alignment", "completed"},
    "completed": {"alignment"},
    "killed": set(),
}

GATE_REQUIRED_FOR_TARGET = {
    "mrd": "G0",
    "prd": "G1",
    "solution_confirmation": "G2",
    "tech_stack_confirmation": "G3",
    "development_backend": "G4",
    "seed_beta": "G5",
    "release_handoff": "G6",
}

GATE_RULES: dict[str, dict[str, object]] = {
    "G0": {
        "source_state": "alignment",
        "target_state": "mrd",
        "required_artifact_kinds": set(),
    },
    "G1": {
        "source_state": "mrd",
        "target_state": "prd",
        "required_artifact_kinds": {"evidence_index", "mrd", "red_team_review"},
    },
    "G2": {
        "source_state": "prd",
        "target_state": "solution_confirmation",
        "required_artifact_kinds": {"prd", "prd_review"},
    },
    "G3": {
        "source_state": "solution_confirmation",
        "target_state": "tech_stack_confirmation",
        "required_artifact_kinds": {"user_flow", "solution_design", "solution_review"},
    },
    "G4": {
        "source_state": "tech_stack_confirmation",
        "target_state": "development_backend",
        "required_artifact_kinds": {
            "technical_adaptation",
            "api_contract",
            "technical_review",
        },
    },
    "G5": {
        "source_state": "internal_acceptance",
        "target_state": "seed_beta",
        "required_artifact_kinds": {
            "mvp_candidate",
            "qa_report",
            "known_issues",
            "seed_test_plan",
            "telemetry_schema",
        },
    },
    "G6": {
        "source_state": "brd",
        "target_state": "release_handoff",
        "required_artifact_kinds": {
            "seed_test_report",
            "commercial_brd",
            "release_plan",
        },
    },
}

CONTROL_PLANE_EVENT_TYPES = {
    "agent.joined",
    "clarification.answered",
    "clarification.recorded",
    "context.pack_created",
    "context.updated",
    "gate.decided",
    "gate.opened",
    "project.state_changed",
    "project_brief.approved",
    "project_brief.created",
    "project_brief.versioned",
    "factory_lead.invocation.started",
    "factory_lead.invocation.completed",
    "factory_lead.invocation.failed",
    "definition.submitted",
    "definition.reviewed",
    "prd.submitted",
    "prd.reviewed",
    "tool_run.started",
    "tool_run.completed",
    "run.resumed",
    "artifact.created",
    "artifact.versioned",
}


class ControlPlaneError(ValueError):
    def __init__(self, code: str, user_message: str):
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


def validate_transition(current: str, target: str, approved_gate: str | None = None) -> None:
    if target not in PROJECT_TRANSITIONS.get(current, set()):
        raise ControlPlaneError("INVALID_STATE_TRANSITION", f"不能从 {current} 直接进入 {target}。")
    required = GATE_REQUIRED_FOR_TARGET.get(target)
    if required and approved_gate != required:
        raise ControlPlaneError("GATE_REQUIRED", f"进入 {target} 前必须批准 {required}。")


def validate_gate_open(
    *, current_state: str, gate_type: str, target_state: str, context_matches: bool
) -> None:
    rule = GATE_RULES.get(gate_type)
    if rule is None:
        raise ControlPlaneError("GATE_TYPE_UNSUPPORTED", "当前纵向切片只开放 G0-G6。")
    if not context_matches:
        raise ControlPlaneError("STALE_CONTEXT", "Gate 必须绑定项目当前 Context 版本。")
    if rule["source_state"] != current_state:
        raise ControlPlaneError(
            "GATE_SOURCE_STATE_MISMATCH",
            f"{gate_type} 只能在 {rule['source_state']} 状态打开。",
        )
    if rule["target_state"] != target_state:
        raise ControlPlaneError(
            "GATE_TARGET_STATE_MISMATCH",
            f"{gate_type} 的目标状态必须是 {rule['target_state']}。",
        )


def validate_gate_artifact_kinds(gate_type: str, artifact_kinds: set[str]) -> None:
    rule = GATE_RULES.get(gate_type)
    if rule is None:
        raise ControlPlaneError("GATE_TYPE_UNSUPPORTED", "当前纵向切片只开放 G0-G4。")
    missing = set(rule["required_artifact_kinds"]) - artifact_kinds
    if missing:
        raise ControlPlaneError(
            "GATE_EVIDENCE_MISSING",
            f"{gate_type} 缺少退出证据：{', '.join(sorted(missing))}。",
        )


def validate_context_binding(
    *, project_id: str, resource_project_id: str, expected_status: str, actual_status: str
) -> None:
    if project_id != resource_project_id:
        raise ControlPlaneError("CONTEXT_RESOURCE_PROJECT_MISMATCH", "Context 引用跨越了项目边界。")
    if expected_status != "approved" or actual_status != "approved":
        raise ControlPlaneError(
            "CONTEXT_RESOURCE_NOT_APPROVED", "Context Pack 只能绑定已批准的精确资源版本。"
        )


def permission_policy(risk_level: str, stage_allowed: bool) -> str:
    if not stage_allowed or risk_level == "critical":
        return "deny"
    if risk_level in {"medium", "high"}:
        return "ask"
    return "allow"


def validate_task_dependency(
    edges: list[tuple[str, str]], task_id: str, depends_on_task_id: str
) -> None:
    if task_id == depends_on_task_id:
        raise ControlPlaneError("TASK_SELF_DEPENDENCY", "任务不能依赖自身。")

    graph: dict[str, list[str]] = defaultdict(list)
    for source, dependency in edges:
        graph[source].append(dependency)
    graph[task_id].append(depends_on_task_id)

    stack = [depends_on_task_id]
    visited: set[str] = set()
    while stack:
        node = stack.pop()
        if node == task_id:
            raise ControlPlaneError("TASK_DEPENDENCY_CYCLE", "任务依赖会形成环。")
        if node in visited:
            continue
        visited.add(node)
        stack.extend(graph[node])
