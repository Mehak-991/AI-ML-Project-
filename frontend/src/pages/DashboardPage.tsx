import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  Crown,
  Database,
  Eye,
  History,
  Layers,
  Loader2,
  ShieldCheck,
  UserSquare2,
  Users,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import {
  adminApi,
  authApi,
  datasetApi,
  employeeApi,
  modelApi,
  parseApiError,
} from '../services/api';
import type { AuditLogEntry, SystemSettings } from '../types/admin';
import type { EmployeeStats } from '../types/employee';
import type { UserRole } from '../types/auth';
import { ROLE_LABELS } from '../types/auth';

const ROLE_SUMMARY: Record<UserRole, { icon: React.ReactNode; can: string[]; cannot: string[] }> = {
  user: {
    icon: <Eye className="w-5 h-5" />,
    can: ['View employee directory (without salary or phone)', 'View datasets, models, monitoring and drift reports'],
    cannot: ['Create, edit or delete any record', 'Run training, predictions or LLM features', 'Access administration'],
  },
  admin: {
    icon: <ShieldCheck className="w-5 h-5" />,
    can: [
      'Create and update any employee record',
      'Upload datasets, train models, run predictions, experiments and jobs',
      'Activate or deactivate User accounts',
      'Review the employee and ML audit trail',
    ],
    cannot: ['Delete employees', 'Deploy models', 'Change roles or manage Admin/Super Admin accounts', 'Change global settings'],
  },
  super_admin: {
    icon: <Crown className="w-5 h-5" />,
    can: [
      'Everything Admins can do',
      'Assign roles, deactivate and delete any account',
      'Delete employee records and deploy models',
      'Change global settings and read the full audit log',
    ],
    cannot: ['Change your own role or delete your own account'],
  },
};

interface Snapshot {
  employees?: EmployeeStats;
  datasets?: number;
  models?: number;
  audit?: AuditLogEntry[];
  usersByRole?: Partial<Record<UserRole, number>>;
  settings?: SystemSettings;
}

