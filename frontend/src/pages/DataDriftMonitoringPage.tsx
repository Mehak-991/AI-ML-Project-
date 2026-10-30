import { useState, useEffect, useCallback } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  Activity,
  TrendingDown,
  RefreshCw,
  Sliders,
  Database,
  BarChart2,
  Check,
  ChevronDown,
  ShieldAlert,
} from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell } from 'recharts';
import { driftApi, modelApi } from '../services/api';
import type {
  DriftOverviewResponse,
  DriftReportRead,
  DriftAlertRead,
  DataQualityResults,
  FeatureDriftResults,
  PerformanceMonitoringResults,
  DriftStatus,
} from '../types/drift';
import type { ModelRead } from '../types/model';
import { useAuth } from '../context/AuthContext';

export function DataDriftMonitoringPage() {
  const { user } = useAuth();
  const canAnalyze = user?.role === 'admin' || user?.role === 'ml_engineer';

  // Overview stats & Models
  const [overview, setOverview] = useState<DriftOverviewResponse | null>(null);
  const [models, setModels] = useState<ModelRead[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<string>('');

  // Selected Model Data
  const [reports, setReports] = useState<DriftReportRead[]>([]);
  const [alerts, setAlerts] = useState<DriftAlertRead[]>([]);
  const [activeReportTab, setActiveReportTab] = useState<'drift' | 'quality' | 'performance' | 'alerts'>('drift');

  // Loading & Action states
  const [loading, setLoading] = useState<boolean>(true);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [actionMessage, setActionMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  // Drift threshold controls
  const [psiThreshold, setPsiThreshold] = useState<number>(0.2);
  const [sampleLimit, setSampleLimit] = useState<number>(500);

  const fetchOverviewAndModels = useCallback(async () => {
    try {
      setLoading(true);
      const [ovData, modelsData] = await Promise.all([
        driftApi.getOverview(),
        modelApi.listModels(),
      ]);
      setOverview(ovData);
      setModels(modelsData.items);

      if (modelsData.items.length > 0 && !selectedModelId) {
        setSelectedModelId(modelsData.items[0].id);
      }
    } catch (err: unknown) {
      console.error('Failed to fetch drift overview or models', err);
    } finally {
      setLoading(false);
    }
  }, [selectedModelId]);

  const fetchModelDetails = useCallback(async (modelId: string) => {
    if (!modelId) return;
    try {
      const [reportsData, alertsData] = await Promise.all([
        driftApi.listReports(modelId, { limit: 20 }),
        driftApi.listModelAlerts(modelId, { limit: 50 }),
      ]);
      setReports(reportsData.items);
      setAlerts(alertsData.items);
    } catch (err: unknown) {
      console.error('Failed to load model reports', err);
    }
  }, []);

  useEffect(() => {
    fetchOverviewAndModels();
  }, [fetchOverviewAndModels]);

  useEffect(() => {
    if (selectedModelId) {
      fetchModelDetails(selectedModelId);
    }
  }, [selectedModelId, fetchModelDetails]);

  // Handlers for On-Demand Analysis
  const handleTriggerQualityCheck = async () => {
    if (!selectedModelId) return;
    try {
      setIsAnalyzing(true);
      setActionMessage(null);
      await driftApi.analyzeQuality(selectedModelId);
      setActionMessage({ text: 'Data quality check completed successfully.', type: 'success' });
      await fetchModelDetails(selectedModelId);
      await fetchOverviewAndModels();
    } catch (err: unknown) {
      setActionMessage({ text: 'Data quality check failed. Ensure recent prediction logs exist.', type: 'error' });
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleTriggerDriftCheck = async () => {
    if (!selectedModelId) return;
    try {
      setIsAnalyzing(true);
      setActionMessage(null);
      await driftApi.analyzeDrift(selectedModelId, {
        psi_threshold: psiThreshold,
        recent_sample_limit: sampleLimit,
      });
      setActionMessage({ text: 'Feature drift analysis completed.', type: 'success' });
      await fetchModelDetails(selectedModelId);
      await fetchOverviewAndModels();
    } catch (err: unknown) {
      setActionMessage({ text: 'Feature drift analysis failed. Verify training baseline and prediction logs.', type: 'error' });
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleTriggerPerformanceCheck = async () => {
    if (!selectedModelId) return;
    try {
      setIsAnalyzing(true);
      setActionMessage(null);
      await driftApi.analyzePerformance(selectedModelId);
      setActionMessage({ text: 'Model performance check completed.', type: 'success' });
      await fetchModelDetails(selectedModelId);
      await fetchOverviewAndModels();
    } catch (err: unknown) {
      setActionMessage({ text: 'Performance analysis failed. Ground truth labels may be missing.', type: 'error' });
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleResolveAlert = async (alertId: string) => {
    try {
      await driftApi.resolveAlert(alertId);
      await fetchModelDetails(selectedModelId);
      await fetchOverviewAndModels();
    } catch (err: unknown) {
      console.error('Failed to resolve alert', err);
    }
  };

  const getStatusBadge = (status: DriftStatus) => {
    switch (status) {
      case 'nominal':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Nominal
          </span>
        );
      case 'warning':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200">
            <AlertTriangle className="w-3 h-3 text-amber-600" /> Warning
          </span>
        );
      case 'critical':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-100 text-rose-800 border border-rose-200">
            <AlertCircle className="w-3 h-3 text-rose-600" /> Critical Drift
          </span>
        );
      case 'insufficient_data':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
            Insufficient Data
          </span>
        );
    }
  };

  // Find latest reports of each type
  const latestDriftReport = reports.find((r) => r.report_type === 'feature_drift');
  const latestQualityReport = reports.find((r) => r.report_type === 'data_quality');
  const latestPerfReport = reports.find((r) => r.report_type === 'performance');

  const driftResults = latestDriftReport?.results as FeatureDriftResults | undefined;
  const qualityResults = latestQualityReport?.results as DataQualityResults | undefined;
  const perfResults = latestPerfReport?.results as PerformanceMonitoringResults | undefined;

  // Prepare PSI chart data if available
  const psiChartData = driftResults?.features
    ? Object.entries(driftResults.features).map(([name, data]) => ({
        name,
        psi: Number((data.psi_score || 0).toFixed(4)),
        severity: data.severity,
      }))
    : [];

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 animate-fadeIn">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              Data Quality & Drift Monitoring
            </h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
              Phase 11
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Statistical distribution shifts (PSI, KS, Chi²), input anomalies, and live accuracy degradation.
          </p>
        </div>

        <button
          onClick={() => {
            fetchOverviewAndModels();
            if (selectedModelId) fetchModelDetails(selectedModelId);
          }}
          disabled={loading || isAnalyzing}
          className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg shadow-sm hover:bg-slate-50 transition"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh Status
        </button>
      </div>

      {/* Action Notification */}
      {actionMessage && (
        <div
          className={`p-4 rounded-xl border flex items-center justify-between text-sm ${
            actionMessage.type === 'success'
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : 'bg-rose-50 text-rose-800 border-rose-200'
          }`}
        >
          <span>{actionMessage.text}</span>
          <button
            onClick={() => setActionMessage(null)}
            className="text-xs uppercase font-semibold tracking-wider hover:opacity-75"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Top Aggregated Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Models Monitored</span>
            <Activity className="w-5 h-5 text-indigo-600" />
          </div>
          <div className="text-2xl font-bold text-slate-900">
            {overview?.total_models_monitored ?? 0}
          </div>
          <p className="text-xs text-slate-400 mt-1">Active registered models</p>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Models in Drift</span>
            <TrendingDown className="w-5 h-5 text-amber-500" />
          </div>
          <div className="text-2xl font-bold text-amber-600">
            {overview?.models_in_drift ?? 0}
          </div>
          <p className="text-xs text-slate-400 mt-1">Significant shift detected</p>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Active Alerts</span>
            <AlertTriangle className="w-5 h-5 text-rose-500" />
          </div>
          <div className="text-2xl font-bold text-slate-900">
            {overview?.total_active_alerts ?? 0}
          </div>
          <p className="text-xs text-slate-400 mt-1">Unresolved platform issues</p>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Critical Severity</span>
            <ShieldAlert className="w-5 h-5 text-rose-600" />
          </div>
          <div className="text-2xl font-bold text-rose-600">
            {overview?.critical_alerts ?? 0}
          </div>
          <p className="text-xs text-slate-400 mt-1">Immediate action recommended</p>
        </div>
      </div>

      {/* Model Selection & Action Trigger Bar */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="w-full lg:w-1/3">
            <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wider mb-1.5">
              Select Model to Inspect
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

          {/* Trigger Action Buttons */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handleTriggerQualityCheck}
              disabled={isAnalyzing || !canAnalyze || !selectedModelId}
              className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-200 disabled:opacity-50 transition"
              title={!canAnalyze ? 'Requires ML Engineer or Admin role' : ''}
            >
              <Database className="w-3.5 h-3.5" />
              Check Data Quality
            </button>

            <button
              onClick={handleTriggerDriftCheck}
              disabled={isAnalyzing || !canAnalyze || !selectedModelId}
              className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg bg-amber-50 text-amber-700 hover:bg-amber-100 border border-amber-200 disabled:opacity-50 transition"
              title={!canAnalyze ? 'Requires ML Engineer or Admin role' : ''}
            >
              <BarChart2 className="w-3.5 h-3.5" />
              Run Drift Analysis (PSI/KS)
            </button>

            <button
              onClick={handleTriggerPerformanceCheck}
              disabled={isAnalyzing || !canAnalyze || !selectedModelId}
              className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg bg-purple-50 text-purple-700 hover:bg-purple-100 border border-purple-200 disabled:opacity-50 transition"
              title={!canAnalyze ? 'Requires ML Engineer or Admin role' : ''}
            >
              <Activity className="w-3.5 h-3.5" />
              Analyze Performance
            </button>
          </div>
        </div>

        {/* Statistical Parameters Accordion/Controls */}
        <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center gap-6 text-xs text-slate-600">
          <div className="flex items-center gap-2">
            <Sliders className="w-3.5 h-3.5 text-slate-400" />
            <span>PSI Alert Threshold:</span>
            <input
              type="number"
              step="0.05"
              min="0.05"
              max="1.0"
              value={psiThreshold}
              onChange={(e) => setPsiThreshold(parseFloat(e.target.value) || 0.2)}
              className="w-16 px-2 py-0.5 border border-slate-300 rounded text-center font-mono"
            />
            <span className="text-slate-400 text-[11px]">(0.1 mild, 0.2 significant)</span>
          </div>

          <div className="flex items-center gap-2">
            <span>Production Sample Window:</span>
            <input
              type="number"
              step="100"
              min="50"
              max="2000"
              value={sampleLimit}
              onChange={(e) => setSampleLimit(parseInt(e.target.value, 10) || 500)}
              className="w-20 px-2 py-0.5 border border-slate-300 rounded text-center font-mono"
            />
            <span className="text-slate-400 text-[11px]">recent rows</span>
          </div>
        </div>
      </div>

      {/* Tabs: Feature Drift | Data Quality | Performance Degradation | Active Alerts */}
      <div className="space-y-6">
        <div className="flex border-b border-slate-200 gap-8">
          <button
            onClick={() => setActiveReportTab('drift')}
            className={`pb-3 text-sm font-semibold transition border-b-2 flex items-center gap-2 ${
              activeReportTab === 'drift'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <BarChart2 className="w-4 h-4" />
            Feature Distribution Drift
            {latestDriftReport && getStatusBadge(latestDriftReport.overall_status)}
          </button>

          <button
            onClick={() => setActiveReportTab('quality')}
            className={`pb-3 text-sm font-semibold transition border-b-2 flex items-center gap-2 ${
              activeReportTab === 'quality'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Database className="w-4 h-4" />
            Data Quality & Integrity
            {latestQualityReport && getStatusBadge(latestQualityReport.overall_status)}
          </button>

          <button
            onClick={() => setActiveReportTab('performance')}
            className={`pb-3 text-sm font-semibold transition border-b-2 flex items-center gap-2 ${
              activeReportTab === 'performance'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Activity className="w-4 h-4" />
            Model Accuracy Degradation
            {latestPerfReport && getStatusBadge(latestPerfReport.overall_status)}
          </button>

          <button
            onClick={() => setActiveReportTab('alerts')}
            className={`pb-3 text-sm font-semibold transition border-b-2 flex items-center gap-2 ${
              activeReportTab === 'alerts'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <AlertTriangle className="w-4 h-4" />
            Alerts & Incidents
            {alerts.filter((a) => !a.resolved).length > 0 && (
              <span className="px-2 py-0.2 rounded-full text-[11px] font-bold bg-rose-500 text-white">
                {alerts.filter((a) => !a.resolved).length}
              </span>
            )}
          </button>
        </div>

        {/* TAB 1: Feature Drift Details */}
        {activeReportTab === 'drift' && (
          <div className="space-y-6">
            {driftResults ? (
              <>
                {/* PSI Chart */}
                {psiChartData.length > 0 && (
                  <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                    <h3 className="text-sm font-semibold text-slate-800 mb-4">
                      Population Stability Index (PSI) per Feature
                    </h3>
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={psiChartData} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                          <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                          <YAxis tick={{ fontSize: 12 }} />
                          <Tooltip
                            formatter={(value: any) => [`PSI: ${Number(value || 0).toFixed(4)}`, 'Score']}
                            contentStyle={{ borderRadius: '8px', fontSize: '12px' }}
                          />
                          <Bar dataKey="psi" radius={[4, 4, 0, 0]}>
                            {psiChartData.map((entry, index) => (
                              <Cell
                                key={`cell-${index}`}
                                fill={
                                  entry.psi >= 0.2
                                    ? '#e11d48'
                                    : entry.psi >= 0.1
                                    ? '#d97706'
                                    : '#10b981'
                                }
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Feature Drift Table */}
                <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                  <div className="p-4 border-b border-slate-100 flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-800">
                        Feature Distribution Statistics
                      </h3>
                      <p className="text-xs text-slate-500">
                        Comparing reference baseline ({driftResults.reference_sample_size} rows) vs production ({driftResults.production_sample_size} rows)
                      </p>
                    </div>
                    <span className="text-xs font-semibold px-2.5 py-1 rounded bg-slate-100 text-slate-700">
                      Drift Ratio: {(driftResults.drift_ratio * 100).toFixed(1)}%
                    </span>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="bg-slate-50 text-slate-600 border-b border-slate-200">
                          <th className="py-3 px-4 font-semibold">Feature</th>
                          <th className="py-3 px-4 font-semibold">Type</th>
                          <th className="py-3 px-4 font-semibold">Status</th>
                          <th className="py-3 px-4 font-semibold">PSI Score</th>
                          <th className="py-3 px-4 font-semibold">KS / Chi² p-value</th>
                          <th className="py-3 px-4 font-semibold">Ref Mean</th>
                          <th className="py-3 px-4 font-semibold">Prod Mean</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {Object.entries(driftResults.features).map(([fName, metric]) => (
                          <tr key={fName} className="hover:bg-slate-50/70">
                            <td className="py-3 px-4 font-medium text-slate-900">{fName}</td>
                            <td className="py-3 px-4 text-slate-500 capitalize">{metric.feature_type}</td>
                            <td className="py-3 px-4">{getStatusBadge(metric.severity)}</td>
                            <td className="py-3 px-4 font-mono">
                              {metric.psi_score !== null && metric.psi_score !== undefined
                                ? metric.psi_score.toFixed(4)
                                : '—'}
                            </td>
                            <td className="py-3 px-4 font-mono">
                              {metric.ks_p_value !== null && metric.ks_p_value !== undefined
                                ? metric.ks_p_value.toExponential(2)
                                : metric.chi2_p_value !== null && metric.chi2_p_value !== undefined
                                ? metric.chi2_p_value.toExponential(2)
                                : '—'}
                            </td>
                            <td className="py-3 px-4 font-mono text-slate-600">
                              {metric.reference_mean !== null && metric.reference_mean !== undefined
                                ? metric.reference_mean.toFixed(2)
                                : '—'}
                            </td>
                            <td className="py-3 px-4 font-mono text-slate-600">
                              {metric.production_mean !== null && metric.production_mean !== undefined
                                ? metric.production_mean.toFixed(2)
                                : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            ) : (
              <div className="bg-white p-12 text-center rounded-xl border border-dashed border-slate-300">
                <BarChart2 className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                <h4 className="text-sm font-semibold text-slate-700">No Feature Drift Reports Found</h4>
                <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                  Run a feature drift analysis using recent production inputs to check against the baseline dataset.
                </p>
                {canAnalyze && (
                  <button
                    onClick={handleTriggerDriftCheck}
                    disabled={isAnalyzing}
                    className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 transition"
                  >
                    Run Drift Analysis Now
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: Data Quality */}
        {activeReportTab === 'quality' && (
          <div className="space-y-6">
            {qualityResults ? (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden p-6 space-y-6">
                <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                  <div>
                    <h3 className="text-base font-semibold text-slate-900">
                      Overall Data Quality Score: {(qualityResults.quality_score * 100).toFixed(0)}%
                    </h3>
                    <p className="text-xs text-slate-500">
                      Evaluated across {qualityResults.sample_size} production inference payloads
                    </p>
                  </div>
                  {getStatusBadge(latestQualityReport?.overall_status || 'nominal')}
                </div>

                {qualityResults.issues.length > 0 && (
                  <div className="p-4 bg-amber-50 rounded-lg border border-amber-200">
                    <h4 className="text-xs font-semibold text-amber-800 uppercase tracking-wider mb-2">
                      Detected Data Quality Issues
                    </h4>
                    <ul className="list-disc pl-5 text-xs text-amber-700 space-y-1">
                      {qualityResults.issues.map((issue, idx) => (
                        <li key={idx}>{issue}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="bg-slate-50 text-slate-600 border-b border-slate-200">
                        <th className="py-3 px-4 font-semibold">Column</th>
                        <th className="py-3 px-4 font-semibold">Missing Count</th>
                        <th className="py-3 px-4 font-semibold">Missing Rate</th>
                        <th className="py-3 px-4 font-semibold">Outliers</th>
                        <th className="py-3 px-4 font-semibold">Unique Values</th>
                        <th className="py-3 px-4 font-semibold">Is Constant</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {Object.entries(qualityResults.feature_metrics).map(([colName, metrics]) => (
                        <tr key={colName} className="hover:bg-slate-50/70">
                          <td className="py-3 px-4 font-medium text-slate-900">{colName}</td>
                          <td className="py-3 px-4 font-mono">{metrics.missing_count}</td>
                          <td className="py-3 px-4 font-mono">
                            {(metrics.missing_rate * 100).toFixed(1)}%
                          </td>
                          <td className="py-3 px-4 font-mono">{metrics.outlier_count ?? '—'}</td>
                          <td className="py-3 px-4 font-mono">{metrics.unique_count}</td>
                          <td className="py-3 px-4">
                            {metrics.is_constant ? (
                              <span className="text-rose-600 font-semibold">Yes</span>
                            ) : (
                              <span className="text-emerald-600">No</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="bg-white p-12 text-center rounded-xl border border-dashed border-slate-300">
                <Database className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                <h4 className="text-sm font-semibold text-slate-700">No Data Quality Reports Found</h4>
                <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                  Evaluate incoming features for nulls, extreme outliers, schema integrity, and constant columns.
                </p>
                {canAnalyze && (
                  <button
                    onClick={handleTriggerQualityCheck}
                    disabled={isAnalyzing}
                    className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 transition"
                  >
                    Check Data Quality Now
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* TAB 3: Model Performance Degradation */}
        {activeReportTab === 'performance' && (
          <div className="space-y-6">
            {perfResults ? (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-6">
                <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                  <div>
                    <h3 className="text-base font-semibold text-slate-900">
                      Baseline vs Production Accuracy ({perfResults.task_type})
                    </h3>
                    <p className="text-xs text-slate-500">
                      Based on {perfResults.evaluated_samples} inference logs with submitted ground truth
                    </p>
                  </div>
                  {getStatusBadge(latestPerfReport?.overall_status || 'nominal')}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {Object.entries(perfResults.production_metrics).map(([metricKey, prodVal]) => {
                    const refVal = perfResults.reference_metrics[metricKey];
                    const drop = perfResults.metric_degradations[metricKey] || 0;
                    return (
                      <div key={metricKey} className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                        <div className="text-xs uppercase font-semibold text-slate-500">{metricKey}</div>
                        <div className="flex items-baseline gap-2 mt-2">
                          <span className="text-2xl font-bold text-slate-900">
                            {(prodVal * 100).toFixed(1)}%
                          </span>
                          <span className="text-xs text-slate-400">
                            (ref: {(refVal * 100).toFixed(1)}%)
                          </span>
                        </div>
                        <div className={`text-xs mt-2 font-medium ${drop > 0.05 ? 'text-rose-600' : 'text-emerald-600'}`}>
                          {drop > 0 ? `-${(drop * 100).toFixed(1)}% degradation` : 'Stable or improved'}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="bg-white p-12 text-center rounded-xl border border-dashed border-slate-300">
                <Activity className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                <h4 className="text-sm font-semibold text-slate-700">No Performance Reports Found</h4>
                <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                  Compare live accuracy against training test scores using submitted ground truth records.
                </p>
                {canAnalyze && (
                  <button
                    onClick={handleTriggerPerformanceCheck}
                    disabled={isAnalyzing}
                    className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 transition"
                  >
                    Analyze Performance
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* TAB 4: Alerts & Incidents */}
        {activeReportTab === 'alerts' && (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="p-4 border-b border-slate-100 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-800">Model Drift Alerts</h3>
              <span className="text-xs text-slate-500">
                {alerts.filter((a) => !a.resolved).length} unresolved / {alerts.length} total
              </span>
            </div>

            {alerts.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-400">
                No active or historical alerts for this model.
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {alerts.map((alert) => (
                  <div
                    key={alert.id}
                    className={`p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                      alert.resolved ? 'bg-slate-50/50 opacity-60' : 'hover:bg-slate-50/80'
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      {alert.severity === 'critical' ? (
                        <AlertCircle className="w-5 h-5 text-rose-500 flex-shrink-0 mt-0.5" />
                      ) : (
                        <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
                      )}
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                            {alert.alert_type.replace(/_/g, ' ')}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                              alert.severity === 'critical'
                                ? 'bg-rose-100 text-rose-700'
                                : 'bg-amber-100 text-amber-700'
                            }`}
                          >
                            {alert.severity}
                          </span>
                          <span className="text-xs text-slate-400">
                            {new Date(alert.created_at).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-xs text-slate-600 mt-1">{alert.message}</p>
                      </div>
                    </div>

                    {!alert.resolved && canAnalyze && (
                      <button
                        onClick={() => handleResolveAlert(alert.id)}
                        className="self-end sm:self-center px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-100 transition inline-flex items-center gap-1.5"
                      >
                        <Check className="w-3.5 h-3.5 text-emerald-600" />
                        Acknowledge & Resolve
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
