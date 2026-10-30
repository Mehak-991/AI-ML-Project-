export type ColumnKind = 'numeric' | 'categorical' | 'boolean' | 'datetime' | 'text' | string;

export interface ColumnInfo {
  name: string;
  dtype: string;
  kind: ColumnKind;
}

export interface ValidationIssue {
  code: string;
  message: string;
  column?: string | null;
}

export interface ValidationReport {
  is_valid: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
}

export interface MissingColumn {
  column: string;
  missing_count: number;
  missing_ratio: number;
}

export interface MissingValueSummary {
  total_missing_cells: number;
  rows_with_missing: number;
  columns: MissingColumn[];
}

export interface DuplicateSummary {
  duplicate_rows: number;
  duplicate_ratio: number;
  sample_row_indices: number[];
}

export interface ColumnSummary {
  name: string;
  dtype: string;
  kind: string;
  missing_count: number;
  missing_ratio: number;
  unique_count: number;
  infinite_count?: number | null;
  stats?: Record<string, unknown> | null;
  top_values?: Array<Record<string, unknown>> | null;
}

export interface DatasetSummary {
  n_rows: number;
  n_columns: number;
  memory_bytes: number;
  columns: ColumnSummary[];
  missing_values: MissingValueSummary;
  duplicates: DuplicateSummary;
}

export interface DatasetRead {
  id: string;
  name: string;
  original_filename: string;
  file_format: string;
  size_bytes: number;
  sha256: string;
  n_rows: number;
  n_columns: number;
  columns: ColumnInfo[];
  created_at: string;
}

export interface DatasetCreateResponse {
  dataset: DatasetRead;
  validation: ValidationReport;
}

export interface DatasetValidationResponse {
  filename: string;
  file_format: string;
  size_bytes: number;
  validation: ValidationReport;
  summary: DatasetSummary;
}

export interface DatasetListResponse {
  items: DatasetRead[];
  total: number;
  offset: number;
  limit: number;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: unknown;
}

export interface ApiErrorResponse {
  error: ApiErrorBody;
}
