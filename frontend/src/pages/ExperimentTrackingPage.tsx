import { useState, useEffect, useCallback } from 'react';
import {
  Cpu,
  Play,
  RotateCcw,
  StopCircle,
  Plus,
  BarChart2,
  CheckCircle2,
  XCircle,
  Clock,
  Layers,
  ArrowRight,
  Sliders,
  Check,
  AlertTriangle,
} from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts';
import { experimentApi, datasetApi } from '../services/api';
import type {
  ExperimentRead,
  ExperimentCompareItem,
  ProblemType,
  Algorithm,
  SearchStrategy,
} from '../types/experiment';
import type { DatasetRead } from '../types/dataset';
import { useAuth } from '../context/AuthContext';

export function ExperimentTrackingPage() {
  const { user } = useAuth();
  const canManage = user?.role === 'admin' || user?.role === 'ml_engineer';

  // Experiments & Datasets
  const [experiments, setExperiments] = useState<ExperimentRead[]>([]);
  const [datasets, setDatasets] = useState<DatasetRead[]>([]);
  const [selectedExperiment, setSelectedExperiment] = useState<ExperimentRead | null>(null);

  // Comparison State
  const [comparisonIds, setComparisonIds] = useState<string[]>([]);
  const [compareResults, setCompareResults] = useState<ExperimentCompareItem[]>([]);
  const [compareWarnings, setCompareWarnings] = useState<string[]>([]);
  const [isComparing, setIsComparing] = useState(false);

  // Modal / Form state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Form Fields
  const [formName, setFormName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formDatasetId, setFormDatasetId] = useState('');
  const [formTargetCol, setFormTargetCol] = useState('');
  const [formProblemType, setFormProblemType] = useState<ProblemType>('classification');
  const [formAlgorithm, setFormAlgorithm] = useState<Algorithm>('random_forest');
  const [formSearchStrategy, setFormSearchStrategy] = useState<SearchStrategy>('none');
  const [formCvFolds, setFormCvFolds] = useState(5);
  const [formTestSize, setFormTestSize] = useState(0.2);
  const [formValidationSize, setFormValidationSize] = useState(0.1);
  const [formHyperparams, setFormHyperparams] = useState('{"n_estimators": [10, 50], "max_depth": [3, 10]}');

  const fetchExperimentsAndDatasets = useCallback(async () => {
    try {
      const [expRes, dRes] = await Promise.all([
        experimentApi.listExperiments({ limit: 50 }),
        datasetApi.listDatasets(0, 50),
      ]);
      setExperiments(expRes.items);
      setDatasets(dRes.items);
      if (expRes.items.length > 0 && !selectedExperiment) {
        setSelectedExperiment(expRes.items[0]);
      }
    } catch (err) {
      console.error('Failed to fetch experiments or datasets', err);
    }
  }, [selectedExperiment]);

  useEffect(() => {
    fetchExperimentsAndDatasets();
  }, [fetchExperimentsAndDatasets]);

  const handleCreateExperiment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName || !formDatasetId || !formTargetCol) {
      setActionError('Please fill in required fields (Name, Dataset, Target Column)');
      return;
    }
    try {
      setIsSubmitting(true);
      setActionError(null);
      let parsedHyperparams = {};
      try {
        parsedHyperparams = JSON.parse(formHyperparams);
      } catch {
        setActionError('Invalid JSON in hyperparameter configuration');
        setIsSubmitting(false);
        return;
      }

      const created = await experimentApi.createExperiment({
        name: formName,
        description: formDescription || undefined,
        dataset_id: formDatasetId,
        target_column: formTargetCol,
        problem_type: formProblemType,
        algorithm: formAlgorithm,
        search_strategy: formSearchStrategy,
        cv_folds: formCvFolds,
        test_size: formTestSize,
        validation_size: formValidationSize,
        hyperparameter_config: parsedHyperparams,
      });

      setShowCreateModal(false);
      await fetchExperimentsAndDatasets();
      setSelectedExperiment(created);
    } catch (err: any) {
      setActionError(err.response?.data?.error?.message || 'Failed to create experiment');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRunPipeline = async (experimentId: string) => {
    try {
      setIsRunning(true);
      setActionError(null);
      await experimentApi.runExperiment(experimentId);
      await fetchExperimentsAndDatasets();
      const updated = await experimentApi.getExperiment(experimentId);
      setSelectedExperiment(updated);
    } catch (err: any) {
      setActionError(err.response?.data?.error?.message || 'Pipeline execution failed');
    } finally {
      setIsRunning(false);
    }
  };

  const handleCancelExperiment = async (experimentId: string) => {
    try {
      await experimentApi.cancelExperiment(experimentId);
      await fetchExperimentsAndDatasets();
      const updated = await experimentApi.getExperiment(experimentId);
      setSelectedExperiment(updated);
    } catch (err: any) {
      setActionError(err.response?.data?.error?.message || 'Cancellation failed');
    }
  };

  const toggleComparison = (id: string) => {
    setComparisonIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const handleRunComparison = async () => {
    if (comparisonIds.length < 2) return;
    try {
      setIsComparing(true);
      const res = await experimentApi.compareExperiments(comparisonIds);
      setCompareResults(res.experiments);
      setCompareWarnings(res.warnings);
    } catch (err) {
      console.error('Comparison error', err);
    } finally {
      setIsComparing(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Completed
          </span>
        );
      case 'running':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 animate-pulse">
            <Clock className="w-3 h-3 text-amber-600" /> Running
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-100 text-rose-800">
            <XCircle className="w-3 h-3 text-rose-600" /> Failed
          </span>
        );
      case 'cancelled':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-200 text-slate-700">
            <StopCircle className="w-3 h-3 text-slate-500" /> Cancelled
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
            <Clock className="w-3 h-3 text-indigo-600" /> Pending
          </span>
        );
    }
  };

  // Prepare comparison chart data
  const compareChartData = compareResults.map((item) => ({
    name: item.experiment_name,
    accuracy: item.test_metrics?.accuracy ? Number((item.test_metrics.accuracy * 100).toFixed(1)) : 0,
    f1: item.test_metrics?.f1_macro ? Number((item.test_metrics.f1_macro * 100).toFixed(1)) : 0,
    r2: item.test_metrics?.r2 ? Number((item.test_metrics.r2 * 100).toFixed(1)) : 0,
  }));

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              Automated ML Studio & Experiment Tracking
            </h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
              Phase 12
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Automated preprocessing, hyperparameter optimization (Grid/Random search), and experiment version comparison.
          </p>
        </div>

        {canManage && (
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl shadow-sm transition cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            New Experiment
          </button>
        )}
      </div>

      {actionError && (
        <div className="p-4 rounded-xl bg-rose-50 text-rose-800 border border-rose-200 text-xs flex items-center justify-between">
          <span>{actionError}</span>
          <button onClick={() => setActionError(null)} className="font-bold uppercase text-[10px]">
            Dismiss
          </button>
        </div>
      )}

      {/* Main Grid: Experiments List & Details */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Experiment List */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              Experiments ({experiments.length})
            </h2>
            {comparisonIds.length > 1 && (
              <button
                onClick={handleRunComparison}
                disabled={isComparing}
                className="text-xs text-indigo-600 font-semibold hover:underline"
              >
                Compare ({comparisonIds.length})
              </button>
            )}
          </div>

          <div className="divide-y divide-slate-100 max-h-[600px] overflow-y-auto">
            {experiments.map((exp) => (
              <div
                key={exp.id}
                onClick={() => setSelectedExperiment(exp)}
                className={`p-3.5 rounded-xl cursor-pointer transition flex items-start justify-between gap-3 ${
                  selectedExperiment?.id === exp.id
                    ? 'bg-indigo-50/70 border-indigo-200 border'
                    : 'hover:bg-slate-50'
                }`}
              >
                <div className="flex items-start gap-2.5">
                  <input
                    type="checkbox"
                    checked={comparisonIds.includes(exp.id)}
                    onChange={(e) => {
                      e.stopPropagation();
                      toggleComparison(exp.id);
                    }}
                    className="mt-1 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900">{exp.name}</h3>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {exp.algorithm} • {exp.problem_type}
                    </div>
                  </div>
                </div>
                {getStatusBadge(exp.status)}
              </div>
            ))}
          </div>
        </div>

        {/* Right Column: Selected Experiment Studio */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-6">
          {selectedExperiment ? (
            <>
              {/* Header and Controls */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-lg font-bold text-slate-900">{selectedExperiment.name}</h2>
                    {getStatusBadge(selectedExperiment.status)}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    {selectedExperiment.description || 'No description provided.'}
                  </p>
                </div>

                {canManage && (
                  <div className="flex items-center gap-2">
                    {selectedExperiment.status === 'running' ? (
                      <button
                        onClick={() => handleCancelExperiment(selectedExperiment.id)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-rose-700 bg-rose-50 border border-rose-200 rounded-lg hover:bg-rose-100 transition"
                      >
                        <StopCircle className="w-3.5 h-3.5" /> Cancel
                      </button>
                    ) : (
                      <button
                        onClick={() => handleRunPipeline(selectedExperiment.id)}
                        disabled={isRunning}
                        className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm transition disabled:opacity-50"
                      >
                        {selectedExperiment.status === 'completed' ? (
                          <>
                            <RotateCcw className="w-3.5 h-3.5" /> Re-run Pipeline
                          </>
                        ) : (
                          <>
                            <Play className="w-3.5 h-3.5" /> Execute Pipeline
                          </>
                        )}
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* Pipeline Configuration Parameters */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs">
                <div>
                  <span className="text-slate-400 block font-medium">Algorithm</span>
                  <span className="font-semibold text-slate-800 capitalize">
                    {selectedExperiment.algorithm.replace('_', ' ')}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block font-medium">Problem Type</span>
                  <span className="font-semibold text-slate-800 capitalize">
                    {selectedExperiment.problem_type}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block font-medium">Search Strategy</span>
                  <span className="font-semibold text-slate-800 capitalize">
                    {selectedExperiment.search_strategy}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block font-medium">Target Column</span>
                  <span className="font-mono font-semibold text-slate-800">
                    {selectedExperiment.target_column}
                  </span>
                </div>
              </div>

              {/* Runs and Evaluation Metrics */}
              <div>
                <h3 className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-3">
                  Pipeline Execution Runs ({selectedExperiment.runs.length})
                </h3>

                {selectedExperiment.runs.length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-xl">
                    No runs yet. Click "Execute Pipeline" to run automated preprocessing, training, and model registration.
                  </div>
                ) : (
                  <div className="space-y-4">
                    {selectedExperiment.runs.map((run) => (
                      <div
                        key={run.id}
                        className="p-4 rounded-xl border border-slate-200 bg-white space-y-3 shadow-xs"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-bold text-slate-800">Run #{run.run_number}</span>
                          <span className="text-slate-500">
                            Duration: {run.execution_duration_seconds ? `${run.execution_duration_seconds}s` : '—'}
                          </span>
                        </div>

                        {run.test_metrics && (
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                            {Object.entries(run.test_metrics).map(([k, v]) => (
                              <div key={k} className="p-2.5 rounded-lg bg-slate-50 text-xs">
                                <span className="text-slate-400 uppercase font-semibold text-[10px]">
                                  {k.replace('_', ' ')}
                                </span>
                                <div className="text-base font-bold text-slate-900 mt-0.5">
                                  {typeof v === 'number' ? (v <= 1 ? (v * 100).toFixed(1) + '%' : v.toFixed(3)) : String(v)}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}

                        {run.best_hyperparameters && Object.keys(run.best_hyperparameters).length > 0 && (
                          <div className="text-xs bg-slate-50 p-2.5 rounded-lg font-mono text-slate-700">
                            <span className="font-bold block text-slate-500 mb-1">Best Hyperparameters:</span>
                            {JSON.stringify(run.best_hyperparameters)}
                          </div>
                        )}

                        {run.registered_model_id && (
                          <div className="text-xs text-emerald-700 flex items-center gap-1.5 font-medium">
                            <Check className="w-3.5 h-3.5" />
                            Registered in Model Registry (ID: {run.registered_model_id})
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="p-12 text-center text-slate-400 text-xs">
              Select an experiment to view parameters and execution history.
            </div>
          )}
        </div>
      </div>

      {/* Comparison Modal / Section */}
      {compareResults.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-6">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Experiment Comparison Matrix</h2>
              <p className="text-xs text-slate-500">Visualizing benchmark metrics across selected runs</p>
            </div>
            <button
              onClick={() => setCompareResults([])}
              className="text-xs text-slate-400 hover:text-slate-700 font-semibold"
            >
              Clear Comparison
            </button>
          </div>

          {compareWarnings.length > 0 && (
            <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 text-xs text-amber-800 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
              <span>{compareWarnings.join(' ')}</span>
            </div>
          )}

          {compareChartData.length > 0 && (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={compareChartData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip contentStyle={{ borderRadius: '8px', fontSize: '12px' }} />
                  <Legend wrapperStyle={{ fontSize: '12px' }} />
                  <Bar dataKey="accuracy" name="Accuracy (%)" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="f1" name="F1 Score (%)" fill="#10b981" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="r2" name="R² (%)" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* Create Experiment Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-fadeIn">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-xl w-full p-6 space-y-4">
            <h2 className="text-base font-bold text-slate-900">Create New Experiment</h2>

            <form onSubmit={handleCreateExperiment} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Experiment Name</label>
                <input
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g., customer_churn_opt_v1"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Dataset</label>
                  <select
                    required
                    value={formDatasetId}
                    onChange={(e) => setFormDatasetId(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  >
                    <option value="">Select Dataset...</option>
                    {datasets.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name} ({d.n_rows} rows)
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Target Column</label>
                  <input
                    type="text"
                    required
                    value={formTargetCol}
                    onChange={(e) => setFormTargetCol(e.target.value)}
                    placeholder="e.g., churn"
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Problem Type</label>
                  <select
                    value={formProblemType}
                    onChange={(e) => setFormProblemType(e.target.value as ProblemType)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                  >
                    <option value="classification">Classification</option>
                    <option value="regression">Regression</option>
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Algorithm</label>
                  <select
                    value={formAlgorithm}
                    onChange={(e) => setFormAlgorithm(e.target.value as Algorithm)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                  >
                    <option value="random_forest">Random Forest</option>
                    <option value="linear">Linear / Logistic Regression</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Search Strategy</label>
                  <select
                    value={formSearchStrategy}
                    onChange={(e) => setFormSearchStrategy(e.target.value as SearchStrategy)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                  >
                    <option value="none">Standard Training (No Search)</option>
                    <option value="grid">GridSearchCV</option>
                    <option value="random">RandomizedSearchCV</option>
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1">CV Folds</label>
                  <input
                    type="number"
                    min="2"
                    max="10"
                    value={formCvFolds}
                    onChange={(e) => setFormCvFolds(parseInt(e.target.value, 10) || 5)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                  />
                </div>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  Hyperparameter Search Grid (JSON)
                </label>
                <textarea
                  rows={2}
                  value={formHyperparams}
                  onChange={(e) => setFormHyperparams(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg font-mono text-xs"
                />
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg font-semibold text-slate-600 hover:bg-slate-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700 transition disabled:opacity-50"
                >
                  Create Experiment
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
