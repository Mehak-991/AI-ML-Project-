export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'retry_pending';

export type JobType =
  | 'model_training'
  | 'experiment_execution'
  | 'batch_prediction'
  | 'drift_analysis'
  | 'explainability';

export interface Job {
  id: string;
  job_type: JobType;
  status: JobStatus;
  created_by_id: string | null;
  model_id: string | null;
  experiment_id: string | null;
  input_config: Record<string, any>;
  progress_percentage: number;
  current_stage: string | null;
  started_at: string | null;
  completed_at: string | null;
  execution_duration_seconds: number | null;
  retry_count: number;
  max_retries: number;
  error_category: string | null;
  error_message: string | null;
  result: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

export interface JobListResponse {
  items: Job[];
  total: number;
  offset: number;
  limit: number;
}

export interface JobMetricsResponse {
  total_jobs: number;
  queued_jobs: number;
  running_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  cancelled_jobs: number;
}

export interface JobCreatePayload {
  job_type: JobType;
  model_id?: string | null;
  experiment_id?: string | null;
  input_config?: Record<string, any>;
  max_retries?: number;
}
