from app.core.security_headers import add_security_headers
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_api_security_headers_are_applied() -> None:
    secured = FastAPI()
    secured.middleware("http")(add_security_headers)

    @secured.get("/api/v1/protected")
    def endpoint() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(secured) as client:
        response = client.get("/api/v1/protected")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
