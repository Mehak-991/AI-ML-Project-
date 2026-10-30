import React, { useState } from 'react';
import {
  FileSpreadsheet,
  Search,
  Filter,
  Eye,
  ChevronLeft,
  ChevronRight,
  Database,
  Calendar,
  ArrowUpDown,
  RefreshCw,
} from 'lucide-react';
import type { DatasetRead } from '../types/dataset';

interface DatasetTableProps {
  datasets: DatasetRead[];
  total: number;
  offset: number;
  limit: number;
  loading: boolean;
  onPageChange: (newOffset: number) => void;
  onSelectDataset: (dataset: DatasetRead) => void;
  onRefresh: () => void;
}

export const DatasetTable: React.FC<DatasetTableProps> = ({
  datasets,
  total,
  offset,
  limit,
  loading,
  onPageChange,
  onSelectDataset,
  onRefresh,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [formatFilter, setFormatFilter] = useState<'all' | 'csv' | 'xlsx'>('all');
  const [sortBy, setSortBy] = useState<'created_at' | 'name' | 'n_rows'>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

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
      return d.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return isoString;
    }
  };

  // Filter datasets client-side based on search term and format
  const filteredDatasets = datasets
    .filter((d) => {
      const matchesSearch =
        d.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        d.original_filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
        d.id.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesFormat =
        formatFilter === 'all' || d.file_format.toLowerCase() === formatFilter;

      return matchesSearch && matchesFormat;
    })
    .sort((a, b) => {
      if (sortBy === 'name') {
        return sortOrder === 'asc'
          ? a.name.localeCompare(b.name)
          : b.name.localeCompare(a.name);
      }
      if (sortBy === 'n_rows') {
        return sortOrder === 'asc' ? a.n_rows - b.n_rows : b.n_rows - a.n_rows;
      }
      // default: created_at
      const dateA = new Date(a.created_at).getTime();
      const dateB = new Date(b.created_at).getTime();
      return sortOrder === 'asc' ? dateA - dateB : dateB - dateA;
    });

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-xl overflow-hidden flex flex-col">
      {/* Table Header Controls */}
      <div className="p-5 border-b border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Database className="w-5 h-5 text-indigo-400" />
            Registered Datasets
          </h2>
          <p className="text-sm text-slate-400 mt-0.5">
            View, inspect schema definitions, and explore stored datasets.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Search bar */}
          <div className="relative min-w-[220px]">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Filter by name or ID..."
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            />
          </div>

          {/* Format filter dropdown */}
          <div className="flex items-center gap-1 bg-slate-950 border border-slate-800 rounded-xl px-2 py-1 text-xs">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={formatFilter}
              onChange={(e) => setFormatFilter(e.target.value as 'all' | 'csv' | 'xlsx')}
              className="bg-transparent text-slate-300 focus:outline-none cursor-pointer pr-1 py-1"
            >
              <option value="all" className="bg-slate-900 text-white">All Formats</option>
              <option value="csv" className="bg-slate-900 text-white">CSV</option>
              <option value="xlsx" className="bg-slate-900 text-white">XLSX</option>
            </select>
          </div>

          {/* Sort selector */}
          <div className="flex items-center gap-1 bg-slate-950 border border-slate-800 rounded-xl px-2 py-1 text-xs">
            <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={`${sortBy}-${sortOrder}`}
              onChange={(e) => {
                const [sb, so] = e.target.value.split('-') as [
                  'created_at' | 'name' | 'n_rows',
                  'asc' | 'desc'
                ];
                setSortBy(sb);
                setSortOrder(so);
              }}
              className="bg-transparent text-slate-300 focus:outline-none cursor-pointer pr-1 py-1"
            >
              <option value="created_at-desc" className="bg-slate-900 text-white">Newest First</option>
              <option value="created_at-asc" className="bg-slate-900 text-white">Oldest First</option>
              <option value="n_rows-desc" className="bg-slate-900 text-white">Most Rows</option>
              <option value="name-asc" className="bg-slate-900 text-white">Name (A-Z)</option>
            </select>
          </div>

          {/* Refresh Button */}
          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-2 rounded-xl bg-slate-950 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition-colors disabled:opacity-50"
            title="Refresh Datasets"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-blue-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Responsive Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-950/60 text-xs text-slate-400 uppercase tracking-wider border-b border-slate-800">
            <tr>
              <th className="px-5 py-3.5 font-semibold">Dataset / Filename</th>
              <th className="px-5 py-3.5 font-semibold">Format</th>
              <th className="px-5 py-3.5 font-semibold">Dimensions</th>
              <th className="px-5 py-3.5 font-semibold">File Size</th>
              <th className="px-5 py-3.5 font-semibold">Columns Summary</th>
              <th className="px-5 py-3.5 font-semibold">Created Date</th>
              <th className="px-5 py-3.5 font-semibold text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {filteredDatasets.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-14 text-center text-slate-400">
                  <div className="max-w-sm mx-auto flex flex-col items-center">
                    <div className="w-12 h-12 rounded-2xl bg-slate-800/80 flex items-center justify-center text-slate-500 mb-3">
                      <FileSpreadsheet className="w-6 h-6" />
                    </div>
                    <p className="text-base font-semibold text-white">No datasets found</p>
                    <p className="text-xs text-slate-500 mt-1">
                      {searchTerm || formatFilter !== 'all'
                        ? 'Try clearing the search query or changing filters.'
                        : 'Upload your first CSV or Excel dataset using the form above.'}
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              filteredDatasets.map((dataset) => (
                <tr
                  key={dataset.id}
                  className="hover:bg-slate-800/40 transition-colors group cursor-pointer"
                  onClick={() => onSelectDataset(dataset)}
                >
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 shrink-0">
                        <FileSpreadsheet className="w-4 h-4" />
                      </div>
                      <div className="min-w-0">
                        <span className="font-semibold text-white group-hover:text-blue-400 transition-colors block truncate max-w-[240px]">
                          {dataset.name}
                        </span>
                        <span className="text-xs text-slate-400 block truncate max-w-[240px]">
                          {dataset.original_filename}
                        </span>
                        <span className="text-[11px] font-mono text-slate-600 block truncate max-w-[180px]">
                          {dataset.id}
                        </span>
                      </div>
                    </div>
                  </td>

                  <td className="px-5 py-3.5">
                    <span className="px-2.5 py-1 rounded-md text-xs font-mono font-semibold uppercase bg-slate-950 text-blue-400 border border-blue-900/40">
                      {dataset.file_format}
                    </span>
                  </td>

                  <td className="px-5 py-3.5 font-mono text-xs">
                    <span className="text-white font-semibold">
                      {dataset.n_rows.toLocaleString()}
                    </span>{' '}
                    <span className="text-slate-500">rows</span>
                    <div className="text-slate-400 text-[11px]">
                      {dataset.n_columns} <span className="text-slate-500">cols</span>
                    </div>
                  </td>

                  <td className="px-5 py-3.5 text-xs text-slate-300 font-mono">
                    {formatFileSize(dataset.size_bytes)}
                  </td>

                  <td className="px-5 py-3.5">
                    <div className="flex flex-wrap gap-1 max-w-[220px]">
                      {dataset.columns.slice(0, 3).map((col) => (
                        <span
                          key={col.name}
                          className="px-1.5 py-0.5 rounded text-[10px] bg-slate-950 border border-slate-800 text-slate-300 font-mono"
                          title={`${col.name} (${col.kind} - ${col.dtype})`}
                        >
                          {col.name}
                        </span>
                      ))}
                      {dataset.columns.length > 3 && (
                        <span className="text-[10px] text-slate-500 self-center">
                          +{dataset.columns.length - 3} more
                        </span>
                      )}
                    </div>
                  </td>

                  <td className="px-5 py-3.5 text-xs text-slate-400 whitespace-nowrap">
                    <div className="flex items-center gap-1.5">
                      <Calendar className="w-3.5 h-3.5 text-slate-500" />
                      {formatDate(dataset.created_at)}
                    </div>
                  </td>

                  <td className="px-5 py-3.5 text-right whitespace-nowrap">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectDataset(dataset);
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-blue-600 text-slate-300 hover:text-white transition-all border border-slate-700/60"
                    >
                      <Eye className="w-3.5 h-3.5" />
                      Details
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Backend Pagination Footer */}
      <div className="p-4 bg-slate-950/70 border-t border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-400">
        <div>
          Showing{' '}
          <strong className="text-white font-mono">
            {total === 0 ? 0 : offset + 1}
          </strong>{' '}
          to{' '}
          <strong className="text-white font-mono">
            {Math.min(offset + limit, total)}
          </strong>{' '}
          of <strong className="text-white font-mono">{total}</strong> total datasets
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onPageChange(Math.max(0, offset - limit))}
            disabled={offset === 0 || loading}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:bg-slate-800 disabled:opacity-40 disabled:pointer-events-none transition-colors"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            Previous
          </button>

          <span className="px-2 font-mono text-slate-300">
            Page {currentPage} of {totalPages}
          </span>

          <button
            onClick={() => onPageChange(offset + limit)}
            disabled={offset + limit >= total || loading}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:bg-slate-800 disabled:opacity-40 disabled:pointer-events-none transition-colors"
          >
            Next
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};
