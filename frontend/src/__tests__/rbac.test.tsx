/**
 * Frontend role-based access: navigation, route guards, role-specific controls and
 * session expiry. The API module is mocked; the server's own enforcement is covered by
 * the backend test suite (tests/unit/test_rbac_roles.py).
 */
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Permission, User, UserRole } from '../types/auth';

const PERMISSIONS: Record<UserRole, Permission[]> = {
  user: ['employees:read', 'ml:read', 'settings:read'],
  admin: [
    'employees:read', 'ml:read', 'settings:read', 'employees:read_sensitive', 'employees:write',
    'ml:write', 'users:read', 'users:manage', 'audit:read',
  ],
  super_admin: [
    'employees:read', 'ml:read', 'settings:read', 'employees:read_sensitive', 'employees:write',
    'employees:delete', 'ml:write', 'ml:deploy', 'users:read', 'users:manage',
    'users:administer', 'audit:read', 'audit:read_all', 'settings:write',
  ],
};

const EMPLOYEE = {
  id: 'e1', employee_code: 'EMP-1', first_name: 'Ada', last_name: 'Lovelace',
  email: 'ada@example.com', department: 'Engineering', job_title: 'Analyst',
  employment_status: 'active', hire_date: '2024-01-01', manager_id: null,
  created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z',
};

const state: { role: UserRole } = { role: 'user' };
const token = { access: 'token' as string | null };

const userFor = (role: UserRole): User => ({
  id: `id-${role}`, email: `${role}@example.com`, full_name: `${role} person`, role,
  is_active: true, created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z',
});

vi.mock('../services/api', () => {
  const page = { items: [], total: 0, offset: 0, limit: 20 };
  return {
    SESSION_EXPIRED_EVENT: 'auth:session-expired',
    tokenStorage: {
      getAccessToken: () => token.access,
      getRefreshToken: () => 'refresh',
      setAccessToken: (t: string) => { token.access = t; },
      setRefreshToken: () => undefined,
      clear: () => { token.access = null; },
    },
    parseApiError: (e: unknown) => ({ code: 'x', message: String(e) }),
    authApi: {
      getMe: vi.fn(async () => userFor(state.role)),
      getMyPermissions: vi.fn(async () => ({ role: state.role, permissions: PERMISSIONS[state.role] })),
      getRegistrationStatus: vi.fn(async () => ({ allow_self_registration: true })),
      listUsers: vi.fn(async () => page),
      logout: vi.fn(async () => undefined),
    },
    employeeApi: {
      list: vi.fn(async () => {
        const sensitive = state.role !== 'user';
        const item = sensitive ? { ...EMPLOYEE, salary: '85000.00', phone: '+1 555' } : EMPLOYEE;
        return { items: [item], total: 1, offset: 0, limit: 20, sensitive_fields_included: sensitive };
      }),
      stats: vi.fn(async () => ({ total: 1, by_status: { active: 1 }, by_department: { Engineering: 1 } })),
    },
    adminApi: {
      getSettings: vi.fn(async () => ({ allow_self_registration: true, maintenance_mode: false, announcement_banner: '' })),
      listAuditLogs: vi.fn(async () => page),
    },
    datasetApi: { listDatasets: vi.fn(async () => page) },
    modelApi: { listModels: vi.fn(async () => page) },
  };
});

// Heavy ML pages are not under test here.
vi.mock('../pages/ModelManagementPage', () => ({ ModelManagementPage: () => <div>models page</div> }));
vi.mock('../pages/DatasetManagementPage', () => ({ DatasetManagementPage: () => <div>datasets page</div> }));
vi.mock('../pages/PredictionManagementPage', () => ({ PredictionManagementPage: () => <div>predictions</div> }));
vi.mock('../pages/DeploymentMonitoringPage', () => ({ DeploymentMonitoringPage: () => <div>deployments</div> }));
vi.mock('../pages/DataDriftMonitoringPage', () => ({ DataDriftMonitoringPage: () => <div>drift</div> }));
vi.mock('../pages/ExperimentTrackingPage', () => ({ ExperimentTrackingPage: () => <div>experiments</div> }));
vi.mock('../pages/ExplainabilityStudioPage', () => ({ ExplainabilityStudioPage: () => <div>xai</div> }));
vi.mock('../pages/JobManagementPage', () => ({ JobManagementPage: () => <div>jobs</div> }));

