"""Pre-deployment checks. Run before `docker compose up`; refuses to bless an unsafe release.

Usage:
    python scripts/preflight.py [--env-file .env] [--check-docker]

Checks:
  * APP_VERSION is set, looks like a release (e.g. 0.5.0-p21), and is not `latest` or the old 0.4.0.
  * Required secrets are present (POSTGRES_PASSWORD, JWT_SECRET_KEY >= 32 bytes, not the shipped
    default) and ALLOW_FIRST_USER_ADMIN is not enabled. Only variable NAMES are printed.
  * METRICS_TOKEN is set (warning only).
  * With --check-docker: both images for that tag exist locally, `docker compose config` is valid,
    and the running containers' tag is reported so a mismatch is visible.

Values from the environment win over the env file, like Docker Compose. Exit code 1 on any ERROR.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RELEASE_PATTERN = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$")
FORBIDDEN_VERSIONS = {"latest": "a moving tag", "0.4.0": "the old compose default"}
DEFAULT_JWT_SECRET_MARKERS = ("change-me", "changeme", "dev-secret", "your-secret")
IMAGES = ("aiproject-backend", "aiproject-frontend")


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE reader (comments and blank lines skipped, optional quotes removed)."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def check_version(version: str | None) -> list[tuple[str, str]]:
    if not version:
        return [("ERROR", "APP_VERSION is not set. Set it to the release tag, e.g. APP_VERSION=0.5.0-p21.")]
    if version in FORBIDDEN_VERSIONS:
        return [("ERROR", f"APP_VERSION={version} is not allowed ({FORBIDDEN_VERSIONS[version]}).")]
    if not RELEASE_PATTERN.match(version):
        return [("ERROR", f"APP_VERSION={version} is not a release tag like 0.5.0 or 0.5.0-p21.")]
    return [("OK", f"APP_VERSION={version}")]


def check_secrets(values: dict[str, str]) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    if not values.get("POSTGRES_PASSWORD"):
        results.append(("ERROR", "POSTGRES_PASSWORD is not set."))
    else:
        results.append(("OK", "POSTGRES_PASSWORD is set"))
    jwt = values.get("JWT_SECRET_KEY", "")
    if len(jwt.encode("utf-8")) < 32 or any(m in jwt.lower() for m in DEFAULT_JWT_SECRET_MARKERS):
        results.append(("ERROR", "JWT_SECRET_KEY is missing, shorter than 32 bytes, or a placeholder."))
    else:
        results.append(("OK", "JWT_SECRET_KEY is set (length ok)"))
    if values.get("ALLOW_FIRST_USER_ADMIN", "").lower() in {"1", "true", "yes", "on"}:
        results.append(("ERROR", "ALLOW_FIRST_USER_ADMIN must not be enabled in production."))
    if not values.get("METRICS_TOKEN"):
        results.append(("WARN", "METRICS_TOKEN is not set; /metrics is open to anything on the internal network."))
    return results


def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60)


def check_docker(version: str | None, env: dict[str, str]) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    try:
        if _docker("version", "--format", "{{.Server.Version}}").returncode != 0:
            return [("ERROR", "Docker engine is not reachable.")]
    except (OSError, subprocess.TimeoutExpired):
        return [("ERROR", "Docker is not installed or did not respond.")]
    if version and version not in FORBIDDEN_VERSIONS and RELEASE_PATTERN.match(version):
        for image in IMAGES:
            found = _docker("image", "inspect", f"{image}:{version}", "--format", "{{.Id}}")
            if found.returncode == 0:
                results.append(("OK", f"image {image}:{version} exists ({found.stdout.strip()[7:19]})"))
            else:
                results.append(("ERROR", f"image {image}:{version} not found; build it first."))
    compose_env = {**os.environ, **{k: v for k, v in env.items() if k not in os.environ}}
    if version:
        compose_env["APP_VERSION"] = version
    cfg = subprocess.run(
        ["docker", "compose", "config", "--quiet"],
        capture_output=True, text=True, cwd=ROOT, env=compose_env, timeout=60,
    )
    results.append(
        ("OK", "docker compose config is valid")
        if cfg.returncode == 0
        else ("ERROR", "docker compose config failed (details withheld; run it manually)")
    )
    running = _docker(
        "ps", "--filter", "label=com.docker.compose.project=aiproject",
        "--format", "{{.Names}} {{.Image}}",
    )
    for line in running.stdout.splitlines():
        name, _, image = line.partition(" ")
        tag = image.rpartition(":")[2]
        if name.endswith(("-app-1", "-worker-1", "-frontend-1")) and version and tag != version:
            results.append(("WARN", f"{name} runs {image}, not {version} (expected until you deploy)"))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-deployment validation")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--check-docker", action="store_true")
    args = parser.parse_args(argv)

    file_values = parse_env_file(args.env_file)
    values = {**file_values, **{k: v for k, v in os.environ.items() if k in _WATCHED}}
    results = check_version(values.get("APP_VERSION"))
    results += check_secrets(values)
    if args.check_docker:
        results += check_docker(values.get("APP_VERSION"), values)

    for level, message in results:
        print(f"[preflight] {level}: {message}")
    errors = sum(1 for level, _ in results if level == "ERROR")
    print(f"[preflight] {'FAILED' if errors else 'PASSED'} ({errors} error(s))")
    return 1 if errors else 0


_WATCHED = {
    "APP_VERSION", "POSTGRES_PASSWORD", "JWT_SECRET_KEY", "METRICS_TOKEN", "ALLOW_FIRST_USER_ADMIN",
}

if __name__ == "__main__":
    sys.exit(main())
