import React from 'react';
import { Layers, CheckCircle2, Search, Hash, Cpu, Target, Calendar } from 'lucide-react';
import type { ModelRead } from '../types/model';

interface ModelSelectorProps {
  models: ModelRead[];
  selectedModel: ModelRead | null;
  onSelectModel: (model: ModelRead) => void;
  loading: boolean;
  manualModelId: string;
  onManualModelIdChange: (id: string) => void;
  onFetchManualModel: () => void;
  isFetchingManual: boolean;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  models,
  selectedModel,
  onSelectModel,
  loading,
  manualModelId,
  onManualModelIdChange,
  onFetchManualModel,
  isFetchingManual,
}) => {
  const [filterQuery, setFilterQuery] = React.useState('');

  const filteredModels = models.filter(
    (m) =>
      m.name.toLowerCase().includes(filterQuery.toLowerCase()) ||
      m.id.toLowerCase().includes(filterQuery.toLowerCase()) ||
      m.algorithm.toLowerCase().includes(filterQuery.toLowerCase()) ||
      m.problem_type.toLowerCase().includes(filterQuery.toLowerCase())
  );

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
        <div>
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Layers className="w-4 h-4 text-indigo-600" />
            1. Select Trained Model
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Choose an active model artifact to load its validated feature schema and generate predictions.
          </p>
        </div>

        {selectedModel && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold self-start sm:self-auto">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
            <span className="truncate max-w-[200px]">Active: {selectedModel.name}</span>
            <span className="px-1.5 py-0.2 rounded bg-emerald-200/70 text-emerald-900 text-[10px] font-mono">
              v{selectedModel.version}
            </span>
          </div>
        )}
      </div>

      {/* Search & Selection Grid */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search by model name, algorithm, or ID..."
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
            />
          </div>

          {/* Manual ID fallback input per requirement */}
          <div className="flex gap-2">
            <div className="relative">
              <Hash className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Or paste Model UUID..."
                value={manualModelId}
                onChange={(e) => onManualModelIdChange(e.target.value)}
                className="w-56 pl-9 pr-3 py-2 text-xs font-mono bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
              />
            </div>
            <button
              type="button"
              onClick={onFetchManualModel}
              disabled={isFetchingManual || !manualModelId.trim()}
              className="px-3.5 py-2 text-xs font-semibold rounded-xl bg-slate-800 hover:bg-slate-900 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
            >
              {isFetchingManual ? 'Loading...' : 'Load'}
            </button>
          </div>
        </div>

        {/* Model Cards / List */}
        {loading ? (
          <div className="py-8 text-center text-slate-500 text-xs">
            <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            Fetching registered models...
          </div>
        ) : filteredModels.length === 0 ? (
          <div className="py-8 text-center bg-slate-50 border border-dashed border-slate-200 rounded-xl">
            <p className="text-xs text-slate-600 font-medium">No trained models matched your query.</p>
            <p className="text-[11px] text-slate-400 mt-1">
              Ensure you have trained a baseline model in Phase 5 or verify the Model UUID above.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-h-60 overflow-y-auto pr-1">
            {filteredModels.map((m) => {
              const isSelected = selectedModel?.id === m.id;
              return (
                <div
                  key={m.id}
                  onClick={() => onSelectModel(m)}
                  className={`p-3.5 rounded-xl border text-left cursor-pointer transition-all ${
                    isSelected
                      ? 'border-indigo-600 bg-indigo-50/50 shadow-sm ring-2 ring-indigo-500/20'
                      : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="truncate">
                      <div className="font-semibold text-slate-900 text-xs truncate flex items-center gap-1.5">
                        <span className="truncate">{m.name}</span>
                        <span className="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-slate-100 text-slate-700 border border-slate-200">
                          v{m.version}
                        </span>
                      </div>
                      <p className="text-[10px] font-mono text-slate-400 truncate mt-0.5">
                        ID: {m.id}
                      </p>
                    </div>
                    {isSelected && (
                      <span className="w-2 h-2 rounded-full bg-indigo-600 shrink-0 mt-1" />
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-2 mt-3 pt-2.5 border-t border-slate-100/80 text-[11px]">
                    <div>
                      <span className="text-[10px] text-slate-400 block">Algorithm</span>
                      <span className="font-mono font-medium text-slate-700 capitalize">
                        {m.algorithm.replace('_', ' ')}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400 block">Target Column</span>
                      <span className="font-mono font-medium text-indigo-700 truncate block">
                        {m.target_column}
                      </span>
                    </div>
                  </div>

                  <div className="mt-2.5 flex items-center justify-between text-[10px] text-slate-500">
                    <span className="px-1.5 py-0.5 rounded font-medium bg-slate-100 text-slate-600 capitalize">
                      {m.problem_type}
                    </span>
                    <span>{m.feature_schema.length} input features</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Selected Model Detailed Spec Banner */}
      {selectedModel && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-indigo-600" />
              <span className="font-bold text-slate-800">
                Active Schema: {selectedModel.name} (v{selectedModel.version})
              </span>
            </div>
            <div className="flex items-center gap-3 text-[11px] text-slate-500 font-mono">
              <span className="flex items-center gap-1">
                <Target className="w-3.5 h-3.5 text-indigo-500" />
                Target: <strong className="text-slate-800">{selectedModel.target_column}</strong>
              </span>
              <span className="flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5 text-slate-400" />
                Trained: {new Date(selectedModel.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>

          <div>
            <span className="text-[11px] font-semibold text-slate-600 block mb-1.5">
              Input Feature Schema ({selectedModel.feature_schema.length} columns expected):
            </span>
            <div className="flex flex-wrap gap-1.5">
              {selectedModel.feature_schema.map((feat) => (
                <span
                  key={feat.name}
                  className="px-2 py-1 rounded-lg bg-white border border-slate-200 text-slate-700 text-[11px] font-mono flex items-center gap-1 shadow-2xs"
                >
                  <span className="font-medium">{feat.name}</span>
                  <span
                    className={`text-[9px] px-1 py-0.2 rounded font-sans uppercase font-bold ${
                      feat.kind === 'numeric'
                        ? 'bg-blue-50 text-blue-700'
                        : 'bg-emerald-50 text-emerald-700'
                    }`}
                  >
                    {feat.kind}
                  </span>
                </span>
              ))}
            </div>
          </div>

          {selectedModel.training_metadata?.class_labels && (
            <div className="pt-2 border-t border-slate-200/60 flex items-center gap-2 text-[11px] text-slate-600">
              <span className="font-semibold text-slate-700">Identified Class Labels:</span>
              <div className="flex items-center gap-1.5">
                {selectedModel.training_metadata.class_labels.map((lbl, idx) => (
                  <span
                    key={idx}
                    className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 font-mono font-medium border border-indigo-100"
                  >
                    Class {idx}: {String(lbl)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
