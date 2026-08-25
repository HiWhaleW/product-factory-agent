from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.domain.models import User
from app.services.session_auth import hash_password, password_matches


class UserIdentityError(ValueError):
    def __init__(self, code: str, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


def get_active_user(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None or user.status != "active":
        raise UserIdentityError("USER_INACTIVE", "用户不存在或已停用，请联系管理员。")
    return user


def normalize_username(username: str) -> str:
    return username.strip().lower()


def register_user(
    session: Session,
    *,
    username: str,
    display_name: str,
    password: str,
) -> User:
    normalized = normalize_username(username)
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('user-registration', 0))")
    )
    if session.scalar(select(User.id).where(User.username == normalized)) is not None:
        raise UserIdentityError("USERNAME_TAKEN", "该账号已存在，请直接登录。")
    credentialed_users = session.scalar(
        select(func.count()).select_from(User).where(User.password_hash.like("scrypt$%"))
    )
    user = User(
        username=normalized,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        role="admin" if credentialed_users == 0 else "user",
        status="active",
        last_login_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()
    return user


def authenticate_user(session: Session, *, username: str, password: str) -> User:
    normalized = normalize_username(username)
    user = session.scalar(select(User).where(User.username == normalized))
    if user is None or not password_matches(password, user.password_hash):
        raise UserIdentityError("INVALID_CREDENTIALS", "账号或密码错误。")
    user = get_active_user(session, user.id)
    user.last_login_at = datetime.now(UTC)
    session.flush()
    return user
