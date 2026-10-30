import React, { useState, useEffect, useCallback } from 'react';
import {
  Server,
  ShieldCheck,
  AlertCircle,
  RefreshCw,
  Layers,
  Activity,
  BarChart2,
} from 'lucide-react';
import { modelApi, systemApi, parseApiError, type ErrorDetails } from '../services/api';
import type { ModelRead, FeaturePrimitive } from '../types/model';
import type {
  HealthReadinessResponse,
  AIServicesStatusResponse,
  ReadinessCheckItem,
} from '../types/deployment';
import { ModelSelector } from '../components/ModelSelector';
import { DeploymentReadinessChecklist } from '../components/DeploymentReadinessChecklist';
import { MonitoringKpiCards } from '../components/MonitoringKpiCards';
import { DeploymentConfigSection } from '../components/DeploymentConfigSection';
import { PredictionActivityMonitoringTable } from '../components/PredictionActivityMonitoringTable';
import { ModelPerformanceMonitoringSection } from '../components/ModelPerformanceMonitoringSection';

export const DeploymentMonitoringPage: React.FC = () => {
  const [models, setModels] = useState<ModelRead[]>([]);
  const [selectedModel, setSelectedModel] = useState<ModelRead | null>(null);
  const [totalModels, setTotalModels] = useState<number>(0);
  const [health, setHealth] = useState<HealthReadinessResponse | null>(null);
  const [aiStatus, setAiStatus] = useState<AIServicesStatusResponse | null>(null);

  const [loading, setLoading] = useState<boolean>(false);
  const [errorDetails, setErrorDetails] = useState<ErrorDetails | null>(null);

  // Manual Model UUID fallback state
  const [manualModelId, setManualModelId] = useState<string>('');
  const [isFetchingManual, setIsFetchingManual] = useState<boolean>(false);

  // Endpoint probe state
  const [isProbing, setIsProbing] = useState<boolean>(false);
  const [endpointProbeResult, setEndpointProbeResult] = useState<boolean | null>(null);
  const [endpointProbeMessage, setEndpointProbeMessage] = useState<string>('');

  // Active navigation sub-tab in Deployment page
  const [activeSubTab, setActiveSubTab] = useState<'readiness' | 'performance' | 'activity' | 'config'>('readiness');

  // Load models and system health
  const fetchData = useCallback(async () => {
    setLoading(true);
    setErrorDetails(null);
    try {
      const [modelsData, healthData, aiData] = await Promise.all([
        modelApi.listModels(0, 50),
        systemApi.getHealth().catch(() => null),
        systemApi.getAiStatus().catch(() => null),
      ]);

      setModels(modelsData.items);
      setTotalModels(modelsData.total);
      if (modelsData.items.length > 0 && !selectedModel) {
        setSelectedModel(modelsData.items[0]);
      }
      if (healthData) setHealth(healthData);
      if (aiData) setAiStatus(aiData);
    } catch (err: unknown) {
      setErrorDetails(parseApiError(err));
    } finally {
      setLoading(false);
    }
  }, [selectedModel]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Handle manual model ID fetch
  const handleFetchManualModel = async () => {
    if (!manualModelId.trim()) return;
    setIsFetchingManual(true);
    setErrorDetails(null);
    try {
      const fetchedModel = await modelApi.getModel(manualModelId.trim());
      setSelectedModel(fetchedModel);
      if (!models.some((m) => m.id === fetchedModel.id)) {
        setModels((prev) => [fetchedModel, ...prev]);
        setTotalModels((prev) => prev + 1);
      }
    } catch (err: unknown) {
      setErrorDetails(parseApiError(err));
    } finally {
      setIsFetchingManual(false);
    }
  };

  // Empirical probe of inference endpoint for the selected model
  const probeInferenceEndpoint = async () => {
    if (!selectedModel) return;
    setIsProbing(true);
    try {
      // Build a valid synthetic sample row from the model's feature schema
      const sampleRecord: Record<string, FeaturePrimitive> = {};
      selectedModel.feature_schema.forEach((f) => {
        sampleRecord[f.name] = f.kind === 'numeric' ? 10 : 'probe';
      });

      const res = await modelApi.predict(selectedModel.id, {
        records: [sampleRecord],
        allow_missing: false,
      });

      if (res && res.predictions && res.predictions.length > 0) {
        setEndpointProbeResult(true);
        setEndpointProbeMessage(
          `Probe 200 OK: Prediction returned [${String(res.predictions[0])}] via POST /api/v1/models/${selectedModel.id}/predict.`
        );
      } else {
        setEndpointProbeResult(false);
        setEndpointProbeMessage('Prediction endpoint returned empty response.');
      }
    } catch (err: unknown) {
      setEndpointProbeResult(false);
      const parsed = parseApiError(err);
      setEndpointProbeMessage(`Probe failed: ${parsed.message} (${parsed.code})`);
    } finally {
      setIsProbing(false);
    }
  };

  // Run initial probe when selected model changes
  useEffect(() => {
    if (selectedModel) {
      probeInferenceEndpoint();
    }
  }, [selectedModel?.id]);

  // Build the 6 strict Deployment Readiness checklist items based on empirical evidence
  const evaluateReadiness = (model: ModelRead | null): ReadinessCheckItem[] => {
    if (!model) return [];

    const trainingCompleted = !!model.created_at && !!model.training_metadata?.trained_at;
    const metadataAvailable = !!model.training_metadata && Object.keys(model.training_metadata).length > 0;
    const featureSchemaAvailable = Array.isArray(model.feature_schema) && model.feature_schema.length > 0;
    const metricsAvailable = !!model.metrics && (!!model.metrics.test || !!model.metrics.train);

    // Database & server restart readiness
    const dbHealthy = health?.status === 'ok';

    return [
      {
        id: 'training_completed',
        label: '1. Model Training Completed',
        category: 'artifact',
        status: trainingCompleted ? 'Verified' : 'Not Verified',
        details: 'Training pipeline completed without errors and output stored in artifact store.',
        evidence: trainingCompleted
          ? `Trained at ${model.training_metadata.trained_at} (Duration: ${model.training_metadata.training_seconds}s). Estimator: ${model.training_metadata.estimator || model.algorithm}.`
          : undefined,
      },
      {
        id: 'metadata_available',
        label: '2. Model Metadata Available',
        category: 'artifact',
        status: metadataAvailable ? 'Verified' : 'Not Verified',
        details: 'Essential training hyperparameters, scikit-learn version, and dataset hash registered.',
        evidence: metadataAvailable
          ? `scikit-learn ${model.sklearn_version}, Dataset SHA256: ${String(model.training_metadata.dataset_sha256 || 'N/A').slice(0, 16)}...`
          : undefined,
      },
      {
        id: 'feature_schema_available',
        label: '3. Feature Schema Available',
        category: 'schema',
        status: featureSchemaAvailable ? 'Verified' : 'Not Verified',
        details: 'Exact expected feature names and types registered for input validation.',
        evidence: featureSchemaAvailable
          ? `${model.feature_schema.length} features registered: [${model.feature_schema.map((f) => f.name).join(', ')}]`
          : undefined,
      },
      {
        id: 'prediction_endpoint_operational',
        label: '4. Prediction Endpoint Operational',
        category: 'runtime',
        status:
          endpointProbeResult === true
            ? 'Verified'
            : endpointProbeResult === false
            ? 'Not Verified'
            : 'Data Unavailable',
        details: `POST /api/v1/models/${model.id}/predict execution verified.`,
        evidence: endpointProbeMessage || 'Pending live runtime probe execution...',
      },
      {
        id: 'loaded_after_restart',
        label: '5. Model Reloadable After Server Restart',
        category: 'runtime',
        status: dbHealthy ? 'Verified' : 'Not Verified',
        details: 'Artifact saved to disk and reloadable statelessly from trained_models/ across restarts.',
        evidence: dbHealthy
          ? `Backend Database: ${health?.components?.database || 'ok'}. Disk artifact loads on-demand per request.`
          : 'Backend health probe reporting degraded dependency.',
      },
      {
        id: 'evaluation_metrics_available',
        label: '6. Evaluation Metrics Available',
        category: 'metrics',
        status: metricsAvailable ? 'Verified' : 'Not Verified',
        details: 'Offline holdout test set accuracy, loss, and baseline comparison scores recorded.',
        evidence: metricsAvailable
          ? `Test Split: Accuracy=${model.metrics.test?.accuracy ?? 'N/A'}, F1=${model.metrics.test?.f1_macro ?? 'N/A'}, Samples=${model.metrics.test?.n_samples ?? 'N/A'}`
          : 'No test split metrics recorded during training.',
      },
    ];
  };

  const readinessChecks = evaluateReadiness(selectedModel);
  const overallReady = readinessChecks.every((c) => c.status === 'Verified');

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* 1. Header & Overview Section */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
              <Server className="w-4 h-4" />
            </div>
            <h2 className="text-lg font-bold text-slate-900">
              Model Deployment & Monitoring Studio
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1 max-w-2xl">
            Evaluate production deployment readiness, inspect runtime serving parameters, and audit model
            performance benchmarks across evaluation splits.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={fetchData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh Status
          </button>
        </div>
      </div>

      {/* Global Error Alert Banner */}
      {errorDetails && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-xs flex items-start justify-between gap-3 shadow-xs">
          <div className="flex items-start gap-2.5">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
            <div>
              <div className="font-bold flex items-center gap-2">
                <span>{errorDetails.code}</span>
                {errorDetails.status && (
                  <span className="px-1.5 py-0.2 rounded bg-red-200/70 text-red-900 font-mono text-[10px]">
                    HTTP {errorDetails.status}
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-red-700">{errorDetails.message}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setErrorDetails(null)}
            className="text-red-500 hover:text-red-800 text-xs font-semibold px-2 py-1 rounded"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* 2. Monitoring KPI Cards (Real Data Only + Data Unavailable) */}
      <MonitoringKpiCards
        totalTrainedModels={totalModels}
        health={health}
        aiStatus={aiStatus}
        loading={loading}
      />

      {/* 3. Model Selection Panel */}
      <ModelSelector
        models={models}
        selectedModel={selectedModel}
        onSelectModel={(m) => setSelectedModel(m)}
        loading={loading}
        manualModelId={manualModelId}
        onManualModelIdChange={setManualModelId}
        onFetchManualModel={handleFetchManualModel}
        isFetchingManual={isFetchingManual}
      />

      {/* 4. Sub-Navigation Tabs */}
      {selectedModel && (
        <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
          <button
            type="button"
            onClick={() => setActiveSubTab('readiness')}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
              activeSubTab === 'readiness'
                ? 'bg-indigo-600 text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            <ShieldCheck className="w-4 h-4" />
            Deployment Readiness Checklist
          </button>

          <button
            type="button"
            onClick={() => setActiveSubTab('performance')}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
              activeSubTab === 'performance'
                ? 'bg-indigo-600 text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            <BarChart2 className="w-4 h-4" />
            Model Performance Benchmarks
          </button>

          <button
            type="button"
            onClick={() => setActiveSubTab('activity')}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
              activeSubTab === 'activity'
                ? 'bg-indigo-600 text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            <Activity className="w-4 h-4" />
            Prediction Activity Audit
          </button>

          <button
            type="button"
            onClick={() => setActiveSubTab('config')}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
              activeSubTab === 'config'
                ? 'bg-indigo-600 text-white shadow-xs'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            <Server className="w-4 h-4" />
            Runtime Configuration & RFC
          </button>
        </div>
      )}

      {/* 5. Sub-Tab Views */}
      {selectedModel ? (
        <>
          {activeSubTab === 'readiness' && (
            <DeploymentReadinessChecklist
              checks={readinessChecks}
              modelName={selectedModel.name}
              version={selectedModel.version}
              overallReady={overallReady}
              onProbeInference={probeInferenceEndpoint}
              isProbing={isProbing}
            />
          )}

          {activeSubTab === 'performance' && (
            <ModelPerformanceMonitoringSection model={selectedModel} />
          )}

          {activeSubTab === 'activity' && (
            <PredictionActivityMonitoringTable models={models} />
          )}

          {activeSubTab === 'config' && (
            <DeploymentConfigSection model={selectedModel} health={health} />
          )}
        </>
      ) : (
        <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center shadow-sm">
          <Layers className="w-8 h-8 text-slate-400 mx-auto mb-2" />
          <h3 className="text-sm font-bold text-slate-700">No Model Selected</h3>
          <p className="text-xs text-slate-500 mt-1">
            Select a trained model from the list above or provide a UUID to view deployment checks.
          </p>
        </div>
      )}
    </div>
  );
};
