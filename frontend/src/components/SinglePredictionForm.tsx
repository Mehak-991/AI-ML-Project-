import React, { useState, useEffect } from 'react';
import { Send, AlertTriangle, RefreshCw, Sparkles } from 'lucide-react';
import type { ModelRead, FeaturePrimitive } from '../types/model';

interface SinglePredictionFormProps {
  model: ModelRead;
  onPredict: (record: Record<string, FeaturePrimitive>, allowMissing: boolean) => Promise<void>;
  loading: boolean;
}

export const SinglePredictionForm: React.FC<SinglePredictionFormProps> = ({
  model,
  onPredict,
  loading,
}) => {
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [allowMissing, setAllowMissing] = useState<boolean>(false);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  // Initialize form fields when model changes
  useEffect(() => {
    const initial: Record<string, string> = {};
    model.feature_schema.forEach((f) => {
      initial[f.name] = '';
    });
    setFormData(initial);
    setValidationErrors({});
  }, [model]);

  const handleChange = (fieldName: string, value: string) => {
    setFormData((prev) => ({ ...prev, [fieldName]: value }));
    if (validationErrors[fieldName]) {
      setValidationErrors((prev) => {
        const next = { ...prev };
        delete next[fieldName];
        return next;
      });
    }
  };

  const handleReset = () => {
    const resetData: Record<string, string> = {};
    model.feature_schema.forEach((f) => {
      resetData[f.name] = '';
    });
    setFormData(resetData);
    setValidationErrors({});
  };

  const validateAndSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};
    const recordPayload: Record<string, FeaturePrimitive> = {};

    model.feature_schema.forEach((field) => {
      const rawVal = formData[field.name]?.trim() ?? '';

      if (rawVal === '') {
        if (!allowMissing) {
          errors[field.name] = 'Field is required when missing values are disallowed.';
        } else {
          recordPayload[field.name] = null;
        }
      } else if (field.kind === 'numeric') {
        const numVal = Number(rawVal);
        if (isNaN(numVal) || !isFinite(numVal)) {
          errors[field.name] = 'Must be a valid finite number.';
        } else {
          recordPayload[field.name] = numVal;
        }
      } else {
        recordPayload[field.name] = rawVal;
      }
    });

    if (Object.keys(errors).length > 0) {
      setValidationErrors(errors);
      return;
    }

    setValidationErrors({});
    await onPredict(recordPayload, allowMissing);
  };

  return (
    <form onSubmit={validateAndSubmit} className="space-y-6">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-600" />
            Single Record Input Form
          </h3>
          <p className="text-xs text-slate-500">
            Dynamically generated based on {model.name} feature schema.
          </p>
        </div>

        <button
          type="button"
          onClick={handleReset}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800 transition-colors font-medium px-2.5 py-1 rounded-lg hover:bg-slate-100"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Clear Form
        </button>
      </div>

      {/* Dynamic Form Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {model.feature_schema.map((field) => {
          const hasError = !!validationErrors[field.name];
          const isNumeric = field.kind === 'numeric';

          return (
            <div key={field.name} className="space-y-1.5">
              <label className="flex items-center justify-between text-xs font-semibold text-slate-700">
                <span className="flex items-center gap-1.5 truncate">
                  <span className="truncate">{field.name}</span>
                  {!allowMissing && <span className="text-red-500 font-bold">*</span>}
                </span>
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded font-mono font-medium ${
                    isNumeric ? 'bg-blue-50 text-blue-700' : 'bg-emerald-50 text-emerald-700'
                  }`}
                >
                  {field.kind}
                </span>
              </label>

              <div className="relative">
                <input
                  type={isNumeric ? 'number' : 'text'}
                  step={isNumeric ? 'any' : undefined}
                  value={formData[field.name] ?? ''}
                  onChange={(e) => handleChange(field.name, e.target.value)}
                  placeholder={
                    isNumeric ? 'e.g. 24 or 85.5' : 'e.g. category value'
                  }
                  className={`w-full px-3 py-2 text-xs rounded-xl border bg-slate-50 focus:bg-white focus:outline-none transition-all ${
                    hasError
                      ? 'border-red-300 focus:ring-2 focus:ring-red-500/20 focus:border-red-500 bg-red-50/20'
                      : 'border-slate-200 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500'
                  }`}
                />
              </div>

              {hasError && (
                <p className="text-[11px] text-red-600 flex items-center gap-1 font-medium">
                  <AlertTriangle className="w-3 h-3 shrink-0" />
                  {validationErrors[field.name]}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* Allow Missing Toggle and Submit Action */}
      <div className="pt-4 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <label className="flex items-start sm:items-center gap-2.5 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={allowMissing}
            onChange={(e) => setAllowMissing(e.target.checked)}
            className="mt-0.5 sm:mt-0 rounded text-indigo-600 focus:ring-indigo-500 h-4 w-4 border-slate-300 cursor-pointer"
          />
          <div className="text-xs">
            <span className="font-semibold text-slate-800">
              Allow missing values (Impute missing data)
            </span>
            <p className="text-[11px] text-slate-500">
              When checked, empty values are submitted as null and imputed via the training pipeline.
            </p>
          </div>
        </label>

        <button
          type="submit"
          disabled={loading}
          className="flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all cursor-pointer shrink-0"
        >
          {loading ? (
            <>
              <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Running Prediction...
            </>
          ) : (
            <>
              <Send className="w-3.5 h-3.5" />
              Run Model Prediction
            </>
          )}
        </button>
      </div>
    </form>
  );
};
