export interface FeatureImportanceItem {
  feature: string;
  importance: number;
  rank: number;
}

export interface GlobalFeatureImportanceResponse {
  model_id: string;
  method: string;
  summary_plot_type: string;
  feature_importances: FeatureImportanceItem[];
  background_sample_size: number;
  computation_time_seconds: number;
}

export interface FeatureContributionItem {
  feature: string;
  value: unknown;
  contribution: number;
  direction: 'positive' | 'negative' | 'neutral';
}

export interface LocalShapExplanationResponse {
  model_id: string;
  prediction: unknown;
  probabilities?: Record<string, number> | null;
  base_value: number;
  feature_contributions: FeatureContributionItem[];
  computation_time_seconds: number;
  disclaimer: string;
}

export interface LimeRuleContributionItem {
  rule: string;
  feature?: string | null;
  weight: number;
  direction: 'positive' | 'negative';
}

export interface LocalLimeExplanationResponse {
  model_id: string;
  prediction: unknown;
  probabilities?: Record<string, number> | null;
  intercept?: number | null;
  rule_contributions: LimeRuleContributionItem[];
  score?: number | null;
  computation_time_seconds: number;
  disclaimer: string;
}

export interface ExplainabilitySummaryResponse {
  model_id: string;
  model_name: string;
  algorithm: string;
  problem_type: string;
  supported_explainers: string[];
  default_explainer: string;
  feature_names: string[];
  global_importance_available: boolean;
}

export interface ExplainPredictionRequest {
  record: Record<string, unknown>;
  target_class?: string;
  num_features?: number;
  background_samples?: number;
}
