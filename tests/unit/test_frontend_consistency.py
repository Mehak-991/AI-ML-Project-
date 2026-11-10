"""Static guards that keep the frontend consistent with the backend and the deployment.

These run in the backend test job, so they need no Node toolchain. The one test that inspects a
production build runs only when frontend/dist exists (after `npm run build`).
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"
VITE_CONFIG = ROOT / "frontend" / "vite.config.ts"
API_TS = SRC / "services" / "api.ts"
AUTH_MODAL = SRC / "components" / "AuthModal.tsx"


def _sources() -> list[Path]:
    return [p for p in SRC.rglob("*") if p.suffix in {".ts", ".tsx"}]


def _flat(text: str) -> str:
    """JSX wraps long sentences over several lines; compare on one whitespace-normalised line."""
    return re.sub(r"\s+", " ", text)


# --- The first-user-becomes-admin claim must not come back --------------------------------------


def test_no_frontend_text_claims_the_first_account_becomes_administrator() -> None:
    pattern = re.compile(
        r"(first|very first)\s+(account|user|registered|registration)[^.]{0,80}\b(admin|administrator)\b"
        r"|becomes?\s+the\s+administrator"
        r"|first\s+to\s+register[^.]{0,40}\badmin",
        re.IGNORECASE,
    )
    offenders = [str(p.relative_to(ROOT)) for p in _sources() if pattern.search(_flat(p.read_text(encoding="utf-8")))]
    assert not offenders, f"stale bootstrap claim (the backend never makes the first public account admin): {offenders}"


def test_registration_hint_states_the_actual_policy() -> None:
    text = _flat(AUTH_MODAL.read_text(encoding="utf-8"))
    assert "New accounts have Viewer (read-only) access." in text
    assert "An administrator can grant additional permissions." in text


def test_registration_form_still_submits_the_expected_fields() -> None:
    """The text fix must not change what the form sends (design and behaviour are preserved)."""
    text = AUTH_MODAL.read_text(encoding="utf-8")
    assert re.search(r"register\(\{\s*email:\s*email\.trim\(\),\s*password,\s*full_name:\s*fullName\.trim\(\)", text)
    assert "password.length < 8" in text


# --- The dev proxy target is configurable, with a local default ---------------------------------


def test_vite_proxy_target_is_configurable_with_a_local_default() -> None:
    config = VITE_CONFIG.read_text(encoding="utf-8")
    assert "VITE_DEV_API_TARGET" in config
    assert "loadEnv(" in config, "must honour frontend/.env.local as well as the shell"
    assert "const DEFAULT_DEV_API_TARGET = 'http://127.0.0.1:8000'" in config
    # The only literal API address allowed in the config is that one default.
    literals = re.findall(r"https?://[^\s'\"`)]+", re.sub(r"//.*", "", config))
    assert set(literals) <= {"http://127.0.0.1:8000"}, f"hard-coded targets: {literals}"
    proxy_block = config[config.index("proxy:") :]
    assert proxy_block.count("proxied") >= 3, "/api, /docs and /openapi.json must all use the configured target"
    assert "target: 'http" not in proxy_block, "no literal target inside the proxy block"


def test_vite_proxy_target_is_validated() -> None:
    config = VITE_CONFIG.read_text(encoding="utf-8")
    assert "new URL(" in config
    assert "http:" in config and "https:" in config
    assert "throw new Error(" in config


def test_dev_target_is_injected_only_for_the_dev_server() -> None:
    config = VITE_CONFIG.read_text(encoding="utf-8")
    assert re.search(r"__DEV_API_PROXY_TARGET__:\s*JSON\.stringify\(command === 'serve' \? apiTarget : ''\)", config)


def test_frontend_api_base_stays_relative_for_production() -> None:
    api = API_TS.read_text(encoding="utf-8")
    assert "baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1'" in api
    # Ignore only the development-only 502 hint, which legitimately mentions an example origin.
    outside_dev_hint = re.sub(r"import\.meta\.env\.DEV && status === 502.*?: 'The backend service", "", _flat(api))
    absolute = [m for m in re.findall(r"https?://[^\s'\"`)]+", outside_dev_hint) if "localhost" in m or "127.0.0.1" in m]
    assert not absolute, f"absolute dev addresses in api.ts outside the dev-only hint: {absolute}"
    assert "http://localhost" in api, "the dev-only hint should still show how to target the Docker stack"


# --- The dev-only 502 diagnostic ----------------------------------------------------------------


def test_dev_502_diagnostic_is_kept_guarded_and_names_the_proxy_target() -> None:
    api = _flat(API_TS.read_text(encoding="utf-8"))
    branch = re.search(r"import\.meta\.env\.DEV && status === 502 \? (.*?) : 'The backend service", api)
    assert branch, "the development-only 502 branch must exist"
    message = branch.group(1)
    assert "The API server is not running." in message
    assert "python -m uvicorn app.main:app --port 8000" in message  # existing diagnostic preserved
    assert "${__DEV_API_PROXY_TARGET__}" in message
    assert "VITE_DEV_API_TARGET" in message
    # The production message must stay generic: no addresses, no commands.
    assert "temporarily unavailable" in api


def test_proxy_target_constant_is_used_only_inside_the_dev_guard() -> None:
    uses = [p for p in _sources() if "__DEV_API_PROXY_TARGET__" in p.read_text(encoding="utf-8")]
    assert {p.name for p in uses} == {"api.ts", "vite-env.d.ts"}
    api = _flat(API_TS.read_text(encoding="utf-8"))
    assert api.count("__DEV_API_PROXY_TARGET__") == 1
    assert api.index("import.meta.env.DEV && status === 502") < api.index("__DEV_API_PROXY_TARGET__")


@pytest.mark.skipif(not (ROOT / "frontend" / "dist" / "assets").is_dir(), reason="no production build present")
def test_production_bundle_has_no_dev_diagnostics_or_stale_text() -> None:
    bundle = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "frontend" / "dist" / "assets").glob("*.js"))
    for needle in (
        "API server is not running",
        "dev proxy could not reach",
        "VITE_DEV_API_TARGET",
        "__DEV_API_PROXY_TARGET__",
        "127.0.0.1:8000",
        "python -m uvicorn",
        "becomes the Administrator",
    ):
        assert needle not in bundle, f"production bundle contains {needle!r}"
    assert "temporarily unavailable" in bundle
    assert "grant additional permissions" in bundle
