export type DriftStatus = 'nominal' | 'warning' | 'critical' | 'insufficient_data';
export type AlertSeverity = 'warning' | 'critical';
export type ReportType = 'data_quality' | 'feature_drift' | 'performance';

export interface DataQualityFeatureMetric {
  missing_count: number;
  missing_rate: number;
  outlier_count?: number;
  outlier_rate?: number;
  unique_count: number;
  is_constant: boolean;
  type: string;
}

export interface DataQualityResults {
  sample_size: number;
  feature_metrics: Record<string, DataQualityFeatureMetric>;
  quality_score: number;
  issues: string[];
}

export interface FeatureDriftMetric {
  feature_name: string;
  feature_type: 'numeric' | 'categorical';
  drift_detected: boolean;
  severity: DriftStatus;
  psi_score?: number | null;
  ks_statistic?: number | null;
  ks_p_value?: number | null;
  chi2_statistic?: number | null;
  chi2_p_value?: number | null;
  reference_mean?: number | null;
  production_mean?: number | null;
  message?: string;
}

export interface FeatureDriftResults {
  reference_sample_size: number;
  production_sample_size: number;
  drifted_features_count: number;
  total_features: number;
  drift_ratio: number;
  features: Record<string, FeatureDriftMetric>;
}

export interface PerformanceMonitoringResults {
  evaluated_samples: number;
  task_type: string;
  reference_metrics: Record<string, number>;
  production_metrics: Record<string, number>;
  metric_degradations: Record<string, number>;
  performance_drift_detected: boolean;
  issues: string[];
}

export interface DriftReportRead {
  id: string;
  model_id: string;
  report_type: ReportType;
  overall_status: DriftStatus;
  sample_size: number;
  summary: string;
  results: DataQualityResults | FeatureDriftResults | PerformanceMonitoringResults | Record<string, unknown>;
  created_at: string;
}

export interface DriftReportList {
  items: DriftReportRead[];
  total: number;
  offset: number;
  limit: number;
}

export interface DriftAlertRead {
  id: string;
  model_id: string;
  drift_report_id?: string | null;
  alert_type: string;
  severity: AlertSeverity;
  message: string;
  details?: Record<string, unknown> | null;
  resolved: boolean;
  resolved_at?: string | null;
  created_at: string;
}

export interface DriftAlertList {
  items: DriftAlertRead[];
  total: number;
  offset: number;
  limit: number;
}

export interface ModelDriftSummary {
  model_id: string;
  model_name: string;
  version: number;
  latest_quality_status: DriftStatus;
  latest_drift_status: DriftStatus;
  latest_performance_status: DriftStatus;
  active_alerts_count: number;
  last_analyzed_at?: string | null;
}

export interface DriftOverviewResponse {
  total_models_monitored: number;
  models_in_drift: number;
  total_active_alerts: number;
  critical_alerts: number;
  model_summaries: ModelDriftSummary[];
}

export interface AnalyzeDriftRequest {
  recent_sample_limit?: number;
  psi_threshold?: number;
  p_value_threshold?: number;
}
