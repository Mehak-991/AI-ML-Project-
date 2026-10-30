import axios, { AxiosError } from 'axios';
import type {
  ApiErrorResponse,
  DatasetCreateResponse,
  DatasetListResponse,
  DatasetRead,
  DatasetValidationResponse,
} from '../types/dataset';

// Base API instance with /api/v1 prefix
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  headers: {
    Accept: 'application/json',
  },
});

const TOKEN_KEY = 'aiml_access_token';
const REFRESH_KEY = 'aiml_refresh_token';

export const tokenStorage = {
  getAccessToken: () => sessionStorage.getItem(TOKEN_KEY),
  setAccessToken: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  getRefreshToken: () => sessionStorage.getItem(REFRESH_KEY),
  setRefreshToken: (token: string) => sessionStorage.setItem(REFRESH_KEY, token),
  clear: () => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(REFRESH_KEY);
  },
};

// Request interceptor: attach Bearer token
apiClient.interceptors.request.use((config) => {
  const token = tokenStorage.getAccessToken();
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: handle 401 with refresh attempt
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value?: unknown) => void;
  reject: (reason?: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry && !originalRequest.url?.includes('/auth/login') && !originalRequest.url?.includes('/auth/refresh')) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return apiClient(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const currentRefresh = tokenStorage.getRefreshToken();
      if (!currentRefresh) {
        tokenStorage.clear();
        isRefreshing = false;
        return Promise.reject(error);
      }

      try {
        const refreshRes = await axios.post('/api/v1/auth/refresh', {
          refresh_token: currentRefresh,
        });
        const { access_token, refresh_token: newRefresh } = refreshRes.data;
        tokenStorage.setAccessToken(access_token);
        if (newRefresh) {
          tokenStorage.setRefreshToken(newRefresh);
        }
        processQueue(null, access_token);
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return apiClient(originalRequest);
      } catch (refreshErr) {
        processQueue(refreshErr, null);
        tokenStorage.clear();
        return Promise.reject(refreshErr);
      } finally {
        isRefreshing = false;
      }
    }
    return Promise.reject(error);
  }
);


export interface ErrorDetails {
  status?: number;
  code: string;
  message: string;
  details?: unknown;
}

export function parseApiError(error: unknown): ErrorDetails {
  if (axios.isAxiosError(error)) {
    const axiosErr = error as AxiosError<ApiErrorResponse | { detail?: unknown }>;
    const status = axiosErr.response?.status;
    const responseData = axiosErr.response?.data;

    // Standard backend ErrorResponse schema: { error: { code, message, details } }
    if (responseData && typeof responseData === 'object' && 'error' in responseData) {
      const errObj = responseData.error;
      return {
        status,
        code: errObj.code || `HTTP_${status || 'UNKNOWN'}`,
        message: errObj.message || 'An error occurred while processing your request.',
        details: errObj.details,
      };
    }

    // Default FastAPI 422 detail format or fallback
    if (responseData && typeof responseData === 'object' && 'detail' in responseData) {
      return {
        status,
        code: `HTTP_${status || 'VALIDATION_ERROR'}`,
        message:
          typeof responseData.detail === 'string'
            ? responseData.detail
            : JSON.stringify(responseData.detail),
        details: responseData.detail,
      };
    }

    // Categorized HTTP error handling
    if (status === 400) {
      return {
        status: 400,
        code: 'BAD_REQUEST',
        message: 'Invalid or unparseable dataset file. Please check file structure and UTF-8 encoding.',
      };
    }
    if (status === 413) {
      return {
        status: 413,
        code: 'PAYLOAD_TOO_LARGE',
        message: 'File size exceeds maximum allowed upload limit (25 MB default).',
      };
    }
    if (status === 415) {
      return {
        status: 415,
        code: 'UNSUPPORTED_MEDIA_TYPE',
        message: 'Unsupported file format. Please upload a valid CSV or XLSX file.',
      };
    }
    if (status === 422) {
      return {
        status: 422,
        code: 'UNPROCESSABLE_ENTITY',
        message: 'Dataset validation failed. Please check required columns and values.',
      };
    }
    if (status === 500) {
      return {
        status: 500,
        code: 'INTERNAL_SERVER_ERROR',
        message: 'Internal server error while processing dataset. Check server logs.',
      };
    }

    if (axiosErr.message === 'Network Error') {
      return {
        code: 'NETWORK_ERROR',
        message: 'Unable to connect to the backend server. Verify the server is running on port 8000.',
      };
    }

    return {
      status,
      code: `ERROR_${status || 'UNKNOWN'}`,
      message: axiosErr.message || 'An unexpected request error occurred.',
    };
  }

  if (error instanceof Error) {
    return {
      code: 'CLIENT_ERROR',
      message: error.message,
    };
  }

  return {
    code: 'UNKNOWN_ERROR',
    message: 'An unknown error occurred.',
  };
}

