from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from pathlib import Path

import psycopg
from app.core.config import get_settings
from psycopg import sql
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime" / "user-beta"
ENV_FILE = RUNTIME / "user-beta.env"
INVITE_FILE = RUNTIME / "invite-code.txt"
DATABASE_NAME = "product_factory_user_beta"


def configure() -> None:
    if ENV_FILE.exists():
        print(json.dumps({"status": "ok", "configured": True, "changed": False}))
        return
    settings = get_settings()
    source_url = make_url(settings.DATABASE_URL)
    with psycopg.connect(
        host=source_url.host or "127.0.0.1",
        port=source_url.port or 5432,
        user=source_url.username,
        password=source_url.password,
        dbname="postgres",
        autocommit=True,
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (DATABASE_NAME,)
        ).fetchone()
        if not exists:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DATABASE_NAME)))
    target_url = source_url.set(database=DATABASE_NAME).render_as_string(hide_password=False)
    invite_code = secrets.token_hex(16)
    invite_hash = hashlib.sha256(invite_code.encode()).hexdigest()
    session_secret = secrets.token_hex(48)
    artifact_root = RUNTIME / "artifacts"
    workspace_root = RUNTIME / "workspaces"
    user_secret_root = RUNTIME / "secrets"
    env_text = "\n".join(
        [
            "APP_ENV=production",
            f"DATABASE_URL={target_url}",
            f"ARTIFACT_ROOT={artifact_root}",
            f"WORKSPACE_ROOT={workspace_root}",
            f"USER_SECRET_ROOT={user_secret_root}",
            "AUTH_ENFORCED=true",
            f"INVITE_CODE_HASH={invite_hash}",
            f"SESSION_SECRET={session_secret}",
            "SESSION_TTL_SECONDS=28800",
            "USER_BETA_API_HOST=127.0.0.1",
            "USER_BETA_API_PORT=8300",
            "USER_BETA_WEB_HOST=127.0.0.1",
            "USER_BETA_WEB_PORT=3300",
            "PRODUCT_FACTORY_API_URL=http://127.0.0.1:8300",
            "",
        ]
    )
    ENV_FILE.write_text(env_text)
    INVITE_FILE.write_text(invite_code + "\n")
    ENV_FILE.chmod(0o600)
    INVITE_FILE.chmod(0o600)
    print(
        json.dumps(
            {
                "status": "ok",
                "configured": True,
                "changed": True,
                "database": DATABASE_NAME,
                "invite_file": str(INVITE_FILE.relative_to(ROOT)),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.parse_args()
    configure()
