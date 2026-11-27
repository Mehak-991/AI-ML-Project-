import React, { useEffect, useMemo, useState } from 'react';
import {
  BrainCircuit,
  ChevronRight,
  Cpu,
  Database,
  ExternalLink,
  History,
  LayoutDashboard,
  Layers,
  LogIn,
  LogOut,
  Megaphone,
  Menu,
  Server,
  Settings,
  ShieldAlert,
  UserSquare2,
  Users,
  X,
} from 'lucide-react';
import { DatasetManagementPage } from './pages/DatasetManagementPage';
import { ModelManagementPage } from './pages/ModelManagementPage';
import { PredictionManagementPage } from './pages/PredictionManagementPage';
import { DeploymentMonitoringPage } from './pages/DeploymentMonitoringPage';
import { UserManagementPage } from './pages/UserManagementPage';
import { DataDriftMonitoringPage } from './pages/DataDriftMonitoringPage';
import { ExperimentTrackingPage } from './pages/ExperimentTrackingPage';
import { ExplainabilityStudioPage } from './pages/ExplainabilityStudioPage';
import { JobManagementPage } from './pages/JobManagementPage';
import { DashboardPage } from './pages/DashboardPage';
import { EmployeesPage } from './pages/EmployeesPage';
import { AuditLogPage } from './pages/AuditLogPage';
import { SystemSettingsPage } from './pages/SystemSettingsPage';
import { AuthModal } from './components/AuthModal';
import { RequirePermission } from './components/RequirePermission';
import { useAuth } from './context/AuthContext';
import { adminApi } from './services/api';
import type { Permission } from './types/auth';
import { ROLE_LABELS } from './types/auth';

type NavTab =
  | 'dashboard'
  | 'employees'
  | 'models'
  | 'datasets'
  | 'training'
  | 'inference'
  | 'deployment'
  | 'drift'
  | 'explainability'
  | 'jobs'
  | 'users'
  | 'audit'
  | 'settings';

interface NavItem {
  id: NavTab;
  label: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  // Permission needed to see the module. The API enforces the same (and finer) rules.
  permission: Permission;
  section: 'workspace' | 'ml' | 'admin';
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', title: 'Dashboard', description: 'Your role, your permissions and a summary of the platform.', icon: <LayoutDashboard className="w-4 h-4" />, permission: 'settings:read', section: 'workspace' },
  { id: 'employees', label: 'Employees', title: 'Employee Directory', description: 'Employee records. Sensitive fields are visible to Admins and Super Admins only.', icon: <UserSquare2 className="w-4 h-4" />, permission: 'employees:read', section: 'workspace' },
  { id: 'models', label: 'Model Registry', title: 'Model Management & Analytics', description: 'Inspect model versioning, feature schemas, training duration, and split analytics.', icon: <Layers className="w-4 h-4" />, permission: 'ml:read', section: 'ml' },
  { id: 'datasets', label: 'Datasets', title: 'Dataset Management', description: 'Upload CSV/XLSX datasets, run pre-upload validations, and inspect schemas.', icon: <Database className="w-4 h-4" />, permission: 'ml:read', section: 'ml' },
  { id: 'training', label: 'AutoML & Experiments', title: 'Model Training Studio', description: 'Train supervised models on registered datasets.', icon: <Cpu className="w-4 h-4" />, permission: 'ml:read', section: 'ml' },
  { id: 'inference', label: 'Predictions & AI', title: 'Predictions & AI Engine', description: 'Batch predictions and local LLM inference (Ollama).', icon: <BrainCircuit className="w-4 h-4" />, permission: 'ml:write', section: 'ml' },
  { id: 'deployment', label: 'Deployment & Monitoring', title: 'Model Deployment & Monitoring', description: 'Deployment readiness, serving architecture and performance benchmarks.', icon: <Server className="w-4 h-4" />, permission: 'ml:read', section: 'ml' },
  { id: 'drift', label: 'Drift & Data Quality', title: 'Data Quality & Drift Monitoring', description: 'Feature distribution shifts (PSI/KS), missing values, outliers and degradation.', icon: <ShieldAlert className="w-4 h-4" />, permission: 'ml:read', section: 'ml' },
  { id: 'explainability', label: 'Explainability (XAI)', title: 'Explainability Studio', description: 'Global feature importance and local SHAP/LIME explanations.', icon: <BrainCircuit className="w-4 h-4" />, permission: 'ml:read', section: 'ml' },
  { id: 'jobs', label: 'Background Jobs', title: 'Background Jobs & Tasks', description: 'Queued, running and finished background jobs.', icon: <Layers className="w-4 h-4" />, permission: 'ml:read', section: 'ml' },
  { id: 'users', label: 'User Administration', title: 'User Administration', description: 'Accounts, roles and access.', icon: <Users className="w-4 h-4" />, permission: 'users:read', section: 'admin' },
  { id: 'audit', label: 'Audit Log', title: 'Audit Log', description: 'Who changed what, and when.', icon: <History className="w-4 h-4" />, permission: 'audit:read', section: 'admin' },
  { id: 'settings', label: 'System Settings', title: 'System Settings', description: 'Global application settings.', icon: <Settings className="w-4 h-4" />, permission: 'settings:read', section: 'admin' },
];

