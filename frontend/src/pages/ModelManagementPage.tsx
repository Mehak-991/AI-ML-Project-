import React, { useState, useEffect, useCallback } from 'react';
import {
  Layers,
  Target,
  Clock,
  GitCompare,
  AlertCircle,
} from 'lucide-react';
import { ModelTable } from '../components/ModelTable';
import { ModelDetailModal } from '../components/ModelDetailModal';
import { ModelAnalyticsModal } from '../components/ModelAnalyticsModal';
import { ModelComparisonModal } from '../components/ModelComparisonModal';
import { modelApi, parseApiError, type ErrorDetails } from '../services/api';
import type { ModelRead } from '../types/model';

export const ModelManagementPage: React.FC = () => {
  const [models, setModels] = useState<ModelRead[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [offset, setOffset] = useState<number>(0);
  const limit = 20;
  const [loading, setLoading] = useState<boolean>(false);
  const [errorDetails, setErrorDetails] = useState<ErrorDetails | null>(null);

  // Modals & Selected Model States
  const [inspectModel, setInspectModel] = useState<ModelRead | null>(null);
  const [analyticsModel, setAnalyticsModel] = useState<ModelRead | null>(null);
  const [selectedModelIds, setSelectedModelIds] = useState<string[]>([]);
  const [isComparing, setIsComparing] = useState<boolean>(false);

  const fetchModels = useCallback(async (currentOffset = 0) => {
    setLoading(true);
    setErrorDetails(null);
    try {
      const data = await modelApi.listModels(currentOffset, limit);
      setModels(data.items);
      setTotal(data.total);
      setOffset(data.offset);
    } catch (err: unknown) {
      setErrorDetails(parseApiError(err));
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    fetchModels(0);
  }, [fetchModels]);

  const handleToggleSelectModel = (id: string) => {
    setSelectedModelIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const selectedModelsForComparison = models.filter((m) =>
    selectedModelIds.includes(m.id)
  );

  // Summary Metrics Calculated from Real Registered Data
  const classificationCount = models.filter((m) => m.problem_type === 'classification').length;
  const regressionCount = models.filter((m) => m.problem_type === 'regression').length;
  const avgTrainingTime =
    models.length > 0
      ? (
          models.reduce((acc, curr) => acc + (curr.training_metadata?.training_seconds || 0), 0) /
          models.length
        ).toFixed(2)
      : '0';

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Top Overview Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Total Models
            </span>
            <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600">
              <Layers className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-3xl font-extrabold font-mono text-slate-900">{total}</span>
            <span className="text-xs text-slate-500 ml-2">artifacts registered</span>
          </div>
        </div>

        <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Task Breakdown
            </span>
            <div className="p-2 rounded-xl bg-blue-50 text-blue-600">
              <Target className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-blue-50 text-blue-700 border border-blue-200">
              {classificationCount} Classification
            </span>
            <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-purple-50 text-purple-700 border border-purple-200">
              {regressionCount} Regression
            </span>
          </div>
        </div>

        <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Average Fit Time
            </span>
            <div className="p-2 rounded-xl bg-amber-50 text-amber-600">
              <Clock className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-3xl font-extrabold font-mono text-slate-900">
              {avgTrainingTime}s
            </span>
            <span className="text-xs text-slate-500 ml-2">fast pipeline execution</span>
          </div>
        </div>

        <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Comparison Tray
            </span>
            <div className="p-2 rounded-xl bg-purple-50 text-purple-600">
              <GitCompare className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-800">
              {selectedModelIds.length} Selected
            </span>
            {selectedModelIds.length >= 2 ? (
              <button
                onClick={() => setIsComparing(true)}
                className="px-3 py-1 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm transition-colors"
              >
                Compare Now
              </button>
            ) : (
              <span className="text-[11px] text-slate-400">Select 2+ to compare</span>
            )}
          </div>
        </div>
      </div>

      {/* Error Alert */}
      {errorDetails && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-3 animate-fadeIn">
          <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold text-red-800">
              Failed to load models ({errorDetails.code}):
            </span>{' '}
            {errorDetails.message}
            <button
              onClick={() => fetchModels(offset)}
              className="mt-2 block text-xs underline text-red-600 hover:text-red-800"
            >
              Retry fetching models
            </button>
          </div>
        </div>
      )}

      {/* Model Table Section */}
      <ModelTable
        models={models}
        total={total}
        offset={offset}
        limit={limit}
        loading={loading}
        selectedModelIds={selectedModelIds}
        onToggleSelectModel={handleToggleSelectModel}
        onSelectModel={(model) => setInspectModel(model)}
        onOpenAnalytics={(model) => setAnalyticsModel(model)}
        onPageChange={(newOffset) => fetchModels(newOffset)}
        onRefresh={() => fetchModels(offset)}
        onCompareSelected={() => setIsComparing(true)}
      />

      {/* Detail Modal */}
      {inspectModel && (
        <ModelDetailModal
          modelId={inspectModel.id}
          initialModel={inspectModel}
          onClose={() => setInspectModel(null)}
          onOpenAnalytics={(model) => setAnalyticsModel(model)}
        />
      )}

      {/* Analytics Modal */}
      {analyticsModel && (
        <ModelAnalyticsModal
          model={analyticsModel}
          onClose={() => setAnalyticsModel(null)}
        />
      )}

      {/* Comparison Modal */}
      {isComparing && selectedModelsForComparison.length > 0 && (
        <ModelComparisonModal
          models={selectedModelsForComparison}
          onClose={() => setIsComparing(false)}
          onRemoveModel={(id) => handleToggleSelectModel(id)}
        />
      )}
    </div>
  );
};
