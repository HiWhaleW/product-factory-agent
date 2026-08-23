import asyncio
from datetime import UTC, datetime

import pytest
from app.adapters.bocha import BochaSearchResponse, BochaSearchResult, BochaTimeoutError
from app.adapters.deepseek import DeepSeekResponse, DeepSeekSchemaError, DeepSeekUsage
from app.agents.builder_contracts import BuilderCodexOutput
from app.agents.checkpoint import CheckpointArchive
from app.agents.context import ApprovedContextPack, ContextBoundaryError
from app.agents.graph import _research_query, build_agent_graph
from app.agents.outputs import (
    AiPmMrdOutput,
    AiPmPrdOutput,
    BuilderSolutionOutput,
    BuilderTechnicalOutput,
    ReviewerMrdOutput,
    ReviewerPrdOutput,
    ReviewerSolutionOutput,
    ReviewerTechnicalOutput,
)
from app.agents.policy import ToolRequest, evaluate_tool_policy
from app.agents.registry import (
    AgentRegistryError,
    load_frozen_prompt,
    require_d5_agent,
    require_runtime_agent,
)
from app.domain.schemas import ContextPackRead, ContextResourceRef
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


def control_pack(*, agent_id: str = "factory-lead", policy: dict | None = None):
    return ContextPackRead(
        id="pack-1",
        project_id="project-1",
        context_version=2,
        stage="alignment" if agent_id == "factory-lead" else "mrd",
        approval_status="approved",
        recipient_agent_id=agent_id,
        primary_resource=ContextResourceRef(
            resource_type="project_brief",
            resource_id="brief-1",
            version=1,
        ),
        required_resources=[],
        task="对齐项目并输出结构化结果。",
        policy=policy
        or {
            "allowed_capability_ids": ["CAP-01"],
            "forbidden_actions": ["advance_project_state", "approve_gate"],
            "budget": {"max_turns": 3, "max_retries": 1, "timeout_seconds": 30},
        },
        created_at=datetime.now(UTC),
    )


def runtime_pack(**kwargs) -> ApprovedContextPack:
    return ApprovedContextPack.from_control_plane(control_pack(**kwargs))


def initial_state(pack: ApprovedContextPack) -> dict:
    return {
        "run_id": "run-1",
        "agent_id": pack.recipient_agent_id,
        "stage": pack.stage,
        "context_pack": pack.model_dump(mode="json"),
        "approved_materials": [
            {
                "resource_type": "project_brief",
                "resource_id": "brief-1",
                "version": 1,
                "objective": "验证 Runtime",
            }
        ],
        "review_candidates": [],
        "user_input": "我要做一个销售复盘 Agent。",
        "turns_used": 0,
        "retries_used": 0,
        "tool_calls_used": 0,
        "status": "queued",
    }


class FakeProvider:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    async def complete(self, messages, **kwargs):
        output = self.outputs[self.calls]
        self.calls += 1
        if isinstance(output, Exception):
            raise output
        model = kwargs["response_model"]
        validated = model.model_validate(output)
        return DeepSeekResponse(
            model="deepseek-test",
            content=None,
            finish_reason="stop",
            usage=DeepSeekUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            structured_output=validated.model_dump(mode="json"),
        )


class FakeResearchProvider:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0
        self.queries = []

    async def search(self, query, **kwargs):
        self.queries.append(query)
        output = self.outputs[self.calls]
        self.calls += 1
        if isinstance(output, Exception):
            raise output
        return output


def factory_output(*, tool_request=None) -> dict:
    return {
        "message": "需要先确认目标用户。",
        "identity_event": None,
        "tool_request": tool_request,
        "artifact_proposals": [],
        "gate_request": None,
        "transition_proposal": None,
        "open_questions": ["目标用户是谁？"],
    }


def research_pack() -> ApprovedContextPack:
    return runtime_pack(
        agent_id="ai-pm",
        policy={
            "allowed_capability_ids": ["CAP-02", "CAP-12"],
            "forbidden_actions": ["advance_project_state", "approve_gate"],
            "budget": {
                "max_turns": 3,
                "max_retries": 1,
                "timeout_seconds": 30,
                "max_tool_calls": 3,
            },
        },
    )


