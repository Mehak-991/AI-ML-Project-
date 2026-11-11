"""Static guards for the frontend side of RBAC v2.

The frontend has no test runner, so these inspect the source (and the production bundle when one
exists). They cannot replace backend enforcement, which is tested separately: hiding a control is
cosmetic. What they protect is that the UI decides from the server-computed permission list, that
it stays in step with the backend registry, and that every write action is hidden from users who
lack the permission.
"""

import re
from pathlib import Path

import pytest

from app.core.permissions import Permission, Role

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"


def _read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _sources() -> list[Path]:
    return [p for p in SRC.rglob("*") if p.suffix in {".ts", ".tsx"}]


# --- parity with the backend registry -----------------------------------------------------------


def test_frontend_roles_are_exactly_the_backend_roles() -> None:
    types = _flat(_read("types/auth.ts"))
    declared = re.search(r"export type UserRole = ([^;]+);", types).group(1)
    assert set(re.findall(r"'([a-z]+)'", declared)) == {r.value for r in Role}


def test_frontend_permission_names_match_the_backend_registry_exactly() -> None:
    """If a permission is added or renamed on the server, this fails until the UI type follows."""
    types = _read("types/auth.ts")
    block = re.search(r"export type Permission =(.*?);", types, re.S).group(1)
    assert set(re.findall(r"'([a-z]+:[a-z]+)'", block)) == {p.value for p in Permission}


def test_assignable_roles_never_include_superadmin() -> None:
    types = _flat(_read("types/auth.ts"))
    assignable = re.search(r"export type AssignableRole = ([^;]+);", types).group(1)
    assert set(re.findall(r"'([a-z]+)'", assignable)) == {"user", "admin"}


# --- the UI decides from permissions, never from role names -------------------------------------


def test_no_legacy_role_names_remain_in_the_frontend() -> None:
    offenders = [
        str(p.relative_to(ROOT))
        for p in _sources()
        if re.search(r"ml_engineer|['\"]viewer['\"]|adminOnly|requiredRoles", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_components_never_compare_a_role_name_to_decide_access() -> None:
    pattern = re.compile(r"\.role\s*[!=]==|role\s*===\s*['\"](user|admin|superadmin)['\"]")
    offenders = [str(p.relative_to(ROOT)) for p in _sources() if pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], "decide with can('<permission>') from the server-provided list"


def test_auth_context_exposes_can_backed_by_the_server_permission_list() -> None:
    context = _flat(_read("context/AuthContext.tsx"))
    assert "can: (permission: Permission) => boolean" in context
    assert "user?.permissions?.includes(permission)" in context
    assert "permissions: Permission[]" in _flat(_read("types/auth.ts"))


def test_public_registration_payload_has_no_role() -> None:
    types = _read("types/auth.ts")
    block = re.search(r"export interface RegisterCredentials \{(.*?)\}", types, re.S).group(1)
    assert "role" not in block
    assert "password" in block and "email" in block


def test_navigation_is_filtered_by_permission() -> None:
    app = _flat(_read("App.tsx"))
    assert ".filter((item) => !item.permission || can(item.permission))" in app
    for tab, permission in (("users", "users:read"), ("audit", "audit:read"), ("settings", "settings:read")):
        item = re.search(rf"id: '{tab}',(.*?)\}},", app)
        assert item and f"permission: '{permission}'" in item.group(1), tab
    # the privileged pages are rendered only behind the permission as well
    assert "can('audit:read') && <AuditLogsPage />" in app
    assert "can('settings:read') && <SystemSettingsPage />" in app
    assert "can('users:read') ?" in app


# --- write actions are hidden from users without the permission ----------------------------------


@pytest.mark.parametrize(
    ("file", "permission", "snippet"),
    [
        ("pages/DatasetManagementPage.tsx", "ml:operate", "can('ml:operate') && <DatasetUploadCard"),
        ("pages/JobManagementPage.tsx", "ml:operate", "const canOperate = can('ml:operate')"),
        ("pages/ExperimentTrackingPage.tsx", "ml:operate", "const canManage = can('ml:operate')"),
        ("pages/DataDriftMonitoringPage.tsx", "ml:operate", "const canAnalyze = can('ml:operate')"),
        ("components/PredictionActivityMonitoringTable.tsx", "ml:operate", "const canAnnotate = can('ml:operate')"),
        ("components/DeploymentConfigSection.tsx", "deployments:manage", "const canManageDeployments = can('deployments:manage')"),
    ],
)
def test_write_actions_are_gated_by_their_permission(file, permission, snippet) -> None:
    assert snippet in _flat(_read(file))


def test_job_actions_require_the_permission() -> None:
    jobs = _flat(_read("pages/JobManagementPage.tsx"))
    assert "{canOperate && (job.status === 'queued' || job.status === 'running') && (" in jobs
    assert "{canOperate && (job.status === 'failed' || job.status === 'cancelled') && (" in jobs


def test_deployment_buttons_are_inside_the_permission_check() -> None:
    cfg = _flat(_read("components/DeploymentConfigSection.tsx"))
    gate = cfg.index("{canManageDeployments && (")
    assert gate < cfg.index("Undeploy Active Model") and gate < cfg.index("Deploy to Production")


# --- user administration UI ----------------------------------------------------------------------


def test_user_administration_only_offers_assignable_roles() -> None:
    page = _read("pages/UserManagementPage.tsx")
    assert "ml_engineer" not in page
    # 'superadmin' is selectable only in the filter, never in an assignment dropdown
    assert page.count('<option value="superadmin">') == 1
    assert "authApi.createUser" in page and "authApi.register" not in page
    assert "authApi.grantSuperadmin" in page and "authApi.revokeSuperadmin" in page
    assert "const isSuperadmin = (u: User) => u.permissions.includes('superadmin:grant')" in page


def test_dangerous_user_actions_are_gated_and_never_offered_on_yourself() -> None:
    page = _flat(_read("pages/UserManagementPage.tsx"))
    assert "canGrantSuperadmin && !isCurrent && u.is_active && !isSuperadmin(u)" in page
    assert "canGrantSuperadmin && !isCurrent && isSuperadmin(u)" in page
    assert "can('users:manage') && !isCurrent && !u.is_active && !isSuperadmin(u)" in page
    assert "canAssignRoles && !isCurrent && !isSuperadmin(u)" in page


def test_api_client_has_the_audit_and_settings_calls() -> None:
    api = _read("services/api.ts")
    assert "export const auditApi" in api and "'/audit-logs'" in api
    assert "'/system/settings'" in api
    assert "`/auth/users/${userId}/superadmin`" in api


# --- built bundle -------------------------------------------------------------------------------


@pytest.mark.skipif(not (ROOT / "frontend" / "dist" / "assets").is_dir(), reason="no production build present")
def test_production_bundle_has_the_new_roles_and_none_of_the_old() -> None:
    bundle = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "frontend" / "dist" / "assets").glob("*.js")
    )
    assert "ml_engineer" not in bundle
    assert "Audit Logs" in bundle and "Superadmin" in bundle
    assert "superadmin:grant" in bundle and "audit:read" in bundle
