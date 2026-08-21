import asyncio
import json

import httpx
import pytest
from app.adapters.deepseek import (
    DeepSeekAdapter,
    DeepSeekAuthenticationError,
    DeepSeekConfig,
    DeepSeekConfigurationError,
    DeepSeekContextTooLongError,
    DeepSeekMessage,
    DeepSeekRateLimitError,
    DeepSeekSchemaError,
    DeepSeekTimeoutError,
    resolve_secret_ref,
)
from pydantic import BaseModel, ConfigDict


def config() -> DeepSeekConfig:
    return DeepSeekConfig(
        model="deepseek-chat",
        base_url="https://api.deepseek.example",
        api_key_ref="TEST_DEEPSEEK_KEY",
        timeout_seconds=5,
    )


def adapter(handler) -> DeepSeekAdapter:
    return DeepSeekAdapter(
        config(),
        transport=httpx.MockTransport(handler),
        secret_resolver=lambda _: "unit-test-secret",
    )


def message() -> list[DeepSeekMessage]:
    return [DeepSeekMessage(role="user", content="返回结果")]


def test_adapter_fails_closed_for_missing_secret() -> None:
    with pytest.raises(DeepSeekConfigurationError, match="SecretRef"):
        DeepSeekAdapter(config(), secret_resolver=lambda _: None)


def test_secret_ref_can_be_resolved_from_local_env_file(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_DEEPSEEK_KEY=local-secret\n", encoding="utf-8")

    assert resolve_secret_ref("TEST_DEEPSEEK_KEY", str(env_file)) == "local-secret"


def test_authentication_error_does_not_echo_secret_or_provider_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer unit-test-secret"
        return httpx.Response(
            401,
            json={"error": {"message": "unit-test-secret is invalid"}},
            headers={"x-request-id": "req-safe"},
        )

    with pytest.raises(DeepSeekAuthenticationError) as error:
        asyncio.run(adapter(handler).complete(message()))

    assert "unit-test-secret" not in str(error.value)
    assert error.value.request_id == "req-safe"


class Brief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    questions: list[str]


def test_structured_output_is_locally_schema_validated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "id": "req-structured",
                "model": "deepseek-chat",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"title":"项目","questions":["目标用户？"]}',
                        },
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 9, "total_tokens": 17},
            },
        )

    result = asyncio.run(adapter(handler).complete(message(), response_model=Brief))

    assert result.structured_output == {"title": "项目", "questions": ["目标用户？"]}
    assert result.usage.total_tokens == 17
    assert result.usage.estimated_cost_cny is None


def test_invalid_structured_output_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "deepseek-chat",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"title":1}'},
                    }
                ],
                "usage": {},
            },
        )

    with pytest.raises(DeepSeekSchemaError) as error:
        asyncio.run(adapter(handler).complete(message(), response_model=Brief))
    assert "questions" in str(error.value)
    assert '"title":1' not in str(error.value)


def test_tool_call_arguments_are_parsed_as_json_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "deepseek-chat",
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "submit_brief",
                                        "arguments": '{"title":"项目"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {},
            },
        )

    result = asyncio.run(adapter(handler).complete(message(), require_tool_call=True))

    assert result.tool_calls[0].name == "submit_brief"
    assert result.tool_calls[0].arguments == {"title": "项目"}


def test_streaming_yields_content_finish_and_usage() -> None:
    events = [
        {
            "id": "req-stream",
            "model": "deepseek-chat",
            "choices": [{"delta": {"content": "你"}, "finish_reason": None}],
        },
        {
            "id": "req-stream",
            "model": "deepseek-chat",
            "choices": [{"delta": {"content": "好"}, "finish_reason": "stop"}],
        },
        {
            "id": "req-stream",
            "model": "deepseek-chat",
            "choices": [],
            "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
        },
    ]
    stream_body = "\n".join([*(f"data: {json.dumps(event)}" for event in events), "data: [DONE]"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=stream_body, headers={"x-request-id": "req-stream"})

    async def collect():
        return [chunk async for chunk in adapter(handler).stream(message())]

    chunks = asyncio.run(collect())

    assert "".join(chunk.content_delta for chunk in chunks) == "你好"
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.total_tokens == 4


def test_timeout_rate_limit_and_context_errors_are_typed() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("contains sensitive request detail", request=request)

    with pytest.raises(DeepSeekTimeoutError):
        asyncio.run(adapter(timeout_handler).complete(message()))

    def rate_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "1.5"})

    with pytest.raises(DeepSeekRateLimitError) as rate_error:
        asyncio.run(adapter(rate_handler).complete(message()))
    assert rate_error.value.retryable is True
    assert rate_error.value.retry_after_seconds == 1.5

    def context_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"code": "context_length_exceeded", "message": "too long"}},
        )

    with pytest.raises(DeepSeekContextTooLongError):
        asyncio.run(adapter(context_handler).complete(message()))
