from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import get_settings
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime" / "user-beta"
BACKUPS = RUNTIME / "backups"
RESTORE_PREFIX = "product_factory_user_restorecheck_"
INTERNAL_PROJECT_ID = "2a3c38e1-9704-4f83-a096-84cb5a5025e7"


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
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            project_count = connection.execute(text("SELECT count(*) FROM projects")).scalar_one()
            user_count = connection.execute(text("SELECT count(*) FROM users")).scalar_one()
            active_invites = connection.execute(
                text("SELECT count(*) FROM user_invites WHERE status = 'active'")
            ).scalar_one()
            internal_projects = connection.execute(
                text("SELECT count(*) FROM projects WHERE id = :project_id"),
                {"project_id": INTERNAL_PROJECT_ID},
            ).scalar_one()
        return {
            "database": make_url(str(engine.url)).database,
            "project_count": project_count,
            "user_count": user_count,
            "active_invites": active_invites,
            "internal_project_count": internal_projects,
            "alembic_revision": revision,
        }
    finally:
        if owned_engine:
            engine.dispose()


def validate_state(state: dict[str, object]) -> None:
    if state["internal_project_count"] != 0:
        raise RuntimeError("用户环境禁止包含内部销售复盘或验收项目")
    head = migration_head()
    if state["alembic_revision"] != head:
        raise RuntimeError(
            f"数据库 migration 不是 head：current={state['alembic_revision']} head={head}"
        )


def command_preflight() -> None:
    settings = get_settings()
    if settings.APP_ENV != "production":
        raise RuntimeError("用户环境必须使用 APP_ENV=production")
    if not settings.AUTH_ENFORCED or not settings.session_auth_ready:
        raise RuntimeError("用户环境必须强制认证并配置 Session")
    state = read_state()
    validate_state(state)
    print(json.dumps({"status": "ok", **state}, ensure_ascii=False))


def command_backup() -> None:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUPS / f"product-factory-user-{now_id()}.dump"
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
    metadata = {
        "backup_file": backup_path.name,
        "bytes": backup_path.stat().st_size,
        "sha256": hashlib.sha256(backup_path.read_bytes()).hexdigest(),
        "state": read_state(),
    }
    backup_path.with_suffix(".json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
    )
    backup_path.with_suffix(".json").chmod(0o600)
    print(json.dumps({"status": "ok", **metadata}, ensure_ascii=False))


def safe_backup_path(value: str | None) -> Path:
    candidates = sorted(BACKUPS.glob("*.dump"), key=lambda item: item.stat().st_mtime)
    candidate = (
        Path(value).resolve() if value else (candidates[-1].resolve() if candidates else None)
    )
    if candidate is None or BACKUPS.resolve() not in candidate.parents or not candidate.is_file():
        raise RuntimeError("恢复演练只允许使用 user-beta/backups 下的 dump")
    return candidate


def command_restore_check(value: str | None) -> None:
    backup_path = safe_backup_path(value)
    url = database_url()
    database_name = f"{RESTORE_PREFIX}{now_id().lower()}_{os.getpid()}"
    created = False
    try:
        with psycopg_connect(url, "postgres", autocommit=True) as connection:
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
        restored_engine = create_engine(url.set(database=database_name), pool_pre_ping=True)
        try:
            state = read_state(restored_engine)
        finally:
            restored_engine.dispose()
        validate_state(state)
        print(
            json.dumps(
                {"status": "ok", "backup_file": backup_path.name, "state": state},
                ensure_ascii=False,
            )
        )
    finally:
        if created:
            with psycopg_connect(url, "postgres", autocommit=True) as connection:
                connection.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (database_name,),
                )
                connection.execute(
                    sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name))
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight")
    subparsers.add_parser("backup")
    restore = subparsers.add_parser("restore-check")
    restore.add_argument("backup", nargs="?")
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            command_preflight()
        elif args.command == "backup":
            command_backup()
        else:
            command_restore_check(args.backup)
        return 0
    except Exception as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
