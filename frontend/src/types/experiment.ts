export type ExperimentStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type SearchStrategy = 'none' | 'grid' | 'random';
export type ProblemType = 'classification' | 'regression';
export type Algorithm = 'linear' | 'random_forest';

export interface ExperimentRunRead {
  id: string;
  experiment_id: string;
  run_number: number;
  status: ExperimentStatus;
  best_hyperparameters?: Record<string, unknown> | null;
  validation_metrics?: Record<string, number> | null;
  test_metrics?: Record<string, number> | null;
  cv_results?: Record<string, unknown> | null;
  registered_model_id?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  execution_duration_seconds?: number | null;
  created_at: string;
}

export interface ExperimentRead {
  id: string;
  name: string;
  description?: string | null;
  dataset_id: string;
  target_column: string;
  problem_type: ProblemType;
  algorithm: Algorithm;
  selected_features?: string[] | null;
  hyperparameter_config: Record<string, unknown>;
  search_strategy: SearchStrategy;
  cv_folds: number;
  scoring_metric?: string | null;
  test_size: number;
  validation_size: number;
  random_state: number;
  status: ExperimentStatus;
  dataset_fingerprint?: string | null;
  created_by_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  execution_duration_seconds?: number | null;
  created_at: string;
  updated_at: string;
  runs: ExperimentRunRead[];
}

export interface ExperimentCreatePayload {
  name: string;
  description?: string;
  dataset_id: string;
  target_column: string;
  problem_type: ProblemType;
  algorithm: Algorithm;
  selected_features?: string[];
  hyperparameter_config?: Record<string, unknown>;
  search_strategy?: SearchStrategy;
  cv_folds?: number;
  scoring_metric?: string;
  test_size?: number;
  validation_size?: number;
  random_state?: number;
}

export interface ExperimentListResponse {
  items: ExperimentRead[];
  total: number;
  offset: number;
  limit: number;
}

export interface ExperimentCompareItem {
  experiment_id: string;
  experiment_name: string;
  run_id: string;
  algorithm: string;
  problem_type: string;
  dataset_id: string;
  target_column: string;
  status: string;
  best_hyperparameters?: Record<string, unknown> | null;
  validation_metrics?: Record<string, number> | null;
  test_metrics?: Record<string, number> | null;
  execution_duration_seconds?: number | null;
  created_at: string;
}

export interface ExperimentComparisonResponse {
  experiments: ExperimentCompareItem[];
  warnings: string[];
}
