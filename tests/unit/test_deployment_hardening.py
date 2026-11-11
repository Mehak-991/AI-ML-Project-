"""Regression tests for the Phase 22 deployment hardening (versions, TLS, metrics, CI scanning)."""

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import create_app
from scripts import check_tracked_files, preflight

ROOT = Path(__file__).resolve().parents[2]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


# --- Release version safety -----------------------------------------------------------------


def test_compose_has_no_default_image_tag() -> None:
    text = _text("compose.yaml")
    image_lines = [line for line in text.splitlines() if re.match(r"\s+image: aiproject-", line)]
    assert len(image_lines) == 4  # migration, app, worker, frontend
    for line in image_lines:
        assert "${APP_VERSION:?" in line, f"image tag must be required, not defaulted: {line.strip()}"
    assert "APP_VERSION:-" not in text
    assert "0.4.0" not in text and ":latest" not in text


def test_containers_receive_the_release_tag() -> None:
    config = yaml.safe_load(_text("compose.yaml"))
    for service in ("migration", "app", "worker"):
        assert config["services"][service]["environment"]["APP_RELEASE"] == "${APP_VERSION}"


def test_production_example_pins_the_current_release() -> None:
    values = preflight.parse_env_file(ROOT / ".env.production.example")
    assert values["APP_VERSION"] == "0.5.0-p21"
    assert preflight.check_version(values["APP_VERSION"])[0][0] == "OK"
    for secret in ("POSTGRES_PASSWORD", "JWT_SECRET_KEY", "METRICS_TOKEN", "OPENAI_API_KEY"):
        assert values.get(secret, "") == "", f"{secret} must not carry a value in the template"


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        (None, "ERROR"),
        ("", "ERROR"),
        ("latest", "ERROR"),
        ("0.4.0", "ERROR"),
        ("v0.5.0", "ERROR"),
        ("0.5", "ERROR"),
        ("0.5.0-p21", "OK"),
        ("0.5.0-p22", "OK"),
        ("1.2.3", "OK"),
    ],
)
def test_preflight_version_rules(version, expected) -> None:
    assert preflight.check_version(version)[0][0] == expected


def test_preflight_secret_rules() -> None:
    good = {"POSTGRES_PASSWORD": "x", "JWT_SECRET_KEY": "k" * 48, "METRICS_TOKEN": "t"}
    assert all(level == "OK" for level, _ in preflight.check_secrets(good))
    assert ("ERROR", "POSTGRES_PASSWORD is not set.") in preflight.check_secrets({**good, "POSTGRES_PASSWORD": ""})
    assert any(l == "ERROR" and "JWT_SECRET_KEY" in m for l, m in preflight.check_secrets({**good, "JWT_SECRET_KEY": "short"}))
    assert any(l == "ERROR" and "JWT_SECRET_KEY" in m for l, m in preflight.check_secrets({**good, "JWT_SECRET_KEY": "change-me" + "x" * 40}))
    # The removed development flag is now only reported as obsolete (it can no longer weaken anything).
    obsolete = preflight.check_secrets({**good, "ALLOW_FIRST_USER_ADMIN": "true"})
    assert any(l == "WARN" and "ALLOW_FIRST_USER_ADMIN" in m and "obsolete" in m for l, m in obsolete)
    assert not any(l == "ERROR" for l, _ in obsolete)
    expand = preflight.check_secrets({**good, "RBAC_STORE_LEGACY_VIEWER": "true"})
    assert any(l == "WARN" and "RBAC_STORE_LEGACY_VIEWER" in m for l, m in expand)
    assert any(l == "WARN" and "METRICS_TOKEN" in m for l, m in preflight.check_secrets({**good, "METRICS_TOKEN": ""}))


def test_preflight_cli_fails_without_a_version_and_never_prints_secret_values(tmp_path, monkeypatch, capsys) -> None:
    secret = "S" * 40
    env_file = tmp_path / ".env"
    env_file.write_text(f"POSTGRES_PASSWORD={secret}\nJWT_SECRET_KEY={secret}\nMETRICS_TOKEN={secret}\n", encoding="utf-8")
    for name in preflight._WATCHED:
        monkeypatch.delenv(name, raising=False)
    assert preflight.main(["--env-file", str(env_file)]) == 1
    out = capsys.readouterr().out
    assert secret not in out and "FAILED" in out and "APP_VERSION is not set" in out

    monkeypatch.setenv("APP_VERSION", "0.5.0-p21")
    assert preflight.main(["--env-file", str(env_file)]) == 0
    assert secret not in capsys.readouterr().out