def reviewer_pack() -> ApprovedContextPack:
    return runtime_pack(
        agent_id="reviewer",
        policy={
            "input_contract": "definition-review/v1",
            "definition_submission_id": "submission-1",
            "allowed_capability_ids": ["CAP-10"],
            "forbidden_actions": ["advance_project_state", "approve_gate"],
            "budget": {
                "max_turns": 3,
                "max_retries": 1,
                "timeout_seconds": 30,
                "max_tool_calls": 0,
            },
        },
    )


def reviewer_state() -> dict:
    state = initial_state(reviewer_pack())
    state["review_candidates"] = [
        {
            "resource_type": "review_candidate_artifact",
            "review_status": "waiting_reviewer",
            "submission_id": "submission-1",
            "kind": "mrd",
            "evidence_refs": [f"bocha:web:{'a' * 64}"],
            "content": "待审 MRD 正文",
        }
    ]
    return state


def research_response() -> BochaSearchResponse:
    return BochaSearchResponse(
        provider_request_id="bocha-request-1",
        query="AI Agent 市场调研",
        total_estimated_matches=10,
        results=[
            BochaSearchResult(
                evidence_ref=f"bocha:web:{'a' * 64}",
                title="官方市场报告",
                url="https://example.com/report",
                site_name="Example",
                snippet="可追溯摘要",
                summary="官方报告摘要",
                date_published="2026-08-20T00:00:00+08:00",
            )
        ],
    )


def ai_pm_output() -> dict:
    evidence_ref = f"bocha:web:{'a' * 64}"
    return {
        "message": "已形成可追溯 Evidence Index 候选。",
        "artifact_proposals": [
            {
                "kind": "evidence_index",
                "title": "Evidence Index",
                "content": f"市场证据索引 {evidence_ref}",
                "evidence_refs": [evidence_ref],
                "assumptions": [],
                "status": "waiting_review",
            },
            {
                "kind": "mrd",
                "title": "MRD",
                "content": f"可追溯市场需求草案 {evidence_ref}",
                "evidence_refs": [evidence_ref],
                "assumptions": [],
                "status": "waiting_review",
            },
        ],
        "verified_fact_proposals": [],
        "open_questions": [],
        "transition_proposal": None,
    }


def test_ai_pm_mrd_schema_rejects_generic_or_incomplete_artifacts() -> None:
    valid = ai_pm_output()
    generic = {
        **valid,
        "artifact_proposals": [{**valid["artifact_proposals"][0], "kind": "markdown"}],
    }
    incomplete = {**valid, "artifact_proposals": [valid["artifact_proposals"][0]]}
    duplicate = {
        **valid,
        "artifact_proposals": [
            valid["artifact_proposals"][0],
            valid["artifact_proposals"][0],
            valid["artifact_proposals"][1],
        ],
    }

    with pytest.raises(ValueError):
        AiPmMrdOutput.model_validate(generic)
    with pytest.raises(ValueError):
        AiPmMrdOutput.model_validate(incomplete)
    with pytest.raises(ValueError):
        AiPmMrdOutput.model_validate(duplicate)
    malformed_ref = {
        **valid,
        "artifact_proposals": [
            {**valid["artifact_proposals"][0], "evidence_refs": ["fabricated"]},
            valid["artifact_proposals"][1],
        ],
    }
    with pytest.raises(ValueError):
        AiPmMrdOutput.model_validate(malformed_ref)
    assert {item.kind for item in AiPmMrdOutput.model_validate(valid).artifact_proposals} == {
        "evidence_index",
        "mrd",
    }


