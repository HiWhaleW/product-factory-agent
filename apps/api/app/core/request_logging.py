from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response

logger = logging.getLogger("product_factory.request")
logger.setLevel(logging.INFO)
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def current_request_id() -> str:
    return request_id_var.get()


async def structured_request_log(request: Request, call_next) -> Response:
    request_id = request.headers.get("x-request-id", "")[:100] or f"req_{uuid4()}"
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    started = perf_counter()
    try:
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        logger.info(
            json.dumps(
                {
                    "event": "http.request.completed",
                    "method": request.method,
                    "path": request.url.path,
                    "request_id": request_id,
                    "status": response.status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return response
    finally:
        request_id_var.reset(token)
