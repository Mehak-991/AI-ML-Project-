import React, { useState } from 'react';
import {
  Search,
  Filter,
  ArrowUpDown,
  RefreshCw,
  Eye,
  BarChart2,
  Calendar,
  Layers,
  Cpu,
  Target,
  CheckSquare,
  Square,
  GitCompare,
} from 'lucide-react';
import type { ModelRead } from '../types/model';

interface ModelTableProps {
  models: ModelRead[];
  total: number;
  offset: number;
  limit: number;
  loading: boolean;
  selectedModelIds: string[];
  onToggleSelectModel: (id: string) => void;
  onSelectModel: (model: ModelRead) => void;
  onOpenAnalytics: (model: ModelRead) => void;
  onPageChange: (newOffset: number) => void;
  onRefresh: () => void;
  onCompareSelected: () => void;
}

export const ModelTable: React.FC<ModelTableProps> = ({
  models,
  total,
  offset,
  limit,
  loading,
  selectedModelIds,
  onToggleSelectModel,
  onSelectModel,
  onOpenAnalytics,
  onPageChange,
  onRefresh,
  onCompareSelected,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [algorithmFilter, setAlgorithmFilter] = useState<'all' | 'linear' | 'random_forest'>('all');
  const [problemFilter, setProblemFilter] = useState<'all' | 'classification' | 'regression'>('all');
  const [sortBy, setSortBy] = useState<'created_at' | 'name' | 'score'>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

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

  const getPrimaryScore = (model: ModelRead): { label: string; value: number | null } => {
    const testMetrics = model.metrics?.test || model.metrics?.validation || model.metrics?.train;
    if (!testMetrics) return { label: 'Score', value: null };

    if (model.problem_type === 'classification') {
      const acc = testMetrics.accuracy ?? testMetrics.f1_macro ?? null;
      return { label: 'Acc', value: acc !== null ? Number(acc) : null };
    }
    const r2 = testMetrics.r2 ?? null;
    return { label: 'R²', value: r2 !== null ? Number(r2) : null };
  };

  const filteredModels = models
    .filter((m) => {
      const matchesSearch =
        m.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        m.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        m.target_column.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesAlgo =
        algorithmFilter === 'all' || m.algorithm.toLowerCase() === algorithmFilter;

      const matchesProblem =
        problemFilter === 'all' || m.problem_type.toLowerCase() === problemFilter;

      return matchesSearch && matchesAlgo && matchesProblem;
    })
    .sort((a, b) => {
      if (sortBy === 'name') {
        return sortOrder === 'asc'
          ? a.name.localeCompare(b.name)
          : b.name.localeCompare(a.name);
      }
      if (sortBy === 'score') {
        const scoreA = getPrimaryScore(a).value ?? -999;
        const scoreB = getPrimaryScore(b).value ?? -999;
        return sortOrder === 'asc' ? scoreA - scoreB : scoreB - scoreA;
      }
      const dateA = new Date(a.created_at).getTime();
      const dateB = new Date(b.created_at).getTime();
      return sortOrder === 'asc' ? dateA - dateB : dateB - dateA;
    });

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  const allFilteredSelected =
    filteredModels.length > 0 &&
    filteredModels.every((m) => selectedModelIds.includes(m.id));

  const toggleSelectAllFiltered = () => {
    if (allFilteredSelected) {
      filteredModels.forEach((m) => {
        if (selectedModelIds.includes(m.id)) {
          onToggleSelectModel(m.id);
        }
      });
    } else {
      filteredModels.forEach((m) => {
        if (!selectedModelIds.includes(m.id)) {
          onToggleSelectModel(m.id);
        }
      });
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden flex flex-col">
      {/* Controls Bar */}
      <div className="p-5 border-b border-slate-200 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
              <Layers className="w-5 h-5 text-indigo-600" />
              Trained Models
            </h2>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
              {total} Total
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Registered machine learning artifacts with persisted weights, schemas, and metrics.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Comparison Trigger if models selected */}
          {selectedModelIds.length > 0 && (
            <button
              onClick={onCompareSelected}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-indigo-600 text-white shadow-sm hover:bg-indigo-700 transition-colors animate-pulse"
            >
              <GitCompare className="w-3.5 h-3.5" />
              Compare ({selectedModelIds.length})
            </button>
          )}

          {/* Search */}
          <div className="relative min-w-[200px]">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search by name, ID, target..."
              className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500"
            />
          </div>

          {/* Algorithm filter */}
          <div className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1 text-xs">
            <Filter className="w-3.5 h-3.5 text-slate-500" />
            <select
              value={algorithmFilter}
              onChange={(e) =>
                setAlgorithmFilter(e.target.value as 'all' | 'linear' | 'random_forest')
              }
              className="bg-transparent text-slate-700 focus:outline-none cursor-pointer pr-1 py-0.5"
            >
              <option value="all">All Algorithms</option>
              <option value="linear">Linear / Logistic</option>
              <option value="random_forest">Random Forest</option>
            </select>
          </div>

          {/* Problem filter */}
          <div className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1 text-xs">
            <Target className="w-3.5 h-3.5 text-slate-500" />
            <select
              value={problemFilter}
              onChange={(e) =>
                setProblemFilter(e.target.value as 'all' | 'classification' | 'regression')
              }
              className="bg-transparent text-slate-700 focus:outline-none cursor-pointer pr-1 py-0.5"
            >
              <option value="all">All Problems</option>
              <option value="classification">Classification</option>
              <option value="regression">Regression</option>
            </select>
          </div>

          {/* Sorting */}
          <div className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1 text-xs">
            <ArrowUpDown className="w-3.5 h-3.5 text-slate-500" />
            <select
              value={`${sortBy}-${sortOrder}`}
              onChange={(e) => {
                const [sb, so] = e.target.value.split('-') as [
                  'created_at' | 'name' | 'score',
                  'asc' | 'desc'
                ];
                setSortBy(sb);
                setSortOrder(so);
              }}
              className="bg-transparent text-slate-700 focus:outline-none cursor-pointer pr-1 py-0.5"
            >
              <option value="created_at-desc">Newest First</option>
              <option value="created_at-asc">Oldest First</option>
              <option value="score-desc">Highest Score</option>
              <option value="name-asc">Name (A-Z)</option>
            </select>
          </div>

          {/* Refresh */}
          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors disabled:opacity-50"
            title="Refresh Models"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-indigo-600' : ''}`} />
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50/80 text-xs text-slate-500 uppercase tracking-wider border-b border-slate-200">
            <tr>
              <th className="px-4 py-3 w-10 text-center">
                <button
                  type="button"
                  onClick={toggleSelectAllFiltered}
                  className="text-slate-400 hover:text-slate-700"
                  title="Select all"
                >
                  {allFilteredSelected ? (
                    <CheckSquare className="w-4 h-4 text-indigo-600" />
                  ) : (
                    <Square className="w-4 h-4" />
                  )}
                </button>
              </th>
              <th className="px-4 py-3 font-semibold">Model Name & ID</th>
              <th className="px-4 py-3 font-semibold">Algorithm & Type</th>
              <th className="px-4 py-3 font-semibold">Target Column</th>
              <th className="px-4 py-3 font-semibold">Features</th>
              <th className="px-4 py-3 font-semibold">Primary Score</th>
              <th className="px-4 py-3 font-semibold">Status</th>
              <th className="px-4 py-3 font-semibold">Trained Date</th>
              <th className="px-4 py-3 font-semibold text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && models.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-6 py-12 text-center text-slate-400">
                  <div className="flex flex-col items-center justify-center">
                    <RefreshCw className="w-6 h-6 animate-spin text-indigo-600 mb-2" />
                    <span className="text-sm font-medium">Loading model registry...</span>
                  </div>
                </td>
              </tr>
            ) : filteredModels.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-6 py-14 text-center text-slate-400">
                  <div className="max-w-sm mx-auto flex flex-col items-center">
                    <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center text-slate-400 mb-3">
                      <Cpu className="w-6 h-6" />
                    </div>
                    <p className="text-base font-semibold text-slate-800">No models found</p>
                    <p className="text-xs text-slate-500 mt-1">
                      {searchTerm || algorithmFilter !== 'all' || problemFilter !== 'all'
                        ? 'Try clearing search filters or selecting different options.'
                        : 'No models trained yet. Train a model in Phase 5 to view it here.'}
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              filteredModels.map((model) => {
                const isSelected = selectedModelIds.includes(model.id);
                const score = getPrimaryScore(model);

                return (
                  <tr
                    key={model.id}
                    className={`hover:bg-indigo-50/30 transition-colors group cursor-pointer ${
                      isSelected ? 'bg-indigo-50/50' : ''
                    }`}
                    onClick={() => onSelectModel(model)}
                  >
                    <td
                      className="px-4 py-3 text-center"
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleSelectModel(model.id);
                      }}
                    >
                      {isSelected ? (
                        <CheckSquare className="w-4 h-4 text-indigo-600 inline" />
                      ) : (
                        <Square className="w-4 h-4 text-slate-300 group-hover:text-slate-500 inline" />
                      )}
                    </td>

                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shrink-0">
                          <Cpu className="w-4 h-4" />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-slate-900 group-hover:text-indigo-600 transition-colors block truncate max-w-[220px]">
                              {model.name}
                            </span>
                            <span className="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-slate-100 text-slate-600 border border-slate-200">
                              v{model.version}
                            </span>
                          </div>
                          <span className="text-[11px] font-mono text-slate-400 block truncate max-w-[200px]">
                            {model.id}
                          </span>
                        </div>
                      </div>
                    </td>

                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1 items-start">
                        <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-800 border border-slate-200 capitalize">
                          {model.algorithm.replace('_', ' ')}
                        </span>
                        <span className="text-[11px] font-mono text-indigo-600 uppercase font-semibold">
                          {model.problem_type}
                        </span>
                      </div>
                    </td>

                    <td className="px-4 py-3">
                      <span className="font-mono text-xs font-semibold text-slate-700 bg-slate-50 px-2 py-0.5 rounded border border-slate-200">
                        {model.target_column}
                      </span>
                    </td>

                    <td className="px-4 py-3 text-xs text-slate-600 font-mono">
                      {model.feature_schema.length} <span className="text-slate-400">features</span>
                    </td>

                    <td className="px-4 py-3">
                      {score.value !== null ? (
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs text-slate-400 font-mono">{score.label}:</span>
                          <span className="text-xs font-mono font-bold text-slate-900 bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded border border-emerald-200">
                            {(score.value * 100).toFixed(1)}%
                          </span>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </td>

                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                        Ready
                      </span>
                    </td>

                    <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5 text-slate-400" />
                        {formatDate(model.created_at)}
                      </div>
                    </td>

                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenAnalytics(model);
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-indigo-50 hover:bg-indigo-600 text-indigo-700 hover:text-white transition-all border border-indigo-200"
                          title="Open Analytics Dashboard"
                        >
                          <BarChart2 className="w-3.5 h-3.5" />
                          Analytics
                        </button>

                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectModel(model);
                          }}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition-all border border-slate-200"
                          title="View Details"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          Details
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="p-4 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-600">
        <div>
          Showing{' '}
          <strong className="text-slate-900 font-mono">
            {total === 0 ? 0 : offset + 1}
          </strong>{' '}
          to{' '}
          <strong className="text-slate-900 font-mono">
            {Math.min(offset + limit, total)}
          </strong>{' '}
          of <strong className="text-slate-900 font-mono">{total}</strong> models
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onPageChange(Math.max(0, offset - limit))}
            disabled={offset === 0 || loading}
            className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 disabled:opacity-40 disabled:pointer-events-none transition-colors"
          >
            Previous
          </button>
          <span className="font-mono text-slate-500">
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => onPageChange(offset + limit)}
            disabled={offset + limit >= total || loading}
            className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 disabled:opacity-40 disabled:pointer-events-none transition-colors"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
};
