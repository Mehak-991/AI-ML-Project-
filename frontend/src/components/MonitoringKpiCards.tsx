import React from 'react';
import {
  Layers,
  Server,
  Activity,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import type {
  HealthReadinessResponse,
  AIServicesStatusResponse,
  MonitoringOverviewResponse,
} from '../types/deployment';

interface MonitoringKpiCardsProps {
  totalTrainedModels: number;
  overview: MonitoringOverviewResponse | null;
  health: HealthReadinessResponse | null;
  aiStatus: AIServicesStatusResponse | null;
  loading: boolean;
}

export const MonitoringKpiCards: React.FC<MonitoringKpiCardsProps> = ({
  totalTrainedModels,
  overview,
  health,
  aiStatus,
  loading,
}) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
      {/* 1. Total Trained Models */}
      <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Trained Models
          </span>
          <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600">
            <Layers className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-3">
          <span className="text-3xl font-extrabold font-mono text-slate-900">
            {loading ? '...' : totalTrainedModels}
          </span>
          <span className="text-xs text-slate-500 ml-2">registered</span>
        </div>
        <p className="text-[11px] text-slate-400 mt-1">Verified via GET /api/v1/models</p>
      </div>

      {/* 2. Total Deployed Models */}
      <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Active Deployments
          </span>
          <div className="p-2 rounded-xl bg-emerald-50 text-emerald-600">
            <Server className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-3 flex items-baseline gap-2">
          <span className="text-3xl font-extrabold font-mono text-emerald-700">
            {overview ? overview.active_deployments : '...'}
          </span>
          <span className="text-xs text-slate-500">
            / {overview ? overview.total_deployments : 0} total
          </span>
        </div>
        <p className="text-[11px] text-emerald-700 font-medium mt-1">
          Managed via /api/v1/deployments
        </p>
      </div>

      {/* 3. Total Predictions Audited */}
      <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Predictions Audited
          </span>
          <div className="p-2 rounded-xl bg-blue-50 text-blue-600">
            <Activity className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-3">
          <span className="text-3xl font-extrabold font-mono text-slate-900">
            {overview ? overview.total_predictions : '...'}
          </span>
          <span className="text-xs text-slate-500 ml-2">in audit log</span>
        </div>
        <p className="text-[11px] text-slate-500 mt-1 font-mono">
          {overview?.total_records_processed ?? 0} total records
        </p>
      </div>

      {/* 4. Successful & Failed Inferences */}
      <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Inference Success
          </span>
          <div className="p-2 rounded-xl bg-emerald-50 text-emerald-600">
            <CheckCircle2 className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-3 flex items-baseline gap-2">
          <span className="text-2xl font-extrabold font-mono text-slate-900">
            {overview ? overview.successful_predictions : 0}
          </span>
          <span className="text-xs text-emerald-600 font-bold">
            ({overview && overview.total_predictions > 0
              ? `${Math.round((overview.successful_predictions / overview.total_predictions) * 100)}%`
              : '100%'})
          </span>
        </div>
        <p className="text-[11px] text-slate-400 mt-1 font-mono">
          Avg latency: {overview?.average_duration_ms ?? 0}ms
        </p>
      </div>

      {/* 5. Live Engine Health */}
      <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Engine Health
          </span>
          <div
            className={`p-2 rounded-xl ${
              health?.status === 'ok' ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'
            }`}
          >
            {health?.status === 'ok' ? (
              <CheckCircle2 className="w-4 h-4" />
            ) : (
              <XCircle className="w-4 h-4" />
            )}
          </div>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <span
            className={`w-2.5 h-2.5 rounded-full ${
              health?.status === 'ok' ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'
            }`}
          />
          <span className="text-xl font-extrabold font-mono text-slate-900 uppercase">
            {health?.status || 'Unknown'}
          </span>
        </div>
        <p className="text-[11px] text-slate-500 mt-1 flex items-center justify-between font-mono">
          <span>DB: {health?.components?.database || 'checking'}</span>
          <span>LLM: {aiStatus?.llm?.provider || 'ollama'}</span>
        </p>
      </div>
    </div>
  );
};
