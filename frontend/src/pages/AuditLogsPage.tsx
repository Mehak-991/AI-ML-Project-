import React, { useCallback, useEffect, useState } from 'react';
import { AlertCircle, ChevronLeft, ChevronRight, ClipboardList, RefreshCw } from 'lucide-react';
import type { AuditLogEntry } from '../types/auth';
import { auditApi, parseApiError } from '../services/api';

const PAGE_SIZE = 25;

/** Known action names, for the filter. The server accepts any value; this is only a convenience. */
const ACTION_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'All actions' },
  { value: 'user.created', label: 'User created' },
  { value: 'user.role_changed', label: 'Role changed' },
  { value: 'user.deactivated', label: 'User deactivated' },
  { value: 'user.reactivated', label: 'User reactivated' },
  { value: 'user.deleted', label: 'User deleted' },
  { value: 'superadmin.granted', label: 'Superadmin granted' },
  { value: 'superadmin.revoked', label: 'Superadmin revoked' },
  { value: 'deployment.deployed', label: 'Model deployed' },
  { value: 'deployment.undeployed', label: 'Model undeployed' },
  { value: 'cli.superadmin_bootstrap', label: 'Superadmin bootstrap (CLI)' },
  { value: 'cli.password_reset', label: 'Password reset (CLI)' },
  { value: 'migration.role_mapped', label: 'Role mapped by migration' },
];

const formatChange = (entry: AuditLogEntry): string => {
  const render = (value: Record<string, unknown> | null) =>
    value ? Object.entries(value).map(([k, v]) => `${k}: ${String(v)}`).join(', ') : '';
  const before = render(entry.before);
  const after = render(entry.after);
  if (before && after) return `${before} → ${after}`;
  return after || before || entry.detail || '';
};

export const AuditLogsPage: React.FC = () => {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [action, setAction] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await auditApi.list({ action: action || undefined, offset, limit: PAGE_SIZE });
      setEntries(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(parseApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, [action, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);
  const page = Math.floor(offset / PAGE_SIZE);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Audit Logs</h1>
            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-amber-50 text-amber-700 border border-amber-200">
              Superadmin Only
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Append-only record of role changes, account lifecycle events and privileged operations.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <select
            value={action}
            onChange={(e) => {
              setOffset(0);
              setAction(e.target.value);
            }}
            aria-label="Filter by action"
            className="px-3 py-2 text-xs border border-slate-300 rounded-lg bg-white text-slate-700"
          >
            {ACTION_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3 py-2 text-xs font-medium rounded-lg border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-sm flex items-start gap-3 shadow-sm">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <p className="text-xs text-rose-700">{error}</p>
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ClipboardList className="w-4 h-4 text-indigo-600" />
            <h2 className="text-sm font-bold text-slate-900">Recorded events</h2>
          </div>
          <span className="text-xs text-slate-500 font-mono">{total} entries</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50/75 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
                <th className="py-3 px-4">When</th>
                <th className="py-3 px-4">Action</th>
                <th className="py-3 px-4">By</th>
                <th className="py-3 px-4">Target</th>
                <th className="py-3 px-4">Change</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {entries.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-400">
                    {loading ? 'Loading audit log...' : 'No audit entries match.'}
                  </td>
                </tr>
              ) : (
                entries.map((e) => (
                  <tr key={e.id} className="hover:bg-slate-50/50">
                    <td className="py-3 px-4 text-slate-500 font-mono text-[11px] whitespace-nowrap">
                      {new Date(e.created_at).toLocaleString()}
                    </td>
                    <td className="py-3 px-4 font-semibold text-slate-800 font-mono text-[11px]">{e.action}</td>
                    <td className="py-3 px-4 text-slate-600">{e.actor_email ?? '—'}</td>
                    <td className="py-3 px-4 text-slate-600">{e.target_email ?? '—'}</td>
                    <td className="py-3 px-4 text-slate-500 text-[11px]">{formatChange(e)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="px-5 py-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <span>
            Page {page + 1} of {lastPage + 1}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0 || loading}
              aria-label="Previous page"
              className="p-1.5 rounded border border-slate-200 disabled:opacity-40"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={page >= lastPage || loading}
              aria-label="Next page"
              className="p-1.5 rounded border border-slate-200 disabled:opacity-40"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
