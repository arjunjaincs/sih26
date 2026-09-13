import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { Overview } from './pages/Overview';
import { Capabilities } from './pages/Capabilities';
import { NewAssessment } from './pages/NewAssessment';
import { AssessmentResult } from './pages/AssessmentResult';
import { Findings } from './pages/Findings';
import { Evidence } from './pages/Evidence';
import { AuditTrail } from './pages/AuditTrail';
import { Assessments } from './pages/Assessments';
import { ThemeProvider } from './hooks/useTheme';
import { AppShell } from './layouts/AppShell';

const MOCK_CAPS = {
  detectors: [
    {
      detector_id: 'DI-01',
      version: '1.0.0',
      name: 'Dataset Integrity Detector',
      description: 'Perceptual hashing and duplicate image detection.',
      applicable_asset_types: ['dataset'],
      available: true,
    },
    {
      detector_id: 'MI-01',
      version: '1.0.0',
      name: 'Model Integrity Fingerprinter',
      description: 'Structural AST topology and weight hashing.',
      applicable_asset_types: ['model'],
      available: true,
    },
    {
      detector_id: 'PI-01',
      version: '1.0.0',
      name: 'Provenance & Output Signature Verifier',
      description: 'Ed25519 signature and digest verification.',
      applicable_asset_types: ['provenance'],
      available: true,
    },
  ],
  supported_dataset_formats: ['image_dir', 'coco_json'],
  supported_model_formats: ['.onnx', '.pt'],
  pramaan_version: '1.0.0',
};

const MOCK_HEALTH = {
  status: 'ok',
  version: '1.0.0',
  db_path: 'data/pramaan.db',
};

const MOCK_SUMMARY = {
  assessment_id: 'b3a8cba4-64e7-45dd-970f-668f2b164ed2',
  title: 'E2E QA Model & Dataset Assurance Run',
  status: 'complete',
  software_version: '1.0.0',
  created_at: '2026-09-12T15:46:00Z',
  started_at: '2026-09-12T15:46:00Z',
  completed_at: '2026-09-12T15:46:02Z',
  error: null,
  findings_count: 3,
  evidence_count: 3,
};

const MOCK_RESULT = {
  ...MOCK_SUMMARY,
  assets_analyzed: ['ast_model_1', 'ast_dataset_1'],
  detectors_executed: ['DI-01', 'MI-01'],
  detectors_skipped: ['PI-01'],
  overall_risk: 'medium',
  risk_qualitative: 'Moderate structural variance observed in model topology.',
  overall_confidence: 'high',
  confidence_qualifier: 'Evaluated through deterministic execution battery.',
  coverage_fraction: 0.67,
  coverage_gaps: [
    {
      detector_id: 'PI-01',
      detector_name: 'Provenance Verifier',
      reason: 'No signed provenance manifest provided with inference artifacts',
      required_capability: 'ed25519_signature',
      observed_capability: 'none',
      impact: 'Output cryptographic authenticity unverified',
      recommended_action: 'Provide provenance_manifest.json and public key',
    },
  ],
  detector_runs: [
    {
      detector_id: 'DI-01',
      detector_name: 'Dataset Integrity Detector',
      asset_id: 'ast_dataset_1',
      applicable: true,
      ran: true,
      status: 'complete',
      risk_level: 'none',
      confidence_level: 'high',
      findings_count: 0,
      evidence_count: 1,
      error: null,
    },
    {
      detector_id: 'MI-01',
      detector_name: 'Model Integrity Fingerprinter',
      asset_id: 'ast_model_1',
      applicable: true,
      ran: true,
      status: 'complete',
      risk_level: 'medium',
      confidence_level: 'high',
      findings_count: 3,
      evidence_count: 2,
      error: null,
    },
  ],
  limitations: [
    'Pixel & perceptual space analysis only.',
    'Identifies material structural drift; does not classify changes as malicious.',
  ],
  audit_chain_valid: true,
};

