import { useEffect, useState } from 'react';
import {
  RefreshCw,
  XCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Activity,
  Search,
  ChevronLeft,
  ChevronRight,
  Terminal,
} from 'lucide-react';
import { jobsApi } from '../services/api';
import type { Job, JobMetricsResponse, JobStatus } from '../types/job';

export function JobManagementPage() {
  const [metrics, setMetrics] = useState<JobMetricsResponse | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const [filterStatus, setFilterStatus] = useState<string>('');
  const [filterType, setFilterType] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);

  const fetchMetrics = async () => {
    try {
      const data = await jobsApi.getJobMetrics();
      setMetrics(data);
    } catch (err) {
      console.error('Failed to load job metrics', err);
    }
  };

  const fetchJobs = async () => {
    setLoading(true);
    try {
      const offset = (page - 1) * pageSize;
      const res = await jobsApi.listJobs({
        offset,
        limit: pageSize,
        status: filterStatus || undefined,
        job_type: filterType || undefined,
      });
      setJobs(res.items);
      setTotal(res.total);
    } catch (err) {
      console.error('Failed to load jobs', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
    fetchJobs();
  }, [page, filterStatus, filterType]);

  // Polling for active jobs (every 3 seconds if active jobs exist)
  useEffect(() => {
    const hasActiveJobs = jobs.some(
      (j) => j.status === 'running' || j.status === 'queued' || j.status === 'retry_pending'
    );
    if (!hasActiveJobs) return;

    const interval = setInterval(() => {
      fetchJobs();
      fetchMetrics();
      if (selectedJob) {
        jobsApi.getJob(selectedJob.id).then(setSelectedJob).catch(() => {});
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [jobs, selectedJob]);

  const handleCancel = async (jobId: string) => {
    setActionLoading(jobId);
    try {
      const updated = await jobsApi.cancelJob(jobId);
      setJobs((prev) => prev.map((j) => (j.id === jobId ? updated : j)));
      if (selectedJob?.id === jobId) setSelectedJob(updated);
      fetchMetrics();
    } catch (err) {
      console.error('Failed to cancel job', err);
    } finally {
      setActionLoading(null);
    }
  };

  const handleRetry = async (jobId: string) => {
    setActionLoading(jobId);
    try {
      const updated = await jobsApi.retryJob(jobId);
      setJobs((prev) => prev.map((j) => (j.id === jobId ? updated : j)));
      if (selectedJob?.id === jobId) setSelectedJob(updated);
      fetchMetrics();
    } catch (err) {
      console.error('Failed to retry job', err);
    } finally {
      setActionLoading(null);
    }
  };

  const filteredJobs = searchQuery
    ? jobs.filter(
        (j) =>
          j.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
          j.job_type.toLowerCase().includes(searchQuery.toLowerCase()) ||
          j.current_stage?.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : jobs;

  const totalPages = Math.ceil(total / pageSize) || 1;

  const getStatusBadge = (status: JobStatus) => {
    switch (status) {
      case 'completed':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Completed
          </span>
        );
      case 'running':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200 animate-pulse">
            <Activity className="w-3.5 h-3.5 animate-spin" />
            Running
          </span>
        );
      case 'queued':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <Clock className="w-3.5 h-3.5" />
            Queued
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <AlertTriangle className="w-3.5 h-3.5" />
            Failed
          </span>
        );
      case 'cancelled':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-300">
            <XCircle className="w-3.5 h-3.5" />
            Cancelled
          </span>
        );
      case 'retry_pending':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            Retry Pending
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">
              Background Jobs & Task Queue
            </h1>
            <span className="px-2 py-0.5 text-xs font-bold font-mono bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-md">
              Phase 14
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Persistent asynchronous job execution, real-time stage progress, worker orchestration and failure recovery.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              fetchMetrics();
              fetchJobs();
            }}
            className="flex items-center gap-2 px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition-colors shadow-sm cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      {metrics && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total</span>
            <p className="text-2xl font-bold text-slate-900 mt-1">{metrics.total_jobs}</p>
          </div>
          <div className="bg-white p-4 rounded-xl border border-amber-200 shadow-sm">
            <span className="text-xs font-semibold text-amber-600 uppercase tracking-wider">Queued</span>
            <p className="text-2xl font-bold text-amber-600 mt-1">{metrics.queued_jobs}</p>
          </div>
          <div className="bg-white p-4 rounded-xl border border-blue-200 shadow-sm">
            <span className="text-xs font-semibold text-blue-600 uppercase tracking-wider">Running</span>
            <p className="text-2xl font-bold text-blue-600 mt-1">{metrics.running_jobs}</p>
          </div>
          <div className="bg-white p-4 rounded-xl border border-emerald-200 shadow-sm">
            <span className="text-xs font-semibold text-emerald-600 uppercase tracking-wider">Completed</span>
            <p className="text-2xl font-bold text-emerald-600 mt-1">{metrics.completed_jobs}</p>
          </div>
          <div className="bg-white p-4 rounded-xl border border-rose-200 shadow-sm">
            <span className="text-xs font-semibold text-rose-600 uppercase tracking-wider">Failed</span>
            <p className="text-2xl font-bold text-rose-600 mt-1">{metrics.failed_jobs}</p>
          </div>
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Cancelled</span>
            <p className="text-2xl font-bold text-slate-600 mt-1">{metrics.cancelled_jobs}</p>
          </div>
        </div>
      )}

      {/* Filters and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
        <div className="flex items-center gap-3 flex-1">
          <div className="relative flex-1 max-w-sm">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search by Job ID, stage, or type..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
            />
          </div>
          <select
            value={filterStatus}
            onChange={(e) => {
              setFilterStatus(e.target.value);
              setPage(1);
            }}
            className="text-xs px-3 py-2 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          >
            <option value="">All Statuses</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <select
            value={filterType}
            onChange={(e) => {
              setFilterType(e.target.value);
              setPage(1);
            }}
            className="text-xs px-3 py-2 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          >
            <option value="">All Types</option>
            <option value="model_training">Model Training</option>
            <option value="experiment_execution">AutoML Experiment</option>
            <option value="drift_analysis">Drift Analysis</option>
            <option value="explainability">Explainability (XAI)</option>
            <option value="batch_prediction">Batch Prediction</option>
          </select>
        </div>
      </div>

      {/* Main Jobs Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 uppercase tracking-wider">
                <th className="px-5 py-3.5">Job ID</th>
                <th className="px-5 py-3.5">Type</th>
                <th className="px-5 py-3.5">Status</th>
                <th className="px-5 py-3.5">Stage & Progress</th>
                <th className="px-5 py-3.5">Duration</th>
                <th className="px-5 py-3.5">Created At</th>
                <th className="px-5 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs text-slate-700">
              {filteredJobs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-12 text-slate-400">
                    No jobs found matching criteria.
                  </td>
                </tr>
              ) : (
                filteredJobs.map((job) => (
                  <tr
                    key={job.id}
                    onClick={() => setSelectedJob(job)}
                    className={`hover:bg-slate-50/80 cursor-pointer transition-colors ${
                      selectedJob?.id === job.id ? 'bg-indigo-50/40' : ''
                    }`}
                  >
                    <td className="px-5 py-3.5 font-mono text-[11px] font-semibold text-indigo-600">
                      {job.id.slice(0, 8)}...
                    </td>
                    <td className="px-5 py-3.5 font-medium text-slate-800 capitalize">
                      {job.job_type.replace(/_/g, ' ')}
                    </td>
                    <td className="px-5 py-3.5">{getStatusBadge(job.status)}</td>
                    <td className="px-5 py-3.5 max-w-xs">
                      <div className="flex flex-col gap-1">
                        <span className="text-[11px] text-slate-600 truncate" title={job.current_stage || ''}>
                          {job.current_stage || 'N/A'}
                        </span>
                        <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
                          <div
                            className={`h-full transition-all duration-500 ${
                              job.status === 'failed'
                                ? 'bg-rose-500'
                                : job.status === 'completed'
                                ? 'bg-emerald-500'
                                : 'bg-indigo-600'
                            }`}
                            style={{ width: `${job.progress_percentage}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-slate-500 font-mono text-[11px]">
                      {job.execution_duration_seconds ? `${job.execution_duration_seconds}s` : '—'}
                    </td>
                    <td className="px-5 py-3.5 text-slate-500">
                      {new Date(job.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="px-5 py-3.5 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-2">
                        {(job.status === 'queued' || job.status === 'running') && (
                          <button
                            disabled={actionLoading === job.id}
                            onClick={() => handleCancel(job.id)}
                            className="px-2.5 py-1 text-rose-600 hover:bg-rose-50 border border-rose-200 rounded-lg text-[11px] font-semibold transition-colors cursor-pointer"
                          >
                            Cancel
                          </button>
                        )}
                        {(job.status === 'failed' || job.status === 'cancelled') && (
                          <button
                            disabled={actionLoading === job.id}
                            onClick={() => handleRetry(job.id)}
                            className="px-2.5 py-1 text-indigo-600 hover:bg-indigo-50 border border-indigo-200 rounded-lg text-[11px] font-semibold transition-colors cursor-pointer"
                          >
                            Retry
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-slate-200 bg-slate-50/50 text-xs text-slate-500">
          <span>
            Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total} jobs
          </span>
          <div className="flex items-center gap-1.5">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-3 font-medium text-slate-700">
              Page {page} of {totalPages}
            </span>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Selected Job Detail Modal/Drawer */}
      {selectedJob && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-4">
            <div className="flex items-center gap-3">
              <Terminal className="w-5 h-5 text-indigo-600" />
              <div>
                <h3 className="font-bold text-slate-900 text-sm">
                  Job Details: <span className="font-mono text-indigo-600">{selectedJob.id}</span>
                </h3>
                <p className="text-xs text-slate-500">Type: {selectedJob.job_type} | Retries: {selectedJob.retry_count}/{selectedJob.max_retries}</p>
              </div>
            </div>
            <button
              onClick={() => setSelectedJob(null)}
              className="text-slate-400 hover:text-slate-600 text-xs font-semibold px-2 py-1 rounded-md"
            >
              Close
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200 text-xs">
              <h4 className="font-semibold text-slate-700 mb-2">Execution Metadata</h4>
              <p><span className="text-slate-500">Stage:</span> {selectedJob.current_stage || 'None'}</p>
              <p><span className="text-slate-500">Progress:</span> {selectedJob.progress_percentage}%</p>
              <p><span className="text-slate-500">Started:</span> {selectedJob.started_at ? new Date(selectedJob.started_at).toLocaleString() : 'N/A'}</p>
              <p><span className="text-slate-500">Completed:</span> {selectedJob.completed_at ? new Date(selectedJob.completed_at).toLocaleString() : 'N/A'}</p>
              <p><span className="text-slate-500">Duration:</span> {selectedJob.execution_duration_seconds ? `${selectedJob.execution_duration_seconds}s` : 'N/A'}</p>
            </div>

            <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200 text-xs">
              <h4 className="font-semibold text-slate-700 mb-2">Status & Output</h4>
              {selectedJob.error_message ? (
                <div className="text-rose-700 bg-rose-50 p-2 rounded-lg border border-rose-200 font-mono text-[11px] overflow-auto max-h-32">
                  <p className="font-bold">Error: {selectedJob.error_category}</p>
                  <p>{selectedJob.error_message}</p>
                </div>
              ) : selectedJob.result ? (
                <pre className="bg-slate-900 text-slate-100 p-2.5 rounded-lg text-[11px] font-mono overflow-auto max-h-32">
                  {JSON.stringify(selectedJob.result, null, 2)}
                </pre>
              ) : (
                <p className="text-slate-400 italic">No output result recorded yet.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