def reviewer_mrd_output() -> dict:
    evidence_ref = f"bocha:web:{'a' * 64}"
    return {
        "message": "MRD 证据充分性存在已记录风险。",
        "verdict": "pass_with_known_issues",
        "findings": [
            {
                "severity": "P2",
                "title": "需要持续核验来源时效性",
                "evidence_refs": [evidence_ref],
                "reproduction": ["打开 Evidence Index 对照发布时间"],
                "impact": "可能影响趋势判断时效性。",
                "recommended_fix": "G1 前由用户确认可接受时间窗口。",
            }
        ],
        "evidence_refs": [evidence_ref],
        "artifact_proposals": [
            {
                "kind": "red_team_review",
                "title": "MRD Red Team Review",
                "content": f"独立审查报告 {evidence_ref}",
                "evidence_refs": [evidence_ref],
                "assumptions": [],
                "status": "waiting_review",
            }
        ],
        "transition_proposal": None,
    }


def test_reviewer_mrd_schema_requires_one_evidence_backed_red_team_review() -> None:
    valid = reviewer_mrd_output()
    assert ReviewerMrdOutput.model_validate(valid).artifact_proposals[0].kind == ("red_team_review")
    with pytest.raises(ValueError):
        ReviewerMrdOutput.model_validate({**valid, "artifact_proposals": []})
    with pytest.raises(ValueError):
        ReviewerMrdOutput.model_validate({**valid, "evidence_refs": []})
    with pytest.raises(ValueError):
        ReviewerMrdOutput.model_validate(
            {
                **valid,
                "artifact_proposals": [{**valid["artifact_proposals"][0], "kind": "markdown"}],
            }
        )


def test_reviewer_uses_bound_review_candidates_not_approved_materials() -> None:
    provider = FakeProvider([reviewer_mrd_output()])
    graph = build_agent_graph(provider)

    completed = asyncio.run(
        graph.ainvoke(
            reviewer_state(),
            {"configurable": {"thread_id": "review-candidate-provenance"}},
        )
    )

    assert completed["status"] == "succeeded"
    assert provider.calls == 1


def test_reviewer_fabricated_candidate_ref_retries_then_hands_back() -> None:
    fabricated = reviewer_mrd_output()
    fabricated_ref = f"bocha:web:{'f' * 64}"
    fabricated["evidence_refs"] = [fabricated_ref]
    fabricated["findings"][0]["evidence_refs"] = [fabricated_ref]
    fabricated["artifact_proposals"][0]["evidence_refs"] = [fabricated_ref]
    fabricated["artifact_proposals"][0]["content"] = f"独立审查报告 {fabricated_ref}"
    provider = FakeProvider([fabricated, fabricated])
    graph = build_agent_graph(provider)

    completed = asyncio.run(
        graph.ainvoke(
            reviewer_state(),
            {"configurable": {"thread_id": "review-candidate-fabricated"}},
        )
    )

    assert completed["status"] == "waiting_human"
    assert completed["error_code"] == "DEEPSEEK_SCHEMA_INVALID"
    assert completed["retries_used"] == 2
    assert f"bocha:web:{'a' * 64}" in completed["validation_feedback"]
    assert fabricated_ref in completed["validation_feedback"]
    assert provider.calls == 2


def prd_pack(agent_id: str) -> ApprovedContextPack:
    return ApprovedContextPack(
        id=f"{agent_id}-prd-pack",
        project_id="project-1",
        context_version=3,
        stage="prd",
        approval_status="approved",
        recipient_agent_id=agent_id,
        primary_resource=ContextResourceRef(
            resource_type="artifact",
            resource_id="11111111-1111-1111-1111-111111111111",
            version=2,
            approval_status="approved",
        ),
        required_resources=[],
        task="基于已批准 MRD 形成并审查 PRD。",
        allowed_capability_ids=["CAP-04" if agent_id == "ai-pm" else "CAP-10"],
        forbidden_actions=["approve_gate", "start_builder"],
        budget={"max_turns": 3, "max_retries": 1, "timeout_seconds": 30},
    )


