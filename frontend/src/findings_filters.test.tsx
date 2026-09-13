import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { Findings } from './pages/Findings';
import * as client from './api/client';
import type { FindingsResponse, AssessmentResultSchema } from './types/api';

vi.mock('./api/client', async () => {
  const actual = await vi.importActual<typeof client>('./api/client');
  return {
    ...actual,
    getFindings: vi.fn(),
    getAssessment: vi.fn(),
  };
});

const MOCK_FINDINGS_DATA: FindingsResponse = {
  assessment_id: 'asmt-qa-1',
  count: 5,
  findings: [
    {
      finding_id: 'f-di-01',
      assessment_id: 'asmt-qa-1',
      asset_id: 'dataset-eval',
      category: 'data_integrity',
      subcategory: 'perceptual_duplicates',
      severity: 'high',
      title: 'Dataset perceptual duplicates detected',
      description: '3 clusters of duplicate images identified via pHash and dHash.',
      detection_method: 'Perceptual hashing (pHash + dHash)',
      detector_id: 'DI-01',
      limitations: ['Hash distance threshold fixed at 10'],
      recommended_disposition: 'Inspect clusters and deduplicate training split.',
      created_at: '2026-09-12T10:00:00Z',
    },
    {
      finding_id: 'f-di-02',
      assessment_id: 'asmt-qa-1',
      asset_id: 'dataset-eval',
      category: 'data_integrity',
      subcategory: 'label_integrity',
      severity: 'medium',
      title: 'Class imbalance and label anomaly',
      description: 'Disproportionate distribution of positive labels detected.',
      detection_method: 'Statistical label distribution test',
      detector_id: 'DI-02',
      limitations: ['Requires at least 100 labeled samples'],
      recommended_disposition: 'Rebalance sampling split across classes.',
      created_at: '2026-09-12T10:01:00Z',
    },
    {
      finding_id: 'f-mi-01',
      assessment_id: 'asmt-qa-1',
      asset_id: 'model-resnet',
      category: 'model_integrity',
      subcategory: 'weight_fingerprint',
      severity: 'critical',
      title: 'Weight corruption in layer conv1',
      description: 'SHA-256 tensor hash mismatch against trusted reference manifest.',
      detection_method: 'Cryptographic tensor fingerprinting',
      detector_id: 'MI-01',
      limitations: ['Reference baseline must be signed'],
      recommended_disposition: 'Do not deploy. Model weights differ from baseline.',
      created_at: '2026-09-12T10:02:00Z',
    },
    {
      finding_id: 'f-pi-01',
      assessment_id: 'asmt-qa-1',
      asset_id: 'model-resnet',
      category: 'inference_provenance',
      subcategory: 'signature_verification',
      severity: 'low',
      title: 'Signature missing timestamp nonce',
      description: 'Signature header lacks cryptographic timestamp nonce.',
      detection_method: 'Ed25519 signature manifest check',
      detector_id: 'PI-01',
      limitations: ['Requires online clock or trusted timestamp server'],
      recommended_disposition: 'Ensure signing service adds nonce to header.',
      created_at: '2026-09-12T10:03:00Z',
    },
    {
      finding_id: 'f-at-01',
      assessment_id: 'asmt-qa-1',
      asset_id: 'audit-ledger',
      category: 'coverage',
      subcategory: 'assurance_gap',
      severity: 'info',
      title: 'Coverage gap: OOD detector skipped',
      description: 'Out-of-distribution detector could not run on non-tabular dataset.',
      detection_method: 'Coverage rule evaluation',
      detector_id: 'AT-01',
      limitations: [],
      recommended_disposition: 'Acknowledge coverage gap in final assurance report.',
      created_at: '2026-09-12T10:04:00Z',
    },
  ],
};