const { App } = await import('../App');
const { AuthProvider } = await import('../context/AuthContext');
const { EmployeesPage } = await import('../pages/EmployeesPage');
const { RequirePermission } = await import('../components/RequirePermission');

const renderWithAuth = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>);

const navLabels = async () => {
  const nav = await screen.findByRole('navigation', { name: 'Main navigation' });
  await within(nav).findByText('Dashboard');
  return within(nav).getAllByRole('button').map((b) => b.textContent?.trim());
};

beforeEach(() => {
  token.access = 'token';
});
afterEach(() => cleanup());

describe('navigation per role', () => {
  it('user sees read-only modules only', async () => {
    state.role = 'user';
    renderWithAuth(<App />);
    const labels = await navLabels();
    expect(labels).toContain('Employees');
    expect(labels).toContain('Model Registry');
    for (const hidden of ['User Administration', 'Audit Log', 'Predictions & AI']) {
      expect(labels).not.toContain(hidden);
    }
  });

  it('admin additionally sees user administration, audit log and predictions', async () => {
    state.role = 'admin';
    renderWithAuth(<App />);
    const labels = await navLabels();
    for (const shown of ['User Administration', 'Audit Log', 'Predictions & AI', 'System Settings']) {
      expect(labels).toContain(shown);
    }
  });

  it('dashboard states what the role can and cannot do', async () => {
    state.role = 'user';
    renderWithAuth(<App />);
    expect(await screen.findByText(/Signed in as/)).toHaveProperty('textContent', 'Signed in as User');
    expect(screen.getByText('Create, edit or delete any record')).toBeTruthy();
  });

  it('signed-out visitors get a sign-in prompt and no modules', async () => {
    token.access = null;
    renderWithAuth(<App />);
    expect(await screen.findByText('Sign in required')).toBeTruthy();
    expect(screen.getByText('Sign in to see your modules.')).toBeTruthy();
  });
});

describe('route guard', () => {
  it('blocks a role without the permission', async () => {
    state.role = 'user';
    renderWithAuth(
      <RequirePermission permission="audit:read">
        <div>secret audit page</div>
      </RequirePermission>
    );
    expect(await screen.findByText('Access restricted')).toBeTruthy();
    expect(screen.queryByText('secret audit page')).toBeNull();
  });

  it('renders children for a role with the permission', async () => {
    state.role = 'admin';
    renderWithAuth(
      <RequirePermission permission="audit:read">
        <div>secret audit page</div>
      </RequirePermission>
    );
    expect(await screen.findByText('secret audit page')).toBeTruthy();
  });
});

describe('employee page controls', () => {
  it('user: read-only, no salary column, no actions', async () => {
    state.role = 'user';
    renderWithAuth(<EmployeesPage />);
    expect(await screen.findByText('EMP-1')).toBeTruthy();
    expect(screen.queryByText('New employee')).toBeNull();
    expect(screen.queryByText('Salary')).toBeNull();
    expect(screen.queryByLabelText(/Edit Ada/)).toBeNull();
    expect(screen.getByText(/Read-only access/)).toBeTruthy();
  });

  it('admin: can create and edit, sees salary, cannot delete', async () => {
    state.role = 'admin';
    renderWithAuth(<EmployeesPage />);
    await screen.findByText('EMP-1');
    await waitFor(() => expect(screen.getByText('New employee')).toBeTruthy());
    expect(screen.getByText('Salary')).toBeTruthy();
    expect(screen.getByLabelText('Edit Ada Lovelace')).toBeTruthy();
    expect(screen.queryByLabelText('Delete Ada Lovelace')).toBeNull();
  });

  it('super admin: can also delete', async () => {
    state.role = 'super_admin';
    renderWithAuth(<EmployeesPage />);
    await screen.findByText('EMP-1');
    await waitFor(() => expect(screen.getByLabelText('Delete Ada Lovelace')).toBeTruthy());
  });
});

describe('session expiry', () => {
  it('signs the user out when the API reports the session cannot be renewed', async () => {
    state.role = 'admin';
    renderWithAuth(<App />);
    await navLabels();
    act(() => {
      window.dispatchEvent(new Event('auth:session-expired'));
    });
    expect(await screen.findByText('Your session has ended. Please sign in again.')).toBeTruthy();
    expect(screen.getByText('Sign in to see your modules.')).toBeTruthy();
  });
});
