import React, { useState } from 'react';
import {
  Target,
  Activity,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import type { ModelRead, SplitMetrics } from '../types/model';

interface ModelPerformanceMonitoringSectionProps {
  model: ModelRead | null;
}

export const ModelPerformanceMonitoringSection: React.FC<
  ModelPerformanceMonitoringSectionProps
> = ({ model }) => {
  const [activeSplit, setActiveSplit] = useState<'test' | 'train' | 'validation' | 'baseline_test'>('test');

  if (!model) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-8 text-center text-slate-500 text-xs">
        Select a model to inspect its training and evaluation metrics.
      </div>
    );
  }

  const isClassification = model.problem_type === 'classification';
  const splitMetrics: SplitMetrics | undefined = model.metrics?.[activeSplit];
  const baselineMetrics: SplitMetrics | undefined = model.metrics?.baseline_test;

  // Prepare comparison data for chart
  const comparisonData = [
    {
      metric: 'Accuracy',
      Model: splitMetrics?.accuracy !== undefined && splitMetrics?.accuracy !== null ? Number((splitMetrics.accuracy * 100).toFixed(1)) : 0,
      Baseline: baselineMetrics?.accuracy !== undefined && baselineMetrics?.accuracy !== null ? Number((baselineMetrics.accuracy * 100).toFixed(1)) : 0,
    },
    {
      metric: 'F1 Score (Macro)',
      Model: splitMetrics?.f1_macro !== undefined && splitMetrics?.f1_macro !== null ? Number((splitMetrics.f1_macro * 100).toFixed(1)) : 0,
      Baseline: baselineMetrics?.f1_macro !== undefined && baselineMetrics?.f1_macro !== null ? Number((baselineMetrics.f1_macro * 100).toFixed(1)) : 0,
    },
    {
      metric: 'Precision',
      Model: splitMetrics?.precision_macro !== undefined && splitMetrics?.precision_macro !== null ? Number((splitMetrics.precision_macro * 100).toFixed(1)) : 0,
      Baseline: baselineMetrics?.precision_macro !== undefined && baselineMetrics?.precision_macro !== null ? Number((baselineMetrics.precision_macro * 100).toFixed(1)) : 0,
    },
    {
      metric: 'Recall',
      Model: splitMetrics?.recall_macro !== undefined && splitMetrics?.recall_macro !== null ? Number((splitMetrics.recall_macro * 100).toFixed(1)) : 0,
      Baseline: baselineMetrics?.recall_macro !== undefined && baselineMetrics?.recall_macro !== null ? Number((baselineMetrics.recall_macro * 100).toFixed(1)) : 0,
    },
  ];

  const confusionMatrix = splitMetrics?.confusion_matrix;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-6">
      {/* Header and Live vs Historical distinction notice */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div>
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Target className="w-4 h-4 text-indigo-600" />
            Model Performance & Validation Benchmarks
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Statistical evaluation metrics generated during model training and validation splits.
          </p>
        </div>

        {/* Split selector */}
        <div className="flex items-center bg-slate-100 p-1 rounded-xl text-xs font-semibold self-start sm:self-auto">
          {(['test', 'validation', 'train', 'baseline_test'] as const).map((split) => (
            <button
              key={split}
              type="button"
              onClick={() => setActiveSplit(split)}
              className={`px-3 py-1 rounded-lg transition-all capitalize ${
                activeSplit === split
                  ? 'bg-white text-indigo-600 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {split.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      {/* Critical Monitoring Distinction Alert */}
      <div className="p-3.5 rounded-xl bg-blue-50 border border-blue-200 text-blue-900 text-xs flex items-start gap-3">
        <Activity className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
        <div className="leading-relaxed text-[11px]">
          <strong className="block font-semibold text-blue-900">
            Metric Source: Historical Training & Evaluation Splits
          </strong>
          These metrics represent offline hold-out evaluation performance (samples: {splitMetrics?.n_samples ?? 'N/A'}).
          <strong> Live production accuracy and concept/data drift monitoring</strong> require ground-truth feedback ingestion, which is not tracked by the stateless backend.
        </div>
      </div>

      {/* KPI Cards for Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
          <span className="text-[10px] text-slate-400 font-semibold uppercase block">
            {isClassification ? 'Accuracy' : 'MAE'}
          </span>
          <span className="text-xl font-extrabold font-mono text-slate-900 mt-1 block">
            {isClassification
              ? splitMetrics?.accuracy !== undefined && splitMetrics?.accuracy !== null
                ? `${(splitMetrics.accuracy * 100).toFixed(1)}%`
                : 'N/A'
              : splitMetrics?.mae !== undefined && splitMetrics?.mae !== null
              ? splitMetrics.mae.toFixed(4)
              : 'N/A'}
          </span>
          <span className="text-[10px] text-slate-500 mt-0.5 block">
            {activeSplit} split
          </span>
        </div>

        <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
          <span className="text-[10px] text-slate-400 font-semibold uppercase block">
            {isClassification ? 'F1-Score (Macro)' : 'RMSE'}
          </span>
          <span className="text-xl font-extrabold font-mono text-slate-900 mt-1 block">
            {isClassification
              ? splitMetrics?.f1_macro !== undefined && splitMetrics?.f1_macro !== null
                ? splitMetrics.f1_macro.toFixed(4)
                : 'N/A'
              : splitMetrics?.rmse !== undefined && splitMetrics?.rmse !== null
              ? splitMetrics.rmse.toFixed(4)
              : 'N/A'}
          </span>
          <span className="text-[10px] text-slate-500 mt-0.5 block">
            {activeSplit} split
          </span>
        </div>

        <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
          <span className="text-[10px] text-slate-400 font-semibold uppercase block">
            {isClassification ? 'ROC-AUC' : 'R² Score'}
          </span>
          <span className="text-xl font-extrabold font-mono text-slate-900 mt-1 block">
            {isClassification
              ? splitMetrics?.roc_auc !== undefined && splitMetrics?.roc_auc !== null
                ? splitMetrics.roc_auc.toFixed(4)
                : 'N/A'
              : splitMetrics?.r2 !== undefined && splitMetrics?.r2 !== null
              ? splitMetrics.r2.toFixed(4)
              : 'N/A'}
          </span>
          <span className="text-[10px] text-slate-500 mt-0.5 block">
            {activeSplit} split
          </span>
        </div>

        <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
          <span className="text-[10px] text-slate-400 font-semibold uppercase block">
            Evaluation Samples
          </span>
          <span className="text-xl font-extrabold font-mono text-slate-900 mt-1 block">
            {splitMetrics?.n_samples ?? 0}
          </span>
          <span className="text-[10px] text-slate-500 mt-0.5 block">
            Rows in {activeSplit}
          </span>
        </div>
      </div>

      {/* Chart & Confusion Matrix Side by Side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Model vs Baseline Chart */}
        <div className="border border-slate-200 rounded-xl p-4 bg-white space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-800">
              Model vs Dummy Baseline ({activeSplit} vs baseline_test)
            </span>
            <span className="text-[10px] font-mono text-slate-400">Values in %</span>
          </div>

          <div className="h-60 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <RechartsBarChart
                data={comparisonData}
                margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="metric" tick={{ fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                <Tooltip
                  formatter={(val: unknown) => [`${val}%`, 'Score']}
                  contentStyle={{ fontSize: '11px', borderRadius: '8px' }}
                />
                <Bar dataKey="Model" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Baseline" fill="#94a3b8" radius={[4, 4, 0, 0]} />
              </RechartsBarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Confusion Matrix Display */}
        <div className="border border-slate-200 rounded-xl p-4 bg-white space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-800">
              Confusion Matrix ({activeSplit} split)
            </span>
            <span className="text-[10px] font-mono text-slate-500">
              Labels: {confusionMatrix ? confusionMatrix.labels.join(', ') : 'None'}
            </span>
          </div>

          {confusionMatrix && confusionMatrix.matrix ? (
            <div className="overflow-x-auto pt-2">
              <table className="w-full text-xs text-center border-collapse">
                <thead>
                  <tr>
                    <th className="p-2 border border-slate-200 bg-slate-50 text-[10px] text-slate-500 font-mono">
                      Actual \ Predicted
                    </th>
                    {confusionMatrix.labels.map((lbl, idx) => (
                      <th
                        key={idx}
                        className="p-2 border border-slate-200 bg-slate-50 font-mono text-slate-700"
                      >
                        Class {String(lbl)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {confusionMatrix.matrix.map((row, rowIdx) => (
                    <tr key={rowIdx}>
                      <td className="p-2 border border-slate-200 bg-slate-50 font-mono font-bold text-slate-700">
                        Class {String(confusionMatrix.labels[rowIdx])}
                      </td>
                      {row.map((cellVal, colIdx) => {
                        const isDiagonal = rowIdx === colIdx;
                        return (
                          <td
                            key={colIdx}
                            className={`p-3 border border-slate-200 font-mono font-bold text-sm ${
                              isDiagonal
                                ? 'bg-indigo-50 text-indigo-700'
                                : cellVal > 0
                                ? 'bg-red-50 text-red-700'
                                : 'text-slate-400'
                            }`}
                          >
                            {cellVal}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="h-56 flex items-center justify-center text-slate-400 text-xs italic">
              No confusion matrix available for regression or this split.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