// Swagger lives on the backend. Same origin behind nginx ('/docs'); on a separate frontend
// host (e.g. Vercel) it is derived from VITE_API_BASE_URL ('https://api.example.com/api/v1').
const API_DOCS_URL = (() => {
  const base = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (!base || base.startsWith('/')) return '/docs';
  try {
    return new URL('/docs', base).toString();
  } catch {
    return '/docs';
  }
})();

const SECTION_LABELS: Record<NavItem['section'], string> = {
  workspace: 'Workspace',
  ml: 'ML Platform',
  admin: 'Administration',
};

export function App() {
  const { user, can, logout, sessionNotice, clearSessionNotice } = useAuth();
  const [activeTab, setActiveTab] = useState<NavTab>('dashboard');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [banner, setBanner] = useState('');

  // Only modules the signed-in role may open are listed.
  const visibleItems = useMemo(() => (user ? NAV_ITEMS.filter((i) => can(i.permission)) : []), [user, can]);
  // After sign-in, sign-out or a role change, a module the user cannot open falls back to the
  // dashboard (derived during render, so a forbidden page is never mounted).
  const active = visibleItems.find((i) => i.id === activeTab) ?? NAV_ITEMS[0];

  useEffect(() => {
    if (!user) {
      setBanner('');
      return;
    }
    adminApi
      .getSettings()
      .then((s) => setBanner(s.announcement_banner))
      .catch(() => setBanner(''));
  }, [user]);

  const navigate = (tab: string) => {
    const target = visibleItems.find((i) => i.id === tab);
    if (target) setActiveTab(target.id);
    setMobileMenuOpen(false);
  };

  const renderNav = (compact: boolean) =>
    (['workspace', 'ml', 'admin'] as const).map((section) => {
      const items = visibleItems.filter((i) => i.section === section);
      if (items.length === 0) return null;
      return (
        <div key={section} className="space-y-1.5">
          {!compact && (
            <div className="px-3 pt-3 pb-1 text-[10px] font-bold text-slate-500 uppercase tracking-wider font-mono">
              {SECTION_LABELS[section]}
            </div>
          )}
          {items.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => navigate(item.id)}
                title={compact ? item.label : undefined}
                aria-current={isActive ? 'page' : undefined}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                    : 'text-slate-400 hover:text-white hover:bg-slate-900'
                }`}
              >
                <div className="shrink-0">{item.icon}</div>
                {!compact && <span className="truncate text-left">{item.label}</span>}
              </button>
            );
          })}
        </div>
      );
    });

  const page = (() => {
    switch (active.id) {
      case 'dashboard':
        return <DashboardPage onNavigate={navigate} />;
      case 'employees':
        return <EmployeesPage />;
      case 'models':
        return <ModelManagementPage />;
      case 'datasets':
        return (
          <div className="bg-slate-950 text-slate-100 p-6 md:p-8 rounded-3xl shadow-lg border border-slate-800">
            <DatasetManagementPage />
          </div>
        );
      case 'training':
        return <ExperimentTrackingPage />;
      case 'inference':
        return <PredictionManagementPage />;
      case 'deployment':
        return <DeploymentMonitoringPage />;
      case 'drift':
        return <DataDriftMonitoringPage />;
      case 'explainability':
        return <ExplainabilityStudioPage />;
      case 'jobs':
        return <JobManagementPage />;
      case 'users':
        return <UserManagementPage />;
      case 'audit':
        return <AuditLogPage />;
      case 'settings':
        return <SystemSettingsPage onChanged={(s) => setBanner(s.announcement_banner)} />;
    }
  })();

  return (
    <div className="min-h-screen bg-slate-50 flex font-sans text-slate-800">
      <aside
        className={`hidden md:flex flex-col justify-between bg-slate-950 text-slate-200 border-r border-slate-900 transition-all duration-300 z-30 sticky top-0 h-screen ${
          sidebarCollapsed ? 'w-20' : 'w-64'
        }`}
      >
        <div className="flex flex-col flex-1 min-h-0">
          <div className="h-16 flex items-center justify-between px-5 border-b border-slate-900">
            <div className="flex items-center gap-3 overflow-hidden">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-blue-500 flex items-center justify-center shadow-lg shadow-indigo-600/30 shrink-0">
                <BrainCircuit className="w-5 h-5 text-white" />
              </div>
              {!sidebarCollapsed && (
                <div className="truncate">
                  <span className="font-bold text-white text-base tracking-tight">AIProject</span>
                  <p className="text-[10px] text-slate-400 font-mono">
                    {user ? ROLE_LABELS[user.role] : 'Not signed in'}
                  </p>
                </div>
              )}
            </div>
          </div>
          <nav className="p-3 flex-1 overflow-y-auto" aria-label="Main navigation">
            {user ? (
              renderNav(sidebarCollapsed)
            ) : (
              !sidebarCollapsed && <p className="px-3 py-4 text-xs text-slate-500">Sign in to see your modules.</p>
            )}
          </nav>
          {!sidebarCollapsed && (
            <a
              href={API_DOCS_URL}
              target="_blank"
              rel="noreferrer"
              className="mx-3 mb-4 p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-[11px] text-indigo-400 hover:text-indigo-300 font-semibold flex items-center justify-between"
            >
              <span>API documentation</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
        <div className="p-3 border-t border-slate-900 flex justify-end">
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-900 transition-colors text-xs"
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <ChevronRight className={`w-4 h-4 transition-transform duration-200 ${sidebarCollapsed ? '' : 'rotate-180'}`} />
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0 min-h-screen">
        <header className="h-16 bg-white border-b border-slate-200 px-6 flex items-center justify-between sticky top-0 z-20 shadow-sm">
          <div className="flex items-center gap-4 min-w-0">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden p-2 rounded-xl text-slate-600 hover:bg-slate-100"
              aria-label="Toggle menu"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
            <div className="min-w-0">
              <h1 className="text-lg font-bold text-slate-900 truncate">{user ? active.title : 'Welcome'}</h1>
              <p className="text-xs text-slate-500 hidden sm:block truncate">
                {user ? active.description : 'Sign in to access the platform.'}
              </p>
            </div>
          </div>

          {user ? (
            <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 py-1 px-2.5 rounded-xl">
              <div className="w-7 h-7 rounded-full bg-indigo-600 text-white font-bold flex items-center justify-center text-xs">
                {user.email.slice(0, 2).toUpperCase()}
              </div>
              <div className="hidden md:block text-left pr-1">
                <div className="text-xs font-semibold text-slate-800 leading-tight">
                  {user.full_name || user.email.split('@')[0]}
                </div>
                <div className="text-[10px] text-slate-500 font-mono">{ROLE_LABELS[user.role]}</div>
              </div>
              <button
                onClick={() => logout()}
                title="Sign out"
                aria-label="Sign out"
                className="p-1 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors ml-1 cursor-pointer"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <button
              onClick={() => setAuthModalOpen(true)}
              className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm cursor-pointer"
            >
              <LogIn className="w-3.5 h-3.5" />
              <span>Sign In</span>
            </button>
          )}
        </header>

        {mobileMenuOpen && user && (
          <div className="md:hidden bg-slate-950 border-b border-slate-900 p-4 text-slate-200">{renderNav(false)}</div>
        )}

        {sessionNotice && (
          <div role="alert" className="mx-6 mt-4 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-center justify-between gap-3">
            <span>{sessionNotice}</span>
            <span className="flex gap-2">
              <button
                onClick={() => {
                  clearSessionNotice();
                  setAuthModalOpen(true);
                }}
                className="font-semibold text-indigo-700"
              >
                Sign in
              </button>
              <button onClick={clearSessionNotice} aria-label="Dismiss" className="text-amber-700">
                <X className="w-3.5 h-3.5" />
              </button>
            </span>
          </div>
        )}

        {user && banner && (
          <div className="mx-6 mt-4 p-3 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-900 text-xs flex items-center gap-2">
            <Megaphone className="w-4 h-4 shrink-0" /> {banner}
          </div>
        )}

        <main className="flex-1 p-6 md:p-8 max-w-7xl w-full mx-auto">
          <RequirePermission permission={active.permission} onSignIn={() => setAuthModalOpen(true)}>
            {page}
          </RequirePermission>
        </main>

        <AuthModal isOpen={authModalOpen} onClose={() => setAuthModalOpen(false)} />

        <footer className="border-t border-slate-200 bg-white py-4 px-8 text-center text-xs text-slate-500">
          AIProject MLOps Platform · Access is enforced by the API for every request
        </footer>
      </div>
    </div>
  );
}

export default App;
