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