export const datasetApi = {
  /**
   * Upload and register a dataset.
   * POST /api/v1/datasets
   */
  async uploadDataset(
    file: File,
    name?: string,
    onUploadProgress?: (progressEvent: { loaded: number; total?: number; percentage: number }) => void
  ): Promise<DatasetCreateResponse> {
    const formData = new FormData();
    formData.append('file', file);
    if (name && name.trim()) {
      formData.append('name', name.trim());
    }

    const response = await apiClient.post<DatasetCreateResponse>('/datasets', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (event) => {
        if (onUploadProgress) {
          const total = event.total ?? file.size;
          const percentage = total > 0 ? Math.round((event.loaded * 100) / total) : 0;
          onUploadProgress({
            loaded: event.loaded,
            total,
            percentage: Math.min(percentage, 100),
          });
        }
      },
    });

    return response.data;
  },

  /**
   * List datasets with offset and limit pagination.
   * GET /api/v1/datasets
   */
  async listDatasets(offset = 0, limit = 10): Promise<DatasetListResponse> {
    const response = await apiClient.get<DatasetListResponse>('/datasets', {
      params: { offset, limit },
    });
    return response.data;
  },

  /**
   * Get single dataset metadata by ID.
   * GET /api/v1/datasets/{dataset_id}
   */
  async getDataset(id: string): Promise<DatasetRead> {
    const response = await apiClient.get<DatasetRead>(`/datasets/${id}`);
    return response.data;
  },

  /**
   * Get detailed summary and statistical profile for a stored dataset.
   * GET /api/v1/datasets/{dataset_id}/summary
   */
  async getDatasetSummary(id: string, targetColumn?: string): Promise<DatasetValidationResponse> {
    const response = await apiClient.get<DatasetValidationResponse>(`/datasets/${id}/summary`, {
      params: targetColumn ? { target_column: targetColumn } : undefined,
    });
    return response.data;
  },
};

export const modelApi = {
  /**
   * List trained models with pagination and optional dataset filter.
   * GET /api/v1/models
   */
  async listModels(
    offset = 0,
    limit = 20,
    datasetId?: string
  ): Promise<import('../types/model').ModelListResponse> {
    const response = await apiClient.get<import('../types/model').ModelListResponse>('/models', {
      params: {
        offset,
        limit,
        dataset_id: datasetId || undefined,
      },
    });
    return response.data;
  },

  /**
   * Get single model metadata, schema, and metrics.
   * GET /api/v1/models/{model_id}
   */
  async getModel(id: string): Promise<import('../types/model').ModelRead> {
    const response = await apiClient.get<import('../types/model').ModelRead>(`/models/${id}`);
    return response.data;
  },

  /**
   * Train a new model.
   * POST /api/v1/models/train
   */
  async trainModel(
    request: import('../types/model').TrainModelRequest
  ): Promise<import('../types/model').ModelRead> {
    const response = await apiClient.post<import('../types/model').ModelRead>(
      '/models/train',
      request
    );
    return response.data;
  },

  /**
   * Run inference on single or multiple records using a saved model.
   * POST /api/v1/models/{model_id}/predict
   */
  async predict(
    modelId: string,
    request: import('../types/model').PredictRequest
  ): Promise<import('../types/model').PredictResponse> {
    const response = await apiClient.post<import('../types/model').PredictResponse>(
      `/models/${modelId}/predict`,
      request
    );
    return response.data;
  },
};

