from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.adapters.deepseek import resolve_secret_ref
from app.core.config import Settings


class BochaError(RuntimeError):
    """Base search-provider error whose message is safe for logs and API responses."""

    code = "BOCHA_ERROR"
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


class BochaConfigurationError(BochaError):
    code = "BOCHA_CONFIGURATION_ERROR"


class BochaAuthenticationError(BochaError):
    code = "BOCHA_AUTHENTICATION_ERROR"


class BochaRateLimitError(BochaError):
    code = "BOCHA_RATE_LIMIT"
    retryable = True


class BochaTimeoutError(BochaError):
    code = "BOCHA_TIMEOUT"
    retryable = True


class BochaSchemaError(BochaError):
    code = "BOCHA_SCHEMA_INVALID"


class BochaProviderError(BochaError):
    code = "BOCHA_PROVIDER_ERROR"

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retryable = bool(self.status_code and self.status_code >= 500)


@dataclass(frozen=True)
class BochaConfig:
    base_url: str = "https://api.bochaai.com/v1"
    api_key_ref: str = "BOCHA_API_KEY"
    timeout_seconds: float = 30.0

    @classmethod
    def from_settings(cls, settings: Settings) -> BochaConfig:
        if settings.WEB_RESEARCH_PROVIDER != "bocha":
            raise BochaConfigurationError("D5 web research provider must be bocha.")
        return cls(
            base_url=settings.WEB_RESEARCH_BASE_URL,
            api_key_ref=settings.WEB_RESEARCH_API_KEY_REF,
            timeout_seconds=settings.WEB_RESEARCH_TIMEOUT_SECONDS,
        )

    def validate(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or parsed.hostname != "api.bochaai.com":
            raise BochaConfigurationError(
                "WEB_RESEARCH_BASE_URL must use the official Bocha HTTPS host."
            )
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise BochaConfigurationError("WEB_RESEARCH_BASE_URL contains forbidden URL parts.")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,127}", self.api_key_ref):
            raise BochaConfigurationError(
                "WEB_RESEARCH_API_KEY_REF is not a valid environment name."
            )
        if not (1 <= self.timeout_seconds <= 120):
            raise BochaConfigurationError("Bocha timeout must be between 1 and 120 seconds.")

    @property
    def web_search_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/web-search"


class BochaSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_ref: str
    title: str = Field(min_length=1, max_length=1_000)
    url: str = Field(min_length=1, max_length=8_000)
    site_name: str | None = Field(default=None, max_length=1_000)
    snippet: str | None = Field(default=None, max_length=50_000)
    summary: str | None = Field(default=None, max_length=100_000)
    date_published: str | None = Field(default=None, max_length=128)


class BochaSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["bocha"] = "bocha"
    provider_request_id: str | None = None
    query: str
    total_estimated_matches: int | None = Field(default=None, ge=0)
    results: list[BochaSearchResult]

    def model_payload(self) -> dict[str, Any]:
        """Return the bounded evidence payload that may enter the Agent checkpoint."""
        return self.model_dump(mode="json")


SecretResolver = Callable[[str], str | None]


