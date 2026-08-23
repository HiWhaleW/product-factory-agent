#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import get_settings
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime" / "seed-beta"
BACKUPS = RUNTIME / "backups"
INVITES = RUNTIME / "invites"
PROJECT_ID = "2a3c38e1-9704-4f83-a096-84cb5a5025e7"
G5_ID = "3fb3ef9f-91c9-433f-a56b-10521ec13b4a"
RESTORE_PREFIX = "product_factory_restorecheck_"


def now_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def database_url() -> URL:
    return make_url(get_settings().DATABASE_URL)


def psycopg_connect(url: URL, database: str | None = None, *, autocommit: bool = False):
    return psycopg.connect(
        host=url.host or "127.0.0.1",
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        dbname=database or url.database,
        autocommit=autocommit,
    )


def postgres_tool(name: str) -> str:
    bundled = ROOT / ".runtime" / "postgresql-16.15" / "bin" / name
    if bundled.is_file():
        return str(bundled)
    resolved = shutil.which(name)
    if not resolved:
        raise RuntimeError(f"缺少 PostgreSQL 工具：{name}")
    return resolved


def postgres_env(url: URL) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PGHOST": url.host or "127.0.0.1",
            "PGPORT": str(url.port or 5432),
            "PGUSER": url.username or "",
            "PGDATABASE": url.database or "",
        }
    )
    if url.password:
        env["PGPASSWORD"] = url.password
    return env


