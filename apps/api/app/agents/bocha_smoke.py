from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from app.adapters.bocha import BochaAdapter, BochaError, BochaTimeoutError
from app.core.config import get_settings


class BochaSmokeCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["pass", "fail", "not_observed"]
    latency_ms: int
    error_code: str | None = None
    note: str


class BochaSmokeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    provider: Literal["bocha"] = "bocha"
    endpoint: str
    secret_ref: str
    secret_present: bool = True
    query_recorded: bool = False
    response_bodies_recorded: bool = False
    provider_error_bodies_recorded: bool = False
    result_count: int
    total_estimated_matches_present: bool
    provider_request_id_present: bool
    field_presence: dict[str, int]
    domains: list[str]
    url_sha256: list[str]
    evidence_ref_sha256: list[str]
    response_sha256: str | None
    usage_or_cost_metadata_present: bool
    evidence_ref_stable: bool
    cases: list[BochaSmokeCase]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _safe_error_case(name: str, started: float, error: Exception) -> BochaSmokeCase:
    return BochaSmokeCase(
        name=name,
        status="fail",
        latency_ms=round((time.perf_counter() - started) * 1000),
        error_code=getattr(error, "code", type(error).__name__),
        note="Provider call failed; provider body and exception text were not recorded.",
    )


async def run_bocha_smoke() -> BochaSmokeReport:
    settings = get_settings()
    adapter = BochaAdapter.from_settings(settings)
    cases: list[BochaSmokeCase] = []

    started = time.perf_counter()
    try:
        response = await adapter.search(
            "2026 年中国 AI Agent 产品市场与企业应用趋势",
            count=10,
            freshness="oneYear",
            summary=True,
        )
    except BochaError as error:
        cases.append(_safe_error_case("authentication_network_chinese_schema", started, error))
        raise RuntimeError(
            json.dumps(
                {
                    "provider": "bocha",
                    "secret_ref": settings.WEB_RESEARCH_API_KEY_REF,
                    "error_code": error.code,
                    "status_code": error.status_code,
                    "request_id_present": bool(error.request_id),
                    "retryable": error.retryable,
                },
                ensure_ascii=False,
            )
        ) from None

    latency_ms = round((time.perf_counter() - started) * 1000)
    serialized = response.model_dump_json()
    results = response.results
    fields = {
        field: sum(bool(getattr(item, field)) for item in results)
        for field in (
            "title",
            "url",
            "site_name",
            "snippet",
            "summary",
            "date_published",
        )
    }
    domains = sorted(
        {
            urlparse(item.url).hostname or ""
            for item in results
            if urlparse(item.url).hostname
        }
    )
    evidence_ref_stable = all(
        item.evidence_ref == f"bocha:web:{_hash(item.url)}" for item in results
    )
    cases.append(
        BochaSmokeCase(
            name="authentication_network_chinese_schema",
            status="pass",
            latency_ms=latency_ms,
            note=(
                "Official endpoint accepted the SecretRef; the Chinese query returned "
                "a response accepted by the strict local schema."
            ),
        )
    )
    cases.append(
        BochaSmokeCase(
            name="evidence_ref_stability",
            status="pass" if evidence_ref_stable else "fail",
            latency_ms=0,
            note="EvidenceRef was recomputed locally from each returned URL.",
        )
    )

    timeout_started = time.perf_counter()
    try:
        await adapter.search(
            "产品工厂 Agent",
            count=1,
            summary=False,
            timeout_seconds=0.001,
        )
    except BochaTimeoutError:
        cases.append(
            BochaSmokeCase(
                name="short_timeout",
                status="pass",
                latency_ms=round((time.perf_counter() - timeout_started) * 1000),
                error_code="BOCHA_TIMEOUT",
                note="A real request with a 1 ms client timeout failed closed as typed timeout.",
            )
        )
    except BochaError as error:
        cases.append(_safe_error_case("short_timeout", timeout_started, error))
    else:
        cases.append(
            BochaSmokeCase(
                name="short_timeout",
                status="not_observed",
                latency_ms=round((time.perf_counter() - timeout_started) * 1000),
                note="The real request completed inside the 1 ms client timeout.",
            )
        )

    cases.extend(
        [
            BochaSmokeCase(
                name="rate_limit_429",
                status="not_observed",
                latency_ms=0,
                note="No request flood was performed to manufacture a provider rate limit.",
            ),
            BochaSmokeCase(
                name="usage_cost_metadata",
                status="not_observed",
                latency_ms=0,
                note=(
                    "The standardized Web Search response exposes no token or cost fields; "
                    "billing must be reconciled outside the response contract."
                ),
            ),
        ]
    )

    safe_payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC),
        "endpoint": adapter.config.web_search_url,
        "secret_ref": adapter.config.api_key_ref,
        "result_count": len(results),
        "total_estimated_matches_present": response.total_estimated_matches is not None,
        "provider_request_id_present": response.provider_request_id is not None,
        "field_presence": fields,
        "domains": domains,
        "url_sha256": [_hash(item.url) for item in results],
        "evidence_ref_sha256": [_hash(item.evidence_ref) for item in results],
        "response_sha256": _hash(serialized),
        "usage_or_cost_metadata_present": False,
        "evidence_ref_stable": evidence_ref_stable,
        "cases": cases,
    }
    return BochaSmokeReport.model_validate(safe_payload)


if __name__ == "__main__":
    print(
        json.dumps(
            asyncio.run(run_bocha_smoke()).model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )
