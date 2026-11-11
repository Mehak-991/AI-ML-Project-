"""RBAC v2: the permission registry, deny-by-default, and every endpoint against every role.

The expected policy below is written out by hand on purpose. It does not import the
implementation's tables, so it fails if the implementation drifts from the approved design:

    user        read everything visible to them; run predictions and SHAP/LIME; own profile
    admin       user + ML management (datasets, training, experiments, jobs, drift analysis,
                ground truth, LLM helpers) and deployment management
    superadmin  admin + user administration, role assignment, audit logs, system settings
"""

import base64
import json
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import PublicRoute, route_has_policy
from app.core.permissions import (
    LEGACY_ROLE_ALIASES,
    ROLE_PERMISSIONS,
    Permission,
    Role,
    effective_role,
    has_full_resource_access,
    has_permission,
    permission_names,
    permissions_for,
)
from app.database.session import get_db
from app.main import create_app
from tests.helpers import DEFAULT_TEST_PASSWORD, insert_account, iter_api_routes

API = "/api/v1"
FAKE_ID = "00000000-0000-0000-0000-000000000001"

# --- the approved permission design, written out by hand --------------------------------------

USER_PERMISSIONS = {"resources:read", "predict:run", "profile:manage"}
ADMIN_PERMISSIONS = USER_PERMISSIONS | {"ml:operate", "deployments:manage"}
SUPERADMIN_PERMISSIONS = ADMIN_PERMISSIONS | {
    "users:read",
    "users:manage",
    "roles:assign",
    "superadmin:grant",
    "audit:read",
    "settings:read",
}


def test_each_role_has_exactly_the_approved_permissions() -> None:
    assert {p.value for p in ROLE_PERMISSIONS[Role.USER]} == USER_PERMISSIONS
    assert {p.value for p in ROLE_PERMISSIONS[Role.ADMIN]} == ADMIN_PERMISSIONS
    assert {p.value for p in ROLE_PERMISSIONS[Role.SUPERADMIN]} == SUPERADMIN_PERMISSIONS


def test_there_are_exactly_three_roles_and_superadmin_holds_every_permission() -> None:
    assert {r.value for r in Role} == {"user", "admin", "superadmin"}
    assert ROLE_PERMISSIONS[Role.SUPERADMIN] == frozenset(Permission)
    assert ROLE_PERMISSIONS[Role.USER] < ROLE_PERMISSIONS[Role.ADMIN] < ROLE_PERMISSIONS[Role.SUPERADMIN]


@pytest.mark.parametrize(
    "permission",
    ["users:read", "users:manage", "roles:assign", "superadmin:grant", "audit:read", "settings:read"],
)
def test_security_permissions_belong_to_superadmin_alone(permission) -> None:
    for role in ("user", "admin"):
        assert not has_permission(role, Permission(permission))
    assert has_permission("superadmin", Permission(permission))


def test_a_user_holds_no_write_permission() -> None:
    assert not has_permission("user", Permission.ML_OPERATE)
    assert not has_permission("user", Permission.DEPLOYMENTS_MANAGE)
    assert has_permission("user", Permission.PREDICT)  # approved D3: predictions and SHAP/LIME


def test_permission_names_are_sorted_strings_for_the_api() -> None:
    names = permission_names("admin")
    assert names == sorted(ADMIN_PERMISSIONS)
    assert all(isinstance(n, str) for n in names)


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("user", Role.USER),
        ("admin", Role.ADMIN),
        ("superadmin", Role.SUPERADMIN),
        ("viewer", Role.USER),  # pre-RBAC-v2 name
        ("ml_engineer", Role.USER),  # never promoted: least privilege until reviewed
        ("ADMIN", None),
        ("root", None),
        ("", None),
        (None, None),
    ],
)
def test_stored_values_map_to_an_effective_role_without_promotion(stored, expected) -> None:
    assert effective_role(stored) == expected
    if expected is None:
        assert permissions_for(stored) == frozenset()
    else:
        assert permissions_for(stored) == ROLE_PERMISSIONS[expected]


def test_legacy_aliases_never_exceed_user() -> None:
    assert set(LEGACY_ROLE_ALIASES.values()) == {Role.USER}
    assert permissions_for("ml_engineer") == permissions_for("user")


@pytest.mark.parametrize(
    ("stored", "full"),
    [("superadmin", True), ("admin", True), ("user", False), ("viewer", False), ("ml_engineer", False), ("zzz", False)],
)
def test_full_resource_access_is_for_admin_and_superadmin_only(stored, full) -> None:
    assert has_full_resource_access(stored) is full


# --- deny-by-default --------------------------------------------------------------------------


@pytest.fixture
def app(make_settings, session_factory) -> FastAPI:
    application = create_app(make_settings(APP_ENV="testing", RATE_LIMIT_ENABLED=False))

    def _get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db] = _get_db
    return application


def _login(client: TestClient, email: str) -> dict:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_a_route_with_no_declared_policy_is_refused_for_everyone(app, session_factory) -> None:
    """Forgetting to protect a new route must fail closed, not open."""

    @app.get("/_test/forgotten")
    def forgotten() -> dict:
        return {"secret": "reachable"}

    @app.get("/_test/intentionally-public", dependencies=[PublicRoute])
    def public() -> dict:
        return {"ok": True}

    insert_account(session_factory, "root@x.com", "superadmin")
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = _login(client, "root@x.com")
        for credentials in ({}, headers):  # anonymous and even a superadmin
            denied = client.get("/_test/forgotten", headers=credentials)
            assert denied.status_code == 403
            assert "reachable" not in denied.text
            assert "no declared access policy" in denied.text
        assert client.get("/_test/intentionally-public").json() == {"ok": True}


def test_every_registered_route_declares_a_policy(app) -> None:
    routes = list(iter_api_routes(app))
    assert len(routes) > 50, "route discovery must find the whole API"
    undeclared = [(m, p) for m, p, route in routes if not route_has_policy(route)]
    assert undeclared == []


# --- the endpoint matrix ----------------------------------------------------------------------

PUBLIC, USER, ADMIN, SUPERADMIN = "public", "user", "admin", "superadmin"
RANK = {None: -1, USER: 0, ADMIN: 1, SUPERADMIN: 2}

# (method, path, lowest role allowed). {} stands for an id.
ENDPOINTS: list[tuple[str, str, str]] = [
    # public
    ("GET", "/", PUBLIC),
    ("GET", "/health", PUBLIC),
    ("GET", "/metrics", PUBLIC),
    ("GET", f"{API}/health", PUBLIC),
    ("POST", f"{API}/auth/login", PUBLIC),
    ("POST", f"{API}/auth/refresh", PUBLIC),
    ("POST", f"{API}/auth/logout", PUBLIC),
    ("POST", f"{API}/auth/register", PUBLIC),
    # own account: any authenticated role
    ("GET", f"{API}/auth/me", USER),
    ("PATCH", f"{API}/auth/me", USER),
    ("POST", f"{API}/auth/change-password", USER),
    # reading: any authenticated role
    ("GET", f"{API}/datasets", USER),
    ("GET", f"{API}/datasets/{{}}", USER),
    ("GET", f"{API}/datasets/{{}}/summary", USER),
    ("GET", f"{API}/models", USER),
    ("GET", f"{API}/models/{{}}", USER),
    ("GET", f"{API}/deployments", USER),
    ("GET", f"{API}/deployments/{{}}", USER),
    ("GET", f"{API}/experiments", USER),
    ("GET", f"{API}/experiments/compare", USER),
    ("GET", f"{API}/experiments/{{}}", USER),
    ("GET", f"{API}/jobs", USER),
    ("GET", f"{API}/jobs/metrics", USER),
    ("GET", f"{API}/jobs/{{}}", USER),
    ("GET", f"{API}/jobs/{{}}/result", USER),
    ("GET", f"{API}/drift/overview", USER),
    ("GET", f"{API}/drift/alerts", USER),
    ("GET", f"{API}/drift/models/{{}}/alerts", USER),
    ("GET", f"{API}/drift/models/{{}}/reports", USER),
    ("GET", f"{API}/monitoring/overview", USER),
    ("GET", f"{API}/monitoring/models/{{}}", USER),
    ("GET", f"{API}/predictions/history", USER),
    ("GET", f"{API}/predictions/history/{{}}", USER),
    ("GET", f"{API}/models/{{}}/predictions/history", USER),
    ("GET", f"{API}/models/{{}}/explainability/summary", USER),
    ("GET", f"{API}/models/{{}}/explainability/feature-importance", USER),
    ("GET", f"{API}/ai/status", USER),
    # inference and explanations (approved D3): any authenticated role
    ("POST", f"{API}/models/{{}}/predict", USER),
    ("POST", f"{API}/models/{{}}/explainability/shap", USER),
    ("POST", f"{API}/models/{{}}/explainability/lime", USER),
    ("POST", f"{API}/embeddings", USER),
    ("POST", f"{API}/nlp/classify", USER),
    ("POST", f"{API}/tokens/count", USER),
    # ML management (approved D2): admin and superadmin
    ("POST", f"{API}/datasets", ADMIN),
    ("POST", f"{API}/datasets/validate", ADMIN),
    ("POST", f"{API}/models/train", ADMIN),
    ("POST", f"{API}/experiments", ADMIN),
    ("POST", f"{API}/experiments/{{}}/run", ADMIN),
    ("POST", f"{API}/experiments/{{}}/cancel", ADMIN),
    ("POST", f"{API}/experiments/{{}}/rerun", ADMIN),
    ("POST", f"{API}/jobs", ADMIN),
    ("POST", f"{API}/jobs/{{}}/cancel", ADMIN),
    ("POST", f"{API}/jobs/{{}}/retry", ADMIN),
    ("POST", f"{API}/drift/alerts/{{}}/resolve", ADMIN),
    ("POST", f"{API}/drift/models/{{}}/analyze-quality", ADMIN),
    ("POST", f"{API}/drift/models/{{}}/analyze-drift", ADMIN),
    ("POST", f"{API}/drift/models/{{}}/analyze-performance", ADMIN),
    ("POST", f"{API}/predictions/history/{{}}/ground-truth", ADMIN),
    ("POST", f"{API}/llm/chat", ADMIN),
    ("POST", f"{API}/nlp/analyze", ADMIN),
    ("POST", f"{API}/models/{{}}/deploy", ADMIN),
    ("POST", f"{API}/models/{{}}/undeploy", ADMIN),
    # user administration, audit and settings: superadmin only
    ("GET", f"{API}/auth/users", SUPERADMIN),
    ("POST", f"{API}/auth/users", SUPERADMIN),
    ("PATCH", f"{API}/auth/users/{{}}", SUPERADMIN),
    ("DELETE", f"{API}/auth/users/{{}}", SUPERADMIN),
    ("POST", f"{API}/auth/users/{{}}/superadmin", SUPERADMIN),
    ("DELETE", f"{API}/auth/users/{{}}/superadmin", SUPERADMIN),
    ("GET", f"{API}/audit-logs", SUPERADMIN),
    ("GET", f"{API}/system/settings", SUPERADMIN),
]


