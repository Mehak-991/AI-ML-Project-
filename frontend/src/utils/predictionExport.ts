import type { FeaturePrimitive, PredictionResultItem } from '../types/model';

/**
 * Escapes a cell value for standard CSV compatibility (RFC 4180).
 */
function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  const str = String(value);
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

/**
 * Exports prediction results to a client-side CSV file.
 * Handles input features, predicted output, class probabilities, and timestamps.
 */
export function exportPredictionsToCsv(
  results: PredictionResultItem[],
  featureNames: string[],
  modelName: string,
  modelId: string,
  classLabels?: Array<string | number | boolean> | null
): void {
  if (!results || results.length === 0) {
    return;
  }

  // Determine probability columns
  const probKeys = new Set<string>();
  results.forEach((r) => {
    if (r.probabilities) {
      Object.keys(r.probabilities).forEach((k) => probKeys.add(k));
    }
  });
  const sortedProbKeys = Array.from(probKeys).sort();

  // CSV Headers
  const headers: string[] = [
    'record_index',
    'timestamp',
    'model_name',
    'model_id',
    ...featureNames.map((f) => `feature_${f}`),
    'prediction',
    'predicted_label',
    ...sortedProbKeys.map((k) => `prob_class_${k}`),
  ];

  // Map each record to row
  const rows = results.map((item) => {
    let predictedLabel = String(item.prediction);
    if (classLabels && typeof item.prediction === 'number' && classLabels[item.prediction] !== undefined) {
      predictedLabel = String(classLabels[item.prediction]);
    }

    const featureValues = featureNames.map((f) => escapeCsvCell(item.input[f] ?? ''));
    const probValues = sortedProbKeys.map((k) =>
      item.probabilities && item.probabilities[k] !== undefined
        ? escapeCsvCell(item.probabilities[k])
        : ''
    );

    return [
      escapeCsvCell(item.index + 1),
      escapeCsvCell(item.timestamp),
      escapeCsvCell(modelName),
      escapeCsvCell(modelId),
      ...featureValues,
      escapeCsvCell(item.prediction),
      escapeCsvCell(predictedLabel),
      ...probValues,
    ].join(',');
  });

  const csvContent = [headers.join(','), ...rows].join('\r\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  link.setAttribute('href', url);
  link.setAttribute('download', `predictions_${modelName.toLowerCase().replace(/\s+/g, '_')}_${timestamp}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Parses CSV raw text into an array of feature objects matching feature schemas.
 */
export function parseCsvToRecords(
  csvText: string,
  featureSchema: Array<{ name: string; kind: 'numeric' | 'categorical' }>
): {
  records: Array<Record<string, FeaturePrimitive>>;
  errors: string[];
  totalRows: number;
} {
  const lines = csvText.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length < 2) {
    return {
      records: [],
      errors: ['CSV file must contain a header row and at least one data row.'],
      totalRows: 0,
    };
  }

  // Parse header
  const rawHeaders = lines[0].split(',').map((h) => h.trim().replace(/^"|"$/g, ''));
  const headerMap: Record<string, number> = {};
  rawHeaders.forEach((h, idx) => {
    headerMap[h] = idx;
  });

  const missingHeaders: string[] = [];

  featureSchema.forEach((f) => {
    if (headerMap[f.name] === undefined) {
      missingHeaders.push(f.name);
    }
  });

  if (missingHeaders.length > 0) {
    return {
      records: [],
      errors: [
        `CSV is missing expected feature columns: ${missingHeaders.join(', ')}. Found: ${rawHeaders.join(', ')}`,
      ],
      totalRows: lines.length - 1,
    };
  }

  const records: Array<Record<string, FeaturePrimitive>> = [];
  const errors: string[] = [];

  for (let i = 1; i < lines.length; i++) {
    const rowLine = lines[i];
    // Simple split handling quotes
    const cells: string[] = [];
    let current = '';
    let insideQuotes = false;
    for (let charIdx = 0; charIdx < rowLine.length; charIdx++) {
      const char = rowLine[charIdx];
      if (char === '"') {
        insideQuotes = !insideQuotes;
      } else if (char === ',' && !insideQuotes) {
        cells.push(current.trim().replace(/^"|"$/g, ''));
        current = '';
      } else {
        current += char;
      }
    }
    cells.push(current.trim().replace(/^"|"$/g, ''));

    const record: Record<string, FeaturePrimitive> = {};
    let rowHasError = false;

    featureSchema.forEach((field) => {
      const colIdx = headerMap[field.name];
      const rawVal = cells[colIdx];

      if (rawVal === undefined || rawVal === '' || rawVal.toLowerCase() === 'null') {
        record[field.name] = null;
      } else if (field.kind === 'numeric') {
        const num = Number(rawVal);
        if (isNaN(num)) {
          errors.push(`Row ${i}: "${field.name}" expected numeric value, found "${rawVal}"`);
          rowHasError = true;
        } else {
          record[field.name] = num;
        }
      } else {
        record[field.name] = rawVal;
      }
    });

    if (!rowHasError) {
      records.push(record);
    }
  }

  return {
    records,
    errors: errors.slice(0, 10), // Report first 10 validation errors
    totalRows: lines.length - 1,
  };
}
