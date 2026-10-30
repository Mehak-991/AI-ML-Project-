import React, { useState, useEffect, useCallback } from 'react';
import {
  BrainCircuit,
  Layers,
  Send,
  FileSpreadsheet,
  AlertCircle,
  HelpCircle,
  Sparkles,
} from 'lucide-react';
import { modelApi, parseApiError, type ErrorDetails } from '../services/api';
import type { ModelRead, FeaturePrimitive, PredictionResultItem } from '../types/model';
import { ModelSelector } from '../components/ModelSelector';
import { SinglePredictionForm } from '../components/SinglePredictionForm';
import { BatchPredictionEditor } from '../components/BatchPredictionEditor';
import { PredictionResultsView } from '../components/PredictionResultsView';

export const PredictionManagementPage: React.FC = () => {
  const [models, setModels] = useState<ModelRead[]>([]);
  const [selectedModel, setSelectedModel] = useState<ModelRead | null>(null);
  const [loadingModels, setLoadingModels] = useState<boolean>(false);
  const [errorDetails, setErrorDetails] = useState<ErrorDetails | null>(null);

  // Manual Model UUID fallback
  const [manualModelId, setManualModelId] = useState<string>('');
  const [isFetchingManual, setIsFetchingManual] = useState<boolean>(false);

  // Mode: single record or batch prediction
  const [activeMode, setActiveMode] = useState<'single' | 'batch'>('single');

  // Prediction execution state
  const [predicting, setPredicting] = useState<boolean>(false);
  const [predictionResults, setPredictionResults] = useState<PredictionResultItem[]>([]);

  // Fetch available models on mount
  const fetchModels = useCallback(async () => {
    setLoadingModels(true);
    setErrorDetails(null);
    try {
      const data = await modelApi.listModels(0, 50);
      setModels(data.items);
      if (data.items.length > 0 && !selectedModel) {
        setSelectedModel(data.items[0]);
      }
    } catch (err: unknown) {
      setErrorDetails(parseApiError(err));
    } finally {
      setLoadingModels(false);
    }
  }, [selectedModel]);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  // Handle manual model ID fetch
  const handleFetchManualModel = async () => {
    if (!manualModelId.trim()) return;
    setIsFetchingManual(true);
    setErrorDetails(null);
    try {
      const fetchedModel = await modelApi.getModel(manualModelId.trim());
      setSelectedModel(fetchedModel);
      // If not already in models list, add it
      if (!models.some((m) => m.id === fetchedModel.id)) {
        setModels((prev) => [fetchedModel, ...prev]);
      }
    } catch (err: unknown) {
      setErrorDetails(parseApiError(err));
    } finally {
      setIsFetchingManual(false);
    }
  };

  // Run single record prediction
  const handleSinglePredict = async (
    record: Record<string, FeaturePrimitive>,
    allowMissing: boolean
  ) => {
    if (!selectedModel) return;
    setPredicting(true);
    setErrorDetails(null);
    try {
      const response = await modelApi.predict(selectedModel.id, {
        records: [record],
        allow_missing: allowMissing,
      });

      const newResult: PredictionResultItem = {
        index: 0,
        input: record,
        prediction: response.predictions[0] ?? null,
        probabilities: response.probabilities ? response.probabilities[0] : null,
        timestamp: new Date().toISOString(),
      };

      setPredictionResults([newResult]);
    } catch (err: unknown) {
      setErrorDetails(parseApiError(err));
    } finally {
      setPredicting(false);
    }
  };

  // Run batch predictions
  const handleBatchPredict = async (
    records: Array<Record<string, FeaturePrimitive>>,
    allowMissing: boolean
  ) => {
    if (!selectedModel) return;
    setPredicting(true);
    setErrorDetails(null);
    try {
      const response = await modelApi.predict(selectedModel.id, {
        records,
        allow_missing: allowMissing,
      });

      const newResults: PredictionResultItem[] = records.map((rec, idx) => ({
        index: idx,
        input: rec,
        prediction: response.predictions[idx] ?? null,
        probabilities: response.probabilities ? response.probabilities[idx] : null,
        timestamp: new Date().toISOString(),
      }));

      setPredictionResults(newResults);
    } catch (err: unknown) {
      setErrorDetails(parseApiError(err));
    } finally {
      setPredicting(false);
    }
  };

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* 1. Header Overview Section */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
              <BrainCircuit className="w-4 h-4" />
            </div>
            <h2 className="text-lg font-bold text-slate-900">
              Prediction & Inference Studio
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1 max-w-2xl">
            Select a trained ML model to run real-time inference on individual records or upload CSV
            batches. Form fields and schemas are dynamically populated from model metadata.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center bg-slate-100 p-1 rounded-xl text-xs font-semibold">
            <button
              type="button"
              onClick={() => setActiveMode('single')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg transition-all ${
                activeMode === 'single'
                  ? 'bg-white text-indigo-600 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Send className="w-3.5 h-3.5" />
              Single Record
            </button>
            <button
              type="button"
              onClick={() => setActiveMode('batch')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg transition-all ${
                activeMode === 'batch'
                  ? 'bg-white text-indigo-600 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <FileSpreadsheet className="w-3.5 h-3.5" />
              Batch Predict
            </button>
          </div>
        </div>
      </div>

      {/* Global Error Banner */}
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
              {errorDetails.details && (
                <pre className="mt-1.5 p-2 bg-red-100/60 rounded text-[10px] font-mono overflow-x-auto max-h-32">
                  {typeof errorDetails.details === 'object'
                    ? JSON.stringify(errorDetails.details, null, 2)
                    : String(errorDetails.details)}
                </pre>
              )}
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

      {/* 2. Model Selection Panel */}
      <ModelSelector
        models={models}
        selectedModel={selectedModel}
        onSelectModel={(m) => {
          setSelectedModel(m);
          setPredictionResults([]);
        }}
        loading={loadingModels}
        manualModelId={manualModelId}
        onManualModelIdChange={setManualModelId}
        onFetchManualModel={handleFetchManualModel}
        isFetchingManual={isFetchingManual}
      />

      {/* 3. Prediction Input Interface (Single Form or Batch Editor) */}
      {selectedModel ? (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          {activeMode === 'single' ? (
            <SinglePredictionForm
              model={selectedModel}
              onPredict={handleSinglePredict}
              loading={predicting}
            />
          ) : (
            <BatchPredictionEditor
              model={selectedModel}
              onPredictBatch={handleBatchPredict}
              loading={predicting}
            />
          )}
        </div>
      ) : (
        <div className="p-12 text-center bg-white border border-slate-200 rounded-2xl shadow-sm">
          <Layers className="w-8 h-8 text-slate-400 mx-auto mb-2" />
          <h3 className="text-sm font-bold text-slate-700">No Model Selected</h3>
          <p className="text-xs text-slate-500 mt-1">
            Please select an existing trained model or enter a valid Model UUID above to activate the
            prediction interface.
          </p>
        </div>
      )}

      {/* 4. Prediction Results Table & CSV Export */}
      {selectedModel && predictionResults.length > 0 && (
        <PredictionResultsView
          model={selectedModel}
          results={predictionResults}
          onClearResults={() => setPredictionResults([])}
        />
      )}
    </div>
  );
};
