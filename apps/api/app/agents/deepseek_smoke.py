from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.deepseek import (
    DeepSeekAdapter,
    DeepSeekContextTooLongError,
    DeepSeekError,
    DeepSeekMessage,
    DeepSeekTimeoutError,
)
from app.core.config import get_settings


class SmokeBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str
    target_user: str
    open_questions: list[str] = Field(max_length=3)


class SmokeCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["pass", "fail", "blocked", "not_observed"]
    latency_ms: int
    provider_request_id: str | None = None
    response_sha256: str | None = None
    output_chars: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_cny: float | None = None
    error_code: str | None = None
    note: str


class DeepSeekSmokeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    provider: Literal["deepseek"] = "deepseek"
    model: str
    base_url_origin: str
    secret_ref: str
    secret_present: bool = True
    prompts_recorded: bool = False
    outputs_recorded: bool = False
    cases: list[SmokeCase]


CaseRunner = Callable[[], Awaitable[SmokeCase]]


def _hash_text(value: str | None) -> str | None:
    return hashlib.sha256((value or "").encode()).hexdigest() if value is not None else None


def _case_from_response(name: str, started: float, response, note: str) -> SmokeCase:
    return SmokeCase(
        name=name,
        status="pass",
        latency_ms=round((time.perf_counter() - started) * 1000),
        provider_request_id=response.provider_request_id,
        response_sha256=_hash_text(response.content),
        output_chars=len(response.content or ""),
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        total_tokens=response.usage.total_tokens,
        estimated_cost_cny=response.usage.estimated_cost_cny,
        note=f"{note} Observed response model={response.model}.",
    )


