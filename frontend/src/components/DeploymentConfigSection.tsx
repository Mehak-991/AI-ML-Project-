import React, { useState } from 'react';
import {
  Server,
  Play,
  Square,
  CheckCircle2,
  AlertCircle,
  Clock,
  Layers,
  FileCode,
  ShieldCheck,
  History,
} from 'lucide-react';
import type { ModelRead } from '../types/model';
import type { DeploymentRead, HealthReadinessResponse } from '../types/deployment';

interface DeploymentConfigSectionProps {
  model: ModelRead | null;
  health: HealthReadinessResponse | null;
  activeDeployment: DeploymentRead | null;
  deploymentHistory: DeploymentRead[];
  onDeploy: (modelId: string, env: string) => Promise<void>;
  onUndeploy: (modelId: string) => Promise<void>;
  isActionLoading: boolean;
}

export const DeploymentConfigSection: React.FC<DeploymentConfigSectionProps> = ({
  model,
  health,
  activeDeployment,
  deploymentHistory,
  onDeploy,
  onUndeploy,
  isActionLoading,
}) => {
  const [targetEnv, setTargetEnv] = useState<string>('production');
  const [confirmDialog, setConfirmDialog] = useState<'deploy' | 'undeploy' | null>(null);

  if (!model) {
    return null;
  }

  const isDeployed = activeDeployment?.status === 'Deployed';

  const handleConfirmAction = async () => {
    if (confirmDialog === 'deploy') {
      await onDeploy(model.id, targetEnv);
    } else if (confirmDialog === 'undeploy') {
      await onUndeploy(model.id);
    }
    setConfirmDialog(null);
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-6">
      {/* Header and Lifecycle Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-5">
        <div>
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Server className="w-4 h-4 text-indigo-600" />
            Model Deployment Lifecycle & Configuration
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Manage live deployment states, version tracking, and environment routing for{' '}
            <strong className="text-slate-700">{model.name}</strong>.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {isDeployed ? (
            <button
              type="button"
              onClick={() => setConfirmDialog('undeploy')}
              disabled={isActionLoading}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-200 text-xs font-semibold shadow-2xs transition-all cursor-pointer disabled:opacity-50"
            >
              <Square className="w-3.5 h-3.5 fill-rose-600 text-rose-600" />
              {isActionLoading ? 'Processing...' : 'Undeploy Active Model'}
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <select
                value={targetEnv}
                onChange={(e) => setTargetEnv(e.target.value)}
                className="px-2.5 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:bg-white"
              >
                <option value="production">production</option>
                <option value="staging">staging</option>
                <option value="canary">canary</option>
              </select>
              <button
                type="button"
                onClick={() => setConfirmDialog('deploy')}
                disabled={isActionLoading}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 transition-all cursor-pointer disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5 fill-white" />
                {isActionLoading ? 'Deploying...' : 'Deploy to Production'}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Confirmation Modal Dialog */}
      {confirmDialog && (
        <div className="p-4 rounded-xl border border-amber-200 bg-amber-50 text-amber-900 text-xs space-y-3">
          <div className="flex items-center gap-2 font-bold text-amber-800">
            <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
            {confirmDialog === 'deploy'
              ? `Confirm Deployment for ${model.name}`
              : `Confirm Undeploy for ${model.name}`}
          </div>
          <p className="text-[11px] leading-relaxed">
            {confirmDialog === 'deploy'
              ? `This will create an active deployment configuration in "${targetEnv}" environment and register serving routes in the database.`
              : 'This will retire the active deployment status. Previous deployments will be preserved in deployment history.'}
          </p>
          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={handleConfirmAction}
              className={`px-3 py-1.5 rounded-lg text-white font-semibold text-xs transition-colors ${
                confirmDialog === 'deploy'
                  ? 'bg-indigo-600 hover:bg-indigo-700'
                  : 'bg-rose-600 hover:bg-rose-700'
              }`}
            >
              Confirm {confirmDialog === 'deploy' ? 'Deploy' : 'Undeploy'}
            </button>
            <button
              type="button"
              onClick={() => setConfirmDialog(null)}
              className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-medium text-xs transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Active Deployment Specs Card */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
          <span className="text-[10px] text-slate-400 uppercase font-mono block">
            Deployment Status
          </span>
          <div className="mt-1 flex items-center gap-1.5">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                isDeployed ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'
              }`}
            />
            <span
              className={`font-mono font-bold text-sm ${
                isDeployed ? 'text-emerald-700' : 'text-slate-700'
              }`}
            >
              {activeDeployment ? activeDeployment.status : 'Ready (Undeployed)'}
            </span>
          </div>
          <span className="text-[10px] text-slate-400 block mt-1">
            Version {activeDeployment ? activeDeployment.version : 1}
          </span>
        </div>

        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
          <span className="text-[10px] text-slate-400 uppercase font-mono block">
            Serving Endpoint
          </span>
          <code className="text-xs font-mono font-bold text-indigo-700 mt-1 block truncate">
            {activeDeployment ? activeDeployment.endpoint_url : `/api/v1/models/${model.id}/predict`}
          </code>
          <span className="text-[10px] text-slate-400 block mt-1">Direct inference URL</span>
        </div>

        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
          <span className="text-[10px] text-slate-400 uppercase font-mono block">
            Serving Environment
          </span>
          <span className="font-mono text-slate-800 font-bold text-sm mt-1 block capitalize">
            {activeDeployment ? activeDeployment.environment : targetEnv}
          </span>
          <span className="text-[10px] text-slate-400 block mt-1">Runtime isolation</span>
        </div>

        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
          <span className="text-[10px] text-slate-400 uppercase font-mono block">
            Deployed Timestamp
          </span>
          <span className="font-mono text-slate-800 text-[11px] mt-1.5 block">
            {activeDeployment?.deployed_at
              ? new Date(activeDeployment.deployed_at).toLocaleString()
              : 'Not deployed yet'}
          </span>
        </div>
      </div>

      {/* Deployment History Table */}
      <div className="border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
        <div className="bg-slate-50 px-4 py-2.5 border-b border-slate-200 flex items-center justify-between">
          <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
            <History className="w-3.5 h-3.5 text-indigo-600" />
            Deployment History ({deploymentHistory.length} revisions recorded)
          </span>
          <span className="text-[10px] font-mono text-slate-400">
            Tracked in `deployments` table
          </span>
        </div>

        {deploymentHistory.length === 0 ? (
          <div className="p-6 text-center text-slate-400 text-xs italic">
            No previous deployment revisions for this model.
          </div>
        ) : (
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50/60 border-b border-slate-100 text-slate-600 font-semibold">
              <tr>
                <th className="py-2 px-3">Revision</th>
                <th className="py-2 px-3">Environment</th>
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3">Deployed At</th>
                <th className="py-2 px-3">Undeployed At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white font-mono text-[11px]">
              {deploymentHistory.map((d) => (
                <tr key={d.id} className="hover:bg-slate-50/70">
                  <td className="py-2 px-3 font-bold text-slate-800">rev-{d.version}</td>
                  <td className="py-2 px-3 text-slate-600 capitalize">{d.environment}</td>
                  <td className="py-2 px-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        d.status === 'Deployed'
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      {d.status}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-slate-500">
                    {d.deployed_at ? new Date(d.deployed_at).toLocaleString() : 'N/A'}
                  </td>
                  <td className="py-2 px-3 text-slate-500">
                    {d.undeployed_at ? new Date(d.undeployed_at).toLocaleString() : 'Active / None'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
