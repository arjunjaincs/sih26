import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ExportJsonButton } from './components/ExportJsonButton';
import { AssessmentHeader } from './components/AssessmentHeader';
import * as client from './api/client';

describe('Assessment Structured JSON Export Frontend Suite', () => {
  const asmtId = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders ExportJsonButton with default label and accessibility attributes', () => {
    render(<ExportJsonButton assessmentId={asmtId} />);
    const btn = screen.getByRole('button', { name: /export machine-readable json assurance package/i });
    expect(btn).toBeDefined();
    expect(screen.getByText('Export JSON')).toBeDefined();
  });

  it('triggers exportAssessmentJson and enters loading state on click', async () => {
    let resolveExport: () => void = () => {};
    const exportPromise = new Promise<void>((resolve) => {
      resolveExport = resolve;
    });

    const exportSpy = vi.spyOn(client, 'exportAssessmentJson').mockReturnValue(exportPromise);

    render(<ExportJsonButton assessmentId={asmtId} />);
    const btn = screen.getByRole('button', { name: /export machine-readable json assurance package/i });

    fireEvent.click(btn);
    expect(exportSpy).toHaveBeenCalledWith(asmtId);

    // Verify loading spinner & text
    expect(screen.getByText('Exporting…')).toBeDefined();
    expect(btn.hasAttribute('disabled')).toBe(true);

    // Resolve promise
    resolveExport();
    await waitFor(() => {
      expect(screen.queryByText('Exporting…')).toBeNull();
      expect(screen.getByText('Export JSON')).toBeDefined();
    });
  });

  it('displays error feedback when export fails', async () => {
    vi.spyOn(client, 'exportAssessmentJson').mockRejectedValue(new Error('Network failure'));

    render(<ExportJsonButton assessmentId={asmtId} />);
    const btn = screen.getByRole('button', { name: /export machine-readable json assurance package/i });

    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByText('Export failed')).toBeDefined();
    });
  });

  it('verifies getExportJsonUrl builds standard endpoint', () => {
    const url = client.getExportJsonUrl('test-123');
    expect(url).toContain('/api/v1/assessments/test-123/export/json');
  });

  it('renders ExportJsonButton alongside ReportDownloadButton in AssessmentHeader', () => {
    render(
      <MemoryRouter>
        <AssessmentHeader
          assessmentId={asmtId}
          title="ResNet-50 Assurance Run"
          status="COMPLETE"
          overallRisk="LOW"
          overallConfidence="HIGH"
          coverageFraction={0.95}
        />
      </MemoryRouter>
    );

    // Both buttons should be present in the header
    expect(screen.getByRole('button', { name: /download official pdf assurance report/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /export machine-readable json assurance package/i })).toBeDefined();
  });
});
