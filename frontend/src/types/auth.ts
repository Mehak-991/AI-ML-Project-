// Must match the backend (app/core/permissions.py and the users.role CHECK constraint).
export type UserRole = 'user' | 'admin' | 'super_admin';

export type Permission =
  | 'employees:read'
  | 'employees:read_sensitive'
  | 'employees:write'
  | 'employees:delete'
  | 'ml:read'
  | 'ml:write'
  | 'ml:deploy'
  | 'users:read'
  | 'users:manage'
  | 'users:administer'
  | 'audit:read'
  | 'audit:read_all'
  | 'settings:read'
  | 'settings:write';

export const ROLE_LABELS: Record<UserRole, string> = {
  user: 'User',
  admin: 'Admin',
  super_admin: 'Super Admin',
};

export const ROLE_RANK: Record<UserRole, number> = { user: 1, admin: 2, super_admin: 3 };

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserPermissions {
  role: UserRole;
  permissions: Permission[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
  user: User;
}

export interface UserListResponse {
  items: User[];
  total: number;
  offset: number;
  limit: number;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterCredentials {
  email: string;
  password: string;
  full_name?: string;
  // Only honoured by the server when an admin (role 'user') or super admin creates the account.
  role?: UserRole;
}

export interface UserUpdatePayload {
  role?: UserRole;
  is_active?: boolean;
  full_name?: string;
}
