import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta


class SessionTokenError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def hash_invite_code(invite_code: str) -> str:
    return hashlib.sha256(invite_code.encode()).hexdigest()


def invite_code_matches(invite_code: str, expected_hash: str) -> bool:
    actual = hash_invite_code(invite_code)
    return hmac.compare_digest(actual, expected_hash)


def issue_session_token(*, user_id: str, secret: str, ttl_seconds: int) -> tuple[str, datetime]:
    expires_at = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).replace(microsecond=0)
    payload = json.dumps(
        {"sub": user_id, "exp": int(expires_at.timestamp())},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
    signature = hmac.new(secret.encode(), encoded, hashlib.sha256).hexdigest().encode()
    return f"{encoded.decode()}.{signature.decode()}", expires_at


def verify_session_token(token: str, *, secret: str) -> tuple[str, datetime]:
    try:
        encoded, supplied_signature = token.split(".", 1)
    except ValueError as exc:
        raise SessionTokenError("invalid") from exc
    expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied_signature):
        raise SessionTokenError("invalid")
    try:
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
        user_id = str(payload["sub"])
        expires_at = datetime.fromtimestamp(int(payload["exp"]), UTC)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SessionTokenError("invalid") from exc
    if expires_at <= datetime.now(UTC):
        raise SessionTokenError("expired")
    return user_id, expires_at
