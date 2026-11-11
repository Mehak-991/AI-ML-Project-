import React, { useState } from 'react';
import {
  X,
  BarChart2,
  Award,
  TrendingUp,
  Percent,
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
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
} from 'recharts';
import type { ModelRead, SplitMetrics } from '../types/model';

interface ModelAnalyticsModalProps {
  model: ModelRead;
  onClose: () => void;
}

export const ModelAnalyticsModal: React.FC<ModelAnalyticsModalProps> = ({ model, onClose }) => {
  const [activeSplit, setActiveSplit] = useState<'test' | 'validation' | 'train'>('test');

  const isClassification = model.problem_type === 'classification';
  const metricsMap = model.metrics || {};
  const currentMetrics: SplitMetrics = metricsMap[activeSplit] || {};
  const baselineMetrics: SplitMetrics = metricsMap.baseline_test || {};

  // Formatted Metric Card Helper
  const renderMetricCard = (
    title: string,
    value: number | null | undefined,
    format: 'percent' | 'float' = 'percent',
    subtitle?: string
  ) => {
    const hasVal = value !== null && value !== undefined && !isNaN(value);
    const displayVal = hasVal
      ? format === 'percent'
        ? `${(Number(value) * 100).toFixed(1)}%`
        : Number(value).toFixed(4)
      : 'N/A';

    return (
      <div className="bg-slate-50 border border-slate-200 p-4 rounded-xl relative overflow-hidden flex flex-col justify-between">
        <div>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">
            {title}
          </span>
          <div className="mt-2 text-2xl font-black font-mono text-slate-900">
            {displayVal}
          </div>
        </div>
        {subtitle && (
          <span className="text-[11px] text-slate-400 mt-2 block">{subtitle}</span>
        )}
      </div>
    );
  };

  // 1. Train vs Validation vs Test Accuracy Chart Data
  const splitAccuracyData = [
    {
      split: 'Train',
      Accuracy: metricsMap.train?.accuracy ?? null,
      F1: metricsMap.train?.f1_macro ?? null,
      Precision: metricsMap.train?.precision_macro ?? null,
      Recall: metricsMap.train?.recall_macro ?? null,
    },
    {
      split: 'Validation',
      Accuracy: metricsMap.validation?.accuracy ?? null,
      F1: metricsMap.validation?.f1_macro ?? null,
      Precision: metricsMap.validation?.precision_macro ?? null,
      Recall: metricsMap.validation?.recall_macro ?? null,
    },
    {
      split: 'Test',
      Accuracy: metricsMap.test?.accuracy ?? null,
      F1: metricsMap.test?.f1_macro ?? null,
      Precision: metricsMap.test?.precision_macro ?? null,
      Recall: metricsMap.test?.recall_macro ?? null,
    },
  ].filter((item) => item.Accuracy !== null || item.F1 !== null);

  // 2. Baseline vs Model Comparison Data (on Test set)
  const baselineComparisonData = isClassification
    ? [
        {
          metric: 'Accuracy',
          Model: metricsMap.test?.accuracy ?? 0,
          Baseline: baselineMetrics.accuracy ?? 0,
        },
        {
          metric: 'F1 Score',
          Model: metricsMap.test?.f1_macro ?? 0,
          Baseline: baselineMetrics.f1_macro ?? 0,
        },
        {
          metric: 'Precision',
          Model: metricsMap.test?.precision_macro ?? 0,
          Baseline: baselineMetrics.precision_macro ?? 0,
        },
        {
          metric: 'Recall',
          Model: metricsMap.test?.recall_macro ?? 0,
          Baseline: baselineMetrics.recall_macro ?? 0,
        },
      ]
    : [
        {
          metric: 'MAE',
          Model: metricsMap.test?.mae ?? 0,
          Baseline: baselineMetrics.mae ?? 0,
        },
        {
          metric: 'RMSE',
          Model: metricsMap.test?.rmse ?? 0,
          Baseline: baselineMetrics.rmse ?? 0,
        },
        {
          metric: 'R²',
          Model: metricsMap.test?.r2 ?? 0,
          Baseline: baselineMetrics.r2 ?? 0,
        },
      ];

  // 3. Radar Chart for Current Split Classification
  const radarData = isClassification
    ? [
        { metric: 'Accuracy', value: (currentMetrics.accuracy ?? 0) * 100 },
        { metric: 'Balanced Acc', value: (currentMetrics.balanced_accuracy ?? 0) * 100 },
        { metric: 'F1 Macro', value: (currentMetrics.f1_macro ?? 0) * 100 },
        { metric: 'Precision', value: (currentMetrics.precision_macro ?? 0) * 100 },
        { metric: 'Recall', value: (currentMetrics.recall_macro ?? 0) * 100 },
        {
          metric: 'ROC-AUC',
          value:
            ((currentMetrics.roc_auc ?? currentMetrics.roc_auc_ovr_macro ?? 0) * 100),
        },
      ]
    : [];

  // Confusion matrix from current split
  const cm = currentMetrics.confusion_matrix;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-fadeIn">
      <div className="bg-white border border-slate-200 w-full max-w-5xl max-h-[92vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden text-slate-800">
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
              <BarChart2 className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-bold text-slate-900">{model.name}</h3>
                <span className="px-2 py-0.5 rounded-full text-[11px] font-mono font-bold bg-indigo-100 text-indigo-700">
                  v{model.version}
                </span>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono uppercase bg-slate-100 text-slate-700 border border-slate-200">
                  {model.problem_type}
                </span>
              </div>
              <p className="text-xs text-slate-500 font-mono mt-0.5">
                Algorithm: {model.algorithm.replace('_', ' ')} • Target: {model.target_column}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Split Switcher */}
            <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200 text-xs">
              {(['test', 'validation', 'train'] as const).map((split) => (
                <button
                  key={split}
                  onClick={() => setActiveSplit(split)}
                  className={`px-3 py-1 rounded-lg font-semibold capitalize transition-all ${
                    activeSplit === split
                      ? 'bg-white text-indigo-700 shadow-sm'
                      : 'text-slate-500 hover:text-slate-900'
                  }`}
                >
                  {split} ({metricsMap[split]?.n_samples ?? 0})
                </button>
              ))}
            </div>

            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-700 p-2 rounded-lg hover:bg-slate-100 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Analytics Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {/* Performance Metric Cards */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                <Award className="w-4 h-4 text-indigo-600" />
                Performance Metrics ({activeSplit.toUpperCase()} Split)
              </h4>
              <span className="text-xs text-slate-400 font-mono">
                Samples: {currentMetrics.n_samples ?? 0}
              </span>
            </div>

            {isClassification ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
                {renderMetricCard('Accuracy', currentMetrics.accuracy, 'percent')}
                {renderMetricCard('Precision (Macro)', currentMetrics.precision_macro, 'percent')}
                {renderMetricCard('Recall (Macro)', currentMetrics.recall_macro, 'percent')}
                {renderMetricCard('F1 Score (Macro)', currentMetrics.f1_macro, 'percent')}
                {renderMetricCard(
                  'ROC-AUC',
                  currentMetrics.roc_auc ?? currentMetrics.roc_auc_ovr_macro,
                  'percent',
                  currentMetrics.roc_auc !== undefined ? 'Binary' : 'OvR Macro'
                )}
                {renderMetricCard('Log Loss', currentMetrics.log_loss, 'float', 'Cross-entropy')}
                {renderMetricCard(
                  'Balanced Acc',
                  currentMetrics.balanced_accuracy,
                  'percent',
                  'Imbalance adjusted'
                )}
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {renderMetricCard('MAE', currentMetrics.mae, 'float', 'Mean Absolute Error')}
                {renderMetricCard('RMSE', currentMetrics.rmse, 'float', 'Root Mean Squared Error')}
                {renderMetricCard('R² Score', currentMetrics.r2, 'float', 'Variance Explained')}
                {renderMetricCard('Median AE', currentMetrics.median_absolute_error, 'float')}
              </div>
            )}
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Chart 1: Split Comparison (Train vs Val vs Test) */}
            <div className="bg-slate-50 border border-slate-200 p-5 rounded-2xl">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                  <TrendingUp className="w-4 h-4 text-indigo-600" />
                  Train vs Validation vs Test Evaluation
                </h4>
              </div>
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={splitAccuracyData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="split" stroke="#64748b" fontSize={12} />
                    <YAxis stroke="#64748b" fontSize={12} domain={[0, 1]} />
                    <Tooltip
                      formatter={(val: unknown) => {
                        if (typeof val === 'number') {
                          return [`${(val * 100).toFixed(1)}%`];
                        }
                        return [String(val ?? '')];
                      }}
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        border: 'none',
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

            {/* Chart 2: Baseline Model vs Trained Model Comparison on Test Set */}
            <div className="bg-slate-50 border border-slate-200 p-5 rounded-2xl">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                  <Percent className="w-4 h-4 text-emerald-600" />
                  Baseline vs Trained Model (Test Split)
                </h4>
                <span className="text-[11px] text-slate-500 font-mono">
                  Dummy: {model.training_metadata?.baseline_model || 'DummyClassifier'}
                </span>
              </div>
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={baselineComparisonData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="metric" stroke="#64748b" fontSize={12} />
                    <YAxis stroke="#64748b" fontSize={12} />
                    <Tooltip
                      formatter={(val: unknown) => {
                        if (typeof val === 'number') {
                          return [
                            isClassification ? `${(val * 100).toFixed(1)}%` : val.toFixed(3),
                          ];
                        }
                        return [String(val ?? '')];
                      }}
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        border: 'none',
                        borderRadius: '0.75rem',
                        color: '#fff',
                        fontSize: '12px',
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: '12px' }} />
                    <Bar dataKey="Model" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Baseline" fill="#94a3b8" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Row 3: Confusion Matrix & Radar Profile */}
          {isClassification && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {/* Confusion Matrix Heatmap */}
              <div className="bg-slate-50 border border-slate-200 p-5 rounded-2xl">
                <div className="flex items-center justify-between mb-4">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                    Confusion Matrix Heatmap ({activeSplit.toUpperCase()})
                  </h4>
                  <span className="text-xs text-slate-500">Predicted (X) vs True (Y)</span>
                </div>

                {cm && cm.matrix && cm.matrix.length > 0 ? (
                  <div className="flex flex-col items-center justify-center p-2">
                    <div className="text-xs font-semibold text-slate-500 mb-1">Predicted Class</div>
                    <div className="flex items-center">
                      <div className="text-xs font-semibold text-slate-500 -rotate-90 mr-2 whitespace-nowrap">
                        Actual Class
                      </div>
                      <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-sm inline-block">
                        {/* Header labels */}
                        <div className="flex gap-2 mb-2 ml-10">
                          {cm.labels.map((lbl, idx) => (
                            <div
                              key={idx}
                              className="w-14 text-center font-mono font-bold text-xs text-slate-600 truncate"
                              title={String(lbl)}
                            >
                              {String(lbl)}
                            </div>
                          ))}
                        </div>

                        {/* Matrix Rows */}
                        {cm.matrix.map((row, rowIdx) => {
                          const rowTotal = row.reduce((a, b) => a + b, 0);
                          return (
                            <div key={rowIdx} className="flex items-center gap-2 mb-2">
                              <div
                                className="w-8 text-right font-mono font-bold text-xs text-slate-600 truncate"
                                title={String(cm.labels[rowIdx])}
                              >
                                {String(cm.labels[rowIdx])}
                              </div>
                              <div className="flex gap-2">
                                {row.map((count, colIdx) => {
                                  const isDiagonal = rowIdx === colIdx;
                                  const intensity = rowTotal > 0 ? count / rowTotal : 0;
                                  return (
                                    <div
                                      key={colIdx}
                                      className={`w-14 h-12 rounded-lg flex flex-col items-center justify-center transition-all ${
                                        isDiagonal
                                          ? intensity > 0.5
                                            ? 'bg-emerald-600 text-white font-bold'
                                            : 'bg-emerald-100 text-emerald-800 font-semibold'
                                          : count > 0
                                          ? 'bg-rose-100 text-rose-800'
                                          : 'bg-slate-50 text-slate-400'
                                      }`}
                                      title={`True: ${cm.labels[rowIdx]}, Pred: ${cm.labels[colIdx]}: ${count}`}
                                    >
                                      <span className="font-mono text-sm">{count}</span>
                                      <span className="text-[10px] opacity-75">
                                        {(intensity * 100).toFixed(0)}%
                                      </span>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="py-12 text-center text-slate-400 text-xs">
                    No confusion matrix available for this split.
                  </div>
                )}
              </div>

              {/* Radar Chart Summary Profile */}
              <div className="bg-slate-50 border border-slate-200 p-5 rounded-2xl">
                <div className="flex items-center justify-between mb-4">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                    Model Holistic Balance Profile
                  </h4>
                  <span className="text-xs text-slate-500 font-mono">0 - 100% Scale</span>
                </div>
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart cx="50%" cy="50%" outerRadius="80%" data={radarData}>
                      <PolarGrid stroke="#cbd5e1" />
                      <PolarAngleAxis dataKey="metric" stroke="#475569" fontSize={11} />
                      <PolarRadiusAxis angle={30} domain={[0, 100]} stroke="#94a3b8" />
                      <Radar
                        name="Model Quality"
                        dataKey="value"
                        stroke="#4f46e5"
                        fill="#4f46e5"
                        fillOpacity={0.4}
                      />
                      <Tooltip
                        formatter={(val: unknown) => {
                          if (typeof val === 'number') {
                            return [`${val.toFixed(1)}%`];
                          }
                          return [String(val ?? '')];
                        }}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl text-xs font-semibold bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 transition-colors shadow-sm"
          >
            Close Dashboard
          </button>
        </div>
      </div>
    </div>
  );
};
