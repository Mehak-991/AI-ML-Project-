export type AuditCategory = 'auth' | 'user_admin' | 'employee' | 'ml' | 'settings';

export interface AuditLogEntry {
  id: string;
  created_at: string;
  actor_id: string | null;
  actor_email: string | null;
  actor_role: string | null;
  action: string;
  category: AuditCategory;
  target_type: string | null;
  target_id: string | null;
  outcome: 'success' | 'failure' | string;
  ip_address: string | null;
  request_id: string | null;
  details: Record<string, unknown>;
}

export interface AuditLogList {
  items: AuditLogEntry[];
  total: number;
  offset: number;
  limit: number;
}

export interface AuditQuery {
  category?: AuditCategory;
  action?: string;
  offset?: number;
  limit?: number;
}

export interface SystemSettings {
  allow_self_registration: boolean;
  maintenance_mode: boolean;
  announcement_banner: string;
}
