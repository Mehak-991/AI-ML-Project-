import React, { useState, useEffect, useCallback } from 'react';
import {
  Database,
  AlertCircle,
  FileSpreadsheet,
  CheckCircle,
  Layers,
  Sparkles,
} from 'lucide-react';
import { DatasetUploadCard } from '../components/DatasetUploadCard';
import { DatasetTable } from '../components/DatasetTable';
import { DatasetDetailModal } from '../components/DatasetDetailModal';
import { datasetApi, parseApiError, type ErrorDetails } from '../services/api';
import type { DatasetRead, DatasetCreateResponse } from '../types/dataset';

export const DatasetManagementPage: React.FC = () => {
  const [datasets, setDatasets] = useState<DatasetRead[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [offset, setOffset] = useState<number>(0);
  const limit = 10;
  const [loading, setLoading] = useState<boolean>(false);
  const [errorDetails, setErrorDetails] = useState<ErrorDetails | null>(null);
  const [selectedDataset, setSelectedDataset] = useState<DatasetRead | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  const fetchDatasets = useCallback(async (currentOffset = 0) => {
    setLoading(true);
    setErrorDetails(null);
    try {
      const data = await datasetApi.listDatasets(currentOffset, limit);
      setDatasets(data.items);
      setTotal(data.total);
      setOffset(data.offset);
    } catch (err: unknown) {
      setErrorDetails(parseApiError(err));
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    fetchDatasets(0);
  }, [fetchDatasets]);

  const handleUploadSuccess = (created: DatasetCreateResponse) => {
    setSuccessBanner(
      `Dataset "${created.dataset.name}" registered successfully with ${created.dataset.n_rows.toLocaleString()} rows and ${created.dataset.n_columns} columns.`
    );
    // Refresh the dataset list to reflect new entry
    fetchDatasets(0);
  };

  const totalRowsCount = datasets.reduce((acc, curr) => acc + curr.n_rows, 0);

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Top Banner / Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Total Datasets
            </span>
            <div className="p-2 rounded-xl bg-blue-500/10 text-blue-400">
              <Database className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-3xl font-extrabold font-mono text-white">{total}</span>
            <span className="text-xs text-slate-400 ml-2">registered</span>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Loaded Rows
            </span>
            <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400">
              <Layers className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-3xl font-extrabold font-mono text-white">
              {totalRowsCount.toLocaleString()}
            </span>
            <span className="text-xs text-slate-400 ml-2">records on page</span>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Supported Formats
            </span>
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400">
              <FileSpreadsheet className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <span className="px-2.5 py-1 rounded bg-slate-950 text-emerald-400 border border-emerald-900/50 text-xs font-mono font-bold">
              CSV (UTF-8)
            </span>
            <span className="px-2.5 py-1 rounded bg-slate-950 text-emerald-400 border border-emerald-900/50 text-xs font-mono font-bold">
              XLSX
            </span>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Backend Engine
            </span>
            <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400">
              <Sparkles className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-sm font-semibold text-white">FastAPI + Polars / Pandas</span>
            <p className="text-[11px] text-slate-500">Auto schema, null & duplicate checks</p>
          </div>
        </div>
      </div>

      {/* Success Notification Banner */}
      {successBanner && (
        <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-800/60 text-emerald-300 text-sm flex items-center justify-between animate-fadeIn">
          <div className="flex items-center gap-2.5">
            <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0" />
            <span>{successBanner}</span>
          </div>
          <button
            onClick={() => setSuccessBanner(null)}
            className="text-xs text-emerald-400 hover:text-emerald-200 underline cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Top Error Alert if listing fails */}
      {errorDetails && (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/60 text-red-300 text-sm flex items-start gap-3 animate-fadeIn">
          <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold text-red-200">
              Failed to load datasets ({errorDetails.code}):
            </span>{' '}
            {errorDetails.message}
            <button
              onClick={() => fetchDatasets(offset)}
              className="mt-2 block text-xs underline text-red-400 hover:text-red-200"
            >
              Retry fetching datasets
            </button>
          </div>
        </div>
      )}

      {/* Section 1: Dataset Upload & Validation */}
      <DatasetUploadCard onUploadSuccess={handleUploadSuccess} />

      {/* Section 2: Datasets Table & Inspection */}
      <DatasetTable
        datasets={datasets}
        total={total}
        offset={offset}
        limit={limit}
        loading={loading}
        onPageChange={(newOffset) => fetchDatasets(newOffset)}
        onSelectDataset={(d) => setSelectedDataset(d)}
        onRefresh={() => fetchDatasets(offset)}
      />

      {/* Dataset Details & Schema Modal */}
      {selectedDataset && (
        <DatasetDetailModal
          dataset={selectedDataset}
          onClose={() => setSelectedDataset(null)}
        />
      )}
    </div>
  );
};
