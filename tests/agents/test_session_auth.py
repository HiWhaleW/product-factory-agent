from datetime import UTC, datetime

import pytest
from app.services.session_auth import (
    SessionTokenError,
    hash_password,
    issue_session_token,
    password_matches,
    verify_session_token,
)


def test_password_hash_and_signed_session_round_trip() -> None:
    encoded = hash_password("correct-horse-battery-staple")
    assert password_matches("correct-horse-battery-staple", encoded)
    assert not password_matches("wrong-password", encoded)
    token, expires_at = issue_session_token(
        user_id="local-admin", secret="test-session-secret", ttl_seconds=300
    )
    user_id, verified_expiry = verify_session_token(token, secret="test-session-secret")
    assert user_id == "local-admin"
    assert verified_expiry == expires_at
    assert verified_expiry > datetime.now(UTC)


def test_password_hash_uses_unique_salts() -> None:
    first = hash_password("same-password")
    second = hash_password("same-password")
    assert first != second
    assert password_matches("same-password", first)
    assert password_matches("same-password", second)


def test_session_rejects_tampering() -> None:
    token, _ = issue_session_token(
        user_id="local-admin", secret="test-session-secret", ttl_seconds=300
    )
    with pytest.raises(SessionTokenError, match="invalid"):
        verify_session_token(f"{token}tampered", secret="test-session-secret")