const MOCK_ASSESSMENT_DATA: AssessmentResultSchema = {
  assessment_id: 'asmt-qa-1',
  title: 'QA Assessment Test Run',
  status: 'complete',
  started_at: '2026-09-12T10:00:00Z',
  completed_at: '2026-09-12T10:05:00Z',
  assets_analyzed: ['dataset-eval', 'model-resnet'],
  detectors_executed: ['DI-01', 'DI-02', 'MI-01', 'PI-01', 'AT-01'],
  detectors_skipped: [],
  findings_count: 5,
  evidence_count: 5,
  overall_risk: 'critical',
  risk_qualitative: 'Critical Risk',
  overall_confidence: 'high',
  confidence_qualifier: 'High Assurance',
  coverage_fraction: 0.9,
  coverage_gaps: [],
  limitations: [],
  audit_chain_valid: true,
  error: null,
  detector_runs: [
    {
      detector_id: 'DI-01',
      detector_name: 'Dataset Duplicates',
      asset_id: 'dataset-eval',
      applicable: true,
      ran: true,
      status: 'fail',
      risk_level: 'high',
      confidence_level: 'high',
      findings_count: 1,
      evidence_count: 1,
      error: null,
    },
    {
      detector_id: 'DI-02',
      detector_name: 'Label Integrity',
      asset_id: 'dataset-eval',
      applicable: true,
      ran: true,
      status: 'warn',
      risk_level: 'medium',
      confidence_level: 'moderate',
      findings_count: 1,
      evidence_count: 1,
      error: null,
    },
    {
      detector_id: 'MI-01',
      detector_name: 'Model Fingerprint',
      asset_id: 'model-resnet',
      applicable: true,
      ran: true,
      status: 'fail',
      risk_level: 'critical',
      confidence_level: 'high',
      findings_count: 1,
      evidence_count: 1,
      error: null,
    },
    {
      detector_id: 'PI-01',
      detector_name: 'Provenance Integrity',
      asset_id: 'model-resnet',
      applicable: true,
      ran: true,
      status: 'warn',
      risk_level: 'low',
      confidence_level: 'moderate',
      findings_count: 1,
      evidence_count: 1,
      error: null,
    },
    {
      detector_id: 'AT-01',
      detector_name: 'Audit Trail Ledger',
      asset_id: 'audit-ledger',
      applicable: true,
      ran: true,
      status: 'pass',
      risk_level: 'none',
      confidence_level: 'low',
      findings_count: 1,
      evidence_count: 1,
      error: null,
    },
  ],
};

