export type UserRole = 'admin' | 'ml_engineer' | 'viewer';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
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

export interface RegisterCredentials {
  email: string;
  password: string;
  full_name?: string;
  role?: UserRole;
}

export interface UserUpdatePayload {
  role?: UserRole;
  is_active?: boolean;
  full_name?: string;
}
