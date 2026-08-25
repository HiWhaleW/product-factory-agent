import base64
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta


class SessionTokenError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


PASSWORD_SCHEME = "scrypt"
PASSWORD_N = 2**14
PASSWORD_R = 8
PASSWORD_P = 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=PASSWORD_N, r=PASSWORD_R, p=PASSWORD_P
    )
    return "$".join(
        (
            PASSWORD_SCHEME,
            str(PASSWORD_N),
            str(PASSWORD_R),
            str(PASSWORD_P),
            base64.urlsafe_b64encode(salt).decode().rstrip("="),
            base64.urlsafe_b64encode(digest).decode().rstrip("="),
        )
    )


def password_matches(password: str, encoded_hash: str) -> bool:
    try:
        scheme, n, r, p, salt_text, digest_text = encoded_hash.split("$", 5)
        if scheme != PASSWORD_SCHEME:
            return False
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
        actual = hashlib.scrypt(
            password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


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
