import React from 'react';
import {
  X,
  GitCompare,
  AlertTriangle,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { ModelRead } from '../types/model';

interface ModelComparisonModalProps {
  models: ModelRead[];
  onClose: () => void;
  onRemoveModel: (id: string) => void;
}

export const ModelComparisonModal: React.FC<ModelComparisonModalProps> = ({
  models,
  onClose,
  onRemoveModel,
}) => {
  if (models.length === 0) return null;

  // Check whether models share the same dataset ID & SHA256
  const firstDatasetId = models[0].dataset_id;
  const firstDatasetSha = models[0].training_metadata?.dataset_sha256;
  const isDifferentDataset = models.some(
    (m) =>
      m.dataset_id !== firstDatasetId ||
      (firstDatasetSha &&
        m.training_metadata?.dataset_sha256 &&
        m.training_metadata.dataset_sha256 !== firstDatasetSha)
  );

  // Check problem types
  const hasMixedProblemTypes = models.some(
    (m) => m.problem_type !== models[0].problem_type
  );

  // Chart data for comparison
  const comparisonChartData = models.map((m) => {
    const testMetrics = m.metrics?.test || m.metrics?.validation || {};
    return {
      name: `${m.name} (v${m.version})`,
      algorithm: m.algorithm,
      Accuracy: testMetrics.accuracy !== undefined && testMetrics.accuracy !== null ? Number(testMetrics.accuracy) * 100 : null,
      F1: testMetrics.f1_macro !== undefined && testMetrics.f1_macro !== null ? Number(testMetrics.f1_macro) * 100 : null,
      Precision: testMetrics.precision_macro !== undefined && testMetrics.precision_macro !== null ? Number(testMetrics.precision_macro) * 100 : null,
      Recall: testMetrics.recall_macro !== undefined && testMetrics.recall_macro !== null ? Number(testMetrics.recall_macro) * 100 : null,
      ROC_AUC:
        (testMetrics.roc_auc ?? testMetrics.roc_auc_ovr_macro) !== undefined &&
        (testMetrics.roc_auc ?? testMetrics.roc_auc_ovr_macro) !== null
          ? Number(testMetrics.roc_auc ?? testMetrics.roc_auc_ovr_macro) * 100
          : null,
      trainingSeconds: m.training_metadata?.training_seconds ?? 0,
    };
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-fadeIn">
      <div className="bg-white border border-slate-200 w-full max-w-5xl max-h-[92vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden text-slate-800">
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
              <GitCompare className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-900">
                Model Benchmark & Comparison
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Comparing {models.length} model artifacts across algorithms, evaluation splits, and performance metrics.
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 p-2 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {/* Validity Warning if models were trained on different datasets or splits */}
          {isDifferentDataset && (
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <strong className="block font-semibold">Different Dataset Warning:</strong>
                Selected models were trained on different datasets or dataset versions. Metric values cannot be compared in a strictly fair cross-validation benchmark.
              </div>
            </div>
          )}

          {hasMixedProblemTypes && (
            <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
              <div>
                <strong className="block font-semibold">Mixed Problem Types:</strong>
                Selected models include both classification and regression tasks. Metric sets differ between problem types.
              </div>
            </div>
          )}

          {/* Side-by-Side Comparison Matrix */}
          <div className="border border-slate-200 rounded-2xl overflow-x-auto shadow-sm">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50/80 border-b border-slate-200 text-slate-500 uppercase tracking-wider">
                  <th className="p-4 font-semibold w-48 bg-slate-50 sticky left-0 z-10 border-r border-slate-200">
                    Attribute / Metric
                  </th>
                  {models.map((m) => (
                    <th key={m.id} className="p-4 font-semibold min-w-[200px] border-r border-slate-100 last:border-r-0">
                      <div className="flex items-center justify-between gap-2">
                        <div>
                          <div className="font-bold text-slate-900 text-sm truncate max-w-[160px]">
                            {m.name}
                          </div>
                          <span className="text-[10px] text-slate-400 font-mono block">v{m.version}</span>
                        </div>
                        {models.length > 2 && (
                          <button
                            onClick={() => onRemoveModel(m.id)}
                            className="text-slate-400 hover:text-rose-600 p-1"
                            title="Remove from comparison"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {/* Algorithm */}
                <tr className="hover:bg-slate-50/50">
                  <td className="p-3.5 font-semibold text-slate-700 bg-slate-50/50 sticky left-0 border-r border-slate-200">
                    Algorithm
                  </td>
                  {models.map((m) => (
                    <td key={m.id} className="p-3.5 capitalize font-medium text-slate-900 border-r border-slate-100 last:border-r-0">
                      {m.algorithm.replace('_', ' ')}
                    </td>
                  ))}
                </tr>

                {/* Problem Type */}
                <tr className="hover:bg-slate-50/50">
                  <td className="p-3.5 font-semibold text-slate-700 bg-slate-50/50 sticky left-0 border-r border-slate-200">
                    Problem Type
                  </td>
                  {models.map((m) => (
                    <td key={m.id} className="p-3.5 uppercase font-mono text-indigo-700 font-bold border-r border-slate-100 last:border-r-0">
                      {m.problem_type}
                    </td>
                  ))}
                </tr>

                {/* Target Column */}
                <tr className="hover:bg-slate-50/50">
                  <td className="p-3.5 font-semibold text-slate-700 bg-slate-50/50 sticky left-0 border-r border-slate-200">
                    Target Column
                  </td>
                  {models.map((m) => (
                    <td key={m.id} className="p-3.5 font-mono text-slate-700 border-r border-slate-100 last:border-r-0">
                      {m.target_column}
                    </td>
                  ))}
                </tr>

                {/* Dataset Provenance */}
                <tr className="hover:bg-slate-50/50">
                  <td className="p-3.5 font-semibold text-slate-700 bg-slate-50/50 sticky left-0 border-r border-slate-200">
                    Dataset ID
                  </td>
                  {models.map((m) => (
                    <td key={m.id} className="p-3.5 font-mono text-slate-500 truncate max-w-[180px] border-r border-slate-100 last:border-r-0" title={m.dataset_id}>
                      {m.dataset_id}
                    </td>
                  ))}
                </tr>

                {/* Test Accuracy */}
                <tr className="hover:bg-slate-50/50">
                  <td className="p-3.5 font-semibold text-slate-700 bg-slate-50/50 sticky left-0 border-r border-slate-200">
                    Test Accuracy
                  </td>
                  {models.map((m) => {
                    const val = m.metrics?.test?.accuracy;
                    return (
                      <td key={m.id} className="p-3.5 font-mono font-bold text-slate-900 border-r border-slate-100 last:border-r-0">
                        {val !== undefined && val !== null ? (
                          <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                            {(Number(val) * 100).toFixed(1)}%
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                    );
                  })}
                </tr>

                {/* Test F1 Score */}
                <tr className="hover:bg-slate-50/50">
                  <td className="p-3.5 font-semibold text-slate-700 bg-slate-50/50 sticky left-0 border-r border-slate-200">
                    Test F1 Score (Macro)
                  </td>
                  {models.map((m) => {
                    const val = m.metrics?.test?.f1_macro;
                    return (
                      <td key={m.id} className="p-3.5 font-mono font-bold text-slate-900 border-r border-slate-100 last:border-r-0">
                        {val !== undefined && val !== null ? `${(Number(val) * 100).toFixed(1)}%` : '—'}
                      </td>
                    );
                  })}
                </tr>

                {/* Test Precision */}
                <tr className="hover:bg-slate-50/50">
                  <td className="p-3.5 font-semibold text-slate-700 bg-slate-50/50 sticky left-0 border-r border-slate-200">
                    Test Precision (Macro)
                  </td>
                  {models.map((m) => {
                    const val = m.metrics?.test?.precision_macro;
                    return (
                      <td key={m.id} className="p-3.5 font-mono text-slate-800 border-r border-slate-100 last:border-r-0">
                        {val !== undefined && val !== null ? `${(Number(val) * 100).toFixed(1)}%` : '—'}
                      </td>
                    );
                  })}
                </tr>

                {/* Test Recall */}
                <tr className="hover:bg-slate-50/50">
                  <td className="p-3.5 font-semibold text-slate-700 bg-slate-50/50 sticky left-0 border-r border-slate-200">
                    Test Recall (Macro)
                  </td>
                  {models.map((m) => {
                    const val = m.metrics?.test?.recall_macro;
                    return (
                      <td key={m.id} className="p-3.5 font-mono text-slate-800 border-r border-slate-100 last:border-r-0">
                        {val !== undefined && val !== null ? `${(Number(val) * 100).toFixed(1)}%` : '—'}
                      </td>
                    );
                  })}
                </tr>

                {/* ROC-AUC */}
                <tr className="hover:bg-slate-50/50">
                  <td className="p-3.5 font-semibold text-slate-700 bg-slate-50/50 sticky left-0 border-r border-slate-200">
                    ROC-AUC
                  </td>
                  {models.map((m) => {
                    const val = m.metrics?.test?.roc_auc ?? m.metrics?.test?.roc_auc_ovr_macro;
                    return (
                      <td key={m.id} className="p-3.5 font-mono text-slate-800 border-r border-slate-100 last:border-r-0">
                        {val !== undefined && val !== null ? `${(Number(val) * 100).toFixed(1)}%` : '—'}
                      </td>
                    );
                  })}
                </tr>

                {/* Training Duration */}
                <tr className="hover:bg-slate-50/50">
                  <td className="p-3.5 font-semibold text-slate-700 bg-slate-50/50 sticky left-0 border-r border-slate-200">
                    Training Duration
                  </td>
                  {models.map((m) => (
                    <td key={m.id} className="p-3.5 font-mono text-slate-700 border-r border-slate-100 last:border-r-0">
                      {m.training_metadata?.training_seconds
                        ? `${m.training_metadata.training_seconds}s`
                        : '< 1s'}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>

          {/* Bar Chart Benchmark */}
          <div className="bg-slate-50 border border-slate-200 p-5 rounded-2xl">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-4">
              Side-by-Side Performance Comparison (Test Set %)
            </h4>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={comparisonChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="name" stroke="#64748b" fontSize={11} />
                  <YAxis stroke="#64748b" fontSize={11} domain={[0, 100]} />
                  <Tooltip
                    formatter={(val: unknown) => {
                      if (typeof val === 'number') {
                        return [`${val.toFixed(1)}%`];
                      }
                      return [String(val ?? '')];
                    }}
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      borderRadius: '0.75rem',
                      color: '#fff',
                      fontSize: '12px',
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px' }} />
                  <Bar dataKey="Accuracy" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="F1" fill="#06b6d4" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Precision" fill="#10b981" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Recall" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl text-xs font-semibold bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 transition-colors shadow-sm"
          >
            Close Comparison
          </button>
        </div>
      </div>
    </div>
  );
};