export const systemApi = {
  /**
   * System readiness & health status probe.
   * GET /api/v1/health
   */
  async getHealth(): Promise<import('../types/deployment').HealthReadinessResponse> {
    const response = await apiClient.get<import('../types/deployment').HealthReadinessResponse>('/health');
    return response.data;
  },

  /**
   * AI service provider configuration and optional packages status.
   * GET /api/v1/ai/status
   */
  async getAiStatus(): Promise<import('../types/deployment').AIServicesStatusResponse> {
    const response = await apiClient.get<import('../types/deployment').AIServicesStatusResponse>('/ai/status');
    return response.data;
  },
};

export const deploymentApi = {
  /**
   * Deploy a model to production serving.
   * POST /api/v1/models/{model_id}/deploy
   */
  async deployModel(
    modelId: string,
    request: import('../types/deployment').DeployModelRequest = {}
  ): Promise<import('../types/deployment').DeploymentRead> {
    const response = await apiClient.post<import('../types/deployment').DeploymentRead>(
      `/models/${modelId}/deploy`,
      request
    );
    return response.data;
  },

  /**
   * Undeploy an active model from production.
   * POST /api/v1/models/{model_id}/undeploy
   */
  async undeployModel(modelId: string): Promise<import('../types/deployment').DeploymentRead> {
    const response = await apiClient.post<import('../types/deployment').DeploymentRead>(
      `/models/${modelId}/undeploy`
    );
    return response.data;
  },

  /**
   * List deployments with optional model filter and pagination.
   * GET /api/v1/deployments
   */
  async listDeployments(
    offset = 0,
    limit = 20,
    modelId?: string
  ): Promise<import('../types/deployment').DeploymentListResponse> {
    const response = await apiClient.get<import('../types/deployment').DeploymentListResponse>(
      '/deployments',
      {
        params: { offset, limit, model_id: modelId || undefined },
      }
    );
    return response.data;
  },

  /**
   * Get single deployment by ID.
   * GET /api/v1/deployments/{deployment_id}
   */
  async getDeployment(deploymentId: string): Promise<import('../types/deployment').DeploymentRead> {
    const response = await apiClient.get<import('../types/deployment').DeploymentRead>(
      `/deployments/${deploymentId}`
    );
    return response.data;
  },
};