const MOCK_FINDINGS = {
  assessment_id: 'b3a8cba4-64e7-45dd-970f-668f2b164ed2',
  count: 3,
  findings: [
    {
      finding_id: 'fnd_001',
      assessment_id: 'b3a8cba4-64e7-45dd-970f-668f2b164ed2',
      asset_id: 'ast_model_1',
      category: 'model_integrity',
      subcategory: 'topology_drift',
      severity: 'medium',
      title: 'Structural Topology Divergence',
      description: 'Operator counts diverge from baseline reference graph by +2 Conv nodes.',
      detection_method: 'AST Structural Diff',
      detector_id: 'MI-01',
      limitations: ['Graph level only'],
      recommended_disposition: 'Inspect model retraining commit history and verify architecture change.',
      created_at: '2026-09-12T15:46:01Z',
    },
    {
      finding_id: 'fnd_002',
      assessment_id: 'b3a8cba4-64e7-45dd-970f-668f2b164ed2',
      asset_id: 'ast_model_1',
      category: 'model_integrity',
      subcategory: 'weight_fingerprint',
      severity: 'low',
      title: 'Weight Hash Delta',
      description: 'Tensor weight SHA-256 fingerprint differs from pristine reference checkpoint.',
      detection_method: 'Exact Byte Hash',
      detector_id: 'MI-01',
      limitations: [],
      recommended_disposition: 'Confirm whether weights were fine-tuned.',
      created_at: '2026-09-12T15:46:01Z',
    },
    {
      finding_id: 'fnd_003',
      assessment_id: 'b3a8cba4-64e7-45dd-970f-668f2b164ed2',
      asset_id: 'ast_model_1',
      category: 'model_integrity',
      subcategory: 'info_metadata',
      severity: 'info',
      title: 'ONNX Opset Version 14 Compliant',
      description: 'Model conforms to ONNX IR version 8, opset 14 specification.',
      detection_method: 'Schema Validator',
      detector_id: 'MI-01',
      limitations: [],
      recommended_disposition: null,
      created_at: '2026-09-12T15:46:01Z',
    },
  ],
};

const MOCK_EVIDENCE = {
  assessment_id: 'b3a8cba4-64e7-45dd-970f-668f2b164ed2',
  count: 3,
  evidence: [
    {
      evidence_id: 'evi_001',
      assessment_id: 'b3a8cba4-64e7-45dd-970f-668f2b164ed2',
      evidence_type: 'ast_digest',
      artifact_sha256: '8d278a9e321240ef1a5c689104fa28db3288bc91240182740924719283716291',
      data: {
        operator_counts: { Conv: 14, Relu: 14, Add: 6, MaxPool: 3 },
        input_tensor: { name: 'input', shape: [1, 3, 224, 224], dtype: 'float32' },
        sha256_hash: '8d278a9e321240ef1a5c689104fa28db3288bc91240182740924719283716291',
      },
      description: 'Model AST structural fingerprint',
      created_at: '2026-09-12T15:46:01Z',
    },
  ],
};

const MOCK_AUDIT = {
  assessment_id: 'b3a8cba4-64e7-45dd-970f-668f2b164ed2',
  chain_valid: true,
  events: [
    {
      event_id: 'evt_001',
      assessment_id: 'b3a8cba4-64e7-45dd-970f-668f2b164ed2',
      event_type: 'assessment_started',
      actor: 'system',
      timestamp_utc: '2026-09-12T15:46:00Z',
      current_hash: 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
      previous_hash: '0',
    },
    {
      event_id: 'evt_002',
      assessment_id: 'b3a8cba4-64e7-45dd-970f-668f2b164ed2',
      event_type: 'detector_executed',
      actor: 'system',
      timestamp_utc: '2026-09-12T15:46:01Z',
      current_hash: 'b2c3d4e5f6a708192a3b4c5d6e7f809123456789abcdef0123456789abcdef01',
      previous_hash: 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
    },
  ],
};

vi.mock('./api/client', () => ({
  getHealth: vi.fn(() => Promise.resolve(MOCK_HEALTH)),
  getCapabilities: vi.fn(() => Promise.resolve(MOCK_CAPS)),
  getAssessment: vi.fn(() => Promise.resolve(MOCK_SUMMARY)),
  listAssessments: vi.fn(() => Promise.resolve({ total: 1, assessments: [MOCK_SUMMARY] })),
  getFindings: vi.fn(() => Promise.resolve(MOCK_FINDINGS)),
  getEvidence: vi.fn(() => Promise.resolve(MOCK_EVIDENCE)),
  getEvidencePreview: vi.fn((asmtId: string, evId: string) => Promise.resolve({
    evidence_id: evId,
    assessment_id: asmtId,
    finding_id: 'fnd_001',
    detector_id: 'MI-01',
    evidence_type: 'structural_ast',
    preview_type: 'structured',
    title: 'AST Structural Diff Preview',
    structured_content: { diff: 'none' },
  })),
  getAudit: vi.fn(() => Promise.resolve(MOCK_AUDIT)),
  createAssessment: vi.fn(() => Promise.resolve(MOCK_RESULT)),
  uploadAsset: vi.fn(() => Promise.resolve({
    asset_id: 'ast_123',
    original_filename: 'model.onnx',
    sha256: 'abc123sha256',
    size_bytes: 1024,
    asset_type: 'model',
    created_at: '2026-09-12T15:46:00Z',
  })),
  getDemos: vi.fn(() => Promise.resolve({ total: 0, demos: [] })),
  getProvenance: vi.fn(() => Promise.resolve({
    assessment_id: 'b3a8cba4-64e7-45dd-970f-668f2b164ed2',
    verified: true,
    ed25519_signature_valid: true,
    replay_attack_detected: false,
    manifest_asset_binding_valid: true,
    manifests: [],
    findings: [],
    evidence: [],
  })),
  downloadReport: vi.fn(() => Promise.resolve(new Blob())),
  getReportUrl: vi.fn((id: string) => `/api/v1/assessments/${id}/report`),
  exportAssessmentJson: vi.fn(() => Promise.resolve()),
  getExportJsonUrl: vi.fn((id: string) => `/api/v1/assessments/${id}/export/json`),
  verifyAuditChain: vi.fn(() => Promise.resolve({ chain_valid: true, events_verified: 5 })),
  NetworkError: class NetworkError extends Error { name = 'NetworkError'; },
}));

