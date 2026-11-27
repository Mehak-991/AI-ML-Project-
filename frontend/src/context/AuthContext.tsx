import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { LoginCredentials, Permission, RegisterCredentials, User } from '../types/auth';
import { SESSION_EXPIRED_EVENT, authApi, parseApiError, tokenStorage } from '../services/api';

/**
 * Authentication state for the UI.
 *
 * `can()` only decides what to *show*. Every endpoint enforces permissions on the server
 * from the role stored in the database, so hiding a button is a convenience, never the
 * security boundary.
 */
interface AuthContextType {
  user: User | null;
  permissions: ReadonlySet<Permission>;
  loading: boolean;
  error: string | null;
  sessionNotice: string | null;
  can: (permission: Permission) => boolean;
  login: (creds: LoginCredentials) => Promise<void>;
  register: (creds: RegisterCredentials) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
  clearSessionNotice: () => void;
  refreshUser: () => Promise<void>;
}

const EMPTY: ReadonlySet<Permission> = new Set();

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [permissions, setPermissions] = useState<ReadonlySet<Permission>>(EMPTY);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);

  const resetSession = useCallback(() => {
    tokenStorage.clear();
    setUser(null);
    setPermissions(EMPTY);
  }, []);

  const loadProfile = useCallback(async () => {
    const [profile, perms] = await Promise.all([authApi.getMe(), authApi.getMyPermissions()]);
    setUser(profile);
    setPermissions(new Set(perms.permissions));
  }, []);

  const fetchCurrentUser = useCallback(async () => {
    if (!tokenStorage.getAccessToken()) {
      resetSession();
      setLoading(false);
      return;
    }
    try {
      await loadProfile();
    } catch {
      resetSession();
    } finally {
      setLoading(false);
    }
  }, [loadProfile, resetSession]);

  useEffect(() => {
    fetchCurrentUser();
  }, [fetchCurrentUser]);

  // The API client fires this when a token can no longer be refreshed (expired session,
  // password/role change, deactivation). Drop all client-side state immediately.
  useEffect(() => {
    const onExpired = () => {
      resetSession();
      setSessionNotice('Your session has ended. Please sign in again.');
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [resetSession]);

  const login = async (creds: LoginCredentials) => {
    setError(null);
    try {
      const data = await authApi.login(creds);
      tokenStorage.setAccessToken(data.access_token);
      tokenStorage.setRefreshToken(data.refresh_token);
      await loadProfile();
      setSessionNotice(null);
    } catch (err) {
      resetSession();
      setError(parseApiError(err).message);
      throw err;
    }
  };

  const register = async (creds: RegisterCredentials) => {
    setError(null);
    try {
      // The server decides whether the role is allowed: 'user' always; 'admin' and
      // 'super_admin' only through their one-time sign-up slot.
      await authApi.register({
        email: creds.email,
        password: creds.password,
        full_name: creds.full_name,
        role: creds.role ?? 'user',
      });
      await login({ email: creds.email, password: creds.password });
    } catch (err) {
      setError(parseApiError(err).message);
      throw err;
    }
  };

  const logout = async () => {
    const refresh = tokenStorage.getRefreshToken();
    if (refresh) {
      try {
        await authApi.logout(refresh);
      } catch {
        // The local session is cleared regardless.
      }
    }
    resetSession();
  };

  const can = useCallback((permission: Permission) => permissions.has(permission), [permissions]);

  return (
    <AuthContext.Provider
      value={{
        user,
        permissions,
        loading,
        error,
        sessionNotice,
        can,
        login,
        register,
        logout,
        clearError: () => setError(null),
        clearSessionNotice: () => setSessionNotice(null),
        refreshUser: fetchCurrentUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
