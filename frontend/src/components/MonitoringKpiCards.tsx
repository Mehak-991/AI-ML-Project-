import React from 'react';
import {
  Layers,
  Server,
  Activity,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import type { HealthReadinessResponse, AIServicesStatusResponse } from '../types/deployment';

interface MonitoringKpiCardsProps {
  totalTrainedModels: number;
  health: HealthReadinessResponse | null;
  aiStatus: AIServicesStatusResponse | null;
  loading: boolean;
}

export const MonitoringKpiCards: React.FC<MonitoringKpiCardsProps> = ({
  totalTrainedModels,
  health,
  aiStatus,
  loading,
}) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
      {/* 1. Total Trained Models (Real API count) */}
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
          <span className="text-xs text-slate-500 ml-2">in registry</span>
        </div>
        <p className="text-[11px] text-slate-400 mt-1">Verified via GET /api/v1/models</p>
      </div>

      {/* 2. Total Deployed Models (Empirical status - No dedicated deploy endpoint) */}
      <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Deployed Models
          </span>
          <div className="p-2 rounded-xl bg-amber-50 text-amber-600">
            <Server className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-3">
          <span className="text-lg font-bold font-mono text-slate-800">
            On-Demand Runtime
          </span>
        </div>
        <p className="text-[11px] text-amber-700 bg-amber-50 px-2 py-0.5 rounded mt-2 inline-block">
          No dedicated deployment table
        </p>
      </div>

      {/* 3. Total Predictions (Historical monitoring table missing) */}
      <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Total Predictions
          </span>
          <div className="p-2 rounded-xl bg-slate-100 text-slate-600">
            <Activity className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-3">
          <span className="text-base font-bold font-mono text-slate-600 italic">
            Data Unavailable
          </span>
        </div>
        <p className="text-[11px] text-slate-400 mt-2">
          No prediction-history API endpoint
        </p>
      </div>

      {/* 4. Successful / Failed Predictions (Real-time telemetry missing) */}
      <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Prediction Telemetry
          </span>
          <div className="p-2 rounded-xl bg-slate-100 text-slate-600">
            <CheckCircle2 className="w-4 h-4" />
          </div>
        </div>
        <div className="mt-3">
          <span className="text-base font-bold font-mono text-slate-600 italic">
            Data Unavailable
          </span>
        </div>
        <p className="text-[11px] text-slate-400 mt-2">
          Backend lacks logging database
        </p>
      </div>

      {/* 5. Live Server Readiness (Verified via GET /api/v1/health) */}
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
