from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings


class DeepSeekError(RuntimeError):
    """Base provider error whose message is safe for logs and API responses."""

    code = "DEEPSEEK_ERROR"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id
        self.retry_after_seconds = retry_after_seconds


class DeepSeekConfigurationError(DeepSeekError):
    code = "DEEPSEEK_CONFIGURATION_ERROR"


class DeepSeekAuthenticationError(DeepSeekError):
    code = "DEEPSEEK_AUTHENTICATION_ERROR"


class DeepSeekRateLimitError(DeepSeekError):
    code = "DEEPSEEK_RATE_LIMIT"
    retryable = True


class DeepSeekTimeoutError(DeepSeekError):
    code = "DEEPSEEK_TIMEOUT"
    retryable = True


class DeepSeekContextTooLongError(DeepSeekError):
    code = "DEEPSEEK_CONTEXT_TOO_LONG"


class DeepSeekSchemaError(DeepSeekError):
    code = "DEEPSEEK_SCHEMA_INVALID"


class DeepSeekToolCompatibilityError(DeepSeekError):
    code = "DEEPSEEK_TOOL_INCOMPATIBLE"


class DeepSeekProviderError(DeepSeekError):
    code = "DEEPSEEK_PROVIDER_ERROR"

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retryable = bool(self.status_code and self.status_code >= 500)


@dataclass(frozen=True)
class DeepSeekConfig:
    model: str
    base_url: str
    api_key_ref: str
    timeout_seconds: float = 60.0

    @classmethod
    def from_settings(cls, settings: Settings) -> DeepSeekConfig:
        if settings.MODEL_PROVIDER != "deepseek":
            raise DeepSeekConfigurationError("V1 model provider must be deepseek.")
        return cls(
            model=settings.MODEL_NAME,
            base_url=settings.MODEL_BASE_URL,
            api_key_ref=settings.MODEL_API_KEY_REF,
        )

    def validate(self) -> None:
        if not self.model.strip():
            raise DeepSeekConfigurationError("MODEL_NAME is required for model execution.")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise DeepSeekConfigurationError("MODEL_BASE_URL must be an absolute HTTPS URL.")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,127}", self.api_key_ref):
            raise DeepSeekConfigurationError("MODEL_API_KEY_REF is not a valid environment name.")
        if not (1 <= self.timeout_seconds <= 600):
            raise DeepSeekConfigurationError("Provider timeout must be between 1 and 600 seconds.")

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


class DeepSeekMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None


class DeepSeekToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, Any]


class DeepSeekUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cache_hit_tokens: int | None = None
    prompt_cache_miss_tokens: int | None = None
    estimated_cost_cny: float | None = None


class DeepSeekResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_request_id: str | None = None
    model: str
    content: str | None
    finish_reason: str | None
    tool_calls: list[DeepSeekToolCall] = Field(default_factory=list)
    usage: DeepSeekUsage
    structured_output: dict[str, Any] | None = None


class DeepSeekStreamChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_request_id: str | None = None
    model: str | None = None
    content_delta: str = ""
    finish_reason: str | None = None
    usage: DeepSeekUsage | None = None


SecretResolver = Callable[[str], str | None]


def resolve_secret_ref(name: str, env_file: str = ".env") -> str | None:
    """Resolve a SecretRef without ever returning it through settings serialization."""
    value = os.getenv(name)
    if value:
        return value
    local_value = dotenv_values(env_file).get(name)
    return str(local_value) if local_value else None


