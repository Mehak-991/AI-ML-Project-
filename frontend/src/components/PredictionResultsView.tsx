import React, { useState } from 'react';
import {
  Download,
  CheckCircle2,
  Calendar,
  ChevronDown,
  ChevronUp,
  Table,
} from 'lucide-react';
import type { ModelRead, PredictionResultItem } from '../types/model';
import { exportPredictionsToCsv } from '../utils/predictionExport';

interface PredictionResultsViewProps {
  model: ModelRead;
  results: PredictionResultItem[];
  onClearResults: () => void;
}

export const PredictionResultsView: React.FC<PredictionResultsViewProps> = ({
  model,
  results,
  onClearResults,
}) => {
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  if (!results || results.length === 0) {
    return null;
  }

  const classLabels = model.training_metadata?.class_labels;
  const isClassification = model.problem_type === 'classification';

  // Get label display for classification, or direct value for regression
  const getDisplayValue = (pred: string | number | boolean | null) => {
    if (pred === null || pred === undefined) return 'N/A';
    if (classLabels && typeof pred === 'number' && classLabels[pred] !== undefined) {
      return `Class ${pred} (${classLabels[pred]})`;
    }
    return String(pred);
  };

  const handleExportCsv = () => {
    const featureNames = model.feature_schema.map((f) => f.name);
    exportPredictionsToCsv(results, featureNames, model.name, model.id, classLabels);
  };

  const toggleRowExpand = (idx: number) => {
    setExpandedRow((prev) => (prev === idx ? null : idx));
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <h3 className="text-base font-bold text-slate-900">
              Prediction Results Output ({results.length}{' '}
              {results.length === 1 ? 'record' : 'records'})
            </h3>
          </div>
          <p className="text-xs text-slate-500 mt-1 flex items-center gap-2 font-mono">
            <span>Model: {model.name} (v{model.version})</span>
            <span>•</span>
            <span className="truncate max-w-xs">ID: {model.id}</span>
          </p>
        </div>

        <div className="flex items-center gap-2.5 self-start sm:self-auto">
          <button
            type="button"
            onClick={onClearResults}
            className="px-3 py-1.5 rounded-xl border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors"
          >
            Clear Results
          </button>

          <button
            type="button"
            onClick={handleExportCsv}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-colors cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            Export to CSV
          </button>
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">
            Records Processed
          </span>
          <span className="text-2xl font-bold font-mono text-slate-900 mt-1 block">
            {results.length}
          </span>
          <span className="text-[11px] text-emerald-600 font-medium mt-0.5 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> 100% Inferred Successfully
          </span>
        </div>

        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">
            Problem Type
          </span>
          <span className="text-lg font-bold text-slate-900 capitalize mt-1 block font-mono">
            {model.problem_type}
          </span>
          <span className="text-[11px] text-slate-500 mt-0.5 block">
            Target: <strong className="text-slate-800">{model.target_column}</strong>
          </span>
        </div>

        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">
            Latest Execution Time
          </span>
          <span className="text-xs font-mono font-medium text-slate-800 mt-2 block flex items-center gap-1">
            <Calendar className="w-3.5 h-3.5 text-slate-400" />
            {results[0]?.timestamp ? new Date(results[0].timestamp).toLocaleTimeString() : 'Just now'}
          </span>
          <span className="text-[10px] text-slate-400 mt-0.5 block font-mono">
            Algorithm: {model.algorithm}
          </span>
        </div>
      </div>

      {/* Results Table */}
      <div className="border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
        <div className="max-h-96 overflow-x-auto overflow-y-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-700 font-semibold sticky top-0 z-10">
              <tr>
                <th className="py-2.5 px-3 w-12 text-center">#</th>
                <th className="py-2.5 px-3 min-w-[120px]">Predicted Output</th>
                {isClassification && (
                  <th className="py-2.5 px-3 min-w-[200px]">Class Probabilities</th>
                )}
                <th className="py-2.5 px-3 min-w-[220px]">Key Input Features</th>
                <th className="py-2.5 px-3 w-16 text-center">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {results.map((item) => {
                const isExpanded = expandedRow === item.index;
                const displayVal = getDisplayValue(item.prediction);

                return (
                  <React.Fragment key={item.index}>
                    <tr
                      className={`hover:bg-slate-50/70 transition-colors ${
                        isExpanded ? 'bg-indigo-50/30' : ''
                      }`}
                    >
                      <td className="py-2.5 px-3 text-center text-slate-400 font-mono text-[11px]">
                        {item.index + 1}
                      </td>

                      {/* Prediction column */}
                      <td className="py-2.5 px-3">
                        <div className="flex items-center gap-2">
                          <span className="px-2.5 py-1 rounded-lg bg-indigo-600 text-white font-mono font-bold text-xs shadow-2xs">
                            {displayVal}
                          </span>
                        </div>
                      </td>

                      {/* Probabilities column */}
                      {isClassification && (
                        <td className="py-2.5 px-3">
                          {item.probabilities ? (
                            <div className="space-y-1.5 max-w-xs">
                              {Object.entries(item.probabilities).map(([cls, prob]) => {
                                const percentage = Math.round(prob * 100);
                                const isWinner =
                                  String(item.prediction) === String(cls) ||
                                  (typeof item.prediction === 'number' &&
                                    Number(cls) === item.prediction);
                                return (
                                  <div key={cls} className="space-y-0.5">
                                    <div className="flex items-center justify-between text-[10px] font-mono">
                                      <span
                                        className={
                                          isWinner
                                            ? 'font-bold text-indigo-700'
                                            : 'text-slate-600'
                                        }
                                      >
                                        Class {cls}:
                                      </span>
                                      <span className="font-semibold text-slate-700">
                                        {(prob * 100).toFixed(1)}%
                                      </span>
                                    </div>
                                    <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                      <div
                                        className={`h-full rounded-full transition-all duration-300 ${
                                          isWinner ? 'bg-indigo-600' : 'bg-slate-300'
                                        }`}
                                        style={{ width: `${percentage}%` }}
                                      />
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <span className="text-slate-400 italic text-[11px]">
                              Not returned by model
                            </span>
                          )}
                        </td>
                      )}

                      {/* Input summary column */}
                      <td className="py-2.5 px-3">
                        <div className="flex flex-wrap gap-1 max-w-sm">
                          {Object.entries(item.input).map(([k, v]) => (
                            <span
                              key={k}
                              className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-mono"
                            >
                              {k}: <strong className="text-slate-900">{String(v ?? 'null')}</strong>
                            </span>
                          ))}
                        </div>
                      </td>

                      {/* Expand / Details Toggle */}
                      <td className="py-2.5 px-3 text-center">
                        <button
                          type="button"
                          onClick={() => toggleRowExpand(item.index)}
                          className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                          title="View record details"
                        >
                          {isExpanded ? (
                            <ChevronUp className="w-4 h-4 text-indigo-600" />
                          ) : (
                            <ChevronDown className="w-4 h-4" />
                          )}
                        </button>
                      </td>
                    </tr>

                    {/* Detailed Row Expansion */}
                    {isExpanded && (
                      <tr className="bg-slate-50/80">
                        <td colSpan={isClassification ? 5 : 4} className="p-4">
                          <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-3">
                            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                              <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                                <Table className="w-3.5 h-3.5 text-indigo-600" />
                                Record #{item.index + 1} Detailed Feature Payload
                              </span>
                              <span className="text-[11px] text-slate-400 font-mono">
                                Timestamp: {new Date(item.timestamp).toISOString()}
                              </span>
                            </div>

                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                              {Object.entries(item.input).map(([featureName, featureVal]) => (
                                <div
                                  key={featureName}
                                  className="p-2.5 rounded-lg bg-slate-50 border border-slate-100"
                                >
                                  <span className="text-[10px] text-slate-400 block uppercase font-mono">
                                    {featureName}
                                  </span>
                                  <span className="font-semibold text-slate-800 font-mono text-xs mt-0.5 block truncate">
                                    {featureVal === null ? (
                                      <span className="text-amber-600 italic">null (imputed)</span>
                                    ) : (
                                      String(featureVal)
                                    )}
                                  </span>
                                </div>
                              ))}
                            </div>

                            {item.probabilities && (
                              <div className="pt-2 border-t border-slate-100 text-xs">
                                <span className="font-semibold text-slate-700 block mb-1">
                                  Raw Model Class Probability Distribution:
                                </span>
                                <div className="flex flex-wrap gap-2">
                                  {Object.entries(item.probabilities).map(([cls, prob]) => (
                                    <div
                                      key={cls}
                                      className="px-2.5 py-1 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-900 font-mono text-[11px]"
                                    >
                                      Class {cls}: {prob.toFixed(6)}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
