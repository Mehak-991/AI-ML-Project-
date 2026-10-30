import React, { useState, useRef } from 'react';
import {
  Upload,
  FileSpreadsheet,
  AlertCircle,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  X,
} from 'lucide-react';
import { datasetApi, parseApiError, type ErrorDetails } from '../services/api';
import type { DatasetCreateResponse } from '../types/dataset';

interface DatasetUploadCardProps {
  onUploadSuccess: (created: DatasetCreateResponse) => void;
}

export const DatasetUploadCard: React.FC<DatasetUploadCardProps> = ({ onUploadSuccess }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [datasetName, setDatasetName] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [errorDetails, setErrorDetails] = useState<ErrorDetails | null>(null);
  const [lastValidationResult, setLastValidationResult] = useState<DatasetCreateResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
  };

  const getFileFormat = (fileName: string): string => {
    const ext = fileName.split('.').pop()?.toUpperCase() || '';
    return ext === 'CSV' || ext === 'XLSX' ? ext : 'UNKNOWN';
  };

  const handleFileSelect = (file: File) => {
    setErrorDetails(null);
    setLastValidationResult(null);

    const ext = file.name.split('.').pop()?.toLowerCase();
    if (ext !== 'csv' && ext !== 'xlsx') {
      setErrorDetails({
        status: 415,
        code: 'UNSUPPORTED_MEDIA_TYPE',
        message: 'Only CSV (.csv) and Excel (.xlsx) file formats are accepted.',
      });
      setSelectedFile(null);
      return;
    }

    // Default 25 MB limit client-side advisory check
    if (file.size > 25 * 1024 * 1024) {
      setErrorDetails({
        status: 413,
        code: 'PAYLOAD_TOO_LARGE',
        message: `File size (${formatFileSize(file.size)}) exceeds server limit of 25 MB.`,
      });
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
    if (!datasetName.trim()) {
      // Suggest default name without file extension
      const baseName = file.name.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ');
      setDatasetName(baseName.charAt(0).toUpperCase() + baseName.slice(1));
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setDatasetName('');
    setErrorDetails(null);
    setUploadProgress(0);
    setUploading(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;

    setUploading(true);
    setErrorDetails(null);
    setUploadProgress(0);

    try {
      const response = await datasetApi.uploadDataset(
        selectedFile,
        datasetName.trim() || undefined,
        (progress) => {
          setUploadProgress(progress.percentage);
        }
      );

      setLastValidationResult(response);
      onUploadSuccess(response);
      // Reset file selection after successful registration
      setSelectedFile(null);
      setDatasetName('');
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err: unknown) {
      const parsed = parseApiError(err);
      setErrorDetails(parsed);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl relative overflow-hidden">
      {/* Decorative background glow */}
      <div className="absolute top-0 right-0 w-80 h-80 bg-blue-500/5 rounded-full blur-3xl pointer-events-none" />

      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Upload className="w-5 h-5 text-blue-400" />
            Upload & Register Dataset
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Upload CSV or XLSX datasets. Automatic schema detection, type inference & data validation.
          </p>
        </div>
        <span className="text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
          Max: 25 MB
        </span>
      </div>

      <form onSubmit={handleUpload} className="mt-6 space-y-5">
        {/* Dataset Name Input */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1.5">
            Dataset Name <span className="text-slate-500 font-normal">(optional alias)</span>
          </label>
          <input
            type="text"
            value={datasetName}
            onChange={(e) => setDatasetName(e.target.value)}
            placeholder="e.g. Customer Churn Q3 2026"
            maxLength={255}
            disabled={uploading}
            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 text-sm transition-all disabled:opacity-50"
          />
        </div>

        {/* Drag and Drop Zone */}
        {!selectedFile ? (
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all flex flex-col items-center justify-center gap-3 ${
              isDragging
                ? 'border-blue-500 bg-blue-500/10 scale-[1.01]'
                : 'border-slate-800 hover:border-slate-700 bg-slate-950/50 hover:bg-slate-950'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx"
              className="hidden"
              onChange={(e) => {
                if (e.target.files && e.target.files.length > 0) {
                  handleFileSelect(e.target.files[0]);
                }
              }}
            />
            <div className="w-14 h-14 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 group-hover:scale-110 transition-transform">
              <FileSpreadsheet className="w-7 h-7" />
            </div>
            <div>
              <p className="text-sm font-medium text-white">
                Click to browse or drag & drop dataset file
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Accepted formats: <span className="text-slate-300 font-semibold">.CSV</span> (UTF-8) or{' '}
                <span className="text-slate-300 font-semibold">.XLSX</span>
              </p>
            </div>
          </div>
        ) : (
          /* File Preview Card Before Upload */
          <div className="bg-slate-950 border border-slate-800 rounded-2xl p-5 relative">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3.5">
                <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 shrink-0">
                  <FileSpreadsheet className="w-6 h-6" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-white break-all">{selectedFile.name}</h4>
                  <div className="flex items-center gap-2 mt-1 text-xs text-slate-400">
                    <span className="px-2 py-0.5 rounded bg-blue-950/60 text-blue-400 border border-blue-800/40 font-mono font-medium">
                      {getFileFormat(selectedFile.name)}
                    </span>
                    <span>•</span>
                    <span>{formatFileSize(selectedFile.size)}</span>
                  </div>
                </div>
              </div>

              {!uploading && (
                <button
                  type="button"
                  onClick={handleReset}
                  className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
                  title="Remove file"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Upload Progress Bar */}
            {uploading && (
              <div className="mt-4 pt-4 border-t border-slate-800">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
                  <span className="flex items-center gap-1.5">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400" />
                    Uploading and parsing file...
                  </span>
                  <span className="font-mono font-semibold text-blue-400">{uploadProgress}%</span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-blue-600 to-indigo-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Action Controls */}
        <div className="flex items-center justify-end gap-3 pt-2">
          {selectedFile && (
            <button
              type="button"
              onClick={handleReset}
              disabled={uploading}
              className="px-4 py-2.5 text-sm text-slate-400 hover:text-white transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
          )}

          <button
            type="submit"
            disabled={!selectedFile || uploading}
            className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 active:bg-blue-700 disabled:opacity-50 disabled:pointer-events-none transition-all shadow-lg shadow-blue-600/20"
          >
            {uploading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Uploading Dataset...
              </>
            ) : (
              <>
                <Upload className="w-4 h-4" />
                Upload & Register
              </>
            )}
          </button>
        </div>
      </form>

      {/* Error Feedback */}
      {errorDetails && (
        <div className="mt-5 p-4 rounded-xl bg-red-950/40 border border-red-800/60 text-red-300 text-sm flex items-start gap-3 animate-fadeIn">
          <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-red-200">
                {errorDetails.status ? `Error ${errorDetails.status} (${errorDetails.code})` : 'Error'}
              </span>
            </div>
            <p className="mt-0.5 text-red-300/90 text-sm">{errorDetails.message}</p>
            {errorDetails.details !== undefined && errorDetails.details !== null && (
              <pre className="mt-2 p-2 bg-red-950/80 rounded border border-red-900/50 text-xs overflow-x-auto text-red-200 font-mono">
                {typeof errorDetails.details === 'string'
                  ? errorDetails.details
                  : JSON.stringify(errorDetails.details, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}

      {/* Validation Result Box */}
      {lastValidationResult && (
        <div className="mt-5 p-4 rounded-xl bg-slate-950 border border-slate-800 animate-fadeIn">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              {lastValidationResult.validation.is_valid ? (
                <div className="flex items-center gap-1.5 text-emerald-400 font-semibold text-sm">
                  <CheckCircle2 className="w-4 h-4" />
                  Dataset Validated & Registered Successfully
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-amber-400 font-semibold text-sm">
                  <AlertTriangle className="w-4 h-4" />
                  Dataset Registered with Validation Warnings
                </div>
              )}
            </div>
            <span className="text-xs font-mono text-slate-400">
              ID: {lastValidationResult.dataset.id.slice(0, 8)}...
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3 text-xs">
            <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800/80">
              <span className="text-slate-400 block">Rows</span>
              <span className="text-white font-mono font-bold text-sm">
                {lastValidationResult.dataset.n_rows.toLocaleString()}
              </span>
            </div>
            <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800/80">
              <span className="text-slate-400 block">Columns</span>
              <span className="text-white font-mono font-bold text-sm">
                {lastValidationResult.dataset.n_columns}
              </span>
            </div>
            <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800/80">
              <span className="text-slate-400 block">Format</span>
              <span className="text-white font-mono font-bold text-sm uppercase">
                {lastValidationResult.dataset.file_format}
              </span>
            </div>
            <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800/80">
              <span className="text-slate-400 block">Status</span>
              <span
                className={`font-semibold text-sm ${
                  lastValidationResult.validation.is_valid ? 'text-emerald-400' : 'text-amber-400'
                }`}
              >
                {lastValidationResult.validation.is_valid ? 'Valid' : 'Has Warnings'}
              </span>
            </div>
          </div>

          {/* Errors list */}
          {lastValidationResult.validation.errors && lastValidationResult.validation.errors.length > 0 && (
            <div className="mt-3 space-y-1.5">
              <p className="text-xs font-semibold text-red-400 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5" /> Errors:
              </p>
              {lastValidationResult.validation.errors.map((err, idx) => (
                <div
                  key={idx}
                  className="text-xs bg-red-950/40 border border-red-900/50 p-2 rounded text-red-300 flex items-start gap-2"
                >
                  <span className="font-mono text-red-400 font-bold">[{err.code}]</span>
                  <span>{err.message}</span>
                  {err.column && (
                    <span className="ml-auto font-mono text-[10px] bg-red-900/40 px-1.5 py-0.5 rounded text-red-200">
                      col: {err.column}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Warnings list */}
          {lastValidationResult.validation.warnings && lastValidationResult.validation.warnings.length > 0 && (
            <div className="mt-3 space-y-1.5">
              <p className="text-xs font-semibold text-amber-400 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" /> Validation Warnings ({lastValidationResult.validation.warnings.length}):
              </p>
              {lastValidationResult.validation.warnings.map((warn, idx) => (
                <div
                  key={idx}
                  className="text-xs bg-amber-950/30 border border-amber-900/50 p-2 rounded text-amber-300 flex items-start gap-2"
                >
                  <span className="font-mono text-amber-400 font-bold">[{warn.code}]</span>
                  <span>{warn.message}</span>
                  {warn.column && (
                    <span className="ml-auto font-mono text-[10px] bg-amber-900/40 px-1.5 py-0.5 rounded text-amber-200">
                      col: {warn.column}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
