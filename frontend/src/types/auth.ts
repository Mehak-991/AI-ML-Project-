/** The only roles the platform has. */
export type UserRole = 'user' | 'admin' | 'superadmin';

/** Roles an administrator may assign through the API. Superadmin has its own grant/revoke call. */
export type AssignableRole = 'user' | 'admin';

/**
 * Permission names, computed by the backend and returned by `GET /auth/me`.
 *
 * The UI decides what to show from this list only (see `can()` in AuthContext). It never infers
 * rights from the role name, so the backend permission registry stays the single source of truth.
 */
export type Permission =
  | 'resources:read'
  | 'predict:run'
  | 'ml:operate'
  | 'deployments:manage'
  | 'profile:manage'
  | 'users:read'
  | 'users:manage'
  | 'roles:assign'
  | 'superadmin:grant'
  | 'audit:read'
  | 'settings:read'
  | 'billing:read';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  permissions: Permission[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
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

/** Public registration has no role: every self-registered account is a read-only user. */
export interface RegisterCredentials {
  email: string;
  password: string;
  full_name?: string;
}

/** Account creation by a superadmin. */
export interface UserCreatePayload {
  email: string;
  password: string;
  full_name?: string;
  role: AssignableRole;
}

export interface UserUpdatePayload {
  role?: AssignableRole;
  is_active?: boolean;
  full_name?: string;
}

export interface AuditLogEntry {
  id: string;
  created_at: string;
  action: string;
  actor_id: string | null;
  actor_email: string | null;
  actor_role: string | null;
  target_id: string | null;
  target_email: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  detail: string | null;
  request_id: string | null;
  client_ip: string | null;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  total: number;
  offset: number;
  limit: number;
}

/** Non-secret runtime settings; the superadmin-only read-only view. */
export interface SystemSettings {
  app_name: string;
  environment: string;
  version: string;
  release: string | null;
  docs_enabled: boolean;
  log_level: string;
  rate_limit_enabled: boolean;
  rate_limits_per_minute: Record<string, number>;
  max_upload_size_mb: number;
  max_dataset_rows: number;
  max_dataset_columns: number;
  max_prediction_records: number;
  access_token_minutes: number;
  refresh_token_days: number;
  job_inline_dispatch: boolean;
  job_stale_timeout_minutes: number;
  database_pool_size: number;
  database_max_overflow: number;
  metrics_token_configured: boolean;
  password_rehash_on_login: boolean;
  rbac_store_legacy_viewer: boolean;
  llm_provider: string;
}