def ai_pm_prd_output() -> dict:
    ref = "artifact:11111111-1111-1111-1111-111111111111:v2"
    return {
        "message": "已形成待独立审查的 PRD。",
        "artifact_proposals": [
            {
                "kind": "prd",
                "title": "销售复盘 Agent PRD",
                "content": f"核心闭环、范围、验收与反指标。来源：{ref}",
                "evidence_refs": [ref],
                "assumptions": ["引用粒度需真实访谈验证"],
                "status": "waiting_review",
            }
        ],
        "verified_fact_proposals": [],
        "open_questions": [],
        "transition_proposal": None,
    }


def reviewer_prd_output() -> dict:
    ref = "artifact:22222222-2222-2222-2222-222222222222:v1"
    return {
        "message": "PRD 可进入 G2，保留 P2。",
        "verdict": "pass_with_known_issues",
        "findings": [
            {
                "severity": "P2",
                "title": "引用粒度仍需访谈验证",
                "evidence_refs": [ref],
                "reproduction": ["检查 PRD 已知问题章节"],
                "impact": "不阻断 G2，但影响证据精度。",
                "recommended_fix": "种子访谈中补齐。",
            }
        ],
        "evidence_refs": [ref],
        "artifact_proposals": [
            {
                "kind": "prd_review",
                "title": "PRD Review",
                "content": f"独立审查结论与已知问题。候选：{ref}",
                "evidence_refs": [ref],
                "assumptions": [],
                "status": "waiting_review",
            }
        ],
        "transition_proposal": None,
    }


def test_prd_schemas_are_stage_specific_and_do_not_propose_gate_transition() -> None:
    assert AiPmPrdOutput.model_validate(ai_pm_prd_output()).artifact_proposals[0].kind == "prd"
    assert (
        ReviewerPrdOutput.model_validate(reviewer_prd_output()).artifact_proposals[0].kind
        == "prd_review"
    )
    invalid = ai_pm_prd_output()
    invalid["artifact_proposals"][0]["kind"] = "mrd"
    with pytest.raises(ValueError):
        AiPmPrdOutput.model_validate(invalid)


def test_ai_pm_prd_uses_only_approved_artifact_refs() -> None:
    pack = prd_pack("ai-pm")
    state = initial_state(pack)
    state["approved_materials"] = [
        {
            "resource_type": "artifact",
            "artifact_ref": "artifact:11111111-1111-1111-1111-111111111111:v2",
            "content": "已批准 MRD",
        }
    ]
    provider = FakeProvider([ai_pm_prd_output()])
    completed = asyncio.run(
        build_agent_graph(provider).ainvoke(
            state,
            {"configurable": {"thread_id": "ai-pm-prd-provenance"}},
        )
    )
    assert completed["status"] == "succeeded"


def test_reviewer_prd_uses_bound_candidate_ref() -> None:
    pack = prd_pack("reviewer")
    state = initial_state(pack)
    state["review_candidates"] = [
        {
            "artifact_ref": "artifact:22222222-2222-2222-2222-222222222222:v1",
            "evidence_refs": [],
            "content": "待审 PRD",
        }
    ]
    provider = FakeProvider([reviewer_prd_output()])
    completed = asyncio.run(
        build_agent_graph(provider).ainvoke(
            state,
            {"configurable": {"thread_id": "reviewer-prd-provenance"}},
        )
    )
    assert completed["status"] == "succeeded"


def test_registry_loads_frozen_prompts_and_builder_is_inactive() -> None:
    prompt, prompt_hash = load_frozen_prompt("factory-lead")
    assert "Factory Lead System Prompt v0.2" in prompt
    assert len(prompt_hash) == 64
    with pytest.raises(AgentRegistryError, match="cannot execute"):
        require_d5_agent("builder", "development_backend")
    assert require_runtime_agent("builder", "solution_confirmation").id == "builder"
    with pytest.raises(AgentRegistryError, match="cannot develop before G4"):
        require_runtime_agent("builder", "development_backend")


