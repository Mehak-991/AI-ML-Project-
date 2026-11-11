import React, { useState } from 'react';
import { AlertCircle, CheckCircle2, KeyRound, UserCircle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { authApi, parseApiError } from '../services/api';

const MIN_PASSWORD_LENGTH = 8;

interface FeedbackMessage {
  ok: boolean;
  text: string;
}

const Feedback: React.FC<{ message: FeedbackMessage | null }> = ({ message }) =>
  message ? (
    <p
      role={message.ok ? 'status' : 'alert'}
      className={`mt-3 flex items-center gap-2 text-sm ${message.ok ? 'text-emerald-700' : 'text-rose-700'}`}
    >
      {message.ok ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
      {message.text}
    </p>
  ) : null;

const inputClass =
  'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500';

export const ProfilePage: React.FC = () => {
  const { user, refreshUser, logout } = useAuth();
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [profileMessage, setProfileMessage] = useState<FeedbackMessage | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordMessage, setPasswordMessage] = useState<FeedbackMessage | null>(null);
  const [changingPassword, setChangingPassword] = useState(false);

  if (!user) return null;

  const saveProfile = async (event: React.FormEvent) => {
    event.preventDefault();
    setSavingProfile(true);
    setProfileMessage(null);
    try {
      await authApi.updateMe({ full_name: fullName.trim() });
      await refreshUser();
      setProfileMessage({ ok: true, text: 'Profile updated.' });
    } catch (err) {
      setProfileMessage({ ok: false, text: parseApiError(err).message });
    } finally {
      setSavingProfile(false);
    }
  };

  const passwordProblem =
    newPassword.length > 0 && newPassword.length < MIN_PASSWORD_LENGTH
      ? `The new password needs at least ${MIN_PASSWORD_LENGTH} characters.`
      : confirmPassword.length > 0 && confirmPassword !== newPassword
        ? 'The two new passwords do not match.'
        : null;

  const submitPassword = async (event: React.FormEvent) => {
    event.preventDefault();
    if (passwordProblem || !currentPassword || !newPassword) return;
    setChangingPassword(true);
    setPasswordMessage(null);
    try {
      await authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordMessage({ ok: true, text: 'Password changed. Signing you out of every session...' });
      // The server revoked all refresh tokens, so the current session cannot continue.
      window.setTimeout(() => void logout(), 1500);
    } catch (err) {
      setPasswordMessage({ ok: false, text: parseApiError(err).message });
    } finally {
      setChangingPassword(false);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2 max-w-5xl">
      <section className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
        <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
          <UserCircle className="w-5 h-5 text-indigo-600" /> Your account
        </h2>
        <dl className="mt-4 grid grid-cols-3 gap-y-2 text-sm">
          <dt className="text-slate-500">Email</dt>
          <dd className="col-span-2 font-mono text-slate-800 break-all">{user.email}</dd>
          <dt className="text-slate-500">Role</dt>
          <dd className="col-span-2 capitalize text-slate-800">{user.role}</dd>
          <dt className="text-slate-500">Permissions</dt>
          <dd className="col-span-2 flex flex-wrap gap-1">
            {user.permissions.map((permission) => (
              <span
                key={permission}
                className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-xs font-mono"
              >
                {permission}
              </span>
            ))}
          </dd>
        </dl>
        <p className="mt-4 text-xs text-slate-500">
          Your role can only be changed by a superadmin. You cannot change it yourself.
        </p>

        <form onSubmit={saveProfile} className="mt-6">
          <label htmlFor="profile-full-name" className="block text-sm font-medium text-slate-700 mb-1">
            Display name
          </label>
          <input
            id="profile-full-name"
            type="text"
            value={fullName}
            maxLength={255}
            onChange={(event) => setFullName(event.target.value)}
            className={inputClass}
          />
          <button
            type="submit"
            disabled={savingProfile || fullName.trim() === (user.full_name ?? '')}
            className="mt-3 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold disabled:opacity-50 cursor-pointer"
          >
            {savingProfile ? 'Saving...' : 'Save name'}
          </button>
          <Feedback message={profileMessage} />
        </form>
      </section>

      <section className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
        <h2 className="flex items-center gap-2 text-base font-bold text-slate-900">
          <KeyRound className="w-5 h-5 text-indigo-600" /> Change password
        </h2>
        <p className="mt-1 text-xs text-slate-500">
          Changing your password signs you out everywhere. Sign in again with the new one.
        </p>
        <form onSubmit={submitPassword} className="mt-4 space-y-3" autoComplete="off">
          <div>
            <label htmlFor="current-password" className="block text-sm font-medium text-slate-700 mb-1">
              Current password
            </label>
            <input
              id="current-password"
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              className={inputClass}
              required
            />
          </div>
          <div>
            <label htmlFor="new-password" className="block text-sm font-medium text-slate-700 mb-1">
              New password
            </label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              className={inputClass}
              required
            />
          </div>
          <div>
            <label htmlFor="confirm-password" className="block text-sm font-medium text-slate-700 mb-1">
              Repeat new password
            </label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              className={inputClass}
              required
            />
          </div>
          {passwordProblem && (
            <p role="alert" className="text-sm text-rose-700">
              {passwordProblem}
            </p>
          )}
          <button
            type="submit"
            disabled={changingPassword || !!passwordProblem || !currentPassword || !newPassword || !confirmPassword}
            className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold disabled:opacity-50 cursor-pointer"
          >
            {changingPassword ? 'Changing...' : 'Change password'}
          </button>
          <Feedback message={passwordMessage} />
        </form>
      </section>
    </div>
  );
};
