from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domain.models import User, UserInvite
from app.services.session_auth import hash_invite_code, invite_code_matches


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


def resolve_invite_user(
    session: Session,
    *,
    invite_code: str,
    legacy_invite_hash: str,
) -> User:
    code_hash = hash_invite_code(invite_code)
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"user-invite:{code_hash}"},
    )
    invite = session.scalar(
        select(UserInvite).where(UserInvite.code_hash == code_hash).with_for_update()
    )
    if invite is None:
        if not invite_code_matches(invite_code, legacy_invite_hash):
            raise UserIdentityError("INVITE_CODE_INVALID", "邀请码无效。")
        user = session.get(User, "local-admin")
        if user is None:
            user = User(
                id="local-admin",
                display_name="内部管理员",
                role="admin",
                status="active",
            )
            session.add(user)
            session.flush()
        invite = UserInvite(
            code_hash=code_hash,
            user_id=user.id,
            display_name=user.display_name,
            role=user.role,
            status="active",
            max_uses=0,
        )
        session.add(invite)
        session.flush()
    if invite.status != "active":
        raise UserIdentityError("INVITE_CODE_INVALID", "邀请码无效。")
    now = datetime.now(UTC)
    if invite.expires_at is not None and invite.expires_at <= now:
        raise UserIdentityError("INVITE_CODE_EXPIRED", "邀请码已过期，请联系管理员。")
    if invite.user_id is None:
        if invite.max_uses > 0 and invite.uses_count >= invite.max_uses:
            raise UserIdentityError("INVITE_CODE_USED", "邀请码已被使用，请联系管理员。")
        user = User(
            display_name=invite.display_name,
            role=invite.role,
            status="active",
        )
        session.add(user)
        session.flush()
        invite.user_id = user.id
    else:
        user = get_active_user(session, invite.user_id)
    invite.uses_count += 1
    invite.last_used_at = now
    user.last_login_at = now
    session.flush()
    return user
