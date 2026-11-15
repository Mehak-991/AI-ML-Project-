export type EmploymentStatus = 'active' | 'on_leave' | 'terminated';

export const EMPLOYMENT_STATUS_LABELS: Record<EmploymentStatus, string> = {
  active: 'Active',
  on_leave: 'On leave',
  terminated: 'Terminated',
};

export interface Employee {
  id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  email: string;
  department: string;
  job_title: string;
  employment_status: EmploymentStatus;
  hire_date: string;
  manager_id: string | null;
  created_at: string;
  updated_at: string;
  // Present only for roles allowed to see sensitive fields (Admin, Super Admin).
  phone?: string | null;
  salary?: string | null;
  created_by_id?: string | null;
  updated_by_id?: string | null;
}

export interface EmployeeList {
  items: Employee[];
  total: number;
  offset: number;
  limit: number;
  sensitive_fields_included: boolean;
}

export interface EmployeeStats {
  total: number;
  by_status: Record<string, number>;
  by_department: Record<string, number>;
}

export interface EmployeeInput {
  employee_code?: string;
  first_name: string;
  last_name: string;
  email: string;
  department: string;
  job_title: string;
  employment_status: EmploymentStatus;
  hire_date: string;
  phone?: string | null;
  salary?: string | null;
  manager_id?: string | null;
}

export type EmployeeSort = 'last_name' | 'hire_date' | 'created_at' | 'department' | 'employee_code';

export interface EmployeeQuery {
  search?: string;
  department?: string;
  employment_status?: EmploymentStatus;
  sort?: EmployeeSort;
  descending?: boolean;
  offset?: number;
  limit?: number;
}
