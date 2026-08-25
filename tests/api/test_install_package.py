from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_compose_package_has_required_services_persistence_and_healthchecks() -> None:
    compose = read("compose.yaml")

    for service in ("db", "init-storage", "migrate", "api", "web"):
        assert re.search(rf"^  {service}:$", compose, re.MULTILINE)
    for volume in (
        "postgres-data",
        "artifacts",
        "workspaces",
        "user-secrets",
        "application-logs",
    ):
        assert volume in compose
    assert compose.count("healthcheck:") >= 3
    assert "condition: service_completed_successfully" in compose
    assert 'AUTH_ENFORCED: "true"' in compose


def test_default_install_is_api_empty_and_builder_fails_closed() -> None:
    compose = read("compose.yaml")
    example = read(".env.example")

    assert 'MODEL_NAME: ""' in compose
    assert 'MODEL_BASE_URL: ""' in compose
    assert 'DEEPSEEK_API_KEY: ""' in compose
    assert 'BOCHA_API_KEY: ""' in compose
    assert 'BUILDER_ENABLED: "false"' in compose
    assert "BUILDER_ENABLED=false" in example
    assert "DEEPSEEK_API_KEY=\n" in example
    assert "BOCHA_API_KEY=\n" in example
    assert "https://api.bochaai.com" not in example


def test_compose_does_not_expand_builder_host_permissions() -> None:
    compose = read("compose.yaml")

    assert "/var/run/docker.sock" not in compose
    assert "privileged:" not in compose
    assert "network_mode: host" not in compose
    assert "BUILDER_ENABLED: \"false\"" in compose
    assert "no-new-privileges:true" in compose
    assert '${WEB_BIND_ADDRESS:-127.0.0.1}' in compose
    db_block = compose.split("  db:\n", 1)[1].split("\n  migrate:", 1)[0]
    api_block = compose.split("  api:\n", 1)[1].split("\n  web:", 1)[0]
    assert "ports:" not in db_block
    assert "ports:" not in api_block


def test_docker_context_excludes_runtime_secrets_and_build_outputs() -> None:
    ignored = set(read(".dockerignore").splitlines())

    for required in (
        ".env",
        ".env.*",
        ".product-factory",
        ".runtime",
        ".next",
        "**/.next",
        "node_modules",
        "**/node_modules",
        "artifacts",
        "workspaces",
        "*.log",
    ):
        assert required in ignored


def test_installer_generates_secrets_and_never_uses_invites() -> None:
    scripts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "scripts/install").glob("*.sh"))
    )

    assert "openssl rand -hex 24" in scripts
    assert "openssl rand -hex 48" in scripts
    assert "chmod 600" in scripts
    assert "invite" not in scripts.lower()
    assert "seed-beta" not in scripts
    assert "user-beta" not in scripts


def test_installer_allows_a_safe_isolated_project_and_port() -> None:
    installer = read("scripts/install/install.sh")

    assert 'COMPOSE_PROJECT_NAME:-product-factory-local' in installer
    assert 'WEB_BIND_ADDRESS:-127.0.0.1' in installer
    assert 'WEB_PORT:-3400' in installer
    assert '"${web_bind_address}" == "127.0.0.1"' in installer
    assert '"${web_port}" -ge 1' in installer
    assert '"${web_port}" -le 65535' in installer


def test_restore_check_uses_an_isolated_project_and_removes_its_volumes() -> None:
    script = read("scripts/install/restore-check.sh")

    assert "product-factory-restore-" in script
    assert "down -v --remove-orphans" in script
    assert "未改动当前安装" in script


def test_install_shell_scripts_parse() -> None:
    scripts = sorted((ROOT / "scripts/install").glob("*.sh"))
    result = subprocess.run(
        ["bash", "-n", *map(str, scripts)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_install_template_contains_no_usable_secret() -> None:
    template = read("deploy/install.env.example")

    assert "GENERATED_BY_INSTALLER" in template
    assert not re.search(r"SESSION_SECRET=[0-9a-f]{32,}", template)
    assert not re.search(r"POSTGRES_PASSWORD=[0-9a-f]{24,}", template)
