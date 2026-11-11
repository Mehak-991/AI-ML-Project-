import React, { Suspense, lazy, useState } from 'react';
import {
  Database,
  BrainCircuit,
  Cpu,
  Layers,
  Server,
  Settings,
  Menu,
  X,
  ExternalLink,
  ChevronRight,
  Users,
  LogIn,
  LogOut,
  ShieldAlert,
} from 'lucide-react';
import { AuthModal } from './components/AuthModal';
import { useAuth } from './context/AuthContext';
import type { Permission } from './types/auth';

// compose.yaml turns the API docs off by default, so production builds opt in to the links.
const SHOW_API_DOCS = import.meta.env.DEV || import.meta.env.VITE_SHOW_API_DOCS === 'true';

// Each page loads on first visit, so the charting code is not part of the initial download.
const DatasetManagementPage = lazy(() =>
  import('./pages/DatasetManagementPage').then((m) => ({ default: m.DatasetManagementPage }))
);
const ModelManagementPage = lazy(() =>
  import('./pages/ModelManagementPage').then((m) => ({ default: m.ModelManagementPage }))
);
const PredictionManagementPage = lazy(() =>
  import('./pages/PredictionManagementPage').then((m) => ({ default: m.PredictionManagementPage }))
);
const DeploymentMonitoringPage = lazy(() =>
  import('./pages/DeploymentMonitoringPage').then((m) => ({ default: m.DeploymentMonitoringPage }))
);
const AuditLogsPage = lazy(() =>
  import('./pages/AuditLogsPage').then((m) => ({ default: m.AuditLogsPage }))
);
const SystemSettingsPage = lazy(() =>
  import('./pages/SystemSettingsPage').then((m) => ({ default: m.SystemSettingsPage }))
);
const UserManagementPage = lazy(() =>
  import('./pages/UserManagementPage').then((m) => ({ default: m.UserManagementPage }))
);
const DataDriftMonitoringPage = lazy(() =>
  import('./pages/DataDriftMonitoringPage').then((m) => ({ default: m.DataDriftMonitoringPage }))
);
const ExperimentTrackingPage = lazy(() =>
  import('./pages/ExperimentTrackingPage').then((m) => ({ default: m.ExperimentTrackingPage }))
);
const ExplainabilityStudioPage = lazy(() =>
  import('./pages/ExplainabilityStudioPage').then((m) => ({ default: m.ExplainabilityStudioPage }))
);
const JobManagementPage = lazy(() =>
  import('./pages/JobManagementPage').then((m) => ({ default: m.JobManagementPage }))
);

type NavTab =
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

