import React from 'react';
import { Loader2, LogIn, ShieldAlert } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import type { Permission } from '../types/auth';

/**
 * Route guard for a page. Renders its children only for a signed-in user whose role holds
 * `permission`; otherwise an explanatory panel. This protects the UI only — the API
 * independently rejects the same requests with 401/403.
 */
export const RequirePermission: React.FC<{
  permission: Permission;
  onSignIn?: () => void;
  children: React.ReactNode;
}> = ({ permission, onSignIn, children }) => {
  const { user, loading, can } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-slate-400 text-sm gap-2" role="status">
        <Loader2 className="w-5 h-5 animate-spin" /> Checking your session…
      </div>
    );
  }

  if (!user) {
    return (
      <AccessPanel
        title="Sign in required"
        message="Sign in to view this part of the application."
        action={
          onSignIn && (
            <button
              onClick={onSignIn}
              className="mt-5 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold cursor-pointer"
            >
              <LogIn className="w-3.5 h-3.5" /> Sign in
            </button>
          )
        }
      />
    );
  }

  if (!can(permission)) {
    return (
      <AccessPanel
        title="Access restricted"
        message="Your role does not include access to this area. Contact a Super Admin if you need it."
      />
    );
  }

  return <>{children}</>;
};

const AccessPanel: React.FC<{ title: string; message: string; action?: React.ReactNode }> = ({
  title,
  message,
  action,
}) => (
  <div className="bg-white border border-rose-200 rounded-2xl p-12 text-center max-w-md mx-auto my-12 shadow-sm">
    <div className="w-16 h-16 rounded-2xl bg-rose-50 border border-rose-100 flex items-center justify-center text-rose-600 mx-auto mb-4">
      <ShieldAlert className="w-8 h-8" />
    </div>
    <h3 className="text-lg font-bold text-slate-900">{title}</h3>
    <p className="text-xs text-slate-500 mt-2">{message}</p>
    {action}
  </div>
);

/** Small read-only notice shown where a write action is hidden for the current role. */
export const ReadOnlyNotice: React.FC<{ what?: string }> = ({ what = 'this data' }) => (
  <div className="px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 text-[11px] text-slate-500">
    Read-only access: your role can view {what} but not change it.
  </div>
);
