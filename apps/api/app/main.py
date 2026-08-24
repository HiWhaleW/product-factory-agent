from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.agent_router import router as agent_router
from app.api.router import router
from app.core.request_logging import structured_request_log
from app.core.security_headers import add_security_headers
from app.core.session_middleware import enforce_session_auth

app = FastAPI(
    title="Product Factory API",
    version="0.1.0",
    description=(
        "Deterministic D5 definition control plane with bounded Agent Runtime; "
        "models can propose artifacts but cannot decide Gates or advance project state."
    ),
)
app.include_router(router)
app.include_router(agent_router)
app.middleware("http")(enforce_session_auth)
app.middleware("http")(structured_request_log)
app.middleware("http")(add_security_headers)

SENSITIVE_INPUT_NAMES = frozenset(
    {"api_key", "invite_code", "password", "secret", "token"}
)


def redact_validation_errors(errors: list[dict]) -> list[dict]:
    redacted: list[dict] = []
    for item in errors:
        safe = dict(item)
        location = [str(part).lower() for part in safe.get("loc", ())]
        if any(
            sensitive in part
            for part in location
            for sensitive in SENSITIVE_INPUT_NAMES
        ):
            safe["input"] = "[REDACTED]"
        redacted.append(safe)
    return redacted


@app.exception_handler(HTTPException)
async def api_http_error(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail, headers=exc.headers)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "req_validation")
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "REQUEST_VALIDATION_FAILED",
                "message": "Request validation failed",
                "user_message": "请求字段不符合确定性 API 契约。",
                "retryable": False,
                "request_id": request_id,
                "fields": redact_validation_errors(exc.errors(include_url=False)),
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "req_unhandled")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Unhandled server error",
                "user_message": "服务暂时不可用，请携带 request_id 查看后端日志。",
                "retryable": True,
                "request_id": request_id,
            }
        },
    )
