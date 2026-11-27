import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Crown,
  Loader2,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserPlus,
  Users,
  UserX,
} from 'lucide-react';
import type { User, UserRole } from '../types/auth';
import { ROLE_LABELS, ROLE_RANK } from '../types/auth';
import { authApi, parseApiError } from '../services/api';
import { useAuth } from '../context/AuthContext';

/**
 * Account administration.
 * - Super Admin: change roles, (de)activate and delete any other account, create any role.
 * - Admin: list accounts; (de)activate/rename 'user' accounts; create 'user' accounts.
 * The UI mirrors these rules for clarity; the API enforces them.
 */
export const UserManagementPage: React.FC = () => {
  const { user: currentUser, can } = useAuth();
  const canAdminister = can('users:administer');
  const canManage = can('users:manage');

  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const [searchTerm, setSearchTerm] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');

  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<User | null>(null);
  const [creating, setCreating] = useState(false);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authApi.listUsers({
        search: appliedSearch || undefined,
        role: roleFilter || undefined,
        is_active: statusFilter === '' ? undefined : statusFilter === 'active',
      });
      setUsers(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(parseApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, [appliedSearch, roleFilter, statusFilter]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  /** Mirrors the server rule: act only on other accounts ranked below you (Super Admin: anyone). */
  const canActOn = (target: User) =>
    target.id !== currentUser?.id &&
    canManage &&
    (canAdminister || ROLE_RANK[target.role] < ROLE_RANK[currentUser?.role ?? 'user']);

  const run = async (target: User, action: () => Promise<unknown>, message: string) => {
    setUpdatingId(target.id);
    setError(null);
    setSuccessMsg(null);
    try {
      await action();
      setSuccessMsg(message);
      await fetchUsers();
    } catch (err) {
      setError(parseApiError(err).message);
    } finally {
      setUpdatingId(null);
    }
  };

  const handleRoleChange = (target: User, newRole: UserRole) => {
    if (target.role === newRole) return;
    run(
      target,
      () => authApi.updateUser(target.id, { role: newRole }),
      `Updated ${target.email} to ${ROLE_LABELS[newRole]}. Their existing sessions were ended.`
    );
  };

  const handleToggleStatus = (target: User) => {
    const next = !target.is_active;
    run(
      target,
      () => authApi.updateUser(target.id, { is_active: next }),
      `${next ? 'Activated' : 'Deactivated'} ${target.email}.`
    );
  };

  const handleDelete = async () => {
    if (!deleting) return;
    const target = deleting;
    setDeleting(null);
    await run(target, () => authApi.deleteUser(target.id), `Deleted account ${target.email}.`);
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">User Administration</h1>
            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-purple-50 text-purple-700 border border-purple-200">
              {canAdminister ? 'Super Admin' : 'Admin · User accounts only'}
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Manage accounts and roles. Every change is recorded in the audit log.
          </p>
        </div>
        <div className="flex gap-2 self-start sm:self-auto">
          {canManage && (
            <button
              onClick={() => setCreating(true)}
              className="inline-flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm"
            >
              <UserPlus className="w-3.5 h-3.5" /> New account
            </button>
          )}
          <button
            onClick={fetchUsers}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3 py-2 text-xs font-medium rounded-lg border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-sm flex items-start gap-3 shadow-sm">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Action failed</p>
            <p className="text-xs text-rose-700 mt-0.5">{error}</p>
          </div>
        </div>
      )}
      {successMsg && (
        <div role="status" className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm flex items-start gap-3 shadow-sm">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
          <p>{successMsg}</p>
        </div>
      )}

      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setAppliedSearch(searchTerm.trim());
          }}
          className="relative flex-1 max-w-md"
        >
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            value={searchTerm}
            maxLength={255}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by email or name… (Enter)"
            aria-label="Search users"
            className="w-full pl-9 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
          />
        </form>
        <div className="flex items-center gap-2">
          <select
            value={roleFilter}
            aria-label="Filter by role"
            onChange={(e) => setRoleFilter(e.target.value)}
            className="px-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white text-slate-700"
          >
            <option value="">All roles</option>
            <option value="super_admin">Super Admin</option>
            <option value="admin">Admin</option>
            <option value="user">User</option>
          </select>
          <select
            value={statusFilter}
            aria-label="Filter by status"
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white text-slate-700"
          >
            <option value="">All statuses</option>
            <option value="active">Active only</option>
            <option value="inactive">Deactivated only</option>
          </select>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-indigo-600" />
            <h2 className="text-sm font-bold text-slate-900">Accounts</h2>
          </div>
          <span className="text-xs text-slate-500 font-mono">
            {total} {total === 1 ? 'account' : 'accounts'}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50/75 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
                <th className="py-3 px-4">User</th>
                <th className="py-3 px-4">Role</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Created</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && users.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-400">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-indigo-500" />
                    Loading accounts…
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-400">
                    No accounts match these filters.
                  </td>
                </tr>
              ) : (
                users.map((u) => {
                  const isCurrent = currentUser?.id === u.id;
                  const isUpdating = updatingId === u.id;
                  const actionable = canActOn(u);
                  return (
                    <tr key={u.id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-slate-700 to-slate-900 text-white font-bold flex items-center justify-center text-xs">
                            {u.email.slice(0, 2).toUpperCase()}
                          </div>
                          <div>
                            <div className="font-semibold text-slate-800 flex items-center gap-1.5">
                              <span>{u.full_name || 'Unnamed user'}</span>
                              {isCurrent && (
                                <span className="px-1.5 rounded text-[10px] font-bold bg-indigo-50 text-indigo-600 border border-indigo-200">
                                  You
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-400 font-mono">{u.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <RoleBadge role={u.role} />
                          {canAdminister && !isCurrent && (
                            <select
                              disabled={isUpdating}
                              value={u.role}
                              aria-label={`Change role of ${u.email}`}
                              onChange={(e) => handleRoleChange(u, e.target.value as UserRole)}
                              className="text-[11px] border border-slate-200 rounded px-1.5 py-0.5 bg-white text-slate-600 cursor-pointer disabled:opacity-50"
                            >
                              <option value="super_admin">Super Admin</option>
                              <option value="admin">Admin</option>
                              <option value="user">User</option>
                            </select>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        {u.is_active ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-rose-50 text-rose-700 border border-rose-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-rose-500" /> Deactivated
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-slate-500 text-[11px]">
                        <div className="flex items-center gap-1.5">
                          <Clock className="w-3.5 h-3.5 text-slate-400" />
                          <span>{new Date(u.created_at).toLocaleDateString()}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right whitespace-nowrap">
                        {!actionable ? (
                          <span className="text-[11px] text-slate-400">{isCurrent ? 'Your account' : 'Higher role'}</span>
                        ) : (
                          <>
                            <button
                              onClick={() => handleToggleStatus(u)}
                              disabled={isUpdating}
                              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium border transition-colors disabled:opacity-50 ${
                                u.is_active
                                  ? 'border-rose-200 text-rose-700 hover:bg-rose-50'
                                  : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50'
                              }`}
                            >
                              {u.is_active ? <UserX className="w-3 h-3" /> : <UserCheck className="w-3 h-3" />}
                              {u.is_active ? 'Deactivate' : 'Activate'}
                            </button>
                            {canAdminister && (
                              <button
                                onClick={() => setDeleting(u)}
                                disabled={isUpdating}
                                aria-label={`Delete ${u.email}`}
                                className="ml-1.5 inline-flex items-center px-2 py-1 rounded text-xs border border-rose-200 text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                              >
                                <Trash2 className="w-3 h-3" />
                              </button>
                            )}
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {deleting && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
          <div className="bg-white rounded-2xl p-6 max-w-sm w-full shadow-xl">
            <h3 className="text-sm font-bold text-slate-900">Delete {deleting.email}?</h3>
            <p className="text-xs text-slate-500 mt-2">
              The account and its sessions are removed permanently. Records it created (models,
              employees, audit entries) are kept. Deactivating is reversible; deleting is not.
            </p>
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setDeleting(null)} className="px-3 py-2 text-xs rounded-lg border border-slate-300">
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="px-3 py-2 text-xs font-semibold rounded-lg bg-rose-600 hover:bg-rose-700 text-white"
              >
                Delete account
              </button>
            </div>
          </div>
        </div>
      )}

      {creating && (
        <CreateAccountDialog
          allowedRoles={canAdminister ? ['user', 'admin', 'super_admin'] : ['user']}
          onClose={() => setCreating(false)}
          onCreated={async (created) => {
            setCreating(false);
            setSuccessMsg(`Created ${ROLE_LABELS[created.role]} account ${created.email}.`);
            await fetchUsers();
          }}
        />
      )}

      <div className="bg-slate-900 text-slate-200 rounded-xl p-5 border border-slate-800 shadow-md">
        <div className="flex items-center gap-2 mb-3">
          <ShieldAlert className="w-4 h-4 text-amber-400" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-white">
            Role-based access control (enforced by the API)
          </h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <RoleCard icon={<Crown className="w-3.5 h-3.5" />} title="Super Admin" color="text-purple-400">
            Full control: assigns roles, deletes accounts and employees, deploys models, manages
            global settings and reads the full audit log. The last active Super Admin cannot be
            removed, and nobody can change their own role.
          </RoleCard>
          <RoleCard icon={<ShieldCheck className="w-3.5 h-3.5" />} title="Admin" color="text-blue-400">
            Creates and edits any employee record, deletes only the ones they created, runs the ML
            lifecycle (upload, train, predict) and
            activates/deactivates User accounts. Cannot change roles or touch Admin/Super Admin
            accounts.
          </RoleCard>
          <RoleCard icon={<Shield className="w-3.5 h-3.5" />} title="User" color="text-slate-300">
            Strictly read-only: views employees (without salary or phone), dashboards, models and
            reports. Cannot change anything.
          </RoleCard>
        </div>
      </div>
    </div>
  );
};

const RoleBadge: React.FC<{ role: UserRole }> = ({ role }) => {
  const styles: Record<UserRole, { cls: string; icon: React.ReactNode }> = {
    super_admin: { cls: 'bg-purple-100 text-purple-800 border-purple-200', icon: <Crown className="w-3 h-3" /> },
    admin: { cls: 'bg-blue-100 text-blue-800 border-blue-200', icon: <ShieldCheck className="w-3 h-3" /> },
    user: { cls: 'bg-slate-100 text-slate-800 border-slate-200', icon: <Shield className="w-3 h-3" /> },
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${styles[role].cls}`}>
      {styles[role].icon}
      {ROLE_LABELS[role]}
    </span>
  );
};

const RoleCard: React.FC<{ icon: React.ReactNode; title: string; color: string; children: React.ReactNode }> = ({
  icon,
  title,
  color,
  children,
}) => (
  <div className="p-3 rounded-lg bg-slate-800/60 border border-slate-700/60">
    <p className={`font-semibold flex items-center gap-1.5 ${color}`}>
      {icon} {title}
    </p>
    <p className="text-slate-400 text-[11px] mt-1">{children}</p>
  </div>
);

const CreateAccountDialog: React.FC<{
  allowedRoles: UserRole[];
  onClose: () => void;
  onCreated: (user: User) => void;
}> = ({ allowedRoles, onClose, onCreated }) => {
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<UserRole>('user');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      onCreated(await authApi.register({ email: email.trim(), password, full_name: fullName.trim(), role }));
    } catch (err) {
      setError(parseApiError(err).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <form onSubmit={submit} className="bg-white rounded-2xl p-6 max-w-sm w-full shadow-xl space-y-3">
        <h3 className="text-sm font-bold text-slate-900">New account</h3>
        {error && (
          <div role="alert" className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs">
            {error}
          </div>
        )}
        <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)}
          placeholder="Email" aria-label="Email" className="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-lg" />
        <input value={fullName} maxLength={255} onChange={(e) => setFullName(e.target.value)}
          placeholder="Full name" aria-label="Full name" className="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-lg" />
        <input required type="password" minLength={8} maxLength={128} value={password} autoComplete="new-password"
          onChange={(e) => setPassword(e.target.value)} aria-label="Initial password"
          placeholder="Initial password (8+ chars, upper, lower, digit)"
          className="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-lg" />
        <select value={role} onChange={(e) => setRole(e.target.value as UserRole)} aria-label="Role"
          className="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white">
          {allowedRoles.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]}
            </option>
          ))}
        </select>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-xs rounded-lg border border-slate-300">
            Cancel
          </button>
          <button type="submit" disabled={saving}
            className="px-3 py-2 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50 inline-flex items-center gap-1.5">
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />} Create
          </button>
        </div>
      </form>
    </div>
  );
};
