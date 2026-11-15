import React, { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, Settings, ShieldAlert } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { ReadOnlyNotice } from '../components/RequirePermission';
import { adminApi, parseApiError } from '../services/api';
import type { SystemSettings } from '../types/admin';

/** Global runtime settings. Everyone signed in can read them; only Super Admins change them. */
export const SystemSettingsPage: React.FC<{ onChanged?: (s: SystemSettings) => void }> = ({ onChanged }) => {
  const { can } = useAuth();
  const canWrite = can('settings:write');

  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [banner, setBanner] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    adminApi
      .getSettings()
      .then((s) => {
        setSettings(s);
        setBanner(s.announcement_banner);
      })
      .catch((err) => setError(parseApiError(err).message))
      .finally(() => setLoading(false));
  }, []);

  const save = async (changes: Partial<SystemSettings>, label: string) => {
    setSaving(label);
    setError(null);
    setSuccess(null);
    try {
      const updated = await adminApi.updateSettings(changes);
      setSettings(updated);
      setBanner(updated.announcement_banner);
      onChanged?.(updated);
      setSuccess(`${label} saved.`);
    } catch (err) {
      setError(parseApiError(err).message);
    } finally {
      setSaving(null);
    }
  };

  if (loading) {
    return (
      <div className="py-16 text-center text-slate-400 text-xs" role="status">
        <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-indigo-500" /> Loading settings…
      </div>
    );
  }

  return (
    <div className="space-y-5 max-w-3xl">
      <div>
        <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
          <Settings className="w-5 h-5 text-indigo-600" /> System Settings
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Application-wide behaviour. Secrets (database, JWT key) are configured in the server
          environment and are never shown here.
        </p>
      </div>

      {!canWrite && <ReadOnlyNotice what="global settings" />}
      {error && (
        <div role="alert" className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}
      {success && (
        <div role="status" className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" /> {success}
        </div>
      )}

      {settings && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm divide-y divide-slate-100">
          <Toggle
            title="Allow self-registration"
            description="Anyone can create a read-only User account from the sign-in screen. When off, only administrators can create accounts."
            checked={settings.allow_self_registration}
            disabled={!canWrite || saving !== null}
            busy={saving === 'Self-registration'}
            onChange={(v) => save({ allow_self_registration: v }, 'Self-registration')}
          />
          <Toggle
            title="Maintenance mode"
            description="Blocks every data-changing request (uploads, training, employee edits, account changes) for everyone except Super Admins. Reads keep working."
            checked={settings.maintenance_mode}
            disabled={!canWrite || saving !== null}
            busy={saving === 'Maintenance mode'}
            danger
            onChange={(v) => save({ maintenance_mode: v }, 'Maintenance mode')}
          />
          <div className="p-5">
            <label htmlFor="banner" className="text-sm font-semibold text-slate-800">
              Announcement banner
            </label>
            <p className="text-xs text-slate-500 mt-0.5">Shown to every signed-in user. Leave empty to hide.</p>
            <div className="flex gap-2 mt-3">
              <input
                id="banner"
                value={banner}
                maxLength={500}
                disabled={!canWrite}
                onChange={(e) => setBanner(e.target.value)}
                className="flex-1 px-3 py-1.5 text-xs border border-slate-200 rounded-lg disabled:bg-slate-50"
              />
              {canWrite && (
                <button
                  disabled={saving !== null || banner === settings.announcement_banner}
                  onClick={() => save({ announcement_banner: banner }, 'Announcement')}
                  className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50"
                >
                  {saving === 'Announcement' ? 'Saving…' : 'Save'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const Toggle: React.FC<{
  title: string;
  description: string;
  checked: boolean;
  disabled: boolean;
  busy: boolean;
  danger?: boolean;
  onChange: (value: boolean) => void;
}> = ({ title, description, checked, disabled, busy, danger, onChange }) => (
  <div className="p-5 flex items-start justify-between gap-4">
    <div>
      <p className="text-sm font-semibold text-slate-800 flex items-center gap-1.5">
        {danger && checked && <ShieldAlert className="w-4 h-4 text-amber-500" />}
        {title}
      </p>
      <p className="text-xs text-slate-500 mt-0.5">{description}</p>
    </div>
    <button
      role="switch"
      aria-checked={checked}
      aria-label={title}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative shrink-0 w-11 h-6 rounded-full transition-colors disabled:opacity-50 ${
        checked ? (danger ? 'bg-amber-500' : 'bg-indigo-600') : 'bg-slate-300'
      }`}
    >
      {busy ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin text-white absolute top-1 left-1/2 -translate-x-1/2" />
      ) : (
        <span
          className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
            checked ? 'translate-x-5' : ''
          }`}
        />
      )}
    </button>
  </div>
);