def test_solution_output_contracts_require_documents_and_forbid_tools() -> None:
    prd_ref = "artifact:11111111-1111-1111-1111-111111111111:v1"
    flow_ref = "artifact:22222222-2222-2222-2222-222222222222:v1"
    design_ref = "artifact:33333333-3333-3333-3333-333333333333:v1"
    builder = BuilderSolutionOutput.model_validate(
        {
            "message": "仅提交方案，不写代码。",
            "technical_decisions": [],
            "tool_requests": [],
            "artifact_proposals": [
                {
                    "kind": "user_flow",
                    "title": "User Flow",
                    "content": f"来源：{prd_ref}",
                    "evidence_refs": [prd_ref],
                },
                {
                    "kind": "solution_design",
                    "title": "方案说明",
                    "content": f"来源：{prd_ref}",
                    "evidence_refs": [prd_ref],
                },
            ],
            "test_results": [],
            "known_issues": [],
            "gate_request": None,
            "transition_proposal": None,
        }
    )
    assert {item.kind for item in builder.artifact_proposals} == {
        "user_flow",
        "solution_design",
    }
    reviewer = ReviewerSolutionOutput.model_validate(
        {
            "message": "方案可进入 G3。",
            "verdict": "pass",
            "findings": [],
            "evidence_refs": [flow_ref, design_ref],
            "artifact_proposals": [
                {
                    "kind": "solution_review",
                    "title": "Solution Review",
                    "content": f"User Flow：{flow_ref}；方案：{design_ref}",
                    "evidence_refs": [flow_ref, design_ref],
                }
            ],
            "transition_proposal": None,
        }
    )
    assert reviewer.verdict == "pass"


def test_technical_output_contracts_require_documents_and_forbid_tools() -> None:
    source_ref = "artifact:11111111-1111-1111-1111-111111111111:v1"
    adaptation_ref = "artifact:22222222-2222-2222-2222-222222222222:v1"
    api_ref = "artifact:33333333-3333-3333-3333-333333333333:v1"
    builder = BuilderTechnicalOutput.model_validate(
        {
            "message": "仅提交技术定义，不写代码。",
            "technical_decisions": [],
            "tool_requests": [],
            "artifact_proposals": [
                {
                    "kind": "technical_adaptation",
                    "title": "Technical Adaptation",
                    "content": f"来源：{source_ref}",
                    "evidence_refs": [source_ref],
                },
                {
                    "kind": "api_contract",
                    "title": "API Contract",
                    "content": f"来源：{source_ref}",
                    "evidence_refs": [source_ref],
                },
            ],
            "test_results": [],
            "known_issues": [],
            "gate_request": None,
            "transition_proposal": None,
        }
    )
    assert {item.kind for item in builder.artifact_proposals} == {
        "technical_adaptation",
        "api_contract",
    }
    reviewer = ReviewerTechnicalOutput.model_validate(
        {
            "message": "技术定义可进入 G4。",
            "verdict": "pass",
            "findings": [],
            "evidence_refs": [adaptation_ref, api_ref],
            "artifact_proposals": [
                {
                    "kind": "technical_review",
                    "title": "Technical Review",
                    "content": f"适配：{adaptation_ref}；API：{api_ref}",
                    "evidence_refs": [adaptation_ref, api_ref],
                }
            ],
            "transition_proposal": None,
        }
    )
    assert reviewer.verdict == "pass"


def test_context_pack_rejects_secret_values_and_unapproved_versions() -> None:
    bad_policy = {"api_key": "must-not-enter-context"}
    with pytest.raises(ContextBoundaryError, match="forbidden field"):
        ApprovedContextPack.from_control_plane(control_pack(policy=bad_policy))

    pack = control_pack()
    pack.approval_status = "draft"
    with pytest.raises(ValueError, match="only approved"):
        ApprovedContextPack.from_control_plane(pack)


def test_tool_policy_returns_allow_ask_and_deny() -> None:
    pack = runtime_pack()
    allow = evaluate_tool_policy(
        agent_id="factory-lead",
        stage="alignment",
        context_pack=pack,
        request=ToolRequest(tool_id="project_fs_read", parameters={}, side_effect="none"),
        tool_calls_used=0,
    )
    ask = evaluate_tool_policy(
        agent_id="factory-lead",
        stage="alignment",
        context_pack=pack,
        request=ToolRequest(tool_id="send_email", parameters={}, side_effect="external-write"),
        tool_calls_used=0,
    )
    deny = evaluate_tool_policy(
        agent_id="factory-lead",
        stage="alignment",
        context_pack=pack,
        request=ToolRequest(tool_id="approve_gate", parameters={}, side_effect="none"),
        tool_calls_used=0,
    )
    assert (allow.outcome, ask.outcome, deny.outcome) == ("allow", "ask", "deny")