def migration_head() -> str:
    config = Config(str(ROOT / "apps" / "api" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "apps" / "api" / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head() or ""


def read_state(engine=None) -> dict[str, object]:
    owned_engine = engine is None
    engine = engine or create_engine(get_settings().DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            project = (
                connection.execute(
                    text(
                        "SELECT state, context_version, iteration_version "
                        "FROM projects WHERE id = :project_id"
                    ),
                    {"project_id": PROJECT_ID},
                )
                .mappings()
                .one()
            )
            gate = (
                connection.execute(
                    text(
                        "SELECT g.status, d.decision FROM gates g "
                        "LEFT JOIN gate_decisions d ON d.gate_id = g.id WHERE g.id = :gate_id"
                    ),
                    {"gate_id": G5_ID},
                )
                .mappings()
                .one()
            )
            g6_count = connection.execute(
                text(
                    "SELECT count(*) FROM gates WHERE project_id = :project_id AND gate_type = 'G6'"
                ),
                {"project_id": PROJECT_ID},
            ).scalar_one()
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        return {
            "project_id": PROJECT_ID,
            "project_state": project["state"],
            "context_version": project["context_version"],
            "iteration_version": project["iteration_version"],
            "g5_status": gate["status"],
            "g5_decision": gate["decision"],
            "g6_count": g6_count,
            "alembic_revision": revision,
        }
    finally:
        if owned_engine:
            engine.dispose()


def validate_expected_state(state: dict[str, object]) -> None:
    expected = {
        "project_state": "seed_beta",
        "context_version": 10,
        "iteration_version": 1,
        "g5_status": "approved",
        "g5_decision": "approve",
        "g6_count": 0,
    }
    mismatches = {
        key: (state.get(key), value) for key, value in expected.items() if state.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"内测状态与预期不一致：{mismatches}")


def command_preflight() -> None:
    settings = get_settings()
    if settings.APP_ENV != "seed_beta":
        raise RuntimeError("内测环境必须使用 APP_ENV=seed_beta")
    if not settings.AUTH_ENFORCED or not settings.session_auth_ready:
        raise RuntimeError("内测环境必须强制认证并配置邀请码哈希与 Session Secret")
    state = read_state()
    validate_expected_state(state)
    head = migration_head()
    if state["alembic_revision"] != head:
        raise RuntimeError(
            f"数据库 migration 不是 head：current={state['alembic_revision']} head={head}"
        )
    print(json.dumps({"status": "ok", **state}, ensure_ascii=False))


def command_backup() -> None:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUPS / f"product-factory-{now_id()}.dump"
    url = database_url()
    subprocess.run(
        [
            postgres_tool("pg_dump"),
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(backup_path),
        ],
        check=True,
        env=postgres_env(url),
    )
    backup_path.chmod(0o600)
    digest = hashlib.sha256(backup_path.read_bytes()).hexdigest()
    state = read_state()
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "backup_file": backup_path.name,
        "bytes": backup_path.stat().st_size,
        "sha256": digest,
        "state": state,
    }
    metadata_path = backup_path.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    metadata_path.chmod(0o600)
    print(json.dumps({"status": "ok", **metadata}, ensure_ascii=False))


def command_create_invite(display_name: str, role: str, expires_hours: int) -> None:
    if role not in {"admin", "user"}:
        raise RuntimeError("邀请码角色只能是 admin 或 user")
    code = secrets.token_urlsafe(24)
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    invite_id = str(uuid4())
    expires_at = datetime.now(UTC) + timedelta(hours=expires_hours)
    url = database_url()
    with psycopg_connect(url) as connection:
        connection.execute(
            """
            INSERT INTO user_invites (
              id, code_hash, user_id, display_name, role, status,
              max_uses, uses_count, expires_at, created_at, last_used_at
            ) VALUES (%s, %s, NULL, %s, %s, 'active', 1, 0, %s, now(), NULL)
            """,
            (invite_id, code_hash, display_name, role, expires_at),
        )
    INVITES.mkdir(parents=True, exist_ok=True)
    output_path = INVITES / f"{invite_id}.txt"
    output_path.write_text(code + "\n")
    output_path.chmod(0o600)
    print(
        json.dumps(
            {
                "status": "ok",
                "invite_id": invite_id,
                "display_name": display_name,
                "role": role,
                "expires_at": expires_at.isoformat(),
                "secret_file": str(output_path.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
    )


def command_revoke_invite(invite_id: str) -> None:
    url = database_url()
    with psycopg_connect(url) as connection:
        row = connection.execute(
            "SELECT user_id FROM user_invites WHERE id = %s FOR UPDATE", (invite_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("邀请码不存在")
        user_id = row[0]
        connection.execute(
            "UPDATE user_invites SET status = 'revoked' WHERE id = %s", (invite_id,)
        )
        if user_id:
            project_count = connection.execute(
                "SELECT count(*) FROM projects WHERE owner_user_id = %s", (user_id,)
            ).fetchone()[0]
            if project_count == 0:
                connection.execute(
                    "UPDATE users SET status = 'inactive' WHERE id = %s", (user_id,)
                )
    secret_file = INVITES / f"{invite_id}.txt"
    if secret_file.is_file():
        secret_file.unlink()
    print(
        json.dumps(
            {
                "status": "ok",
                "invite_id": invite_id,
                "user_inactivated": bool(user_id and project_count == 0),
                "secret_file_removed": not secret_file.exists(),
            },
            ensure_ascii=False,
        )
    )


def safe_backup_path(value: str | None) -> Path:
    if value:
        candidate = Path(value).expanduser().resolve()
    else:
        candidates = sorted(BACKUPS.glob("*.dump"), key=lambda item: item.stat().st_mtime)
        if not candidates:
            raise RuntimeError("没有可用于恢复演练的备份文件")
        candidate = candidates[-1].resolve()
    backup_root = BACKUPS.resolve()
    if (
        backup_root not in candidate.parents
        or candidate.suffix != ".dump"
        or not candidate.is_file()
    ):
        raise RuntimeError("恢复演练只允许使用 .runtime/seed-beta/backups 下的 .dump 文件")
    return candidate


def command_restore_check(value: str | None) -> None:
    backup_path = safe_backup_path(value)
    url = database_url()
    database_name = f"{RESTORE_PREFIX}{now_id().lower()}_{os.getpid()}"
    if not database_name.startswith(RESTORE_PREFIX):
        raise RuntimeError("恢复演练数据库名不安全")
    maintenance_database = "postgres"
    created = False
    try:
        with psycopg_connect(url, maintenance_database, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
            created = True
        restore_env = postgres_env(url)
        restore_env["PGDATABASE"] = database_name
        subprocess.run(
            [
                postgres_tool("pg_restore"),
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                database_name,
                str(backup_path),
            ],
            check=True,
            env=restore_env,
        )
        restored_url = url.set(database=database_name)
        restored_engine = create_engine(restored_url, pool_pre_ping=True)
        try:
            state = read_state(restored_engine)
        finally:
            restored_engine.dispose()
        validate_expected_state(state)
        if state["alembic_revision"] != migration_head():
            raise RuntimeError("恢复副本的 Alembic revision 不是 head")
        print(
            json.dumps(
                {
                    "status": "ok",
                    "backup_file": backup_path.name,
                    "restored_database": database_name,
                    "state": state,
                    "cleanup": "temporary_database_removed",
                },
                ensure_ascii=False,
            )
        )
    finally:
        if created:
            with psycopg_connect(url, maintenance_database, autocommit=True) as connection:
                connection.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (database_name,),
                )
                connection.execute(
                    sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name))
                )


def main() -> int:
    parser = argparse.ArgumentParser(description="造物工场种子内测运维操作")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight")
    subparsers.add_parser("backup")
    invite_parser = subparsers.add_parser("create-invite")
    invite_parser.add_argument("--display-name", required=True)
    invite_parser.add_argument("--role", choices=("admin", "user"), default="user")
    invite_parser.add_argument("--expires-hours", type=int, default=24)
    revoke_parser = subparsers.add_parser("revoke-invite")
    revoke_parser.add_argument("invite_id")
    restore_parser = subparsers.add_parser("restore-check")
    restore_parser.add_argument("backup", nargs="?")
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            command_preflight()
        elif args.command == "backup":
            command_backup()
        elif args.command == "create-invite":
            command_create_invite(args.display_name, args.role, args.expires_hours)
        elif args.command == "revoke-invite":
            command_revoke_invite(args.invite_id)
        else:
            command_restore_check(args.backup)
        return 0
    except Exception as error:
        print(
            json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
