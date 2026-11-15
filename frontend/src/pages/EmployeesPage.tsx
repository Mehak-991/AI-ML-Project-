import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  UserSquare2,
  X,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { ReadOnlyNotice } from '../components/RequirePermission';
import { employeeApi, parseApiError } from '../services/api';
import type {
  Employee,
  EmployeeInput,
  EmployeeList,
  EmploymentStatus,
} from '../types/employee';
import { EMPLOYMENT_STATUS_LABELS } from '../types/employee';

const PAGE_SIZE = 20;

const STATUS_STYLES: Record<EmploymentStatus, string> = {
  active: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  on_leave: 'bg-amber-50 text-amber-700 border-amber-200',
  terminated: 'bg-slate-100 text-slate-600 border-slate-200',
};

const EMPTY_FORM: EmployeeInput & { employee_code: string } = {
  employee_code: '',
  first_name: '',
  last_name: '',
  email: '',
  department: '',
  job_title: '',
  employment_status: 'active',
  hire_date: new Date().toISOString().slice(0, 10),
  phone: '',
  salary: '',
  manager_id: null,
};

export const EmployeesPage: React.FC = () => {
  const { can } = useAuth();
  const canWrite = can('employees:write');
  const canDelete = can('employees:delete');

  const [data, setData] = useState<EmployeeList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [status, setStatus] = useState<EmploymentStatus | ''>('');
  const [offset, setOffset] = useState(0);

  const [editing, setEditing] = useState<Employee | 'new' | null>(null);
  const [deleting, setDeleting] = useState<Employee | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await employeeApi.list({
          search: appliedSearch || undefined,
          employment_status: status || undefined,
          offset,
          limit: PAGE_SIZE,
        })
      );
    } catch (err) {
      setError(parseApiError(err).message);
    } finally {
      setLoading(false);
    }
  }, [appliedSearch, status, offset]);

  useEffect(() => {
    load();
  }, [load]);

  const flash = (message: string) => {
    setSuccess(message);
    window.setTimeout(() => setSuccess(null), 4000);
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    setBusy(true);
    setError(null);
    try {
      await employeeApi.remove(deleting.id);
      flash(`Deleted ${deleting.first_name} ${deleting.last_name}.`);
      setDeleting(null);
      await load();
    } catch (err) {
      setError(parseApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  const sensitive = data?.sensitive_fields_included ?? false;
  const total = data?.total ?? 0;
  const columns = 6 + (sensitive ? 2 : 0) + (canWrite || canDelete ? 1 : 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <UserSquare2 className="w-5 h-5 text-indigo-600" /> Employee Directory
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            {canWrite
              ? 'Create and update employee records. Every change is recorded in the audit log.'
              : 'Browse employee records.'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3 py-2 text-xs font-medium rounded-lg border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
          {canWrite && (
            <button
              onClick={() => setEditing('new')}
              className="inline-flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm"
            >
              <Plus className="w-3.5 h-3.5" /> New employee
            </button>
          )}
        </div>
      </div>

      {!canWrite && <ReadOnlyNotice what="employee records" />}

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

      <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-2">
        <form
          className="relative flex-1"
          onSubmit={(e) => {
            e.preventDefault();
            setOffset(0);
            setAppliedSearch(search.trim());
          }}
        >
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            maxLength={100}
            placeholder="Search name, email, code or title… (Enter)"
            aria-label="Search employees"
            className="w-full pl-9 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          />
        </form>
        <select
          value={status}
          aria-label="Filter by status"
          onChange={(e) => {
            setOffset(0);
            setStatus(e.target.value as EmploymentStatus | '');
          }}
          className="px-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white"
        >
          <option value="">All statuses</option>
          {Object.entries(EMPLOYMENT_STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider">
                <th className="py-3 px-4">Code</th>
                <th className="py-3 px-4">Name</th>
                <th className="py-3 px-4">Department</th>
                <th className="py-3 px-4">Title</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Hired</th>
                {sensitive && <th className="py-3 px-4">Phone</th>}
                {sensitive && <th className="py-3 px-4 text-right">Salary</th>}
                {(canWrite || canDelete) && <th className="py-3 px-4 text-right">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && !data ? (
                <tr>
                  <td colSpan={columns} className="py-10 text-center text-slate-400">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-indigo-500" />
                    Loading employees…
                  </td>
                </tr>
              ) : !data || data.items.length === 0 ? (
                <tr>
                  <td colSpan={columns} className="py-10 text-center text-slate-400">
                    {appliedSearch || status
                      ? 'No employees match these filters.'
                      : canWrite
                        ? 'No employees yet. Use “New employee” to add the first record.'
                        : 'No employee records have been added yet.'}
                  </td>
                </tr>
              ) : (
                data.items.map((e) => (
                  <tr key={e.id} className="hover:bg-slate-50/60">
                    <td className="py-2.5 px-4 font-mono text-slate-600">{e.employee_code}</td>
                    <td className="py-2.5 px-4">
                      <div className="font-semibold text-slate-800">
                        {e.first_name} {e.last_name}
                      </div>
                      <div className="text-[11px] text-slate-400">{e.email}</div>
                    </td>
                    <td className="py-2.5 px-4 text-slate-600">{e.department}</td>
                    <td className="py-2.5 px-4 text-slate-600">{e.job_title}</td>
                    <td className="py-2.5 px-4">
                      <span className={`px-2 py-0.5 rounded-full border text-[11px] font-medium ${STATUS_STYLES[e.employment_status]}`}>
                        {EMPLOYMENT_STATUS_LABELS[e.employment_status]}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-slate-500">{e.hire_date}</td>
                    {sensitive && <td className="py-2.5 px-4 text-slate-500">{e.phone || '—'}</td>}
                    {sensitive && (
                      <td className="py-2.5 px-4 text-right font-mono text-slate-700">
                        {e.salary ? Number(e.salary).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '—'}
                      </td>
                    )}
                    {(canWrite || canDelete) && (
                      <td className="py-2.5 px-4 text-right whitespace-nowrap">
                        {canWrite && (
                          <button
                            onClick={() => setEditing(e)}
                            aria-label={`Edit ${e.first_name} ${e.last_name}`}
                            className="p-1.5 rounded text-slate-500 hover:text-indigo-600 hover:bg-indigo-50"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {canDelete && (
                          <button
                            onClick={() => setDeleting(e)}
                            aria-label={`Delete ${e.first_name} ${e.last_name}`}
                            className="p-1.5 rounded text-slate-500 hover:text-rose-600 hover:bg-rose-50"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <span>
            {total === 0 ? '0 records' : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total}`}
          </span>
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

      {editing && canWrite && (
        <EmployeeForm
          employee={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={async (saved, created) => {
            setEditing(null);
            flash(`${created ? 'Created' : 'Updated'} ${saved.first_name} ${saved.last_name}.`);
            await load();
          }}
        />
      )}

      {deleting && canDelete && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
          <div className="bg-white rounded-2xl p-6 max-w-sm w-full shadow-xl">
            <h3 className="text-sm font-bold text-slate-900">Delete employee permanently?</h3>
            <p className="text-xs text-slate-500 mt-2">
              {deleting.first_name} {deleting.last_name} ({deleting.employee_code}) will be removed. Direct
              reports lose their manager link. This cannot be undone; consider setting the status to
              “Terminated” instead.
            </p>
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setDeleting(null)} className="px-3 py-2 text-xs rounded-lg border border-slate-300">
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={busy}
                className="px-3 py-2 text-xs font-semibold rounded-lg bg-rose-600 hover:bg-rose-700 text-white disabled:opacity-50 inline-flex items-center gap-1.5"
              >
                {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />} Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const EmployeeForm: React.FC<{
  employee: Employee | null;
  onClose: () => void;
  onSaved: (employee: Employee, created: boolean) => void;
}> = ({ employee, onClose, onSaved }) => {
  const [form, setForm] = useState(() =>
    employee
      ? {
          ...EMPTY_FORM,
          ...employee,
          phone: employee.phone ?? '',
          salary: employee.salary ?? '',
        }
      : EMPTY_FORM
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: e.target.value });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setFieldErrors({});
    const payload: EmployeeInput = {
      first_name: form.first_name,
      last_name: form.last_name,
      email: form.email,
      department: form.department,
      job_title: form.job_title,
      employment_status: form.employment_status,
      hire_date: form.hire_date,
      phone: form.phone ? form.phone : null,
      salary: form.salary ? String(form.salary) : null,
    };
    try {
      const saved = employee
        ? await employeeApi.update(employee.id, payload)
        : await employeeApi.create({ ...payload, employee_code: form.employee_code });
      onSaved(saved, !employee);
    } catch (err) {
      const parsed = parseApiError(err);
      setError(parsed.message);
      if (Array.isArray(parsed.details)) {
        const map: Record<string, string> = {};
        for (const d of parsed.details as Array<{ loc?: unknown[]; msg?: string }>) {
          const field = d.loc?.[d.loc.length - 1];
          if (typeof field === 'string' && d.msg) map[field] = d.msg;
        }
        setFieldErrors(map);
      }
    } finally {
      setSaving(false);
    }
  };

  const input = (key: keyof typeof form, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label className="block">
      <span className="block text-[11px] font-semibold text-slate-600 mb-1">{label}</span>
      <input
        value={String(form[key] ?? '')}
        onChange={set(key)}
        className={`w-full px-3 py-1.5 text-xs border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 ${
          fieldErrors[key as string] ? 'border-rose-400' : 'border-slate-200'
        }`}
        {...props}
      />
      {fieldErrors[key as string] && (
        <span className="text-[10px] text-rose-600">{fieldErrors[key as string]}</span>
      )}
    </label>
  );

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <form onSubmit={submit} className="bg-white rounded-2xl p-6 max-w-2xl w-full shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-slate-900">
            {employee ? `Edit ${employee.first_name} ${employee.last_name}` : 'New employee'}
          </h3>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1 rounded hover:bg-slate-100">
            <X className="w-4 h-4" />
          </button>
        </div>
        {error && (
          <div role="alert" className="mb-3 p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs">
            {error}
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {employee ? (
            <div>
              <span className="block text-[11px] font-semibold text-slate-600 mb-1">Employee code</span>
              <div className="px-3 py-1.5 text-xs font-mono bg-slate-50 border border-slate-200 rounded-lg">
                {employee.employee_code} <span className="text-slate-400">(cannot change)</span>
              </div>
            </div>
          ) : (
            input('employee_code', 'Employee code *', { required: true, maxLength: 32, pattern: '[A-Za-z0-9][A-Za-z0-9_-]*' })
          )}
          {input('email', 'Work email *', { type: 'email', required: true, maxLength: 255 })}
          {input('first_name', 'First name *', { required: true, maxLength: 100 })}
          {input('last_name', 'Last name *', { required: true, maxLength: 100 })}
          {input('department', 'Department *', { required: true, maxLength: 100 })}
          {input('job_title', 'Job title *', { required: true, maxLength: 150 })}
          <label className="block">
            <span className="block text-[11px] font-semibold text-slate-600 mb-1">Status *</span>
            <select
              value={form.employment_status}
              onChange={set('employment_status')}
              className="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white"
            >
              {Object.entries(EMPLOYMENT_STATUS_LABELS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          {input('hire_date', 'Hire date *', { type: 'date', required: true })}
          {input('phone', 'Phone (sensitive)', { maxLength: 32 })}
          {input('salary', 'Annual salary (sensitive)', { type: 'number', min: 0, step: '0.01' })}
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button type="button" onClick={onClose} className="px-3 py-2 text-xs rounded-lg border border-slate-300">
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {employee ? 'Save changes' : 'Create employee'}
          </button>
        </div>
      </form>
    </div>
  );
};