export const predictionLogApi = {
  /**
   * List prediction audit history with pagination and filters.
   * GET /api/v1/predictions/history
   */
  async listHistory(params?: {
    offset?: number;
    limit?: number;
    model_id?: string;
    deployment_id?: string;
    status?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<import('../types/deployment').PredictionLogListResponse> {
    const response = await apiClient.get<import('../types/deployment').PredictionLogListResponse>(
      '/predictions/history',
      { params }
    );
    return response.data;
  },

  /**
   * Get single prediction audit record.
   * GET /api/v1/predictions/history/{prediction_id}
   */
  async getHistoryItem(predictionId: string): Promise<import('../types/deployment').PredictionLogRead> {
    const response = await apiClient.get<import('../types/deployment').PredictionLogRead>(
      `/predictions/history/${predictionId}`
    );
    return response.data;
  },

  /**
   * Submit ground-truth labels for production evaluation.
   * POST /api/v1/predictions/history/{prediction_id}/ground-truth
   */
  async submitGroundTruth(
    predictionId: string,
    groundTruth: unknown[]
  ): Promise<import('../types/deployment').PredictionLogRead> {
    const response = await apiClient.post<import('../types/deployment').PredictionLogRead>(
      `/predictions/history/${predictionId}/ground-truth`,
      { ground_truth: groundTruth }
    );
    return response.data;
  },
};

export const monitoringApi = {
  /**
   * Aggregated production monitoring overview.
   * GET /api/v1/monitoring/overview
   */
  async getOverview(): Promise<import('../types/deployment').MonitoringOverviewResponse> {
    const response = await apiClient.get<import('../types/deployment').MonitoringOverviewResponse>(
      '/monitoring/overview'
    );
    return response.data;
  },

  /**
   * Model-specific monitoring telemetry.
   * GET /api/v1/monitoring/models/{model_id}
   */
  async getModelMonitoring(
    modelId: string
  ): Promise<import('../types/deployment').ModelMonitoringResponse> {
    const response = await apiClient.get<import('../types/deployment').ModelMonitoringResponse>(
      `/monitoring/models/${modelId}`
    );
    return response.data;
  },
};

export const authApi = {
  /**
   * Register a new user account.
   * POST /api/v1/auth/register
   */
  async register(data: import('../types/auth').RegisterCredentials): Promise<import('../types/auth').User> {
    const response = await apiClient.post<import('../types/auth').User>('/auth/register', data);
    return response.data;
  },

  /**
   * Login with email and password.
   * POST /api/v1/auth/login
   */
  async login(data: import('../types/auth').LoginCredentials): Promise<import('../types/auth').TokenResponse> {
    const response = await apiClient.post<import('../types/auth').TokenResponse>('/auth/login', data);
    return response.data;
  },

  /**
   * Refresh access token.
   * POST /api/v1/auth/refresh
   */
  async refresh(refreshToken: string): Promise<import('../types/auth').TokenResponse> {
    const response = await apiClient.post<import('../types/auth').TokenResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    });
    return response.data;
  },

  /**
   * Logout and revoke refresh token.
   * POST /api/v1/auth/logout
   */
  async logout(refreshToken: string): Promise<void> {
    await apiClient.post('/auth/logout', { refresh_token: refreshToken });
  },

  /**
   * Get current authenticated user profile.
   * GET /api/v1/auth/me
   */
  async getMe(): Promise<import('../types/auth').User> {
    const response = await apiClient.get<import('../types/auth').User>('/auth/me');
    return response.data;
  },

  /**
   * List users with optional filtering (Admin only).
   * GET /api/v1/auth/users
   */
  async listUsers(params?: {
    role?: string;
    is_active?: boolean;
    search?: string;
    offset?: number;
    limit?: number;
  }): Promise<import('../types/auth').UserListResponse> {
    const response = await apiClient.get<import('../types/auth').UserListResponse>('/auth/users', {
      params,
    });
    return response.data;
  },

  /**
   * Update user status or role (Admin only).
   * PATCH /api/v1/auth/users/{user_id}
   */
  async updateUser(
    userId: string,
    payload: import('../types/auth').UserUpdatePayload
  ): Promise<import('../types/auth').User> {
    const response = await apiClient.patch<import('../types/auth').User>(
      `/auth/users/${userId}`,
      payload
    );
    return response.data;
  },
};

export const driftApi = {
  /**
   * Get cross-model drift overview
   * GET /api/v1/drift/overview
   */
  async getOverview(): Promise<import('../types/drift').DriftOverviewResponse> {
    const response = await apiClient.get<import('../types/drift').DriftOverviewResponse>('/drift/overview');
    return response.data;
  },

  /**
   * List drift/quality reports for a specific model
   * GET /api/v1/drift/models/{model_id}/reports
   */
  async listReports(
    modelId: string,
    params?: { report_type?: string; offset?: number; limit?: number }
  ): Promise<import('../types/drift').DriftReportList> {
    const response = await apiClient.get<import('../types/drift').DriftReportList>(
      `/drift/models/${modelId}/reports`,
      { params }
    );
    return response.data;
  },

  /**
   * List drift alerts for a specific model
   * GET /api/v1/drift/models/{model_id}/alerts
   */
  async listModelAlerts(
    modelId: string,
    params?: { severity?: string; resolved?: boolean; offset?: number; limit?: number }
  ): Promise<import('../types/drift').DriftAlertList> {
    const response = await apiClient.get<import('../types/drift').DriftAlertList>(
      `/drift/models/${modelId}/alerts`,
      { params }
    );
    return response.data;
  },

  /**
   * List platform-wide drift alerts
   * GET /api/v1/drift/alerts
   */
  async listAllAlerts(params?: {
    severity?: string;
    resolved?: boolean;
    offset?: number;
    limit?: number;
  }): Promise<import('../types/drift').DriftAlertList> {
    const response = await apiClient.get<import('../types/drift').DriftAlertList>('/drift/alerts', {
      params,
    });
    return response.data;
  },

  /**
   * Resolve an alert
   * POST /api/v1/drift/alerts/{alert_id}/resolve
   */
  async resolveAlert(alertId: string): Promise<import('../types/drift').DriftAlertRead> {
    const response = await apiClient.post<import('../types/drift').DriftAlertRead>(
      `/drift/alerts/${alertId}/resolve`
    );
    return response.data;
  },

  /**
   * Trigger on-demand data quality check
   * POST /api/v1/drift/models/{model_id}/analyze-quality
   */
  async analyzeQuality(modelId: string): Promise<import('../types/drift').DriftReportRead> {
    const response = await apiClient.post<import('../types/drift').DriftReportRead>(
      `/drift/models/${modelId}/analyze-quality`
    );
    return response.data;
  },

  /**
   * Trigger on-demand feature drift analysis (PSI, KS, Chi-Square)
   * POST /api/v1/drift/models/{model_id}/analyze-drift
   */
  async analyzeDrift(
    modelId: string,
    params?: import('../types/drift').AnalyzeDriftRequest
  ): Promise<import('../types/drift').DriftReportRead> {
    const response = await apiClient.post<import('../types/drift').DriftReportRead>(
      `/drift/models/${modelId}/analyze-drift`,
      params || {}
    );
    return response.data;
  },

  /**
   * Trigger on-demand model performance analysis vs baseline
   * POST /api/v1/drift/models/{model_id}/analyze-performance
   */
  async analyzePerformance(modelId: string): Promise<import('../types/drift').DriftReportRead> {
    const response = await apiClient.post<import('../types/drift').DriftReportRead>(
      `/drift/models/${modelId}/analyze-performance`
    );
    return response.data;
  },
};

