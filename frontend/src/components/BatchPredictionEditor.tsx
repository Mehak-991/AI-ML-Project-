import React, { useState, useRef } from 'react';
import { UploadCloud, Plus, Trash2, AlertCircle, FileText, Download } from 'lucide-react';
import type { ModelRead, FeaturePrimitive } from '../types/model';
import { parseCsvToRecords } from '../utils/predictionExport';

interface BatchPredictionEditorProps {
  model: ModelRead;
  onPredictBatch: (
    records: Array<Record<string, FeaturePrimitive>>,
    allowMissing: boolean
  ) => Promise<void>;
  loading: boolean;
}

export const BatchPredictionEditor: React.FC<BatchPredictionEditorProps> = ({
  model,
  onPredictBatch,
  loading,
}) => {
  const [rows, setRows] = useState<Array<Record<string, string>>>(() => {
    // Start with 2 empty rows
    const createEmpty = () => {
      const r: Record<string, string> = {};
      model.feature_schema.forEach((f) => {
        r[f.name] = '';
      });
      return r;
    };
    return [createEmpty(), createEmpty()];
  });

  const [allowMissing, setAllowMissing] = useState<boolean>(false);
  const [errorMessages, setErrorMessages] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleCellChange = (rowIndex: number, fieldName: string, val: string) => {
    setRows((prev) => {
      const copy = [...prev];
      copy[rowIndex] = { ...copy[rowIndex], [fieldName]: val };
      return copy;
    });
  };

  const handleAddRow = () => {
    const emptyRow: Record<string, string> = {};
    model.feature_schema.forEach((f) => {
      emptyRow[f.name] = '';
    });
    setRows((prev) => [...prev, emptyRow]);
  };

  const handleRemoveRow = (index: number) => {
    if (rows.length <= 1) return;
    setRows((prev) => prev.filter((_, idx) => idx !== index));
  };

  const handleClearAll = () => {
    const emptyRow: Record<string, string> = {};
    model.feature_schema.forEach((f) => {
      emptyRow[f.name] = '';
    });
    setRows([emptyRow]);
    setErrorMessages([]);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      if (!text) return;

      const parsed = parseCsvToRecords(text, model.feature_schema);
      if (parsed.errors.length > 0) {
        setErrorMessages(parsed.errors);
      } else {
        setErrorMessages([]);
      }

      if (parsed.records.length > 0) {
        const stringifiedRows = parsed.records.map((rec) => {
          const strRow: Record<string, string> = {};
          model.feature_schema.forEach((f) => {
            const v = rec[f.name];
            strRow[f.name] = v === null || v === undefined ? '' : String(v);
          });
          return strRow;
        });
        setRows(stringifiedRows);
      }
    };
    reader.readAsText(file);
    // Reset file input value
    e.target.value = '';
  };

  const downloadSampleTemplate = () => {
    const headers = model.feature_schema.map((f) => f.name).join(',');
    const sampleRow = model.feature_schema
      .map((f) => (f.kind === 'numeric' ? '10' : 'category_val'))
      .join(',');
    const csv = `${headers}\r\n${sampleRow}\r\n`;
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `template_${model.name.toLowerCase().replace(/\s+/g, '_')}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleSubmit = async () => {
    const validationErrors: string[] = [];
    const validRecords: Array<Record<string, FeaturePrimitive>> = [];

    rows.forEach((row, rowIdx) => {
      const record: Record<string, FeaturePrimitive> = {};
      let rowHasInvalidValue = false;

      model.feature_schema.forEach((field) => {
        const val = row[field.name]?.trim() ?? '';
        if (val === '') {
          if (!allowMissing) {
            validationErrors.push(`Row ${rowIdx + 1}: "${field.name}" is required.`);
            rowHasInvalidValue = true;
          } else {
            record[field.name] = null;
          }
        } else if (field.kind === 'numeric') {
          const num = Number(val);
          if (isNaN(num) || !isFinite(num)) {
            validationErrors.push(
              `Row ${rowIdx + 1}: "${field.name}" must be a number (received "${val}").`
            );
            rowHasInvalidValue = true;
          } else {
            record[field.name] = num;
          }
        } else {
          record[field.name] = val;
        }
      });

      if (!rowHasInvalidValue) {
        validRecords.push(record);
      }
    });

    if (validationErrors.length > 0) {
      setErrorMessages(validationErrors.slice(0, 8));
      return;
    }

    if (validRecords.length === 0) {
      setErrorMessages(['At least one valid record must be entered.']);
      return;
    }

    setErrorMessages([]);
    await onPredictBatch(validRecords, allowMissing);
  };

  return (
    <div className="space-y-5">
      {/* Top action row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <FileText className="w-4 h-4 text-indigo-600" />
            Batch Records Table Editor & CSV Importer
          </h3>
          <p className="text-xs text-slate-500">
            Enter multiple records manually or import a matching CSV file ({rows.length} rows staged).
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={downloadSampleTemplate}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors"
          >
            <Download className="w-3.5 h-3.5 text-slate-500" />
            CSV Template
          </button>

          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            accept=".csv"
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-900 text-white text-xs font-semibold transition-colors"
          >
            <UploadCloud className="w-3.5 h-3.5" />
            Import CSV
          </button>
        </div>
      </div>

      {/* Validation alert banner if any */}
      {errorMessages.length > 0 && (
        <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs space-y-1">
          <div className="flex items-center gap-2 font-semibold">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            Validation Issues ({errorMessages.length})
          </div>
          <ul className="list-disc list-inside space-y-0.5 text-[11px] pl-1">
            {errorMessages.map((msg, i) => (
              <li key={i}>{msg}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Structured Table Editor */}
      <div className="border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
        <div className="max-h-72 overflow-x-auto overflow-y-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold sticky top-0 z-10">
              <tr>
                <th className="py-2.5 px-3 w-12 text-center">#</th>
                {model.feature_schema.map((f) => (
                  <th key={f.name} className="py-2.5 px-3 min-w-[140px]">
                    <div className="flex items-center justify-between gap-1">
                      <span className="truncate">{f.name}</span>
                      <span
                        className={`text-[9px] px-1 py-0.2 rounded font-mono uppercase ${
                          f.kind === 'numeric'
                            ? 'bg-blue-50 text-blue-700'
                            : 'bg-emerald-50 text-emerald-700'
                        }`}
                      >
                        {f.kind}
                      </span>
                    </div>
                  </th>
                ))}
                <th className="py-2.5 px-3 w-12 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {rows.map((row, rowIdx) => (
                <tr key={rowIdx} className="hover:bg-slate-50/70 transition-colors">
                  <td className="py-2 px-3 text-center text-slate-400 font-mono text-[11px]">
                    {rowIdx + 1}
                  </td>
                  {model.feature_schema.map((f) => {
                    const isNumeric = f.kind === 'numeric';
                    return (
                      <td key={f.name} className="py-1 px-2">
                        <input
                          type={isNumeric ? 'number' : 'text'}
                          step={isNumeric ? 'any' : undefined}
                          value={row[f.name] ?? ''}
                          onChange={(e) => handleCellChange(rowIdx, f.name, e.target.value)}
                          placeholder={isNumeric ? '0' : 'text'}
                          className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white"
                        />
                      </td>
                    );
                  })}
                  <td className="py-2 px-3 text-center">
                    <button
                      type="button"
                      onClick={() => handleRemoveRow(rowIdx)}
                      disabled={rows.length <= 1}
                      title="Remove row"
                      className="p-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50 disabled:opacity-30 disabled:hover:text-slate-400 disabled:hover:bg-transparent transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Table footer action bar */}
        <div className="bg-slate-50 px-4 py-2.5 border-t border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleAddRow}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-200 hover:bg-slate-100 text-slate-700 text-xs font-semibold shadow-2xs transition-colors"
            >
              <Plus className="w-3.5 h-3.5 text-indigo-600" />
              Add Record Row
            </button>
            <button
              type="button"
              onClick={handleClearAll}
              className="text-xs text-slate-500 hover:text-slate-700 font-medium px-2 py-1 transition-colors"
            >
              Clear Table
            </button>
          </div>

          <span className="text-[11px] font-mono text-slate-500">
            Total Staged: {rows.length} {rows.length === 1 ? 'record' : 'records'}
          </span>
        </div>
      </div>

      {/* Bottom controls & batch prediction button */}
      <div className="pt-2 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <label className="flex items-start sm:items-center gap-2.5 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={allowMissing}
            onChange={(e) => setAllowMissing(e.target.checked)}
            className="mt-0.5 sm:mt-0 rounded text-indigo-600 focus:ring-indigo-500 h-4 w-4 border-slate-300 cursor-pointer"
          />
          <div className="text-xs">
            <span className="font-semibold text-slate-800">
              Allow missing values (Impute missing features)
            </span>
            <p className="text-[11px] text-slate-500">
              Empty cells will be sent as null and imputed automatically during preprocessing.
            </p>
          </div>
        </label>

        <button
          type="button"
          onClick={handleSubmit}
          disabled={loading || rows.length === 0}
          className="flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-md shadow-indigo-600/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all cursor-pointer shrink-0"
        >
          {loading ? (
            <>
              <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Processing Batch ({rows.length} records)...
            </>
          ) : (
            <>
              Run Batch Inference ({rows.length} records)
            </>
          )}
        </button>
      </div>
    </div>
  );
};