describe('PRAMAAN v1 Full Browser & DOM E2E QA', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('verifies Home page layout, static composition, and theme toggle', async () => {
    render(
      <ThemeProvider>
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<Overview />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    );

    // Navbar logo and links
    expect(screen.getByText('PRAMAAN')).toBeDefined();
    expect(screen.getByText('Home')).toBeDefined();
    expect(screen.getByText('Assess')).toBeDefined();
    expect(screen.getByText('Capabilities')).toBeDefined();

    // Live backend indicator
    expect(await screen.findByTitle(/Backend connected/i)).toBeDefined();
    expect(screen.getByText('Live')).toBeDefined();

    // Headline and value proposition
    expect(screen.getByText('Trust AI')).toBeDefined();
    expect(screen.getByText('Evidence')).toBeDefined();

    // Truthful capabilities indicators
    expect(screen.getByText(/4 ASSURANCE LAYERS/i)).toBeDefined();
    expect(screen.getByText(/OFFLINE EXECUTION/i)).toBeDefined();

    // Theme toggle interaction
    const themeBtn = screen.getByRole('button', { name: /switch to light mode/i });
    expect(themeBtn).toBeDefined();
    fireEvent.click(themeBtn);
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('verifies Capabilities page, layer specifications, and interactive category filters', async () => {
    render(
      <MemoryRouter initialEntries={['/capabilities']}>
        <Capabilities />
      </MemoryRouter>
    );

    // Header & Summary Ribbon
    expect(await screen.findByRole('heading', { name: /Capabilities & Detector Specification/i })).toBeDefined();
    expect(screen.getByText('4 Layers')).toBeDefined();
    expect(screen.getByText('100% Offline')).toBeDefined();

    // Verify all 4 assurance layers are present initially
    expect(screen.getAllByText('DI-01').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('MI-01').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('AT-01').length).toBeGreaterThanOrEqual(1);

    // Filter by Detectors
    const detTab = screen.getByRole('button', { name: /detectors/i });
    fireEvent.click(detTab);
    expect(screen.getAllByText('DI-01').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('AT-01: Tamper-Evident Audit Trail')).toBeNull();

    // Filter by Audit Trail
    const ledgerTab = screen.getByRole('button', { name: /audit trail/i });
    fireEvent.click(ledgerTab);
    expect(screen.getByText('AT-01: Tamper-Evident Audit Trail')).toBeDefined();
    expect(screen.queryByText('Dataset Integrity Detector')).toBeNull();

    // Reset to All
    const allTab = screen.getByRole('button', { name: /all capabilities/i });
    fireEvent.click(allTab);
    expect(screen.getByText('AT-01: Tamper-Evident Audit Trail')).toBeDefined();
    expect(screen.getByText('Dataset Integrity Detector')).toBeDefined();
  });

  it('verifies New Assessment mode switching between Upload and Local Path', async () => {
    render(
      <MemoryRouter initialEntries={['/assessments/new']}>
        <NewAssessment />
      </MemoryRouter>
    );

    expect(screen.getByRole('heading', { name: /New Assessment/i })).toBeDefined();

    // Both sections default to Upload File mode
    const browseButtons = screen.getAllByText(/click to browse/i);
    expect(browseButtons.length).toBeGreaterThanOrEqual(1);

    // Switch model to Local Path (Advanced)
    const localButtons = screen.getAllByRole('button', { name: /local path \(advanced\)/i });
    fireEvent.click(localButtons[0]);

    // Local path input should be visible
    expect(screen.getByPlaceholderText(/classifier\.onnx/i)).toBeDefined();

    // Switch back to Upload File
    const uploadButtons = screen.getAllByRole('button', { name: /upload file/i });
    fireEvent.click(uploadButtons[0]);
    expect(screen.queryByPlaceholderText(/classifier\.onnx/i)).toBeNull();
  });

  it('verifies Results page: prominent metrics and 4 layers matrix', async () => {
    render(
      <MemoryRouter initialEntries={['/assessments/b3a8cba4-64e7-45dd-970f-668f2b164ed2/result']}>
        <Routes>
          <Route path="/assessments/:id/result" element={<AssessmentResult />} />
        </Routes>
      </MemoryRouter>
    );

    // Wait for async load
    expect(await screen.findByRole('heading', { name: /E2E QA Model & Dataset Assurance Run/i })).toBeDefined();

    // Sub-navigation tabs
    expect(screen.getAllByRole('link', { name: /results/i }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole('link', { name: /findings/i }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole('link', { name: /evidence/i }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole('link', { name: /audit trail/i }).length).toBeGreaterThanOrEqual(1);

    // Persisted metrics in SummaryView
    expect(await screen.findByText(/Persisted Findings/i)).toBeDefined();
    expect(screen.getByText(/Evidence Artifacts/i)).toBeDefined();
    expect(screen.getByText(/Audit Chain \(AT-01\)/i)).toBeDefined();

    // 4 Layers Execution Matrix
    expect(screen.getByText(/Assurance Layers/i)).toBeDefined();
    expect(screen.getAllByText('DI-01').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('MI-01').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('AT-01').length).toBeGreaterThanOrEqual(1);
  });

  it('verifies Findings, Evidence, and Audit Trail pages', async () => {
    // 1. Findings
    const { unmount: unmountFindings } = render(
      <MemoryRouter initialEntries={['/assessments/b3a8cba4-64e7-45dd-970f-668f2b164ed2/findings']}>
        <Routes>
          <Route path="/assessments/:id/findings" element={<Findings />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByRole('heading', { name: /Assessment Findings/i })).toBeDefined();
    expect(await screen.findByText('Structural Topology Divergence')).toBeDefined();
    unmountFindings();

    // 2. Evidence
    const { unmount: unmountEvidence } = render(
      <MemoryRouter initialEntries={['/assessments/b3a8cba4-64e7-45dd-970f-668f2b164ed2/evidence']}>
        <Routes>
          <Route path="/assessments/:id/evidence" element={<Evidence />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByRole('heading', { name: /Evidence Artifacts/i })).toBeDefined();
    expect(await screen.findByText('evi_001')).toBeDefined();
    expect(screen.getByText(/Structured Inspector/i)).toBeDefined();
    expect(screen.getByText(/Raw JSON/i)).toBeDefined();
    unmountEvidence();

    // 3. Audit Trail
    render(
      <MemoryRouter initialEntries={['/assessments/b3a8cba4-64e7-45dd-970f-668f2b164ed2/audit']}>
        <Routes>
          <Route path="/assessments/:id/audit" element={<AuditTrail />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByRole('heading', { name: /Audit Trail/i })).toBeDefined();
    expect((await screen.findAllByText('Chain Valid')).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('00000000 (Genesis Block)')).toBeDefined();

    // Verify Chain button
    const verifyBtn = screen.getByRole('button', { name: /verify chain/i });
    fireEvent.click(verifyBtn);
    expect(await screen.findByText(/Hash chain verification passed/i)).toBeDefined();
  });

  it('verifies Assessment History page, copy ID, and search filter', async () => {
    render(
      <MemoryRouter initialEntries={['/assessments']}>
        <Assessments />
      </MemoryRouter>
    );

    expect(await screen.findByText('Assessment History')).toBeDefined();
    expect(screen.getByText('E2E QA Model & Dataset Assurance Run')).toBeDefined();
    expect(screen.getByText('b3a8cba4-64e7-45dd-970f-668f2b164ed2')).toBeDefined();

    // Search filter input
    const searchInput = screen.getByPlaceholderText(/filter by title, id, or status/i);
    fireEvent.change(searchInput, { target: { value: 'nonexistent' } });
    expect(screen.getByText('No matching assessments')).toBeDefined();

    fireEvent.change(searchInput, { target: { value: 'Assurance' } });
    expect(screen.getByText('E2E QA Model & Dataset Assurance Run')).toBeDefined();
  });
});
