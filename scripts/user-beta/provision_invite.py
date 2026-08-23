from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
INVITE_FILE = ROOT / ".runtime" / "user-beta" / "invite-code.txt"


def main() -> None:
    invite_hash = hashlib.sha256(INVITE_FILE.read_text().strip().encode()).hexdigest()
    engine = create_engine(get_settings().DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO user_invites (
                      id, code_hash, user_id, display_name, role, status,
                      max_uses, uses_count, expires_at, created_at, last_used_at
                    ) VALUES (
                      :id, :code_hash, NULL, '首位种子用户', 'user', 'active',
                      1, 0, NULL, now(), NULL
                    )
                    ON CONFLICT (code_hash) DO NOTHING
                    """
                ),
                {"id": str(uuid4()), "code_hash": invite_hash},
            )
        print(json.dumps({"status": "ok", "invite_provisioned": True}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