async def run_deepseek_smoke() -> DeepSeekSmokeReport:
    settings = get_settings()
    adapter = DeepSeekAdapter.from_settings(settings)
    cases: list[SmokeCase] = []

    async def authentication_network() -> SmokeCase:
        started = time.perf_counter()
        response = await adapter.complete(
            [DeepSeekMessage(role="user", content="只回复：OK")],
            max_tokens=8,
        )
        return _case_from_response(
            "authentication_network",
            started,
            response,
            "Official endpoint accepted the configured SecretRef and returned a completion.",
        )

    async def streaming() -> SmokeCase:
        started = time.perf_counter()
        deltas: list[str] = []
        usage = None
        request_id = None
        model = None
        async for chunk in adapter.stream(
            [DeepSeekMessage(role="user", content="用一句中文说明流式输出。")],
            max_tokens=80,
        ):
            deltas.append(chunk.content_delta)
            usage = chunk.usage or usage
            request_id = chunk.provider_request_id or request_id
            model = chunk.model or model
        content = "".join(deltas)
        if len([delta for delta in deltas if delta]) < 2:
            raise RuntimeError("stream did not contain multiple content deltas")
        return SmokeCase(
            name="streaming",
            status="pass",
            latency_ms=round((time.perf_counter() - started) * 1000),
            provider_request_id=request_id,
            response_sha256=_hash_text(content),
            output_chars=len(content),
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
            estimated_cost_cny=usage.estimated_cost_cny if usage else None,
            note=f"Received multiple SSE deltas; response model={model or 'unknown'}.",
        )

    async def tool_calling() -> SmokeCase:
        started = time.perf_counter()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "submit_project_brief",
                    "description": "Submit a minimal project brief.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "project_name": {"type": "string"},
                            "target_user": {"type": "string"},
                        },
                        "required": ["project_name", "target_user"],
                        "additionalProperties": False,
                    },
                },
            }
        ]
        response = await adapter.complete(
            [
                DeepSeekMessage(
                    role="user",
                    content="调用 submit_project_brief，项目名用户反馈分析，目标用户产品团队。",
                )
            ],
            max_tokens=160,
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "submit_project_brief"}},
            require_tool_call=True,
        )
        arguments = response.tool_calls[0].arguments
        if set(arguments) != {"project_name", "target_user"}:
            raise RuntimeError("tool call arguments did not match the declared schema")
        return _case_from_response(
            "tool_calling",
            started,
            response,
            "Required function call returned JSON-object arguments matching the declared keys.",
        )

    async def structured_output() -> SmokeCase:
        started = time.perf_counter()
        response = await adapter.complete(
            [
                DeepSeekMessage(
                    role="system",
                    content=(
                        "只输出 JSON 对象，必须包含 project_name、target_user、"
                        "open_questions。"
                    ),
                ),
                DeepSeekMessage(
                    role="user",
                    content="用户反馈分析 Agent，面向产品团队；列出不超过三个待澄清问题。",
                ),
            ],
            max_tokens=240,
            response_model=SmokeBrief,
        )
        return _case_from_response(
            "json_schema",
            started,
            response,
            "JSON mode output passed strict local Pydantic validation (extra fields forbidden).",
        )

    async def chinese_long_document() -> SmokeCase:
        started = time.perf_counter()
        paragraph = (
            "销售团队每周复盘线索来源、首次响应、商机推进、丢单原因和下一步责任人。"
            "当前记录散落在会议纪要和表格中，主管难以及时识别可复用打法与风险。"
        )
        document = "\n".join(f"第{index}段：{paragraph}" for index in range(1, 181))
        response = await adapter.complete(
            [
                DeepSeekMessage(
                    role="user",
                    content=f"阅读以下中文材料，输出三条有编号的事实摘要，不补充材料外事实：\n{document}",
                )
            ],
            max_tokens=360,
            timeout_seconds=120,
        )
        if not response.content or len(response.content) < 30:
            raise RuntimeError("Chinese long-document response was unexpectedly short")
        return _case_from_response(
            "chinese_long_document",
            started,
            response,
            f"Processed {len(document)} Chinese characters; output retained only as hash/length.",
        )

    async def timeout() -> SmokeCase:
        started = time.perf_counter()
        try:
            await adapter.complete(
                [DeepSeekMessage(role="user", content="只回复 OK")],
                max_tokens=8,
                timeout_seconds=0.001,
            )
        except DeepSeekTimeoutError as exc:
            return SmokeCase(
                name="timeout",
                status="pass",
                latency_ms=round((time.perf_counter() - started) * 1000),
                error_code=exc.code,
                note="A real network request with a 1ms deadline failed closed as a typed timeout.",
            )
        return SmokeCase(
            name="timeout",
            status="fail",
            latency_ms=round((time.perf_counter() - started) * 1000),
            note="The real request unexpectedly completed within the forced deadline.",
        )

    async def context_too_long() -> SmokeCase:
        started = time.perf_counter()
        # The 2026-08-22 official model page declares a 1M-token context.
        # The preceding live probe measured exactly four tokens per repeated phrase.
        oversized = "上下文边界测试。" * 262_510
        try:
            response = await adapter.complete(
                [DeepSeekMessage(role="user", content=oversized)],
                max_tokens=8,
                timeout_seconds=120,
            )
        except DeepSeekContextTooLongError as exc:
            return SmokeCase(
                name="context_too_long",
                status="pass",
                latency_ms=round((time.perf_counter() - started) * 1000),
                error_code=exc.code,
                note=(
                    f"Provider rejected an oversized {len(oversized)}-character input and the "
                    "adapter classified it without storing the payload."
                ),
            )
        return SmokeCase(
            name="context_too_long",
            status="fail",
            latency_ms=round((time.perf_counter() - started) * 1000),
            provider_request_id=response.provider_request_id,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            note=(
                "Provider did not return a recognized context-too-long error for the "
                f"{len(oversized)}-character input; observed response model={response.model}."
            ),
        )

    runners: list[CaseRunner] = [
        authentication_network,
        streaming,
        tool_calling,
        structured_output,
        chinese_long_document,
        timeout,
        context_too_long,
    ]
    selected = {
        item.strip()
        for item in os.getenv("DEEPSEEK_SMOKE_CASES", "").split(",")
        if item.strip()
    }
    for runner in runners:
        if selected and runner.__name__ not in selected:
            continue
        started = time.perf_counter()
        try:
            cases.append(await runner())
        except DeepSeekError as exc:
            cases.append(
                SmokeCase(
                    name=runner.__name__,
                    status="fail",
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    provider_request_id=exc.request_id,
                    error_code=exc.code,
                    note="Provider smoke failed closed; no prompt, output, or secret was recorded.",
                )
            )
        except Exception as exc:  # noqa: BLE001 - converted to a redacted smoke result
            cases.append(
                SmokeCase(
                    name=runner.__name__,
                    status="fail",
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    error_code=type(exc).__name__,
                    note=(
                        "Smoke assertion failed; exception detail was suppressed to avoid "
                        "data leakage."
                    ),
                )
            )

    if not selected or "rate_limit" in selected:
        cases.append(
            SmokeCase(
                name="rate_limit",
                status="not_observed",
                latency_ms=0,
                note=(
                    "No intentional request flood was sent. HTTP 429 classification and "
                    "Retry-After handling are covered by Adapter unit tests; a real quota "
                    "response remains unverified."
                ),
            )
        )
    return DeepSeekSmokeReport(
        generated_at=datetime.now(UTC),
        model=settings.MODEL_NAME,
        base_url_origin=settings.MODEL_BASE_URL,
        secret_ref=settings.MODEL_API_KEY_REF,
        cases=cases,
    )


async def _main() -> None:
    report = await run_deepseek_smoke()
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
