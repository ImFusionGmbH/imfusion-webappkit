import type { ExportFormat } from './types';

export function exportFormatLabel(format: ExportFormat): string {
  if (format === 'nii.gz') return 'NIfTI (.nii.gz)';
  if (format === 'dicom') return 'DICOM (.dcm)';
  return 'ImFusion (.imf)';
}