def test_environment_overrides_the_env_file(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_VERSION=latest\nPOSTGRES_PASSWORD=x\nJWT_SECRET_KEY=" + "k" * 40 + "\n", encoding="utf-8")
    monkeypatch.setenv("APP_VERSION", "0.5.0-p21")
    assert preflight.main(["--env-file", str(env_file)]) == 0


def test_health_reports_the_release_tag(make_settings) -> None:
    with TestClient(create_app(make_settings(APP_ENV="testing", APP_RELEASE="0.5.0-p21"))) as client:
        body = client.get("/health").json()
    assert body["release"] == "0.5.0-p21"
    with TestClient(create_app(make_settings(APP_ENV="testing"))) as client:
        assert client.get("/health").json()["release"] is None


# --- TLS / nginx -----------------------------------------------------------------------------


def test_proxies_report_the_trusted_scheme_not_the_raw_one() -> None:
    common = _text("frontend/server-common.inc")
    lines = [l for l in common.splitlines() if "X-Forwarded-Proto" in l and "proxy_set_header" in l]
    assert len(lines) == 3
    assert all("$forwarded_proto" in l and "$scheme" not in l for l in lines)


def test_nothing_is_trusted_by_default() -> None:
    trust = _text("frontend/proxy-trust.conf")
    geo = trust[trust.index("geo $trusted_tls_proxy") : trust.index("map ")]
    active = [l.strip() for l in geo.splitlines() if l.strip() and not l.strip().startswith("#")]
    assert active == ["geo $trusted_tls_proxy {", "default 0;", "}"]
    assert '"1:https" https;' in trust and "default   $scheme;" in trust


def test_hsts_only_for_https_and_on_every_header_include() -> None:
    assert "Strict-Transport-Security $hsts_header" in _text("frontend/security-headers.inc")
    assert "Strict-Transport-Security $hsts_header" in _text("frontend/server-common.inc")  # /docs
    assert 'default ""' in _text("frontend/proxy-trust.conf")  # empty value => header omitted


def test_http_config_stays_plain_and_hides_the_version() -> None:
    http = _text("frontend/nginx.conf")
    assert "listen 80;" in http and "443" not in http and "ssl" not in http
    assert "server_tokens off;" in http and "server-common.inc" in http


def test_tls_config_redirects_and_uses_modern_tls() -> None:
    tls = _text("frontend/nginx.tls.conf")
    assert "return 301 https://$host$request_uri;" in tls
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in tls
    assert "ssl_session_tickets off;" in tls and "server_tokens off;" in tls
    assert "/etc/nginx/tls/fullchain.pem" in tls and "/etc/nginx/tls/privkey.pem" in tls
    assert re.search(r"location = /healthz \{[^}]*return 200", tls), "container health check must stay on :80"
    assert not re.search(r"BEGIN [A-Z ]*(PRIVATE KEY|CERTIFICATE)", tls), "no certificate material in the repo"


def test_tls_override_requires_a_certificate_directory_and_mounts_it_read_only() -> None:
    config = yaml.safe_load(_text("compose.tls.yaml"))
    volumes = config["services"]["frontend"]["volumes"]
    assert any("${TLS_CERT_DIR:?" in v and v.endswith(":/etc/nginx/tls:ro") for v in volumes)
    assert any(v.endswith(":/etc/nginx/conf.d/default.conf:ro") for v in volumes)
    assert any(p.endswith(":443") for p in config["services"]["frontend"]["ports"])


def test_metrics_is_never_proxied_publicly() -> None:
    common = _text("frontend/server-common.inc")
    assert re.search(r"location = /metrics \{\s*return 404;", common)


def test_no_private_key_or_certificate_is_tracked() -> None:
    for path in ROOT.joinpath("frontend").glob("*"):
        if path.is_file() and path.suffix in {".conf", ".inc", ".pem", ".key"}:
            assert "PRIVATE KEY" not in path.read_text(encoding="utf-8", errors="ignore")


# --- Prometheus ------------------------------------------------------------------------------


def test_prometheus_scrapes_the_api_with_a_token_file_not_an_inline_token() -> None:
    config = yaml.safe_load(_text("monitoring/prometheus.yml"))
    (job,) = config["scrape_configs"]
    assert job["static_configs"][0]["targets"] == ["app:8000"]
    assert job["metrics_path"] == "/metrics"
    assert job["authorization"]["credentials_file"] == "/etc/prometheus/secrets/metrics_token"
    assert "credentials" not in job["authorization"], "never inline the token"


def test_prometheus_override_is_local_only_and_locked_down() -> None:
    config = yaml.safe_load(_text("compose.monitoring.yaml"))
    service = config["services"]["prometheus"]
    assert re.fullmatch(r"prom/prometheus:v\d+\.\d+\.\d+", service["image"]), "pin an exact version"
    assert service["ports"] == ["${PROMETHEUS_BIND:-127.0.0.1}:${PROMETHEUS_PORT:-9090}:9090"]
    assert service["read_only"] is True and service["cap_drop"] == ["ALL"]
    assert any(v.endswith("/etc/prometheus/secrets/metrics_token:ro") for v in service["volumes"])


def test_metrics_token_file_is_git_ignored() -> None:
    ignore = _text("monitoring/secrets/.gitignore").splitlines()
    assert "*" in ignore and "!.gitignore" in ignore


# --- CI secret scanning ----------------------------------------------------------------------


def test_ci_scans_full_history_with_redaction_and_checks_forbidden_files() -> None:
    workflow = yaml.safe_load(_text(".github/workflows/ci.yml"))
    job = workflow["jobs"]["secret-scan"]
    checkout = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0, "history scan needs full history"
    commands = " ".join(s.get("run", "") for s in job["steps"])
    assert "gitleaks" in commands and "--redact=100" in commands and "--exit-code 1" in commands
    assert re.search(r"gitleaks:v\d+\.\d+\.\d+", commands), "pin the scanner version"
    assert "scripts/check_tracked_files.py" in commands
    assert "useDefault = true" in _text(".gitleaks.toml")


@pytest.mark.parametrize(
    "path",
    [
        "backups/db_backup_x.sql.gz",
        "backups/anything.txt",
        "dump.sql",
        "nightly.dump",
        "server.pem",
        "id.key",
        ".env",
        ".env.production",
        "deploy/.env.local",
        "monitoring/secrets/metrics_token",
        "data/app.sqlite3",
    ],
)
def test_guard_rejects_dumps_env_files_and_keys(path) -> None:
    assert check_tracked_files.forbidden_files([path]) == [path]


@pytest.mark.parametrize(
    "path",
    [".env.example", ".env.production.example", "monitoring/secrets/.gitignore", "backups/.gitkeep", "app/main.py", "README.md"],
)
def test_guard_allows_templates_and_normal_files(path) -> None:
    assert check_tracked_files.forbidden_files([path]) == []


def test_repository_currently_tracks_no_forbidden_file() -> None:
    assert check_tracked_files.main([]) == 0