/** Landing page whose content depends on the signed-in role. */
export const DashboardPage: React.FC<{ onNavigate: (tab: string) => void }> = ({ onNavigate }) => {
  const { user, can } = useAuth();
  const [snapshot, setSnapshot] = useState<Snapshot>({});
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    const tasks: Array<Promise<Partial<Snapshot>>> = [
      employeeApi.stats().then((employees) => ({ employees })),
      datasetApi.listDatasets(0, 1).then((r) => ({ datasets: r.total })),
      modelApi.listModels(0, 1).then((r) => ({ models: r.total })),
    ];
    if (can('audit:read')) {
      tasks.push(adminApi.listAuditLogs({ limit: 6 }).then((r) => ({ audit: r.items })));
    }
    if (can('users:read')) {
      tasks.push(
        Promise.all(
          (['user', 'admin', 'super_admin'] as UserRole[]).map((role) =>
            authApi.listUsers({ role, limit: 1 }).then((r) => [role, r.total] as const)
          )
        ).then((pairs) => ({ usersByRole: Object.fromEntries(pairs) }))
      );
    }
    if (can('settings:write')) {
      tasks.push(adminApi.getSettings().then((settings) => ({ settings })));
    }
    Promise.allSettled(tasks).then((results) => {
      if (cancelled) return;
      const merged: Snapshot = {};
      const failures: string[] = [];
      for (const r of results) {
        if (r.status === 'fulfilled') Object.assign(merged, r.value);
        else failures.push(parseApiError(r.reason).message);
      }
      setSnapshot(merged);
      setErrors([...new Set(failures)]);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [can]);

  if (!user) return null;
  const summary = ROLE_SUMMARY[user.role];

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-slate-900 to-indigo-900 text-white rounded-2xl p-6 shadow-lg">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl bg-white/10 flex items-center justify-center">{summary.icon}</div>
          <div>
            <h2 className="text-lg font-bold">Welcome, {user.full_name || user.email.split('@')[0]}</h2>
            <p className="text-xs text-indigo-200">
              Signed in as <strong>{ROLE_LABELS[user.role]}</strong>
            </p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-5 text-xs">
          <div>
            <p className="font-semibold text-emerald-300 mb-1.5">You can</p>
            <ul className="space-y-1 text-indigo-100 list-disc list-inside">
              {summary.can.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="font-semibold text-rose-300 mb-1.5">You cannot</p>
            <ul className="space-y-1 text-indigo-100 list-disc list-inside">
              {summary.cannot.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {errors.length > 0 && (
        <div role="alert" className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs flex gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          Some figures could not be loaded: {errors.join('; ')}
        </div>
      )}

      {snapshot.settings?.maintenance_mode && (
        <div className="p-3 rounded-xl bg-amber-50 border border-amber-300 text-amber-900 text-xs">
          Maintenance mode is <strong>on</strong>: only Super Admins can make changes.
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Kpi loading={loading} icon={<UserSquare2 className="w-4 h-4" />} label="Employees"
          value={snapshot.employees?.total} hint={`${snapshot.employees?.by_status.active ?? 0} active`}
          onClick={() => onNavigate('employees')} />
        <Kpi loading={loading} icon={<Database className="w-4 h-4" />} label="Datasets"
          value={snapshot.datasets} onClick={() => onNavigate('datasets')} />
        <Kpi loading={loading} icon={<Layers className="w-4 h-4" />} label="Models visible to you"
          value={snapshot.models} onClick={() => onNavigate('models')} />
        {snapshot.usersByRole ? (
          <Kpi loading={loading} icon={<Users className="w-4 h-4" />} label="Accounts"
            value={Object.values(snapshot.usersByRole).reduce((a, b) => a + (b ?? 0), 0)}
            hint={`${snapshot.usersByRole.super_admin ?? 0} super · ${snapshot.usersByRole.admin ?? 0} admin · ${snapshot.usersByRole.user ?? 0} user`}
            onClick={() => onNavigate('users')} />
        ) : (
          <Kpi loading={loading} icon={<UserSquare2 className="w-4 h-4" />} label="Departments"
            value={snapshot.employees ? Object.keys(snapshot.employees.by_department).length : undefined} />
        )}
      </div>

      {snapshot.audit && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
          <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <History className="w-4 h-4 text-indigo-600" /> Recent activity
            </h3>
            <button onClick={() => onNavigate('audit')} className="text-xs text-indigo-600 font-semibold">
              View all
            </button>
          </div>
          {snapshot.audit.length === 0 ? (
            <p className="px-5 py-6 text-xs text-slate-400">No recorded activity yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {snapshot.audit.map((a) => (
                <li key={a.id} className="px-5 py-2.5 text-xs flex justify-between gap-3">
                  <span>
                    <span className="font-mono text-slate-700">{a.action}</span>{' '}
                    <span className="text-slate-400">by {a.actor_email ?? 'system'}</span>
                  </span>
                  <span className="text-slate-400 whitespace-nowrap">{new Date(a.created_at).toLocaleString()}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

const Kpi: React.FC<{
  loading: boolean;
  icon: React.ReactNode;
  label: string;
  value?: number;
  hint?: string;
  onClick?: () => void;
}> = ({ loading, icon, label, value, hint, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={!onClick}
    className="text-left bg-white rounded-xl border border-slate-200 p-4 shadow-sm hover:border-indigo-300 disabled:hover:border-slate-200 transition-colors"
  >
    <div className="flex items-center gap-2 text-slate-500 text-xs font-semibold">
      {icon} {label}
    </div>
    <div className="text-2xl font-bold text-slate-900 mt-2">
      {loading ? <Loader2 className="w-5 h-5 animate-spin text-slate-300" /> : value ?? '—'}
    </div>
    {hint && !loading && <div className="text-[11px] text-slate-400 mt-1">{hint}</div>}
  </button>
);