function renderFindingsPage(initialEntry = '/assessments/asmt-qa-1/findings') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/assessments/:id/findings" element={<Findings />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('Findings Filters and Grouping Component', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders header, total count, and default Assurance Layer grouping', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    renderFindingsPage();

    expect(await screen.findByRole('heading', { name: /Assessment Findings/i })).toBeDefined();
    expect(screen.getByText(/DEFECT REGISTRY/i)).toBeDefined();
    expect(screen.getByText('5 Records')).toBeDefined();

    // Default grouping is 'layer' — verify layer headings/badges exist
    expect(screen.getAllByText('Data Integrity').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Model Integrity').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Provenance & Inference').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Audit & Ledger').length).toBeGreaterThan(0);
  });

  it('switches grouping to Detector', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    renderFindingsPage();
    await screen.findByRole('heading', { name: /Assessment Findings/i });

    const groupBySelect = screen.getByLabelText(/Group findings by/i);
    fireEvent.change(groupBySelect, { target: { value: 'detector' } });

    await waitFor(() => {
      expect(screen.getByText(/Detector ID: DI-01/i)).toBeDefined();
      expect(screen.getByText(/Detector ID: MI-01/i)).toBeDefined();
      expect(screen.getByText(/Detector ID: PI-01/i)).toBeDefined();
    });
  });

  it('switches grouping to Severity', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    renderFindingsPage();
    await screen.findByRole('heading', { name: /Assessment Findings/i });

    const groupBySelect = screen.getByLabelText(/Group findings by/i);
    fireEvent.change(groupBySelect, { target: { value: 'severity' } });

    await waitFor(() => {
      expect(screen.getByText('Critical Severity')).toBeDefined();
      expect(screen.getByText('High Severity')).toBeDefined();
      expect(screen.getByText('Medium Severity')).toBeDefined();
      expect(screen.getByText('Low Severity')).toBeDefined();
      expect(screen.getByText('Info Severity')).toBeDefined();
    });
  });

  it('switches grouping to Flat List (none)', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    renderFindingsPage();
    await screen.findByRole('heading', { name: /Assessment Findings/i });

    const groupBySelect = screen.getByLabelText(/Group findings by/i);
    fireEvent.change(groupBySelect, { target: { value: 'none' } });

    await waitFor(() => {
      expect(screen.getByText('Weight corruption in layer conv1')).toBeDefined();
      expect(screen.getByText('Dataset perceptual duplicates detected')).toBeDefined();
      expect(screen.getByText('Signature missing timestamp nonce')).toBeDefined();
    });
  });

  it('filters by Severity and updates active filters pill', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    renderFindingsPage();
    await screen.findByRole('heading', { name: /Assessment Findings/i });

    const severitySelect = screen.getByLabelText(/Filter by severity/i);
    fireEvent.change(severitySelect, { target: { value: 'critical' } });

    await waitFor(() => {
      expect(screen.getByText('Weight corruption in layer conv1')).toBeDefined();
      expect(screen.queryByText('Dataset perceptual duplicates detected')).toBeNull();
      expect(screen.getAllByText(/CRITICAL/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/Showing/i)).toBeDefined();
    });
  });

  it('filters by Assurance Layer', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    renderFindingsPage();
    await screen.findByRole('heading', { name: /Assessment Findings/i });

    const layerSelect = screen.getByLabelText(/Filter by layer/i);
    fireEvent.change(layerSelect, { target: { value: 'model_integrity' } });

    await waitFor(() => {
      expect(screen.getByText('Weight corruption in layer conv1')).toBeDefined();
      expect(screen.queryByText('Dataset perceptual duplicates detected')).toBeNull();
    });
  });

  it('filters by Detector ID', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    renderFindingsPage();
    await screen.findByRole('heading', { name: /Assessment Findings/i });

    const detectorSelect = screen.getByLabelText(/^Filter by detector$/i);
    fireEvent.change(detectorSelect, { target: { value: 'DI-01' } });

    await waitFor(() => {
      expect(screen.getByText('Dataset perceptual duplicates detected')).toBeDefined();
      expect(screen.queryByText('Weight corruption in layer conv1')).toBeNull();
    });
  });

  it('filters by Correlated Detector Risk', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    renderFindingsPage();
    await screen.findByRole('heading', { name: /Assessment Findings/i });

    const riskSelect = screen.getByLabelText(/Filter by detector risk/i);
    fireEvent.change(riskSelect, { target: { value: 'critical' } });

    await waitFor(() => {
      expect(screen.getByText('Weight corruption in layer conv1')).toBeDefined();
      expect(screen.queryByText('Dataset perceptual duplicates detected')).toBeNull();
    });
  });

  it('filters by Free-text Search', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    renderFindingsPage();
    await screen.findByRole('heading', { name: /Assessment Findings/i });

    const searchInput = screen.getByPlaceholderText(/Search findings, detectors/i);
    fireEvent.change(searchInput, { target: { value: 'conv1' } });

    await waitFor(() => {
      expect(screen.getByText('Weight corruption in layer conv1')).toBeDefined();
      expect(screen.queryByText('Dataset perceptual duplicates detected')).toBeNull();
    });
  });

  it('removes an active filter using its pill dismiss button', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    renderFindingsPage();
    await screen.findByRole('heading', { name: /Assessment Findings/i });

    const severitySelect = screen.getByLabelText(/Filter by severity/i);
    fireEvent.change(severitySelect, { target: { value: 'critical' } });

    await waitFor(() => {
      expect(screen.getByText('Weight corruption in layer conv1')).toBeDefined();
      expect(screen.queryByText('Dataset perceptual duplicates detected')).toBeNull();
    });

    const dismissBtn = screen.getByTitle(/Remove Severity filter/i);
    fireEvent.click(dismissBtn);

    await waitFor(() => {
      expect(screen.getByText('Dataset perceptual duplicates detected')).toBeDefined();
      expect(screen.getByText('Weight corruption in layer conv1')).toBeDefined();
    });
  });

  it('resets all filters using the Reset All button', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    renderFindingsPage();
    await screen.findByRole('heading', { name: /Assessment Findings/i });

    const searchInput = screen.getByPlaceholderText(/Search findings, detectors/i);
    fireEvent.change(searchInput, { target: { value: 'conv1' } });

    await waitFor(() => {
      expect(screen.getByText('Weight corruption in layer conv1')).toBeDefined();
    });

    const resetBtn = screen.getByTitle(/Reset all active filters/i);
    fireEvent.click(resetBtn);

    await waitFor(() => {
      expect(screen.getByText('Dataset perceptual duplicates detected')).toBeDefined();
      expect(screen.getByText('Signature missing timestamp nonce')).toBeDefined();
    });
  });

  it('renders empty filtered state when active filters match zero findings', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    renderFindingsPage();
    await screen.findByRole('heading', { name: /Assessment Findings/i });

    const searchInput = screen.getByPlaceholderText(/Search findings, detectors/i);
    fireEvent.change(searchInput, { target: { value: 'nonexistent_anomaly_query' } });

    await waitFor(() => {
      expect(screen.getByText(/No findings match the selected filters/i)).toBeDefined();
      expect(screen.getByRole('button', { name: /Reset all filters/i })).toBeDefined();
    });

    // Clicking the reset button in empty state restores findings
    fireEvent.click(screen.getByRole('button', { name: /Reset all filters/i }));

    await waitFor(() => {
      expect(screen.getByText('Weight corruption in layer conv1')).toBeDefined();
    });
  });

  it('renders clean state when assessment has 0 findings total', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce({
      assessment_id: 'asmt-clean',
      count: 0,
      findings: [],
    });
    vi.mocked(client.getAssessment).mockResolvedValueOnce({
      ...MOCK_ASSESSMENT_DATA,
      assessment_id: 'asmt-clean',
      findings_count: 0,
    });

    renderFindingsPage('/assessments/asmt-clean/findings');

    expect(await screen.findByText('Zero Findings Recorded')).toBeDefined();
    expect(screen.getByText(/No structural mutations, duplicate anomalies/i)).toBeDefined();
    expect(screen.getByText(/Inspect Verified Evidence Artifacts/i)).toBeDefined();
  });

  it('expands finding card to display technical metadata, correlated risk and disposition', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    renderFindingsPage();
    await screen.findByRole('heading', { name: /Assessment Findings/i });

    // Click to expand the conv1 finding card
    const findingBtn = screen.getByRole('button', { name: /Weight corruption in layer conv1/i });
    fireEvent.click(findingBtn);

    await waitFor(() => {
      expect(screen.getByText('f-mi-01')).toBeDefined();
      expect(screen.getByText('model-resnet')).toBeDefined();
      expect(screen.getByText('Cryptographic tensor fingerprinting')).toBeDefined();
      expect(screen.getByText(/Detector Assessed Risk/i)).toBeDefined();
      expect(screen.getByText('Recommended Analyst Disposition')).toBeDefined();
      expect(screen.getByText(/Do not deploy. Model weights differ from baseline./i)).toBeDefined();
      expect(screen.getByText('Ask Copilot')).toBeDefined();
      expect(screen.getByText('Inspect Supporting Evidence')).toBeDefined();
    });
  });

  it('honors URL search parameters on initial load', async () => {
    vi.mocked(client.getFindings).mockResolvedValueOnce(MOCK_FINDINGS_DATA);
    vi.mocked(client.getAssessment).mockResolvedValueOnce(MOCK_ASSESSMENT_DATA);

    // Initial URL with severity=critical and groupBy=detector
    renderFindingsPage('/assessments/asmt-qa-1/findings?severity=critical&groupBy=detector');

    await waitFor(() => {
      expect(screen.getByText(/Detector ID: MI-01/i)).toBeDefined();
      expect(screen.getByText('Weight corruption in layer conv1')).toBeDefined();
      expect(screen.queryByText('Dataset perceptual duplicates detected')).toBeNull();
      expect(screen.getAllByText(/CRITICAL/i).length).toBeGreaterThan(0);
    });
  });
});