def test_langgraph_retries_schema_once_and_stops_with_structured_output() -> None:
    provider = FakeProvider([DeepSeekSchemaError("invalid"), factory_output()])
    graph = build_agent_graph(provider)
    result = asyncio.run(
        graph.ainvoke(initial_state(runtime_pack()), {"configurable": {"thread_id": "retry"}})
    )
    assert result["status"] == "succeeded"
    assert result["retries_used"] == 1
    assert result["turns_used"] == 2
    assert result["observed_model"] == "deepseek-test"
    assert provider.calls == 2


def test_langgraph_checkpoint_pause_and_resume_permission() -> None:
    provider = FakeProvider(
        [
            factory_output(
                tool_request={
                    "tool_id": "send_email",
                    "reason": "需要外发",
                    "parameters": {"recipient": "redacted@example.invalid"},
                    "side_effect": "external-write",
                }
            )
        ]
    )
    graph = build_agent_graph(provider)
    config = {"configurable": {"thread_id": "permission"}}
    first = asyncio.run(graph.ainvoke(initial_state(runtime_pack()), config))
    assert first["__interrupt__"][0].value["kind"] == "permission_request"
    snapshot = graph.get_state(config)
    assert snapshot.next == ("policy",)

    resumed = asyncio.run(graph.ainvoke(Command(resume={"decision": "deny"}), config))
    assert resumed["status"] == "failed"
    assert resumed["error_code"] == "PERMISSION_DENIED"
    assert provider.calls == 1


def test_checkpoint_archive_restores_interrupt_into_new_runtime(tmp_path) -> None:
    provider = FakeProvider(
        [
            factory_output(
                tool_request={
                    "tool_id": "send_email",
                    "reason": "需要外发",
                    "parameters": {"recipient": "redacted@example.invalid"},
                    "side_effect": "external-write",
                }
            )
        ]
    )
    first_saver = InMemorySaver()
    first_graph = build_agent_graph(provider, checkpointer=first_saver)
    config = {"configurable": {"thread_id": "durable-resume"}}
    interrupted = asyncio.run(first_graph.ainvoke(initial_state(runtime_pack()), config))
    assert "__interrupt__" in interrupted

    archive = CheckpointArchive(tmp_path)
    relative_path, digest = archive.save(first_saver, config)

    restored_saver = InMemorySaver()
    restored_config = archive.restore(
        restored_saver,
        config,
        relative_path=relative_path,
        expected_hash=digest,
    )
    restored_graph = build_agent_graph(provider, checkpointer=restored_saver)
    resumed = asyncio.run(
        restored_graph.ainvoke(Command(resume={"decision": "deny"}), restored_config)
    )
    assert resumed["status"] == "failed"
    assert resumed["error_code"] == "PERMISSION_DENIED"
    assert provider.calls == 1


def test_ai_pm_research_is_ask_then_runs_bocha_after_permission() -> None:
    model = FakeProvider([ai_pm_output()])
    research = FakeResearchProvider([research_response()])
    graph = build_agent_graph(model, research_provider=research)
    config = {"configurable": {"thread_id": "ai-pm-research"}}

    waiting = asyncio.run(graph.ainvoke(initial_state(research_pack()), config))

    assert waiting["__interrupt__"][0].value["tool_id"] == "web_research"
    assert "query_sha256" in waiting["__interrupt__"][0].value["parameters"]
    assert research.calls == model.calls == 0

    completed = asyncio.run(graph.ainvoke(Command(resume={"decision": "allow"}), config))

    assert completed["status"] == "succeeded"
    assert completed["tool_calls_used"] == 1
    assert completed["tool_results"][0]["provider"] == "bocha"
    assert completed["output"]["artifact_proposals"][0]["evidence_refs"] == [
        f"bocha:web:{'a' * 64}"
    ]
    assert research.calls == model.calls == 1