class BochaAdapter:
    def __init__(
        self,
        config: BochaConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        secret_resolver: SecretResolver = resolve_secret_ref,
    ) -> None:
        config.validate()
        api_key = secret_resolver(config.api_key_ref)
        if not api_key:
            raise BochaConfigurationError(
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
    ) -> BochaAdapter:
        return cls(
            BochaConfig.from_settings(settings),
            transport=transport,
            secret_resolver=lambda ref: (
                settings.resolve_web_research_api_key()
                if ref == settings.WEB_RESEARCH_API_KEY_REF
                else None
            ),
        )

    @classmethod
    def from_user_credential(
        cls,
        settings: Settings,
        *,
        api_key: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> BochaAdapter:
        """Build the search adapter from the current user's isolated secret."""
        secret_ref = "USER_BOCHA_API_KEY"
        return cls(
            BochaConfig(
                base_url=base_url,
                api_key_ref=secret_ref,
                timeout_seconds=settings.WEB_RESEARCH_TIMEOUT_SECONDS,
            ),
            transport=transport,
            secret_resolver=lambda ref: api_key if ref == secret_ref else None,
        )

    async def search(
        self,
        query: str,
        *,
        count: int = 10,
        freshness: Literal["noLimit", "oneDay", "oneWeek", "oneMonth", "oneYear"] = "noLimit",
        summary: bool = True,
        timeout_seconds: float | None = None,
    ) -> BochaSearchResponse:
        query = query.strip()
        if not query or len(query) > 2_000:
            raise BochaSchemaError("Bocha query must contain between 1 and 2000 characters.")
        if not (1 <= count <= 50):
            raise BochaSchemaError("Bocha count must be between 1 and 50.")
        payload = {
            "query": query,
            "freshness": freshness,
            "summary": summary,
            "count": count,
        }
        timeout = timeout_seconds or self.config.timeout_seconds
        try:
            async with httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(timeout),
                transport=self._transport,
            ) as client:
                response = await client.post(self.config.web_search_url, json=payload)
        except httpx.TimeoutException as exc:
            raise BochaTimeoutError("Bocha search request timed out.") from exc
        except httpx.HTTPError as exc:
            raise BochaProviderError("Bocha search network request failed.") from exc

        self._raise_for_status(response)
        try:
            body = response.json()
            request_id = self._request_id(response, body)
            data = body.get("data") if isinstance(body, dict) and "data" in body else body
            if not isinstance(data, dict):
                raise TypeError("invalid data envelope")
            pages = data["webPages"]
            values = pages.get("value") or []
            if not isinstance(values, list):
                raise TypeError("invalid result list")
            results = [self._parse_result(item) for item in values]
            original_query = (data.get("queryContext") or {}).get("originalQuery") or query
            total = pages.get("totalEstimatedMatches")
            if total is not None:
                total = int(total)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise BochaSchemaError("Bocha returned an invalid search response.") from exc
        return BochaSearchResponse(
            provider_request_id=request_id,
            query=str(original_query),
            total_estimated_matches=total,
            results=results,
        )

    @staticmethod
    def _parse_result(item: Any) -> BochaSearchResult:
        if not isinstance(item, dict):
            raise TypeError("invalid search item")
        url = str(item["url"])
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("invalid result URL")
        title = str(item.get("name") or "").strip()
        evidence_hash = hashlib.sha256(url.encode()).hexdigest()
        return BochaSearchResult(
            evidence_ref=f"bocha:web:{evidence_hash}",
            title=title,
            url=url,
            site_name=_optional_text(item.get("siteName")),
            snippet=_optional_text(item.get("snippet")),
            summary=_optional_text(item.get("summary")),
            date_published=_optional_text(item.get("datePublished")),
        )

    @staticmethod
    def _request_id(response: httpx.Response, body: Any | None = None) -> str | None:
        header_id = response.headers.get("x-request-id")
        if header_id:
            return header_id[:200]
        if isinstance(body, dict):
            value = body.get("log_id") or body.get("request_id")
            return str(value)[:200] if value else None
        return None

    @classmethod
    def _raise_for_status(cls, response: httpx.Response) -> None:
        request_id = cls._request_id(response)
        if response.status_code in {401, 403}:
            raise BochaAuthenticationError(
                "Bocha rejected the configured SecretRef.",
                status_code=response.status_code,
                request_id=request_id,
            )
        if response.status_code == 429:
            raise BochaRateLimitError(
                "Bocha rate limit was reached.",
                status_code=429,
                request_id=request_id,
                retry_after_seconds=_retry_after(response.headers.get("retry-after")),
            )
        if response.is_error:
            raise BochaProviderError(
                "Bocha search request failed.",
                status_code=response.status_code,
                request_id=request_id,
            )
        try:
            body = response.json()
        except ValueError:
            return
        if isinstance(body, dict) and "code" in body and body.get("code") not in {0, 200}:
            code = body.get("code")
            if code in {401, 403, "401", "403"}:
                raise BochaAuthenticationError(
                    "Bocha rejected the configured SecretRef.",
                    status_code=response.status_code,
                    request_id=cls._request_id(response, body),
                )
            if code in {429, "429"}:
                raise BochaRateLimitError(
                    "Bocha rate limit was reached.",
                    status_code=429,
                    request_id=cls._request_id(response, body),
                    retry_after_seconds=_retry_after(response.headers.get("retry-after")),
                )
            raise BochaProviderError(
                "Bocha search provider returned an error.",
                status_code=response.status_code,
                request_id=cls._request_id(response, body),
            )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
