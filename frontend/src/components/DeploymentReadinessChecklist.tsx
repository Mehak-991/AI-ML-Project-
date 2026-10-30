import React from 'react';
import {
  CheckCircle2,
  XCircle,
  HelpCircle,
  ShieldCheck,
  Cpu,
  Layers,
  FileCode,
  Activity,
  BarChart,
  HardDrive,
} from 'lucide-react';
import type { ReadinessCheckItem, ReadinessCheckStatus } from '../types/deployment';

interface DeploymentReadinessChecklistProps {
  checks: ReadinessCheckItem[];
  modelName: string;
  version: number;
  overallReady: boolean;
  onProbeInference?: () => void;
  isProbing?: boolean;
}

export const DeploymentReadinessChecklist: React.FC<DeploymentReadinessChecklistProps> = ({
  checks,
  modelName,
  version,
  overallReady,
  onProbeInference,
  isProbing = false,
}) => {
  const verifiedCount = checks.filter((c) => c.status === 'Verified').length;
  const notVerifiedCount = checks.filter((c) => c.status === 'Not Verified').length;
  const unavailableCount = checks.filter((c) => c.status === 'Data Unavailable').length;

  const getStatusBadge = (status: ReadinessCheckStatus) => {
    switch (status) {
      case 'Verified':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            Verified
          </span>
        );
      case 'Not Verified':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <XCircle className="w-3 h-3 text-rose-600" />
            Not Verified
          </span>
        );
      case 'Data Unavailable':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
            <HelpCircle className="w-3 h-3 text-slate-400" />
            Data Unavailable
          </span>
        );
    }
  };

  const getCategoryIcon = (category: ReadinessCheckItem['category']) => {
    switch (category) {
      case 'artifact':
        return <HardDrive className="w-4 h-4 text-indigo-500" />;
      case 'schema':
        return <FileCode className="w-4 h-4 text-blue-500" />;
      case 'runtime':
        return <Activity className="w-4 h-4 text-emerald-500" />;
      case 'metrics':
        return <BarChart className="w-4 h-4 text-amber-500" />;
      default:
        return <Layers className="w-4 h-4 text-slate-400" />;
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-6">
      {/* Header and summary status */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                Production Deployment Readiness Checklist
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Evaluated against stored ML artifacts, schemas, runtime endpoints, and metadata for{' '}
                <strong className="text-slate-700">{modelName}</strong> (v{version}).
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {onProbeInference && (
            <button
              type="button"
              onClick={onProbeInference}
              disabled={isProbing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-xs font-semibold text-slate-700 transition-colors cursor-pointer disabled:opacity-50"
            >
              <Cpu className="w-3.5 h-3.5 text-indigo-600" />
              {isProbing ? 'Probing Endpoint...' : 'Re-verify Predict Endpoint'}
            </button>
          )}

          <div
            className={`px-3.5 py-1.5 rounded-xl border text-xs font-bold flex items-center gap-2 ${
              overallReady
                ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                : 'bg-amber-50 text-amber-800 border-amber-200'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                overallReady ? 'bg-emerald-500' : 'bg-amber-500'
              }`}
            />
            {overallReady ? 'Eligible for Production Inference' : 'Pre-flight Incomplete'}
          </div>
        </div>
      </div>

      {/* Summary KPI Pills */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="flex items-center justify-between p-3 rounded-xl bg-emerald-50/60 border border-emerald-100">
          <span className="text-xs font-medium text-emerald-800">Verified Checks</span>
          <span className="font-mono font-bold text-sm text-emerald-900">
            {verifiedCount} / {checks.length}
          </span>
        </div>
        <div className="flex items-center justify-between p-3 rounded-xl bg-rose-50/60 border border-rose-100">
          <span className="text-xs font-medium text-rose-800">Not Verified</span>
          <span className="font-mono font-bold text-sm text-rose-900">{notVerifiedCount}</span>
        </div>
        <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-200">
          <span className="text-xs font-medium text-slate-600">Data Unavailable</span>
          <span className="font-mono font-bold text-sm text-slate-700">{unavailableCount}</span>
        </div>
      </div>

      {/* Checklist Table */}
      <div className="border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
        <table className="w-full text-xs text-left">
          <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold">
            <tr>
              <th className="py-2.5 px-4 w-12 text-center">Category</th>
              <th className="py-2.5 px-4 min-w-[200px]">Readiness Item</th>
              <th className="py-2.5 px-4 w-36">Evaluation Status</th>
              <th className="py-2.5 px-4 min-w-[280px]">Observed Evidence & Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {checks.map((item) => (
              <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                <td className="py-3 px-4 text-center">
                  <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center mx-auto" title={item.category}>
                    {getCategoryIcon(item.category)}
                  </div>
                </td>
                <td className="py-3 px-4">
                  <span className="font-semibold text-slate-800 block">{item.label}</span>
                  <span className="text-[11px] text-slate-500 block mt-0.5">{item.details}</span>
                </td>
                <td className="py-3 px-4">{getStatusBadge(item.status)}</td>
                <td className="py-3 px-4">
                  {item.evidence ? (
                    <div className="font-mono text-[11px] text-slate-700 bg-slate-50 p-1.5 rounded border border-slate-200/80 break-all">
                      {item.evidence}
                    </div>
                  ) : (
                    <span className="text-slate-400 italic text-[11px]">
                      No empirical evidence recorded by backend.
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
