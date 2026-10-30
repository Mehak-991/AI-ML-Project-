export type ProblemType = 'classification' | 'regression';
export type Algorithm = 'linear' | 'random_forest';

export interface FeatureSchemaItem {
  name: string;
  kind: 'numeric' | 'categorical';
}

export interface ConfusionMatrixData {
  labels: Array<string | number | boolean>;
  matrix: number[][];
}

export interface SplitMetrics {
  n_samples?: number;
  accuracy?: number | null;
  balanced_accuracy?: number | null;
  precision_macro?: number | null;
  recall_macro?: number | null;
  f1_macro?: number | null;
  log_loss?: number | null;
  roc_auc?: number | null;
  roc_auc_ovr_macro?: number | null;
  confusion_matrix?: ConfusionMatrixData | null;

  // Regression metrics (if regression problem)
  mae?: number | null;
  rmse?: number | null;
  median_absolute_error?: number | null;
  r2?: number | null;
  [key: string]: unknown;
}

export interface ModelMetricsMap {
  train?: SplitMetrics;
  validation?: SplitMetrics;
  test?: SplitMetrics;
  baseline_test?: SplitMetrics;
  [split: string]: SplitMetrics | undefined;
}

export interface TrainingMetadataRows {
  raw: number;
  used: number;
  train: number;
  validation: number;
  test: number;
  dropped_missing_target: number;
  dropped_duplicates: number;
  [key: string]: number;
}

export interface TrainingConfigData {
  test_size: number;
  validation_size: number;
  random_state: number;
  drop_duplicates: boolean;
  problem_type_inferred: boolean;
  [key: string]: unknown;
}

export interface ModelTrainingMetadata {
  trained_at: string;
  training_seconds: number;
  rows: TrainingMetadataRows;
  stratified?: boolean;
  dropped_columns?: Array<{ column: string; reason: string }>;
  config: TrainingConfigData;
  baseline_model?: string;
  estimator?: string;
  class_labels?: Array<string | number | boolean> | null;
  dataset_sha256?: string;
  validation_warnings?: Array<{ code: string; message: string; column?: string | null }>;
  versions?: {
    'scikit-learn'?: string;
    pandas?: string;
    numpy?: string;
    [pkg: string]: string | undefined;
  };
  [key: string]: unknown;
}

export interface ModelRead {
  id: string;
  name: string;
  version: number;
  dataset_id: string;
  problem_type: ProblemType;
  algorithm: Algorithm;
  target_column: str;
  feature_schema: FeatureSchemaItem[];
  metrics: ModelMetricsMap;
  training_metadata: ModelTrainingMetadata;
  sklearn_version: string;
  created_at: string;
}

type str = string;

export interface ModelListResponse {
  items: ModelRead[];
  total: number;
  offset: number;
  limit: number;
}

export interface TrainModelRequest {
  dataset_id: string;
  target_column: string;
  name?: string;
  problem_type?: ProblemType;
  algorithm?: Algorithm;
  feature_columns?: string[];
  exclude_columns?: string[];
  test_size?: number;
  validation_size?: number;
  random_state?: number;
  drop_duplicates?: boolean;
}

export type FeaturePrimitive = string | number | boolean | null;

export interface PredictRequest {
  records: Array<Record<string, FeaturePrimitive>>;
  allow_missing?: boolean;
}

export interface PredictResponse {
  model_id: string;
  problem_type: ProblemType;
  predictions: Array<string | number | boolean | null>;
  probabilities?: Array<Record<string, number>> | null;
}

export interface PredictionResultItem {
  index: number;
  input: Record<string, FeaturePrimitive>;
  prediction: string | number | boolean | null;
  probabilities?: Record<string, number> | null;
  timestamp: string;
}
