import React from 'react';
import {
  Server,
  AlertTriangle,
  Code2,
} from 'lucide-react';
import type { ModelRead } from '../types/model';
import type { HealthReadinessResponse } from '../types/deployment';

interface DeploymentConfigSectionProps {
  model: ModelRead | null;
  health: HealthReadinessResponse | null;
}

export const DeploymentConfigSection: React.FC<DeploymentConfigSectionProps> = ({
  model,
  health,
}) => {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
        <div>
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Server className="w-4 h-4 text-indigo-600" />
            Runtime Configuration & Production Deployment Architecture
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Backend runtime architecture inspection and endpoint operational parameters.
          </p>
        </div>

        <div className="px-3 py-1 rounded-xl bg-slate-100 text-slate-700 font-mono text-xs flex items-center gap-1.5 self-start sm:self-auto">
          <span>Env:</span>
          <strong className="text-slate-900 capitalize">{health?.environment || 'development'}</strong>
        </div>
      </div>

      {/* Backend Architecture Reality Callout */}
      <div className="p-4 rounded-xl bg-amber-50/80 border border-amber-200 text-amber-900 text-xs space-y-2">
        <div className="flex items-center gap-2 font-bold text-amber-800">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          Production Deployment Architecture Reality: Dynamic Disk Loading
        </div>
        <p className="text-amber-800 leading-relaxed text-[11px]">
          The FastAPI backend follows a <strong>stateless on-demand model serving architecture</strong>. All models saved to the database (and written to disk in <code className="bg-amber-100 px-1 py-0.5 rounded font-mono">trained_models/</code>) are immediately accessible for inference via <code className="bg-amber-100 px-1 py-0.5 rounded font-mono">POST /api/v1/models/{'{model_id}'}/predict</code>.
        </p>
        <p className="text-amber-800 leading-relaxed text-[11px]">
          Dedicated deployment lifecycles (e.g. <code className="bg-amber-100 px-1 py-0.5 rounded font-mono">POST /deploy</code>, Canary releases, Blue-Green traffic routing, or model decommissioning endpoints) <strong>do not exist in the current backend API contract</strong>. In strict compliance with guidelines, no false deployment simulation is applied.
        </p>
      </div>

      {/* Active Serving Specifications */}
      {model && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
            <span className="text-[10px] text-slate-400 uppercase font-semibold block">
              Inference Endpoint URL
            </span>
            <code className="text-xs font-mono font-bold text-indigo-700 mt-1 block truncate">
              POST /api/v1/models/{model.id}/predict
            </code>
            <span className="text-[10px] text-slate-500 mt-1 block">
              Direct live inference URL
            </span>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
            <span className="text-[10px] text-slate-400 uppercase font-semibold block">
              Artifact Persistence & Compatibility
            </span>
            <span className="font-mono text-slate-800 font-semibold mt-1 block truncate">
              scikit-learn {model.sklearn_version}
            </span>
            <span className="text-[10px] text-slate-500 mt-1 block">
              Strict checksum & version verification
            </span>
          </div>

          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
            <span className="text-[10px] text-slate-400 uppercase font-semibold block">
              Serving Constraints
            </span>
            <span className="font-mono text-slate-800 font-semibold mt-1 block">
              Max 1,000 records / req
            </span>
            <span className="text-[10px] text-slate-500 mt-1 block">
              Non-blocking FastAPI threadpool
            </span>
          </div>
        </div>
      )}

      {/* Technical Proposal for Deployment Endpoints */}
      <div className="border border-slate-200 rounded-xl p-4 bg-slate-50/50 space-y-3 text-xs">
        <div className="flex items-center justify-between">
          <span className="font-bold text-slate-800 flex items-center gap-1.5">
            <Code2 className="w-4 h-4 text-indigo-600" />
            Backend Gap Analysis: Proposed Deployment API Endpoints
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-200 text-slate-700">
            RFC Proposal
          </span>
        </div>

        <p className="text-[11px] text-slate-600">
          To transition from on-demand disk execution to formal enterprise deployment states, the following backend endpoints and schema migrations are recommended:
        </p>

        <div className="space-y-2 text-[11px] font-mono">
          <div className="p-2 rounded bg-white border border-slate-200 flex items-center justify-between">
            <div>
              <span className="text-emerald-700 font-bold">POST</span> /api/v1/models/{'{id}'}/deploy
              <span className="text-slate-500 font-sans ml-2">— Activate model to production memory pool with traffic %</span>
            </div>
            <span className="text-rose-600 font-sans text-[10px] font-bold">Missing</span>
          </div>
          <div className="p-2 rounded bg-white border border-slate-200 flex items-center justify-between">
            <div>
              <span className="text-amber-700 font-bold">POST</span> /api/v1/models/{'{id}'}/undeploy
              <span className="text-slate-500 font-sans ml-2">— Retire model artifact from serving routes</span>
            </div>
            <span className="text-rose-600 font-sans text-[10px] font-bold">Missing</span>
          </div>
          <div className="p-2 rounded bg-white border border-slate-200 flex items-center justify-between">
            <div>
              <span className="text-blue-700 font-bold">GET</span> /api/v1/predictions/history
              <span className="text-slate-500 font-sans ml-2">— Paginated table of live prediction executions and request latency</span>
            </div>
            <span className="text-rose-600 font-sans text-[10px] font-bold">Missing</span>
          </div>
        </div>
      </div>
    </div>
  );
};
