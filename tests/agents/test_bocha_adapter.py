from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from app.adapters.bocha import (
    BochaAdapter,
    BochaAuthenticationError,
    BochaConfig,
    BochaConfigurationError,
    BochaRateLimitError,
    BochaSchemaError,
    BochaTimeoutError,
)


def adapter(handler, *, secret: str | None = "local-test-secret") -> BochaAdapter:
    return BochaAdapter(
        BochaConfig(),
        transport=httpx.MockTransport(handler),
        secret_resolver=lambda _: secret,
    )


def response_body() -> dict:
    return {
        "code": 200,
        "log_id": "bocha-log-1",
        "msg": None,
        "data": {
            "_type": "SearchResponse",
            "queryContext": {"originalQuery": "AI Agent 产品市场"},
            "webPages": {
                "totalEstimatedMatches": 20,
                "value": [
                    {
                        "name": "官方研究报告",
                        "url": "https://example.com/report",
                        "siteName": "Example",
                        "snippet": "报告摘要",
                        "summary": "可引用摘要",
                        "datePublished": "2026-08-20T00:00:00+08:00",
                    }
                ],
            },
        },
    }


def test_missing_secret_and_non_official_host_fail_closed() -> None:
    with pytest.raises(BochaConfigurationError, match="missing"):
        adapter(lambda _: httpx.Response(200), secret=None)
    with pytest.raises(BochaConfigurationError, match="official Bocha"):
        BochaAdapter(
            BochaConfig(base_url="https://attacker.invalid/v1"),
            secret_resolver=lambda _: "must-not-leak",
        )


def test_search_uses_bearer_and_returns_stable_evidence_refs() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=response_body())

    result = asyncio.run(adapter(handler).search("AI Agent 产品市场", count=8))

    assert captured["authorization"] == "Bearer local-test-secret"
    assert captured["body"] == {
        "query": "AI Agent 产品市场",
        "freshness": "noLimit",
        "summary": True,
        "count": 8,
    }
    assert result.provider_request_id == "bocha-log-1"
    assert result.results[0].title == "官方研究报告"
    assert result.results[0].evidence_ref.startswith("bocha:web:")
    assert len(result.results[0].evidence_ref) == len("bocha:web:") + 64
    assert "local-test-secret" not in result.model_dump_json()


def test_direct_search_envelope_is_supported() -> None:
    body = response_body()["data"]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body, headers={"x-request-id": "header-id"})

    result = asyncio.run(adapter(handler).search("用户复盘"))
    assert result.provider_request_id == "header-id"
    assert result.total_estimated_matches == 20


def test_auth_error_is_typed_and_does_not_echo_provider_body() -> None:
    leaked = "provider-secret-body"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"msg": leaked})

    with pytest.raises(BochaAuthenticationError) as error:
        asyncio.run(adapter(handler).search("市场调研"))
    assert leaked not in str(error.value)
    assert "local-test-secret" not in str(error.value)


def test_timeout_rate_limit_and_schema_errors_are_typed() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("contains request and key", request=request)

    with pytest.raises(BochaTimeoutError):
        asyncio.run(adapter(timeout_handler).search("市场调研"))

    def rate_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "2.5"})

    with pytest.raises(BochaRateLimitError) as rate_error:
        asyncio.run(adapter(rate_handler).search("市场调研"))
    assert rate_error.value.retryable is True
    assert rate_error.value.retry_after_seconds == 2.5

    def envelope_rate_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 429, "msg": "provider body must not leak"},
            headers={"retry-after": "3"},
        )

    with pytest.raises(BochaRateLimitError) as envelope_rate_error:
        asyncio.run(adapter(envelope_rate_handler).search("市场调研"))
    assert envelope_rate_error.value.retry_after_seconds == 3

    def schema_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 200, "data": {}})

    with pytest.raises(BochaSchemaError):
        asyncio.run(adapter(schema_handler).search("市场调研"))


def test_query_and_count_are_bounded_before_network() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=response_body())

    client = adapter(handler)
    with pytest.raises(BochaSchemaError):
        asyncio.run(client.search(""))
    with pytest.raises(BochaSchemaError):
        asyncio.run(client.search("x", count=51))
    assert calls == 0
