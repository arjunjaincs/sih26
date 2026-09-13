import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuditTrail } from './pages/AuditTrail';
import * as client from './api/client';
import type { AuditResponse } from './types/api';

describe('Audit Trail Structured JSON Export Suite', () => {
  const asmtId = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';
  const mockAuditData: AuditResponse = {
    assessment_id: asmtId,
    chain_valid: true,
    events_checked: 2,
    failures: [],
    first_invalid_event_id: null,
    events: [
      {
        event_id: 'evt-001',
        event_type: 'ASSESSMENT_CREATED',
        timestamp_utc: '2026-09-13T01:00:00Z',
        actor: 'system',
        current_hash: '11'.repeat(32),
        previous_hash: '0'.repeat(64),
      },
      {
        event_id: 'evt-002',
        event_type: 'ASSESSMENT_COMPLETE',
        timestamp_utc: '2026-09-13T01:05:00Z',
        actor: 'system',
        current_hash: '22'.repeat(32),
        previous_hash: '11'.repeat(32),
      },
    ],
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(client, 'getAudit').mockResolvedValue(mockAuditData);
  });

  it('builds standard export audit URL via getExportAuditJsonUrl', () => {
    const url = client.getExportAuditJsonUrl(asmtId);
    expect(url).toContain(`/api/v1/assessments/${encodeURIComponent(asmtId)}/audit/export`);
  });

  it('renders Export Audit button with verification artifact designation in AuditTrail', async () => {
    render(
      <MemoryRouter initialEntries={[`/assessments/${asmtId}/audit`]}>
        <Routes>
          <Route path="/assessments/:id/audit" element={<AuditTrail />} />
        </Routes>
      </MemoryRouter>
    );

    // Wait for audit trail to load
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: 'Audit Trail' })).toBeDefined();
    });

    // Verification artifact badge
    expect(screen.getByText('VERIFICATION ARTIFACT')).toBeDefined();

    // Export Audit button
    const exportBtn = screen.getByRole('button', { name: /export audit/i });
    expect(exportBtn).toBeDefined();
    expect(exportBtn.getAttribute('title')).toContain('Verification Artifact');
  });

  it('triggers exportAuditJson and displays loading state and success feedback on click', async () => {
    let resolveExport: () => void = () => {};
    const exportPromise = new Promise<void>((resolve) => {
      resolveExport = resolve;
    });

    const exportSpy = vi.spyOn(client, 'exportAuditJson').mockReturnValue(exportPromise);

    render(
      <MemoryRouter initialEntries={[`/assessments/${asmtId}/audit`]}>
        <Routes>
          <Route path="/assessments/:id/audit" element={<AuditTrail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /export audit/i })).toBeDefined();
    });

    const exportBtn = screen.getByRole('button', { name: /export audit/i });
    fireEvent.click(exportBtn);

    // Expected call with assessment ID and safe filename
    const safeShortId = asmtId.slice(0, 8);
    expect(exportSpy).toHaveBeenCalledWith(asmtId, `pramaan_audit_export_${safeShortId}.json`);

    // In loading/exporting state
    expect(screen.getByText('Exporting…')).toBeDefined();
    expect(exportBtn.hasAttribute('disabled')).toBe(true);

    // Resolve export
    resolveExport();

    await waitFor(() => {
      expect(screen.getByText('Export Audit')).toBeDefined();
      expect(screen.getByText(/verification artifact downloaded/i)).toBeDefined();
    });
  });

  it('displays error feedback when exportAuditJson fails', async () => {
    vi.spyOn(client, 'exportAuditJson').mockRejectedValue(new Error('Export request timed out'));

    render(
      <MemoryRouter initialEntries={[`/assessments/${asmtId}/audit`]}>
        <Routes>
          <Route path="/assessments/:id/audit" element={<AuditTrail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /export audit/i })).toBeDefined();
    });

    const exportBtn = screen.getByRole('button', { name: /export audit/i });
    fireEvent.click(exportBtn);

    await waitFor(() => {
      expect(screen.getByText('Export request timed out')).toBeDefined();
    });
  });
});
