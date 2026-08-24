from datetime import UTC, datetime

import pytest
from app.services.session_auth import (
    SessionTokenError,
    invite_code_matches,
    issue_session_token,
    verify_session_token,
)


def test_invite_code_and_signed_session_round_trip() -> None:
    assert invite_code_matches(
        "approved-code",
        "946aa3bfef0e3c72aa90367cd3cfbe95f722a2662eabd0baf1d4d0d3d468d5d1",
    )
    token, expires_at = issue_session_token(
        user_id="local-admin", secret="test-session-secret", ttl_seconds=300
    )
    user_id, verified_expiry = verify_session_token(token, secret="test-session-secret")
    assert user_id == "local-admin"
    assert verified_expiry == expires_at
    assert verified_expiry > datetime.now(UTC)


def test_session_rejects_tampering() -> None:
    token, _ = issue_session_token(
        user_id="local-admin", secret="test-session-secret", ttl_seconds=300
    )
    with pytest.raises(SessionTokenError, match="invalid"):
        verify_session_token(f"{token}tampered", secret="test-session-secret")