class DeepSeekAdapter:
    def __init__(
        self,
        config: DeepSeekConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        secret_resolver: SecretResolver = resolve_secret_ref,
    ) -> None:
        config.validate()
        api_key = secret_resolver(config.api_key_ref)
        if not api_key:
            raise DeepSeekConfigurationError(
                f"SecretRef {config.api_key_ref} is missing or empty."
            )
        self.config = config
        self._api_key = api_key
        self._transport = transport

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> DeepSeekAdapter:
        return cls(
            DeepSeekConfig.from_settings(settings),
            transport=transport,
            secret_resolver=lambda ref: (
                settings.resolve_model_api_key()
                if ref == settings.MODEL_API_KEY_REF
                else None
            ),
        )

    def _client(self, timeout_seconds: float | None = None) -> httpx.AsyncClient:
        timeout = timeout_seconds or self.config.timeout_seconds
        return httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout),
            transport=self._transport,
        )

    def _payload(
        self,
        messages: Sequence[DeepSeekMessage],
        *,
        max_tokens: int,
        temperature: float,
        stream: bool,
        response_model: type[BaseModel] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not messages:
            raise DeepSeekSchemaError("At least one model message is required.")
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [message.model_dump(exclude_none=True) for message in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if response_model is not None:
            payload["response_format"] = {"type": "json_object"}
        if tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice
        return payload

    async def complete(
        self,
        messages: Sequence[DeepSeekMessage],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout_seconds: float | None = None,
        response_model: type[BaseModel] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        require_tool_call: bool = False,
    ) -> DeepSeekResponse:
        payload = self._payload(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=False,
            response_model=response_model,
            tools=tools,
            tool_choice=tool_choice,
        )
        try:
            async with self._client(timeout_seconds) as client:
                response = await client.post(self.config.chat_completions_url, json=payload)
        except httpx.TimeoutException as exc:
            raise DeepSeekTimeoutError("DeepSeek request timed out.") from exc
        except httpx.HTTPError as exc:
            raise DeepSeekProviderError("DeepSeek network request failed.") from exc

        self._raise_for_status(response)
        try:
            body = response.json()
            choice = body["choices"][0]
            message = choice["message"]
            content = message.get("content")
            tool_calls = self._parse_tool_calls(message.get("tool_calls", []))
            usage = DeepSeekUsage.model_validate(body.get("usage") or {})
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            raise DeepSeekSchemaError("DeepSeek returned an invalid response envelope.") from exc

        if require_tool_call and not tool_calls:
            raise DeepSeekToolCompatibilityError(
                "DeepSeek did not return the required structured tool call."
            )

        structured_output: dict[str, Any] | None = None
        if response_model is not None:
            if not content:
                raise DeepSeekSchemaError("DeepSeek returned empty structured output.")
            try:
                raw_output = json.loads(content)
                validated = response_model.model_validate(raw_output)
                structured_output = validated.model_dump(mode="json")
            except json.JSONDecodeError as exc:
                raise DeepSeekSchemaError(
                    "DeepSeek structured output was not valid JSON "
                    f"(line {exc.lineno}, column {exc.colno})."
                ) from exc
            except ValidationError as exc:
                safe_errors = [
                    {
                        "loc": list(item["loc"]),
                        "type": item["type"],
                        "msg": item["msg"],
                    }
                    for item in exc.errors(include_url=False, include_input=False)
                ]
                raise DeepSeekSchemaError(
                    "DeepSeek structured output failed local schema validation: "
                    + json.dumps(safe_errors, ensure_ascii=False)
                ) from exc
            except TypeError as exc:
                raise DeepSeekSchemaError(
                    "DeepSeek structured output had an invalid JSON value type."
                ) from exc

        return DeepSeekResponse(
            provider_request_id=self._request_id(response, body),
            model=str(body.get("model") or self.config.model),
            content=content,
            finish_reason=choice.get("finish_reason"),
            tool_calls=tool_calls,
            usage=usage,
            structured_output=structured_output,
        )

    async def stream(
        self,
        messages: Sequence[DeepSeekMessage],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[DeepSeekStreamChunk]:
        payload = self._payload(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        try:
            async with self._client(timeout_seconds) as client, client.stream(
                "POST", self.config.chat_completions_url, json=payload
            ) as response:
                self._raise_for_status(response)
                request_id = self._request_id(response)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        body = json.loads(data)
                        choices = body.get("choices") or []
                        choice = choices[0] if choices else {}
                        delta = choice.get("delta") or {}
                        usage_body = body.get("usage")
                        usage = (
                            DeepSeekUsage.model_validate(usage_body)
                            if usage_body
                            else None
                        )
                    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
                        raise DeepSeekSchemaError(
                            "DeepSeek returned an invalid stream event."
                        ) from exc
                    yield DeepSeekStreamChunk(
                        provider_request_id=request_id,
                        model=body.get("model"),
                        content_delta=delta.get("content") or "",
                        finish_reason=choice.get("finish_reason"),
                        usage=usage,
                    )
        except httpx.TimeoutException as exc:
            raise DeepSeekTimeoutError("DeepSeek stream timed out.") from exc
        except DeepSeekError:
            raise
        except httpx.HTTPError as exc:
            raise DeepSeekProviderError("DeepSeek stream request failed.") from exc

    @staticmethod
    def _parse_tool_calls(items: list[dict[str, Any]]) -> list[DeepSeekToolCall]:
        parsed: list[DeepSeekToolCall] = []
        for item in items:
            try:
                function = item["function"]
                arguments = json.loads(function["arguments"])
                if not isinstance(arguments, dict):
                    raise TypeError("tool arguments must be an object")
                parsed.append(
                    DeepSeekToolCall(
                        id=item["id"],
                        name=function["name"],
                        arguments=arguments,
                    )
                )
            except (KeyError, TypeError, json.JSONDecodeError, ValidationError) as exc:
                raise DeepSeekToolCompatibilityError(
                    "DeepSeek returned an invalid tool call envelope."
                ) from exc
        return parsed

    @staticmethod
    def _request_id(response: httpx.Response, body: dict[str, Any] | None = None) -> str | None:
        return (
            response.headers.get("x-request-id")
            or response.headers.get("cf-ray")
            or ((body or {}).get("id"))
        )

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("retry-after")
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        request_id = self._request_id(response)
        status_code = response.status_code
        common = {"status_code": status_code, "request_id": request_id}
        if status_code in {401, 403}:
            raise DeepSeekAuthenticationError("DeepSeek authentication failed.", **common)
        if status_code == 429:
            raise DeepSeekRateLimitError(
                "DeepSeek rate limit was reached.",
                retry_after_seconds=self._retry_after(response),
                **common,
            )
        if status_code == 400 and self._is_context_too_long(response):
            raise DeepSeekContextTooLongError("DeepSeek context limit was exceeded.", **common)
        raise DeepSeekProviderError("DeepSeek provider returned an error.", **common)

    @staticmethod
    def _is_context_too_long(response: httpx.Response) -> bool:
        try:
            error = response.json().get("error") or {}
            code = str(error.get("code") or "").lower()
            message = str(error.get("message") or "").lower()
        except (ValueError, AttributeError):
            return False
        markers = ("context", "maximum context", "too long", "token limit")
        return "context" in code or any(marker in message for marker in markers)
