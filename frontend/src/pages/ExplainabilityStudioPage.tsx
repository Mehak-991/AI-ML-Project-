import { useState, useEffect, useCallback } from 'react';
import {
  Brain,
  HelpCircle,
  BarChart2,
  ListFilter,
  CheckCircle2,
  RefreshCw,
  Info,
  ChevronDown,
  ChevronRight,
  TrendingUp,
  TrendingDown,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  Legend,
} from 'recharts';
import { modelApi, explainabilityApi } from '../services/api';
import type { ModelRead } from '../types/model';
import type {
  GlobalFeatureImportanceResponse,
  LocalShapExplanationResponse,
  LocalLimeExplanationResponse,
  ExplainabilitySummaryResponse,
} from '../types/explainability';

export function ExplainabilityStudioPage() {
  const [models, setModels] = useState<ModelRead[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<string>('');
  const [selectedModel, setSelectedModel] = useState<ModelRead | null>(null);
  const [summary, setSummary] = useState<ExplainabilitySummaryResponse | null>(null);

  // Global feature importance
  const [globalImportance, setGlobalImportance] = useState<GlobalFeatureImportanceResponse | null>(null);
  const [loadingGlobal, setLoadingGlobal] = useState(false);

  // Local record explainability state
  const [recordInputs, setRecordInputs] = useState<Record<string, any>>({});
  const [shapResult, setShapResult] = useState<LocalShapExplanationResponse | null>(null);
  const [limeResult, setLimeResult] = useState<LocalLimeExplanationResponse | null>(null);
  const [activeLocalMethod, setActiveLocalMethod] = useState<'shap' | 'lime'>('shap');
  const [explainingLocal, setExplainingLocal] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);

  // Fetch Models
  useEffect(() => {
    async function loadModels() {
      try {
        const res = await modelApi.listModels();
        setModels(res.items);
        if (res.items.length > 0) {
          setSelectedModelId(res.items[0].id);
          setSelectedModel(res.items[0]);
        }
      } catch (err) {
        console.error('Failed to list models', err);
      }
    }
    loadModels();
  }, []);

  // Update selected model & defaults
  useEffect(() => {
    if (selectedModelId) {
      const found = models.find((m) => m.id === selectedModelId) || null;
      setSelectedModel(found);
      if (found) {
        const initialInputs: Record<string, any> = {};
        found.feature_schema.forEach((f) => {
          initialInputs[f.name] = f.kind === 'numeric' ? 0.0 : '';
        });
        setRecordInputs(initialInputs);
      }
    }
  }, [selectedModelId, models]);

  // Load Model Summary & Global Importance
  const loadExplainabilityData = useCallback(async () => {
    if (!selectedModelId) return;
    try {
      setLoadingGlobal(true);
      setErrorText(null);
      const [sumRes, globalRes] = await Promise.all([
        explainabilityApi.getSummary(selectedModelId),
        explainabilityApi.getGlobalImportance(selectedModelId, 40),
      ]);
      setSummary(sumRes);
      setGlobalImportance(globalRes);
    } catch (err: any) {
      console.error('Failed to load explainability data', err);
      setErrorText(err.response?.data?.error?.message || 'Could not load explainability data');
    } finally {
      setLoadingGlobal(false);
    }
  }, [selectedModelId]);

  useEffect(() => {
    loadExplainabilityData();
  }, [loadExplainabilityData]);

  const handleComputeLocalExplanation = async () => {
    if (!selectedModelId) return;
    try {
      setExplainingLocal(true);
      setErrorText(null);

      // Parse numeric fields
      const cleanRecord: Record<string, any> = {};
      selectedModel?.feature_schema.forEach((f) => {
        const val = recordInputs[f.name];
        cleanRecord[f.name] = f.kind === 'numeric' ? (parseFloat(val) || 0.0) : val;
      });

      if (activeLocalMethod === 'shap') {
        const res = await explainabilityApi.explainWithShap(selectedModelId, {
          record: cleanRecord,
          num_features: 10,
          background_samples: 30,
        });
        setShapResult(res);
      } else {
        const res = await explainabilityApi.explainWithLime(selectedModelId, {
          record: cleanRecord,
          num_features: 10,
        });
        setLimeResult(res);
      }
    } catch (err: any) {
      console.error('Failed to compute local explanation', err);
      setErrorText(err.response?.data?.error?.message || 'Explanation failed');
    } finally {
      setExplainingLocal(false);
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              Model Explainability & Attribution Studio
            </h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
              Phase 13
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Global SHAP feature attribution and local LIME/SHAP prediction explanations.
          </p>
        </div>

        <button
          onClick={loadExplainabilityData}
          disabled={loadingGlobal}
          className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-lg shadow-sm hover:bg-slate-50 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loadingGlobal ? 'animate-spin' : ''}`} />
          Refresh Attribution
        </button>
      </div>

      {errorText && (
        <div className="p-4 rounded-xl bg-rose-50 text-rose-800 border border-rose-200 text-xs flex items-center justify-between">
          <span>{errorText}</span>
          <button onClick={() => setErrorText(null)} className="font-bold uppercase text-[10px]">
            Dismiss
          </button>
        </div>
      )}

      {/* Model Selector Card */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="w-full sm:w-1/2">
          <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wider mb-1.5">
            Select Model for Explanation
          </label>
          <div className="relative">
            <select
              value={selectedModelId}
              onChange={(e) => setSelectedModelId(e.target.value)}
              className="w-full appearance-none bg-slate-50 border border-slate-300 text-slate-900 text-sm rounded-lg px-3.5 py-2.5 pr-8 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} (v{m.version}) — {m.algorithm}
                </option>
              ))}
            </select>
            <ChevronDown className="w-4 h-4 text-slate-500 absolute right-3 top-3.5 pointer-events-none" />
          </div>
        </div>

        {summary && (
          <div className="flex items-center gap-4 text-xs text-slate-600">
            <div>
              <span className="block text-slate-400">Problem Type</span>
              <span className="font-semibold text-slate-800 capitalize">{summary.problem_type}</span>
            </div>
            <div>
              <span className="block text-slate-400">Default Explainer</span>
              <span className="font-semibold text-slate-800 uppercase">{summary.default_explainer}</span>
            </div>
            <div>
              <span className="block text-slate-400">Features</span>
              <span className="font-semibold text-slate-800">{summary.feature_names.length} inputs</span>
            </div>
          </div>
        )}
      </div>

      {/* Main Grid: Global Feature Importance & Local Prediction Explanation */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* SECTION 1: Global Feature Importance */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h2 className="text-base font-bold text-slate-900">Global Feature Importance</h2>
              <p className="text-xs text-slate-500">
                Mean absolute SHAP value impact across background dataset
              </p>
            </div>
            <span className="text-[11px] font-mono text-slate-400">
              {globalImportance?.method || 'loading'}
            </span>
          </div>

          {globalImportance?.feature_importances && globalImportance.feature_importances.length > 0 ? (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={globalImportance.feature_importances}
                  layout="vertical"
                  margin={{ top: 10, right: 20, left: 40, bottom: 10 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="feature" tick={{ fontSize: 11 }} width={80} />
                  <Tooltip
                    formatter={(val: any) => [`Importance: ${val}`, 'Score']}
                    contentStyle={{ borderRadius: '8px', fontSize: '12px' }}
                  />
                  <Bar dataKey="importance" fill="#4f46e5" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="p-12 text-center text-xs text-slate-400">
              No feature importances available.
            </div>
          )}

          <div className="p-3 bg-slate-50 rounded-xl text-[11px] text-slate-500 flex items-start gap-2">
            <Info className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" />
            <span>
              <strong>Note on Causality:</strong> Feature importance ranks how heavily the model relies on
              each feature to generate predictions. It reflects statistical correlation within the model architecture, not empirical causality.
            </span>
          </div>
        </div>

        {/* SECTION 2: Local Prediction Explainability */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-6">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h2 className="text-base font-bold text-slate-900">Local Prediction Attribution</h2>
              <p className="text-xs text-slate-500">
                Inspect positive and negative feature contributions for an individual record
              </p>
            </div>

            <div className="flex rounded-lg border border-slate-200 p-0.5 text-xs font-semibold">
              <button
                onClick={() => setActiveLocalMethod('shap')}
                className={`px-3 py-1 rounded-md transition ${
                  activeLocalMethod === 'shap' ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                SHAP
              </button>
              <button
                onClick={() => setActiveLocalMethod('lime')}
                className={`px-3 py-1 rounded-md transition ${
                  activeLocalMethod === 'lime' ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                LIME
              </button>
            </div>
          </div>

          {/* Record Input Form */}
          <div className="space-y-3">
            <label className="block text-xs font-semibold text-slate-700">Sample Feature Inputs</label>
            <div className="grid grid-cols-2 gap-3 max-h-48 overflow-y-auto p-1">
              {selectedModel?.feature_schema.map((feat) => (
                <div key={feat.name}>
                  <span className="block text-[11px] font-mono text-slate-500 mb-0.5">
                    {feat.name} ({feat.kind})
                  </span>
                  <input
                    type={feat.kind === 'numeric' ? 'number' : 'text'}
                    value={recordInputs[feat.name] ?? ''}
                    onChange={(e) =>
                      setRecordInputs({ ...recordInputs, [feat.name]: e.target.value })
                    }
                    className="w-full px-2.5 py-1.5 border border-slate-300 rounded-lg text-xs focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
              ))}
            </div>

            <button
              onClick={handleComputeLocalExplanation}
              disabled={explainingLocal}
              className="w-full py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition shadow-sm disabled:opacity-50"
            >
              {explainingLocal ? 'Computing Explanations...' : `Explain Prediction via ${activeLocalMethod.toUpperCase()}`}
            </button>
          </div>

          {/* Explanation Output */}
          {activeLocalMethod === 'shap' && shapResult && (
            <div className="space-y-4 pt-4 border-t border-slate-100">
              <div className="flex items-center justify-between text-xs">
                <div>
                  <span className="text-slate-500 block">Predicted Output</span>
                  <span className="text-base font-bold text-slate-900">{String(shapResult.prediction)}</span>
                </div>
                <div className="text-right">
                  <span className="text-slate-500 block">Baseline Expected Value</span>
                  <span className="font-mono font-semibold text-slate-700">{shapResult.base_value}</span>
                </div>
              </div>

              {/* Waterfall / Bar chart for contributions */}
              <div className="space-y-2">
                <span className="text-xs font-semibold text-slate-700 block">
                  Feature Impact (SHAP Values)
                </span>
                <div className="space-y-1.5 text-xs max-h-48 overflow-y-auto">
                  {shapResult.feature_contributions.map((c) => (
                    <div
                      key={c.feature}
                      className="flex items-center justify-between p-2 rounded-lg bg-slate-50 text-xs"
                    >
                      <div className="flex items-center gap-2">
                        {c.direction === 'positive' ? (
                          <TrendingUp className="w-3.5 h-3.5 text-emerald-600" />
                        ) : (
                          <TrendingDown className="w-3.5 h-3.5 text-rose-600" />
                        )}
                        <span className="font-medium text-slate-800">{c.feature}</span>
                        <span className="text-slate-400 font-mono text-[11px]">({String(c.value)})</span>
                      </div>
                      <span
                        className={`font-mono font-bold ${
                          c.contribution > 0 ? 'text-emerald-700' : 'text-rose-700'
                        }`}
                      >
                        {c.contribution > 0 ? `+${c.contribution}` : c.contribution}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeLocalMethod === 'lime' && limeResult && (
            <div className="space-y-4 pt-4 border-t border-slate-100">
              <div className="flex items-center justify-between text-xs">
                <div>
                  <span className="text-slate-500 block">Predicted Output</span>
                  <span className="text-base font-bold text-slate-900">{String(limeResult.prediction)}</span>
                </div>
                {limeResult.score !== null && (
                  <div className="text-right">
                    <span className="text-slate-500 block">Local Fidelity (R²)</span>
                    <span className="font-mono font-semibold text-slate-700">
                      {(limeResult.score * 100).toFixed(1)}%
                    </span>
                  </div>
                )}
              </div>

              {/* LIME Rule Table */}
              <div className="space-y-2">
                <span className="text-xs font-semibold text-slate-700 block">
                  Surrogate Local Decision Rules
                </span>
                <div className="space-y-1.5 text-xs max-h-48 overflow-y-auto">
                  {limeResult.rule_contributions.map((r, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between p-2 rounded-lg bg-slate-50 text-xs"
                    >
                      <span className="font-mono text-slate-700">{r.rule}</span>
                      <span
                        className={`font-mono font-bold ${
                          r.weight > 0 ? 'text-emerald-700' : 'text-rose-700'
                        }`}
                      >
                        {r.weight > 0 ? `+${r.weight}` : r.weight}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