def _normalize(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


def test_the_matrix_covers_exactly_the_routes_the_app_serves(app) -> None:
    """Adding or removing a route without deciding its policy here fails the build."""
    served = {(m, _normalize(p)) for m, p, _ in iter_api_routes(app)}
    expected = {(m, p) for m, p, _ in ENDPOINTS}
    assert served - expected == set(), "routes missing from the matrix (decide their policy)"
    assert expected - served == set(), "matrix entries for routes that no longer exist"


@pytest.fixture
def tokens(app, session_factory):
    for email, role in (("root@x.com", "superadmin"), ("staff@x.com", "admin"), ("member@x.com", "user")):
        insert_account(session_factory, email, role)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, {
            None: {},
            USER: _login(client, "member@x.com"),
            ADMIN: _login(client, "staff@x.com"),
            SUPERADMIN: _login(client, "root@x.com"),
        }


def _call(client: TestClient, method: str, path: str, headers: dict):
    url = path.replace("{}", FAKE_ID)
    if "/auth/users/" in url and method == "DELETE" and not url.endswith("/superadmin"):
        url += "?confirm_email=nobody@x.com"
    kwargs = {"headers": headers}
    if method in {"POST", "PATCH", "PUT"}:
        kwargs["json"] = {}
    return client.request(method, url, **kwargs)


def test_every_endpoint_enforces_its_policy_for_every_role(tokens) -> None:
    client, headers = tokens
    wrong: list[str] = []
    for method, path, tier in ENDPOINTS:
        for who in (None, USER, ADMIN, SUPERADMIN):
            status = _call(client, method, path, headers[who]).status_code
            if tier == PUBLIC:
                ok = status not in (401, 403)
            elif who is None:
                ok = status == 401
            elif RANK[who] >= RANK[tier]:
                ok = status not in (401, 403)  # authorised: 404/422/200 are all fine
            else:
                ok = status == 403
            if not ok:
                wrong.append(f"{method} {path} as {who or 'anonymous'} -> {status} (needs {tier})")
    assert wrong == [], "\n" + "\n".join(wrong)


# --- direct API bypass attempts (the frontend is irrelevant to these) ------------------------


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_a_user_cannot_change_anything_through_the_api(tokens, method) -> None:
    """Every state-changing route in the matrix is closed to the read-only user (except the few
    that act on their own account or are read-class inference)."""
    client, headers = tokens
    own_or_read_class = {
        f"{API}/auth/me",
        f"{API}/auth/change-password",
        f"{API}/auth/login",
        f"{API}/auth/refresh",
        f"{API}/auth/logout",
        f"{API}/auth/register",
        f"{API}/models/{{}}/predict",
        f"{API}/models/{{}}/explainability/shap",
        f"{API}/models/{{}}/explainability/lime",
        f"{API}/embeddings",
        f"{API}/nlp/classify",
        f"{API}/tokens/count",
    }
    checked = 0
    for m, path, tier in ENDPOINTS:
        if m != method or path in own_or_read_class or tier == PUBLIC:
            continue
        checked += 1
        assert _call(client, m, path, headers[USER]).status_code == 403, (m, path)
    if method in ("POST", "DELETE", "PATCH"):
        assert checked > 0


def test_a_forged_or_unsigned_token_gets_nothing(tokens) -> None:
    client, _ = tokens
    # An unsigned ("alg": "none") token claiming superadmin, built here so no JWT literal sits in the repo.
    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    forged = {"Authorization": f"Bearer {part({'alg': 'none'})}.{part({'sub': '1', 'role': 'superadmin'})}."}
    for method, path in (("GET", f"{API}/auth/users"), ("GET", f"{API}/audit-logs"), ("POST", f"{API}/auth/users")):
        assert _call(client, method, path, forged).status_code == 401


def test_the_role_claim_in_a_token_is_not_trusted(tokens, session_factory) -> None:
    """Authorisation reads the account from the database, so demoting someone takes effect on
    their existing token immediately (the claim inside the JWT is informational)."""
    client, headers = tokens
    assert client.get(f"{API}/auth/users", headers=headers[SUPERADMIN]).status_code == 200
    from sqlalchemy import select

    from app.database.models.user import User

    with session_factory() as session:
        root = session.scalar(select(User).where(User.email == "root@x.com"))
        root.role = "user"
        session.commit()
    assert client.get(f"{API}/auth/users", headers=headers[SUPERADMIN]).status_code == 403
