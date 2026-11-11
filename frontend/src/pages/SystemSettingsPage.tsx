import React, { useEffect, useState } from 'react';
import { AlertCircle, RefreshCw, Settings } from 'lucide-react';
import type { SystemSettings } from '../types/auth';
import { parseApiError, systemApi } from '../services/api';

const yesNo = (v: boolean) => (v ? 'Yes' : 'No');

export const SystemSettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setSettings(await systemApi.getSettings());
    } catch (err) {
      setError(parseApiError(err).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const rows: Array<[string, string]> = settings
    ? [
        ['Application', settings.app_name],
        ['Environment', settings.environment],
        ['Release', settings.release ?? 'not set'],
        ['Package version', settings.version],
        ['API docs enabled', yesNo(settings.docs_enabled)],
        ['Log level', settings.log_level],
        ['Rate limiting', yesNo(settings.rate_limit_enabled)],
        ...Object.entries(settings.rate_limits_per_minute).map(
          ([name, n]): [string, string] => [`Rate limit: ${name} / minute`, String(n)]
        ),
        ['Max upload size (MB)', String(settings.max_upload_size_mb)],
        ['Max dataset rows', String(settings.max_dataset_rows)],
        ['Max dataset columns', String(settings.max_dataset_columns)],
        ['Max prediction records', String(settings.max_prediction_records)],
        ['Access token lifetime (min)', String(settings.access_token_minutes)],
        ['Refresh token lifetime (days)', String(settings.refresh_token_days)],
        ['Jobs run in the API process', yesNo(settings.job_inline_dispatch)],
        ['Job stale timeout (min)', String(settings.job_stale_timeout_minutes)],
        ['Database pool size', String(settings.database_pool_size)],
        ['Database max overflow', String(settings.database_max_overflow)],
        ['Metrics token configured', yesNo(settings.metrics_token_configured)],
        ['Rehash passwords on login', yesNo(settings.password_rehash_on_login)],
        ['Store new users as legacy "viewer"', yesNo(settings.rbac_store_legacy_viewer)],
        ['LLM provider', settings.llm_provider],
      ]
    : [];

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">System Settings</h1>
            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-amber-50 text-amber-700 border border-amber-200">
              Superadmin Only · Read-only
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Non-secret runtime configuration. Secrets such as keys, passwords and tokens are never shown. Change values through the
            server environment, not here.
          </p>
        </div>
        <button
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 text-xs font-medium rounded-lg border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 shadow-sm self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-sm flex items-start gap-3 shadow-sm">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <p className="text-xs text-rose-700">{error}</p>
        </div>
      )}

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
          <Settings className="w-4 h-4 text-indigo-600" />
          <h2 className="text-sm font-bold text-slate-900">Runtime configuration</h2>
        </div>
        <dl className="divide-y divide-slate-100 text-xs">
          {rows.length === 0 ? (
            <div className="py-8 text-center text-slate-400">{loading ? 'Loading settings...' : 'No data.'}</div>
          ) : (
            rows.map(([label, value]) => (
              <div key={label} className="flex items-center justify-between px-5 py-2.5">
                <dt className="text-slate-500">{label}</dt>
                <dd className="font-mono text-slate-800">{value}</dd>
              </div>
            ))
          )}
        </dl>
      </div>
    </div>
  );
};
