import React, { useState } from 'react';
import {
  Activity,
  Search,
  Filter,
  CheckCircle2,
  XCircle,
  Calendar,
  Layers,
  ChevronDown,
  ChevronUp,
  Tag,
  Clock,
  Sparkles,
} from 'lucide-react';
import type { PredictionLogRead } from '../types/deployment';
import type { ModelRead } from '../types/model';

interface PredictionActivityMonitoringTableProps {
  logs: PredictionLogRead[];
  models: ModelRead[];
  loading: boolean;
  totalLogs: number;
  offset: number;
  limit: number;
  onPageChange: (newOffset: number) => void;
  onSubmitGroundTruth: (logId: string, truthVal: unknown) => Promise<void>;
  statusFilter: string;
  onStatusFilterChange: (status: string) => void;
  modelFilter: string;
  onModelFilterChange: (modelId: string) => void;
}

export const PredictionActivityMonitoringTable: React.FC<
  PredictionActivityMonitoringTableProps
> = ({
  logs,
  models,
  loading,
  totalLogs,
  offset,
  limit,
  onPageChange,
  onSubmitGroundTruth,
  statusFilter,
  onStatusFilterChange,
  modelFilter,
  onModelFilterChange,
}) => {
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [groundTruthInput, setGroundTruthInput] = useState<Record<string, string>>({});
  const [submittingTruth, setSubmittingTruth] = useState<string | null>(null);

  const toggleRowExpand = (id: string) => {
    setExpandedRow((prev) => (prev === id ? null : id));
  };

  const handleGroundTruthSubmit = async (logId: string) => {
    const val = groundTruthInput[logId]?.trim();
    if (val === undefined || val === '') return;
    setSubmittingTruth(logId);
    try {
      const parsedVal = isNaN(Number(val)) ? val : Number(val);
      await onSubmitGroundTruth(logId, [parsedVal]);
      setGroundTruthInput((prev) => ({ ...prev, [logId]: '' }));
    } finally {
      setSubmittingTruth(null);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-6">
      {/* Table Header & Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
        <div>
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-600" />
            Prediction Audit Log & Telemetry ({totalLogs} records)
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Persisted execution records from <code className="font-mono text-slate-700">/api/v1/predictions/history</code>.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Model Filter */}
          <select
            value={modelFilter}
            onChange={(e) => onModelFilterChange(e.target.value)}
            className="px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none"
          >
            <option value="">All Models</option>
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} (v{m.version})
              </option>
            ))}
          </select>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => onStatusFilterChange(e.target.value)}
            className="px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none"
          >
            <option value="">All Statuses</option>
            <option value="success">Success</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </div>

      {/* Table Content */}
      {loading ? (
        <div className="py-12 text-center text-slate-500 text-xs">
          <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
          Fetching prediction audit logs...
        </div>
      ) : logs.length === 0 ? (
        <div className="py-12 text-center bg-slate-50 border border-dashed border-slate-200 rounded-xl">
          <Activity className="w-8 h-8 text-slate-400 mx-auto mb-2" />
          <p className="text-xs text-slate-700 font-semibold">No prediction activity recorded yet.</p>
          <p className="text-[11px] text-slate-400 mt-1">
            Execute single or batch predictions in Phase 7 to view live audit telemetry here.
          </p>
        </div>
      ) : (
        <div className="border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
          <div className="max-h-96 overflow-x-auto overflow-y-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-700 font-semibold sticky top-0 z-10">
                <tr>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3">Timestamp</th>
                  <th className="py-2.5 px-3">Model</th>
                  <th className="py-2.5 px-3">Records</th>
                  <th className="py-2.5 px-3">Duration</th>
                  <th className="py-2.5 px-3">Summary / Outcome</th>
                  <th className="py-2.5 px-3 text-center">Inspect / Ground Truth</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {logs.map((log) => {
                  const isExpanded = expandedRow === log.id;
                  const isSuccess = log.status === 'success';
                  const matchedModel = models.find((m) => m.id === log.model_id);

                  return (
                    <React.Fragment key={log.id}>
                      <tr className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-2.5 px-3">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-mono text-[10px] font-bold ${
                              isSuccess
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                : 'bg-rose-50 text-rose-700 border border-rose-200'
                            }`}
                          >
                            {isSuccess ? (
                              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                            ) : (
                              <XCircle className="w-3 h-3 text-rose-600" />
                            )}
                            {log.status}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px] text-slate-600 whitespace-nowrap">
                          {new Date(log.created_at).toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3">
                          <span className="font-semibold text-slate-800 block truncate max-w-[150px]">
                            {matchedModel ? matchedModel.name : log.model_id}
                          </span>
                          <span className="text-[10px] text-slate-400 font-mono block">
                            ID: {log.model_id.slice(0, 8)}...
                          </span>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-700 font-semibold">
                          {log.record_count} {log.record_count === 1 ? 'record' : 'records'}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-700">
                          {log.duration_ms} ms
                        </td>
                        <td className="py-2.5 px-3">
                          {isSuccess && log.prediction_summary ? (
                            <div className="flex items-center gap-1.5 font-mono text-[11px]">
                              <span className="text-slate-500">Output:</span>
                              <span className="px-1.5 py-0.2 rounded bg-indigo-50 text-indigo-700 font-bold border border-indigo-100">
                                {JSON.stringify(log.prediction_summary.predictions || [])}
                              </span>
                            </div>
                          ) : (
                            <span className="text-rose-600 font-mono text-[11px] truncate block max-w-xs">
                              {log.error_message || log.error_category || 'Error'}
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          <button
                            type="button"
                            onClick={() => toggleRowExpand(log.id)}
                            className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                          >
                            {isExpanded ? (
                              <ChevronUp className="w-4 h-4 text-indigo-600" />
                            ) : (
                              <ChevronDown className="w-4 h-4" />
                            )}
                          </button>
                        </td>
                      </tr>

                      {/* Expandable Ground-Truth & Audit Inspection Row */}
                      {isExpanded && (
                        <tr className="bg-slate-50/80">
                          <td colSpan={7} className="p-4">
                            <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
                              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-2">
                                <span className="font-bold text-slate-800 text-xs flex items-center gap-1.5">
                                  <Tag className="w-3.5 h-3.5 text-indigo-600" />
                                  Audit Details & Ground-Truth Association
                                </span>
                                <span className="text-[11px] font-mono text-slate-400">
                                  Prediction UUID: {log.id}
                                </span>
                              </div>

                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-[11px]">
                                <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                                  <span className="text-[10px] text-slate-400 uppercase font-mono block">
                                    Deployment ID
                                  </span>
                                  <span className="font-mono text-slate-800 font-semibold truncate block mt-0.5">
                                    {log.deployment_id || 'On-demand serving (none)'}
                                  </span>
                                </div>
                                <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                                  <span className="text-[10px] text-slate-400 uppercase font-mono block">
                                    Problem Type
                                  </span>
                                  <span className="font-mono text-slate-800 font-semibold capitalize block mt-0.5">
                                    {log.problem_type}
                                  </span>
                                </div>
                                <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                                  <span className="text-[10px] text-slate-400 uppercase font-mono block">
                                    Evaluation Status
                                  </span>
                                  <span
                                    className={`font-mono font-bold block mt-0.5 ${
                                      log.is_evaluated ? 'text-emerald-700' : 'text-amber-700'
                                    }`}
                                  >
                                    {log.is_evaluated ? 'Evaluated with Ground Truth' : 'Pending Ground Truth'}
                                  </span>
                                </div>
                              </div>

                              {/* Ground-truth submission input */}
                              <div className="p-3 rounded-lg bg-indigo-50/50 border border-indigo-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                                <div>
                                  <span className="font-bold text-indigo-950 block">
                                    Ground Truth Annotation
                                  </span>
                                  <p className="text-[11px] text-indigo-800/80">
                                    Supply actual realized outcomes to calculate empirical production accuracy.
                                  </p>
                                </div>
                                <div className="flex items-center gap-2">
                                  <input
                                    type="text"
                                    placeholder="e.g. 1 or 0"
                                    value={groundTruthInput[log.id] || ''}
                                    onChange={(e) =>
                                      setGroundTruthInput((prev) => ({
                                        ...prev,
                                        [log.id]: e.target.value,
                                      }))
                                    }
                                    className="w-28 px-2.5 py-1 text-xs bg-white border border-indigo-200 rounded-lg focus:outline-none"
                                  />
                                  <button
                                    type="button"
                                    onClick={() => handleGroundTruthSubmit(log.id)}
                                    disabled={submittingTruth === log.id || !groundTruthInput[log.id]?.trim()}
                                    className="px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-2xs disabled:opacity-50 transition-colors"
                                  >
                                    {submittingTruth === log.id ? 'Saving...' : 'Submit'}
                                  </button>
                                </div>
                              </div>
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

          {/* Pagination */}
          <div className="bg-slate-50 px-4 py-2.5 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500 font-mono">
            <span>
              Showing {logs.length} of {totalLogs} logs
            </span>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => onPageChange(Math.max(0, offset - limit))}
                disabled={offset === 0}
                className="px-2.5 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 transition-colors"
              >
                Previous
              </button>
              <button
                type="button"
                onClick={() => onPageChange(offset + limit)}
                disabled={offset + limit >= totalLogs}
                className="px-2.5 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