export const experimentApi = {
  /**
   * List experiments with optional pagination and status filter.
   * GET /api/v1/experiments
   */
  async listExperiments(params?: {
    offset?: number;
    limit?: number;
    status?: string;
  }): Promise<import('../types/experiment').ExperimentListResponse> {
    const response = await apiClient.get<import('../types/experiment').ExperimentListResponse>(
      '/experiments',
      { params }
    );
    return response.data;
  },

  /**
   * Get single experiment by ID.
   * GET /api/v1/experiments/{experiment_id}
   */
  async getExperiment(experimentId: string): Promise<import('../types/experiment').ExperimentRead> {
    const response = await apiClient.get<import('../types/experiment').ExperimentRead>(
      `/experiments/${experimentId}`
    );
    return response.data;
  },

  /**
   * Create a new ML experiment.
   * POST /api/v1/experiments
   */
  async createExperiment(
    payload: import('../types/experiment').ExperimentCreatePayload
  ): Promise<import('../types/experiment').ExperimentRead> {
    const response = await apiClient.post<import('../types/experiment').ExperimentRead>(
      '/experiments',
      payload
    );
    return response.data;
  },

  /**
   * Execute pipeline run for an experiment.
   * POST /api/v1/experiments/{experiment_id}/run
   */
  async runExperiment(experimentId: string): Promise<import('../types/experiment').ExperimentRunRead> {
    const response = await apiClient.post<import('../types/experiment').ExperimentRunRead>(
      `/experiments/${experimentId}/run`
    );
    return response.data;
  },

  /**
   * Cancel a pending or running experiment.
   * POST /api/v1/experiments/{experiment_id}/cancel
   */
  async cancelExperiment(experimentId: string): Promise<import('../types/experiment').ExperimentRead> {
    const response = await apiClient.post<import('../types/experiment').ExperimentRead>(
      `/experiments/${experimentId}/cancel`
    );
    return response.data;
  },

  /**
   * Rerun an experiment.
   * POST /api/v1/experiments/{experiment_id}/rerun
   */
  async rerunExperiment(experimentId: string): Promise<import('../types/experiment').ExperimentRunRead> {
    const response = await apiClient.post<import('../types/experiment').ExperimentRunRead>(
      `/experiments/${experimentId}/rerun`
    );
    return response.data;
  },

  /**
   * Compare multiple experiments.
   * GET /api/v1/experiments/compare?experiment_ids=...
   */
  async compareExperiments(
    experimentIds: string[]
  ): Promise<import('../types/experiment').ExperimentComparisonResponse> {
    const params = new URLSearchParams();
    experimentIds.forEach((id) => params.append('experiment_ids', id));
    const response = await apiClient.get<import('../types/experiment').ExperimentComparisonResponse>(
      `/experiments/compare?${params.toString()}`
    );
    return response.data;
  },
};


