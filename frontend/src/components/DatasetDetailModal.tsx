import React, { useState, useEffect } from 'react';
import {
  X,
  FileSpreadsheet,
  Calendar,
  Layers,
  Database,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Table as TableIcon,
  BarChart3,
  Hash,
  AlertCircle,
} from 'lucide-react';
import type { DatasetRead, DatasetValidationResponse } from '../types/dataset';
import { datasetApi, parseApiError, type ErrorDetails } from '../services/api';

interface DatasetDetailModalProps {
  dataset: DatasetRead;
  onClose: () => void;
}

export const DatasetDetailModal: React.FC<DatasetDetailModalProps> = ({ dataset, onClose }) => {
  const [activeTab, setActiveTab] = useState<'schema' | 'profile'>('schema');
  const [summaryData, setSummaryData] = useState<DatasetValidationResponse | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [errorDetails, setErrorDetails] = useState<ErrorDetails | null>(null);

  useEffect(() => {
    let isMounted = true;
    const fetchSummary = async () => {
      setLoadingSummary(true);
      setErrorDetails(null);
      try {
        const data = await datasetApi.getDatasetSummary(dataset.id);
        if (isMounted) {
          setSummaryData(data);
        }
      } catch (err: unknown) {
        if (isMounted) {
          setErrorDetails(parseApiError(err));
        }
      } finally {
        if (isMounted) {
          setLoadingSummary(false);
        }
      }
    };

    fetchSummary();
    return () => {
      isMounted = false;
    };
  }, [dataset.id]);

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
  };

  const formatDate = (isoString: string): string => {
    try {
      const d = new Date(isoString);
      return d.toLocaleString(undefined, {
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

  const getKindBadgeClass = (kind: string) => {
    switch (kind.toLowerCase()) {
      case 'numeric':
        return 'bg-blue-950/80 text-blue-400 border-blue-800/50';
      case 'categorical':
        return 'bg-emerald-950/80 text-emerald-400 border-emerald-800/50';
      case 'datetime':
        return 'bg-purple-950/80 text-purple-400 border-purple-800/50';
      case 'boolean':
        return 'bg-amber-950/80 text-amber-400 border-amber-800/50';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
      <div className="bg-slate-900 border border-slate-800 w-full max-w-4xl max-h-[90vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Modal Header */}
        <div className="px-6 py-5 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                {dataset.name}
                <span className="text-xs uppercase px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800/50 font-mono">
                  {dataset.file_format}
                </span>
              </h3>
              <p className="text-xs text-slate-400 font-mono mt-0.5">
                ID: {dataset.id}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-2 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Metric Badges */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-6 pb-2">
          <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
            <span className="text-xs text-slate-400 flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5 text-blue-400" /> Total Rows
            </span>
            <p className="text-lg font-bold font-mono text-white mt-1">
              {dataset.n_rows.toLocaleString()}
            </p>
          </div>
          <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
            <span className="text-xs text-slate-400 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-indigo-400" /> Columns
            </span>
            <p className="text-lg font-bold font-mono text-white mt-1">{dataset.n_columns}</p>
          </div>
          <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
            <span className="text-xs text-slate-400 flex items-center gap-1.5">
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" /> File Size
            </span>
            <p className="text-lg font-bold font-mono text-white mt-1">
              {formatFileSize(dataset.size_bytes)}
            </p>
          </div>
          <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
            <span className="text-xs text-slate-400 flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-purple-400" /> Created
            </span>
            <p className="text-xs font-semibold text-white mt-2 truncate">
              {formatDate(dataset.created_at)}
            </p>
          </div>
        </div>

        {/* Tab Controls */}
        <div className="px-6 flex gap-4 border-b border-slate-800 mt-2">
          <button
            onClick={() => setActiveTab('schema')}
            className={`pb-3 text-sm font-semibold flex items-center gap-2 border-b-2 transition-colors ${
              activeTab === 'schema'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-slate-400 hover:text-slate-300'
            }`}
          >
            <TableIcon className="w-4 h-4" />
            Column Schema & Data Types ({dataset.columns.length})
          </button>
          <button
            onClick={() => setActiveTab('profile')}
            className={`pb-3 text-sm font-semibold flex items-center gap-2 border-b-2 transition-colors ${
              activeTab === 'profile'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-slate-400 hover:text-slate-300'
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            Statistical Profile & Quality
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          {activeTab === 'schema' && (
            <div className="space-y-4">
              <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-900/80 text-xs text-slate-400 uppercase tracking-wider border-b border-slate-800">
                    <tr>
                      <th className="px-4 py-3 font-semibold">#</th>
                      <th className="px-4 py-3 font-semibold">Column Name</th>
                      <th className="px-4 py-3 font-semibold">Detected Kind</th>
                      <th className="px-4 py-3 font-semibold">Native Data Type (dtype)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                    {dataset.columns.map((col, index) => (
                      <tr key={col.name} className="hover:bg-slate-900/40 transition-colors">
                        <td className="px-4 py-2.5 text-slate-500">{index + 1}</td>
                        <td className="px-4 py-2.5 font-semibold text-white font-sans flex items-center gap-2">
                          <Hash className="w-3.5 h-3.5 text-slate-500" />
                          {col.name}
                        </td>
                        <td className="px-4 py-2.5">
                          <span
                            className={`px-2 py-0.5 rounded border text-[11px] font-sans font-medium uppercase ${getKindBadgeClass(
                              col.kind
                            )}`}
                          >
                            {col.kind}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-slate-300">{col.dtype}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="p-3 bg-slate-950 rounded-xl border border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
                <span>Original File: <strong className="text-white font-mono">{dataset.original_filename}</strong></span>
                <span>SHA256: <strong className="text-slate-300 font-mono">{dataset.sha256.slice(0, 16)}...</strong></span>
              </div>
            </div>
          )}

          {activeTab === 'profile' && (
            <div>
              {loadingSummary ? (
                <div className="py-16 text-center text-slate-400">
                  <Loader2 className="w-8 h-8 animate-spin mx-auto text-blue-400 mb-3" />
                  <p className="text-sm">Calculating dataset quality metrics & column statistics...</p>
                </div>
              ) : errorDetails ? (
                <div className="p-4 rounded-xl bg-red-950/40 border border-red-800 text-red-300 text-sm flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
                  <div>
                    <span className="font-semibold">{errorDetails.message}</span>
                    <p className="text-xs text-red-400 mt-1">
                      Endpoint: GET /api/v1/datasets/{dataset.id}/summary
                    </p>
                  </div>
                </div>
              ) : summaryData ? (
                <div className="space-y-4">
                  {/* Validation status report */}
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {summaryData.validation.is_valid ? (
                        <div className="flex items-center gap-2 text-emerald-400 font-semibold text-sm">
                          <CheckCircle2 className="w-5 h-5" />
                          Dataset Passed All Validation Checks
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 text-amber-400 font-semibold text-sm">
                          <AlertTriangle className="w-5 h-5" />
                          Validation Warnings Detected
                        </div>
                      )}
                    </div>
                    <div className="text-xs text-slate-400">
                      Duplicate Rows:{' '}
                      <strong className="text-white font-mono">
                        {summaryData.summary.duplicates.duplicate_rows} (
                        {(summaryData.summary.duplicates.duplicate_ratio * 100).toFixed(1)}%)
                      </strong>
                    </div>
                  </div>

                  {/* Missing values and memory summary */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800">
                      <span className="text-xs text-slate-400">Total Missing Cells</span>
                      <p className="text-base font-bold font-mono text-white mt-1">
                        {summaryData.summary.missing_values.total_missing_cells.toLocaleString()}
                      </p>
                    </div>
                    <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800">
                      <span className="text-xs text-slate-400">Rows With Missing Data</span>
                      <p className="text-base font-bold font-mono text-white mt-1">
                        {summaryData.summary.missing_values.rows_with_missing.toLocaleString()}
                      </p>
                    </div>
                    <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800">
                      <span className="text-xs text-slate-400">Memory in RAM</span>
                      <p className="text-base font-bold font-mono text-white mt-1">
                        {formatFileSize(summaryData.summary.memory_bytes)}
                      </p>
                    </div>
                  </div>

                  {/* Column Stats breakdown */}
                  <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden">
                    <div className="px-4 py-3 bg-slate-900/80 border-b border-slate-800">
                      <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                        Column Level Statistical Breakdown
                      </h4>
                    </div>
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-900/40 text-slate-400 uppercase tracking-wider border-b border-slate-800 font-mono text-[11px]">
                        <tr>
                          <th className="px-4 py-2.5">Column</th>
                          <th className="px-4 py-2.5">Kind</th>
                          <th className="px-4 py-2.5">Missing</th>
                          <th className="px-4 py-2.5">Unique Values</th>
                          <th className="px-4 py-2.5">Key Metrics / Summary</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                        {summaryData.summary.columns.map((c) => (
                          <tr key={c.name} className="hover:bg-slate-900/30">
                            <td className="px-4 py-2.5 font-bold text-white font-sans">{c.name}</td>
                            <td className="px-4 py-2.5">
                              <span
                                className={`px-2 py-0.5 rounded border text-[10px] font-sans font-medium uppercase ${getKindBadgeClass(
                                  c.kind
                                )}`}
                              >
                                {c.kind}
                              </span>
                            </td>
                            <td className="px-4 py-2.5 text-slate-300">
                              {c.missing_count} ({(c.missing_ratio * 100).toFixed(1)}%)
                            </td>
                            <td className="px-4 py-2.5 text-slate-300">{c.unique_count}</td>
                            <td className="px-4 py-2.5 text-slate-400 font-sans text-xs">
                              {c.stats ? (
                                <span className="text-slate-300">
                                  {Object.entries(c.stats)
                                    .slice(0, 3)
                                    .map(([k, v]) => `${k}: ${typeof v === 'number' ? v.toFixed(2) : v}`)
                                    .join(' | ')}
                                </span>
                              ) : c.top_values && c.top_values.length > 0 ? (
                                <span className="text-slate-300">
                                  Top: {c.top_values.slice(0, 2).map((item) => String(item.value ?? Object.values(item)[0])).join(', ')}
                                </span>
                              ) : (
                                <span className="text-slate-500">—</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 bg-slate-950 border-t border-slate-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl text-sm font-semibold bg-slate-800 hover:bg-slate-700 text-white transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
