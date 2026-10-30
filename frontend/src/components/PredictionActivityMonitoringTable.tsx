import React, { useState } from 'react';
import {
  Activity,
  Search,
  Filter,
  FileQuestion,
  Info,
  Calendar,
  Layers,
  CheckCircle2,
} from 'lucide-react';
import type { ModelRead } from '../types/model';

interface PredictionActivityMonitoringTableProps {
  models: ModelRead[];
}

export const PredictionActivityMonitoringTable: React.FC<
  PredictionActivityMonitoringTableProps
> = ({ models }) => {
  const [searchTerm, setSearchTerm] = useState('');

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
        <div>
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-600" />
            Prediction Activity & Inference Audit Log
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Continuous auditing of inference requests, execution latency, and prediction outcomes.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Filter audit log..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              disabled
              className="pl-8 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-xl opacity-60 cursor-not-allowed"
            />
          </div>
        </div>
      </div>

      {/* Backend Reality Notice */}
      <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center space-y-3">
        <div className="w-12 h-12 rounded-2xl bg-slate-100 text-slate-500 flex items-center justify-center mx-auto">
          <FileQuestion className="w-6 h-6" />
        </div>
        <div className="max-w-md mx-auto">
          <h4 className="text-sm font-bold text-slate-800">
            Prediction History API: Data Unavailable
          </h4>
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">
            The FastAPI backend currently serves predictions statelessly and does not persist inference requests, execution outcomes, or request records to a database table.
          </p>
          <div className="mt-4 p-3 rounded-xl bg-white border border-slate-200 text-left text-xs space-y-1.5">
            <div className="flex items-center gap-2 text-indigo-600 font-semibold text-[11px]">
              <Info className="w-3.5 h-3.5 shrink-0" />
              Verified Backend API Surface
            </div>
            <p className="text-slate-600 text-[11px]">
              Inspected routers <code className="bg-slate-100 px-1 py-0.5 rounded font-mono">app/api/routes/models.py</code> and <code className="bg-slate-100 px-1 py-0.5 rounded font-mono">root.py</code>. No <code className="bg-slate-100 px-1 py-0.5 rounded font-mono">/api/v1/predictions</code> or audit logging endpoints exist.
            </p>
          </div>
        </div>
      </div>

      {/* Available Runtime Ingestion Points */}
      <div className="border border-slate-200 rounded-xl p-4 bg-white space-y-2">
        <span className="text-xs font-bold text-slate-800 block">
          Models Available for Immediate Inference (GET /api/v1/models):
        </span>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {models.map((m) => (
            <div
              key={m.id}
              className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-between text-xs"
            >
              <div className="flex items-center gap-2 truncate">
                <Layers className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
                <span className="font-semibold text-slate-800 truncate">{m.name}</span>
                <span className="text-[10px] font-mono text-slate-400">v{m.version}</span>
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 shrink-0">
                Live Serving
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