def test_ai_pm_uses_explicit_research_query_without_sending_task_instructions() -> None:
    query = "official sales conversation intelligence transcript coaching CRM"
    state = initial_state(research_pack())
    state["user_input"] = f"Research query: {query}\n任务说明：生成 MRD，不得推进 Gate。"
    model = FakeProvider([ai_pm_output()])
    research = FakeResearchProvider([research_response()])
    graph = build_agent_graph(model, research_provider=research)
    config = {"configurable": {"thread_id": "ai-pm-explicit-query"}}

    waiting = asyncio.run(graph.ainvoke(state, config))
    assert waiting["__interrupt__"][0].value["parameters"]["query_sha256"] == _hash_for_test(query)

    completed = asyncio.run(graph.ainvoke(Command(resume={"decision": "allow"}), config))
    assert completed["status"] == "succeeded"
    assert research.queries == [query]


def _hash_for_test(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def test_research_query_falls_back_to_full_input() -> None:
    assert _research_query("销售复盘 Agent") == "销售复盘 Agent"


def test_ai_pm_research_permission_denial_never_calls_provider() -> None:
    model = FakeProvider([])
    research = FakeResearchProvider([])
    graph = build_agent_graph(model, research_provider=research)
    config = {"configurable": {"thread_id": "ai-pm-deny"}}
    asyncio.run(graph.ainvoke(initial_state(research_pack()), config))

    denied = asyncio.run(graph.ainvoke(Command(resume={"decision": "deny"}), config))

    assert denied["status"] == "failed"
    assert denied["error_code"] == "PERMISSION_DENIED"
    assert research.calls == model.calls == 0


def test_ai_pm_research_timeout_retries_once_then_succeeds() -> None:
    model = FakeProvider([ai_pm_output()])
    research = FakeResearchProvider([BochaTimeoutError("timeout"), research_response()])
    graph = build_agent_graph(model, research_provider=research)
    config = {"configurable": {"thread_id": "ai-pm-retry"}}
    asyncio.run(graph.ainvoke(initial_state(research_pack()), config))

    completed = asyncio.run(graph.ainvoke(Command(resume={"decision": "allow"}), config))

    assert completed["status"] == "succeeded"
    assert completed["research_retries_used"] == 1
    assert completed["tool_calls_used"] == 2
    assert research.calls == 2


def test_ai_pm_fabricated_evidence_ref_retries_model_without_repeating_search() -> None:
    fabricated = ai_pm_output()
    for artifact in fabricated["artifact_proposals"]:
        fabricated_ref = f"bocha:web:{'f' * 64}"
        artifact["evidence_refs"] = [fabricated_ref]
        artifact["content"] = f"伪造证据 {fabricated_ref}"
    model = FakeProvider([fabricated, ai_pm_output()])
    research = FakeResearchProvider([research_response()])
    graph = build_agent_graph(model, research_provider=research)
    config = {"configurable": {"thread_id": "ai-pm-provenance"}}
    asyncio.run(graph.ainvoke(initial_state(research_pack()), config))

    completed = asyncio.run(graph.ainvoke(Command(resume={"decision": "allow"}), config))

    assert completed["status"] == "succeeded"
    assert completed["turns_used"] == 2
    assert completed["retries_used"] == 1
    assert research.calls == 1
    assert model.calls == 2


def test_builder_codex_output_schema_requires_every_declared_property() -> None:
    schema = BuilderCodexOutput.model_json_schema()

    def assert_strict_object(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                assert_strict_object(item)
            return
        if not isinstance(node, dict):
            return
        properties = node.get("properties")
        if isinstance(properties, dict):
            assert set(node.get("required") or []) == set(properties)
            assert node.get("additionalProperties") is False
        for value in node.values():
            assert_strict_object(value)

    assert_strict_object(schema)
