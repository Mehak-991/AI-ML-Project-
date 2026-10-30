import React, { useEffect, useState } from 'react';
import {
  X,
  Cpu,
  Database,
  Calendar,
  Layers,
  Hash,
  ShieldCheck,
  BarChart2,
  Clock,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import type { ModelRead } from '../types/model';
import { modelApi, parseApiError, type ErrorDetails } from '../services/api';

interface ModelDetailModalProps {
  modelId: string;
  initialModel?: ModelRead | null;
  onClose: () => void;
  onOpenAnalytics: (model: ModelRead) => void;
}

export const ModelDetailModal: React.FC<ModelDetailModalProps> = ({
  modelId,
  initialModel,
  onClose,
  onOpenAnalytics,
}) => {
  const [model, setModel] = useState<ModelRead | null>(initialModel || null);
  const [loading, setLoading] = useState<boolean>(!initialModel);
  const [errorDetails, setErrorDetails] = useState<ErrorDetails | null>(null);

  useEffect(() => {
    let isMounted = true;
    const fetchModel = async () => {
      setLoading(true);
      setErrorDetails(null);
      try {
        const data = await modelApi.getModel(modelId);
        if (isMounted) {
          setModel(data);
        }
      } catch (err) {
        if (isMounted) {
          setErrorDetails(parseApiError(err));
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    fetchModel();
    return () => {
      isMounted = false;
    };
  }, [modelId]);

  const formatDate = (isoString: string): string => {
    try {
      return new Date(isoString).toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-fadeIn">
      <div className="bg-white border border-slate-200 w-full max-w-4xl max-h-[92vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden text-slate-800">
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-bold text-slate-900">
                  {model?.name || 'Loading Model...'}
                </h3>
                {model && (
                  <span className="px-2 py-0.5 rounded-full text-[11px] font-mono font-bold bg-indigo-100 text-indigo-700">
                    v{model.version}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 font-mono mt-0.5">ID: {modelId}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {model && (
              <button
                onClick={() => {
                  onClose();
                  onOpenAnalytics(model);
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm transition-colors"
              >
                <BarChart2 className="w-3.5 h-3.5" />
                Open Analytics
              </button>
            )}
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-700 p-2 rounded-lg hover:bg-slate-100 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Scrollable Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {loading ? (
            <div className="py-20 text-center text-slate-400">
              <Loader2 className="w-8 h-8 animate-spin mx-auto text-indigo-600 mb-3" />
              <p className="text-sm">Fetching model metadata from server...</p>
            </div>
          ) : errorDetails ? (
            <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold">{errorDetails.message}</span>
                <p className="text-xs text-red-500 mt-1">Endpoint: GET /api/v1/models/{modelId}</p>
              </div>
            </div>
          ) : model ? (
            <>
              {/* Primary Metadata Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
                <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                  <span className="text-xs text-slate-500 flex items-center gap-1">
                    <Layers className="w-3.5 h-3.5 text-indigo-600" /> Algorithm
                  </span>
                  <p className="text-sm font-bold text-slate-900 mt-1 capitalize">
                    {model.algorithm.replace('_', ' ')}
                  </p>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {model.training_metadata?.estimator || 'Scikit-Learn'}
                  </span>
                </div>

                <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                  <span className="text-xs text-slate-500 flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> Problem Type
                  </span>
                  <p className="text-sm font-bold text-slate-900 mt-1 uppercase font-mono">
                    {model.problem_type}
                  </p>
                  <span className="text-[10px] text-slate-500">
                    Target: <strong className="text-slate-700 font-mono">{model.target_column}</strong>
                  </span>
                </div>

                <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                  <span className="text-xs text-slate-500 flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5 text-amber-600" /> Duration
                  </span>
                  <p className="text-sm font-bold text-slate-900 mt-1 font-mono">
                    {model.training_metadata?.training_seconds
                      ? `${model.training_metadata.training_seconds}s`
                      : '< 1s'}
                  </p>
                  <span className="text-[10px] text-slate-500">
                    Scikit-Learn v{model.sklearn_version}
                  </span>
                </div>

                <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                  <span className="text-xs text-slate-500 flex items-center gap-1">
                    <Calendar className="w-3.5 h-3.5 text-purple-600" /> Trained At
                  </span>
                  <p className="text-xs font-semibold text-slate-800 mt-1 truncate">
                    {formatDate(model.created_at)}
                  </p>
                  <span className="text-[10px] text-emerald-600 font-medium">Status: Ready</span>
                </div>
              </div>

              {/* Dataset Connection & Provenance */}
              <div className="p-4 rounded-xl bg-indigo-50/40 border border-indigo-100 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center">
                    <Database className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-slate-500 block">Trained on Dataset ID</span>
                    <span className="font-mono font-bold text-slate-900">{model.dataset_id}</span>
                  </div>
                </div>

                {model.training_metadata?.dataset_sha256 && (
                  <div className="text-right">
                    <span className="text-slate-500 block">Dataset Hash SHA-256</span>
                    <span className="font-mono text-slate-700 font-medium text-[11px]">
                      {model.training_metadata.dataset_sha256.slice(0, 16)}...
                    </span>
                  </div>
                )}
              </div>

              {/* Training Configuration & Data Splits */}
              <div className="border border-slate-200 rounded-xl overflow-hidden">
                <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Data Splits & Samples
                  </span>
                  <span className="text-xs font-mono text-slate-500">
                    Random State: {model.training_metadata?.config?.random_state ?? 42}
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-5 divide-x divide-slate-100 text-center p-3 text-xs">
                  <div>
                    <span className="text-slate-400 block text-[11px]">Raw Rows</span>
                    <span className="font-mono font-bold text-slate-800 text-sm">
                      {model.training_metadata?.rows?.raw ?? '—'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[11px]">Used Rows</span>
                    <span className="font-mono font-bold text-slate-800 text-sm">
                      {model.training_metadata?.rows?.used ?? '—'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[11px]">Train Split</span>
                    <span className="font-mono font-bold text-slate-800 text-sm">
                      {model.training_metadata?.rows?.train ?? '—'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[11px]">Validation Split</span>
                    <span className="font-mono font-bold text-slate-800 text-sm">
                      {model.training_metadata?.rows?.validation ?? '—'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[11px]">Test Split</span>
                    <span className="font-mono font-bold text-slate-800 text-sm">
                      {model.training_metadata?.rows?.test ?? '—'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Feature Schema Table */}
              <div className="border border-slate-200 rounded-xl overflow-hidden">
                <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Feature Schema ({model.feature_schema.length} Features)
                  </span>
                  <span className="text-xs text-slate-500">Required inference columns</span>
                </div>
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50/60 text-slate-500 uppercase tracking-wider border-b border-slate-100">
                    <tr>
                      <th className="px-4 py-2">#</th>
                      <th className="px-4 py-2">Feature Name</th>
                      <th className="px-4 py-2">Data Kind</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono">
                    {model.feature_schema.map((feat, idx) => (
                      <tr key={feat.name} className="hover:bg-slate-50/50">
                        <td className="px-4 py-2 text-slate-400">{idx + 1}</td>
                        <td className="px-4 py-2 font-semibold text-slate-900 font-sans flex items-center gap-1.5">
                          <Hash className="w-3.5 h-3.5 text-slate-400" />
                          {feat.name}
                        </td>
                        <td className="px-4 py-2">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-sans font-medium uppercase ${
                              feat.kind === 'numeric'
                                ? 'bg-blue-50 text-blue-700 border border-blue-200'
                                : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            }`}
                          >
                            {feat.kind}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl text-xs font-semibold bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 transition-colors shadow-sm"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