export function App() {
  const { user, loading, logout, can } = useAuth();
  const [activeTab, setActiveTab] = useState<NavTab>('models');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const [authModalOpen, setAuthModalOpen] = useState(false);

  const navItems: Array<{
    id: NavTab;
    label: string;
    icon: React.ReactNode;
    phase: string;
    /** Shown only when the server granted this permission; the API enforces it independently. */
    permission?: Permission;
  }> = [
    {
      id: 'models',
      label: 'Model Registry & Analytics',
      icon: <Layers className="w-4 h-4" />,
      phase: 'Phase 6',
    },
    {
      id: 'datasets',
      label: 'Dataset Management',
      icon: <Database className="w-4 h-4" />,
      phase: 'Phase 4',
    },
    {
      id: 'training',
      label: 'AutoML & Experiments',
      icon: <Cpu className="w-4 h-4" />,
      phase: 'Phase 12',
    },
    {
      id: 'inference',
      label: 'Predictions & AI',
      icon: <BrainCircuit className="w-4 h-4" />,
      phase: 'Phase 7',
    },
    {
      id: 'deployment',
      label: 'Deployment & Monitoring',
      icon: <Server className="w-4 h-4" />,
      phase: 'Phase 8 & 9',
    },
    {
      id: 'drift',
      label: 'Drift & Data Quality',
      icon: <ShieldAlert className="w-4 h-4" />,
      phase: 'Phase 11',
    },
    {
      id: 'explainability',
      label: 'Explainability (XAI)',
      icon: <BrainCircuit className="w-4 h-4" />,
      phase: 'Phase 13',
    },
    {
      id: 'jobs',
      label: 'Background Jobs & Tasks',
      icon: <Layers className="w-4 h-4" />,
      phase: 'Phase 14',
    },
    {
      id: 'users',
      label: 'User Administration',
      icon: <Users className="w-4 h-4" />,
      phase: 'Phase 10',
      permission: 'users:read',
    },
    {
      id: 'audit',
      label: 'Audit Logs',
      icon: <ShieldAlert className="w-4 h-4" />,
      phase: 'Security',
      permission: 'audit:read',
    },
    {
      id: 'settings',
      label: 'System Settings',
      icon: <Settings className="w-4 h-4" />,
      phase: 'System',
      permission: 'settings:read',
    },
  ];


  return (
    <div className="min-h-screen bg-slate-50 flex font-sans text-slate-800">
      {/* 1. Dark Navy Sidebar (Enterprise SaaS Theme) */}
      <aside
        className={`hidden md:flex flex-col justify-between bg-slate-950 text-slate-200 border-r border-slate-900 transition-all duration-300 z-30 sticky top-0 h-screen ${
          sidebarCollapsed ? 'w-20' : 'w-64'
        }`}
      >
        <div className="flex flex-col flex-1">
          {/* Logo & Platform Name */}
          <div className="h-16 flex items-center justify-between px-5 border-b border-slate-900">
            <div className="flex items-center gap-3 overflow-hidden">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-blue-500 flex items-center justify-center shadow-lg shadow-indigo-600/30 shrink-0">
                <BrainCircuit className="w-5 h-5 text-white" />
              </div>
              {!sidebarCollapsed && (
                <div className="truncate">
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-white text-base tracking-tight">AIProject</span>
                    <span className="text-[9px] px-1.5 py-0.2 rounded font-mono font-bold bg-indigo-900/70 text-indigo-300 border border-indigo-700/50">
                      MLOps
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-400 font-mono">v1.0.0 Production</p>
                </div>
              )}
            </div>
          </div>

          {/* Navigation Links */}
          <div className="p-3 space-y-1.5 flex-1">
            {!sidebarCollapsed && (
              <div className="px-3 py-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider font-mono">
                ML Platform Modules
              </div>
            )}
            {navItems
              .filter((item) => !item.permission || can(item.permission))
              .map((item) => {
                const isActive = activeTab === item.id;

              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  title={sidebarCollapsed ? item.label : undefined}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                    isActive
                      ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                      : 'text-slate-400 hover:text-white hover:bg-slate-900'
                  }`}
                >
                  <div className="shrink-0">{item.icon}</div>
                  {!sidebarCollapsed && (
                    <div className="flex-1 flex items-center justify-between truncate text-left">
                      <span>{item.label}</span>
                      <span
                        className={`text-[9px] px-1.5 py-0.2 rounded font-mono ${
                          isActive
                            ? 'bg-indigo-700 text-indigo-100'
                            : 'bg-slate-900 text-slate-500'
                        }`}
                      >
                        {item.phase}
                      </span>
                    </div>
                  )}
                </button>
              );
            })}
          </div>

          {/* Quick API status card in sidebar */}
          {!sidebarCollapsed && (
            <div className="p-4 mx-3 mb-4 rounded-xl bg-slate-900/80 border border-slate-800 text-xs">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="font-semibold text-slate-200">FastAPI ML Engine</span>
              </div>
              <p className="text-[11px] text-slate-400">
                Ingestion & Scikit-learn Ready
              </p>
              {SHOW_API_DOCS && (
                <a
                  href="/docs"
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2.5 flex items-center justify-between text-[11px] text-indigo-400 hover:text-indigo-300 font-semibold"
                >
                  <span>Swagger Specs</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          )}
        </div>

        {/* Sidebar Toggle at bottom */}
        <div className="p-3 border-t border-slate-900 flex justify-end">
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-900 transition-colors text-xs"
            title={sidebarCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
          >
            <ChevronRight
              className={`w-4 h-4 transition-transform duration-200 ${
                sidebarCollapsed ? '' : 'rotate-180'
              }`}
            />
          </button>
        </div>
      </aside>

      {/* 2. Main Content Container (Light Theme) */}
      <div className="flex-1 flex flex-col min-w-0 min-h-screen">
        {/* Header Bar */}
        <header className="h-16 bg-white border-b border-slate-200 px-6 flex items-center justify-between sticky top-0 z-20 shadow-sm">
          <div className="flex items-center gap-4">
            {/* Mobile menu trigger */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden p-2 rounded-xl text-slate-600 hover:bg-slate-100"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>

            <div>
              <h1 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                {activeTab === 'models' && 'Model Management & Analytics Dashboard'}
                {activeTab === 'datasets' && 'Dataset Management'}
                {activeTab === 'training' && 'Model Training Studio'}
                {activeTab === 'inference' && 'Predictions & AI Engine'}
                {activeTab === 'deployment' && 'Model Deployment & Monitoring Studio'}
                {activeTab === 'drift' && 'Data Quality & Drift Monitoring'}
                {activeTab === 'users' && 'Enterprise User Administration'}
                {activeTab === 'audit' && 'Audit Logs'}
                {activeTab === 'settings' && 'System Settings'}
              </h1>
              <p className="text-xs text-slate-500 hidden sm:block">
                {activeTab === 'models' &&
                  'Inspect model versioning, feature schemas, training duration, and split analytics.'}
                {activeTab === 'datasets' &&
                  'Upload CSV/XLSX datasets, run pre-upload validations, and inspect schemas.'}
                {activeTab === 'training' && 'Train supervised models on registered datasets.'}
                {activeTab === 'inference' && 'Execute batch predictions and LLM inference.'}
                {activeTab === 'deployment' &&
                  'Evaluate deployment readiness, inspect serving architecture, and audit performance benchmarks.'}
                {activeTab === 'drift' &&
                  'Detect feature distribution shifts (PSI/KS), missing value rates, outliers, and performance degradation.'}
                {activeTab === 'users' &&
                  'Role-Based Access Control, user provisioning, account statuses, and admin security.'}
                {activeTab === 'audit' && 'Append-only record of role changes and privileged operations.'}
                {activeTab === 'settings' && 'Runtime configuration and backend server properties.'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {SHOW_API_DOCS && (
              <a
                href="/docs"
                target="_blank"
                rel="noreferrer"
                className="hidden sm:flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 transition-colors"
              >
                <span>API Specs</span>
                <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
              </a>
            )}

            {user ? (
              <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 py-1 px-2.5 rounded-xl">
                <div className="w-7 h-7 rounded-full bg-indigo-600 text-white font-bold flex items-center justify-center text-xs">
                  {user.email.slice(0, 2).toUpperCase()}
                </div>
                <div className="hidden md:block text-left pr-1">
                  <div className="text-xs font-semibold text-slate-800 leading-tight">
                    {user.full_name || user.email.split('@')[0]}
                  </div>
                  <div className="text-[10px] text-slate-500 font-mono capitalize">
                    {user.role.replace('_', ' ')}
                  </div>
                </div>
                <button
                  onClick={() => logout()}
                  title="Sign Out"
                  className="p-1 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors ml-1 cursor-pointer"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setAuthModalOpen(true)}
                className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-all shadow-indigo-600/20 cursor-pointer"
              >
                <LogIn className="w-3.5 h-3.5" />
                <span>Sign In</span>
              </button>
            )}

            <div className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs font-semibold text-emerald-700">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              API Connected
            </div>
          </div>
        </header>


        {/* Mobile menu overlay */}
        {mobileMenuOpen && (
          <div className="md:hidden bg-slate-950 border-b border-slate-900 p-4 space-y-1.5 text-slate-200">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => {
                  setActiveTab(item.id);
                  setMobileMenuOpen(false);
                }}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-semibold ${
                  activeTab === item.id ? 'bg-indigo-600 text-white' : 'hover:bg-slate-900'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  {item.icon}
                  {item.label}
                </div>
                <span className="text-[10px] font-mono opacity-75">{item.phase}</span>
              </button>
            ))}
          </div>
        )}

        {/* Dynamic Main Workspace View */}
        <main className="flex-1 p-6 md:p-8 max-w-7xl w-full mx-auto">
          {!loading && !user ? (
            <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center max-w-md mx-auto my-12 shadow-sm">
              <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 mx-auto mb-4">
                <LogIn className="w-8 h-8" />
              </div>
              <h3 className="text-lg font-bold text-slate-900">Sign in to continue</h3>
              <p className="text-xs text-slate-500 mt-2">
                Datasets, models and monitoring data are only available to signed-in users.
              </p>
              <button
                onClick={() => setAuthModalOpen(true)}
                className="mt-5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-colors shadow-sm cursor-pointer"
              >
                Sign In
              </button>
            </div>
          ) : (
          <Suspense fallback={<div className="p-12 text-center text-xs text-slate-500">Loading...</div>}>
          {activeTab === 'models' && <ModelManagementPage />}

          {activeTab === 'inference' && <PredictionManagementPage />}

          {activeTab === 'deployment' && <DeploymentMonitoringPage />}

          {activeTab === 'drift' && <DataDriftMonitoringPage />}

          {activeTab === 'training' && <ExperimentTrackingPage />}

          {activeTab === 'explainability' && <ExplainabilityStudioPage />}

          {activeTab === 'jobs' && <JobManagementPage />}

          {activeTab === 'audit' && can('audit:read') && <AuditLogsPage />}

          {activeTab === 'settings' && can('settings:read') && <SystemSettingsPage />}

          {activeTab === 'datasets' && (
            <div className="bg-slate-950 text-slate-100 p-6 md:p-8 rounded-3xl shadow-lg border border-slate-800">
              <DatasetManagementPage />
            </div>
          )}

          {activeTab === 'users' && (
            can('users:read') ? (
              <UserManagementPage />
            ) : (
              <div className="bg-white border border-rose-200 rounded-2xl p-12 text-center max-w-md mx-auto my-12 shadow-sm">
                <div className="w-16 h-16 rounded-2xl bg-rose-50 border border-rose-100 flex items-center justify-center text-rose-600 mx-auto mb-4">
                  <ShieldAlert className="w-8 h-8" />
                </div>
                <h3 className="text-lg font-bold text-slate-900">Access Restricted</h3>
                <p className="text-xs text-slate-500 mt-2">
                  User Administration requires superadmin privileges. Please contact a superadmin or sign in with a superadmin account.
                </p>
                {!user && (
                  <button
                    onClick={() => setAuthModalOpen(true)}
                    className="mt-5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-colors shadow-sm cursor-pointer"
                  >
                    Sign In as Superadmin
                  </button>
                )}
              </div>
            )
          )}

          {activeTab !== 'models' &&
            activeTab !== 'datasets' &&
            activeTab !== 'training' &&
            activeTab !== 'inference' &&
            activeTab !== 'deployment' &&
            activeTab !== 'drift' &&
            activeTab !== 'explainability' &&
            activeTab !== 'users' &&
            activeTab !== 'audit' &&
            activeTab !== 'settings' && (
            <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center max-w-md mx-auto my-12 shadow-sm">
              <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 mx-auto mb-4">
                <Cpu className="w-8 h-8" />
              </div>
              <h3 className="text-lg font-bold text-slate-900 capitalize">{activeTab} View</h3>
              <p className="text-xs text-slate-500 mt-2">
                Phase 6 (Model Registry & Analytics), Phase 7 (Prediction Studio), Phase 8 (Deployment & Monitoring),
                and Phase 10 (Enterprise Security & RBAC) are active. Additional modules will unlock in subsequent phases.
              </p>
              <button
                onClick={() => setActiveTab('deployment')}
                className="mt-5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-colors shadow-sm cursor-pointer"
              >
                Go to Deployment & Monitoring
              </button>
            </div>
          )}
          </Suspense>
          )}
        </main>

        {/* Auth Modal for Login / Registration */}
        <AuthModal isOpen={authModalOpen} onClose={() => setAuthModalOpen(false)} />

        {/* Light Footer */}
        <footer className="border-t border-slate-200 bg-white py-4 px-8 text-center text-xs text-slate-500">
          AIProject Enterprise MLOps Platform • Phase 10: Authentication, Authorization & Enterprise Security
        </footer>
      </div>
    </div>
  );
}


export default App;
