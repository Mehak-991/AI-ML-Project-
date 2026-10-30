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
};

