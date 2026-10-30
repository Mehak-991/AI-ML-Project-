export interface HealthReadinessResponse {
  status: 'ok' | 'degraded' | 'error' | string;
  name: string;
  version: string;
  environment: string;
  timestamp: string;
  components: {
    database?: string;
    [key: string]: string | undefined;
  };
}

export interface AIServicesStatusResponse {
  packages: Record<string, boolean>;
  llm: {
    provider: string;
    configured: boolean;
    requires_api_key: boolean;
    default_model: string;
    allowed_models: string[];
  };
  embeddings?: {
    model: string;
    expected_dimension: number | null;
  };
  classifier?: {
    model: string;
  };
  device_preference: string;
  downloads_allowed: boolean;
  loaded_models: string[];
}

export type ReadinessCheckStatus = 'Verified' | 'Not Verified' | 'Data Unavailable';

export interface ReadinessCheckItem {
  id: string;
  label: string;
  category: 'artifact' | 'schema' | 'runtime' | 'metrics';
  status: ReadinessCheckStatus;
  details: string;
  evidence?: string;
}

export interface ModelDeploymentEvaluation {
  modelId: string;
  modelName: string;
  version: number;
  overallReady: boolean;
  checks: ReadinessCheckItem[];
  verifiedCount: number;
  totalChecks: number;
  evaluatedAt: string;
}

export type DeploymentStatus = 'Draft' | 'Ready' | 'Deployed' | 'Failed' | 'Undeployed';

export interface DeployModelRequest {
  environment?: string;
  configuration?: Record<string, unknown>;
}

export interface DeploymentRead {
  id: string;
  model_id: string;
  status: DeploymentStatus;
  version: number;
  environment: string;
  endpoint_url: string;
  configuration: Record<string, unknown>;
  deployed_at?: string | null;
  undeployed_at?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DeploymentListResponse {
  items: DeploymentRead[];
  total: number;
  offset: number;
  limit: number;
}

export interface PredictionLogRead {
  id: string;
  model_id: string;
  deployment_id?: string | null;
  record_count: number;
  duration_ms: number;
  status: 'success' | 'failed';
  problem_type: string;
  error_category?: string | null;
  error_message?: string | null;
  prediction_summary?: {
    count?: number;
    predictions?: Array<string | number | boolean | null>;
    [key: string]: unknown;
  } | null;
  is_evaluated: boolean;
  created_at: string;
}

export interface PredictionLogListResponse {
  items: PredictionLogRead[];
  total: number;
  offset: number;
  limit: number;
}

export interface MonitoringOverviewResponse {
  total_models: number;
  total_deployments: number;
  active_deployments: number;
  total_predictions: number;
  successful_predictions: number;
  failed_predictions: number;
  average_duration_ms: number;
  total_records_processed: number;
  recent_volume_24h: number;
}

export interface ModelMonitoringResponse {
  model_id: string;
  total_predictions: number;
  successful_predictions: number;
  failed_predictions: number;
  average_duration_ms: number;
  total_records_processed: number;
  active_deployment?: DeploymentRead | null;
  ground_truth_evaluated_count: number;
  production_accuracy?: number | null;
}
