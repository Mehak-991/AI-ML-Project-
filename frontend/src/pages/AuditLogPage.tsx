import React, { useCallback, useEffect, useState } from 'react';
import { AlertCircle, ChevronLeft, ChevronRight, History, Loader2, RefreshCw } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { adminApi, parseApiError } from '../services/api';
import type { AuditCategory, AuditLogList } from '../types/admin';

const PAGE_SIZE = 50;

const CATEGORY_LABELS: Record<AuditCategory, string> = {
  employee: 'Employees',
  ml: 'ML resources',
  auth: 'Authentication',
  user_admin: 'Account administration',
  settings: 'Settings',
};

/** Admins see employee + ML events; Super Admins see everything (enforced server-side). */
export const AuditLogPage: React.FC = () => {
  const { can } = useAuth();
  const seesAll = can('audit:read_all');
  const categories = (Object.keys(CATEGORY_LABELS) as AuditCategory[]).filter(
    (c) => seesAll || c === 'employee' || c === 'ml'
  );

  const [data, setData] = useState<AuditLogList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState<AuditCategory | ''>('');
  const [offset, setOffset] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await adminApi.listAuditLogs({ category: category || undefined, offset, limit: PAGE_SIZE }));
    } catch (err) {
      setError(parseApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, [category, offset]);

  useEffect(() => {
    load();
  }, [load]);

  const total = data?.total ?? 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <History className="w-5 h-5 text-indigo-600" /> Audit Log
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            {seesAll
              ? 'Every security-relevant and data-changing operation across the platform.'
              : 'Changes to employee records and ML resources.'}
          </p>
        </div>
        <div className="flex gap-2">
          <select
            value={category}
            aria-label="Filter by category"
            onChange={(e) => {
              setOffset(0);
              setCategory(e.target.value as AuditCategory | '');
            }}
            className="px-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white"
          >
            <option value="">All visible categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABELS[c]}
              </option>
            ))}
          </select>
          <button
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3 py-2 text-xs font-medium rounded-lg border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
                <th className="py-3 px-4">When</th>
                <th className="py-3 px-4">Actor</th>
                <th className="py-3 px-4">Action</th>
                <th className="py-3 px-4">Target</th>
                <th className="py-3 px-4">Outcome</th>
                <th className="py-3 px-4">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && !data ? (
                <tr>
                  <td colSpan={6} className="py-10 text-center text-slate-400">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-indigo-500" /> Loading audit trail…
                  </td>
                </tr>
              ) : !data || data.items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-10 text-center text-slate-400">
                    No audit entries{category ? ' in this category' : ''} yet.
                  </td>
                </tr>
              ) : (
                data.items.map((entry) => (
                  <tr key={entry.id} className="align-top hover:bg-slate-50/60">
                    <td className="py-2.5 px-4 text-slate-500 whitespace-nowrap">
                      {new Date(entry.created_at).toLocaleString()}
                    </td>
                    <td className="py-2.5 px-4">
                      <div className="text-slate-800">{entry.actor_email ?? '—'}</div>
                      <div className="text-[10px] text-slate-400">{entry.actor_role ?? ''}</div>
                    </td>
                    <td className="py-2.5 px-4 font-mono text-slate-700">{entry.action}</td>
                    <td className="py-2.5 px-4 text-slate-500">
                      {entry.target_type ? `${entry.target_type}` : '—'}
                      {entry.target_id && (
                        <div className="text-[10px] font-mono text-slate-400 truncate max-w-[10rem]" title={entry.target_id}>
                          {entry.target_id}
                        </div>
                      )}
                    </td>
                    <td className="py-2.5 px-4">
                      <span
                        className={`px-2 py-0.5 rounded-full border text-[11px] ${
                          entry.outcome === 'success'
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : 'bg-rose-50 text-rose-700 border-rose-200'
                        }`}
                      >
                        {entry.outcome}
                      </span>
                    </td>
                    <td className="py-2.5 px-4">
                      <code className="block text-[10px] text-slate-500 whitespace-pre-wrap break-all max-w-xs">
                        {Object.keys(entry.details).length ? JSON.stringify(entry.details) : '—'}
                      </code>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <span>{total === 0 ? '0 entries' : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total}`}</span>
          <div className="flex gap-1">
            <button
              disabled={offset === 0 || loading}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              aria-label="Previous page"
              className="p-1.5 rounded border border-slate-200 disabled:opacity-40"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <button
              disabled={offset + PAGE_SIZE >= total || loading}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              aria-label="Next page"
              className="p-1.5 rounded border border-slate-200 disabled:opacity-40"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
