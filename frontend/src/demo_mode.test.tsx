import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { NewAssessment } from './pages/NewAssessment';
import { AssessmentResult } from './pages/AssessmentResult';
import * as client from './api/client';
import type {
  CapabilitiesResponse,
  AssessmentResultSchema,
  DemoPresetSchema
} from './types/api';

const MOCK_CAPS: CapabilitiesResponse = {
  detectors: [
    {
      detector_id: 'DI-01',
      version: '1.0',
      name: 'Duplicate Image Detector',
      description: 'Detects duplicate images.',
      applicable_asset_types: ['dataset', 'image'],
      available: true,
    },
    {
      detector_id: 'MI-01',
      version: '1.0',
      name: 'Model Fingerprint Verifier',
      description: 'Model integrity verification.',
      applicable_asset_types: ['model'],
      available: true,
    },
  ],
  supported_dataset_formats: ['image_dir'],
  supported_model_formats: ['.onnx'],
  pramaan_version: '1.0.0',
};

const MOCK_DEMOS: DemoPresetSchema[] = [
  {
    id: 'clean_baseline',
    name: 'Clean Reference Baseline',
    category: 'Model Integrity',
    description: 'Validates an untampered ONNX candidate against reference.',
    expected_risk: 'NONE',
    expected_confidence: 'HIGH',
    detectors_targeted: ['MI-01', 'MI-02', 'MI-04'],
    expected_layer: 'Model Integrity',
    expected_finding_type: 'Clean baseline verification (0 defects / Risk: NONE)',
    complexity: 'Level 1 · Reference Baseline',
    is_deterministic_corpus: true,
    payload: {
      title: 'Demo: Clean Reference Baseline',
      model_path: 'C:/corpus/models/clean.onnx',
      model_reference_path: 'C:/corpus/models/ref.onnx',
    },
  },
  {
    id: 'duplicate_data',
    name: 'Dataset Duplicates & Collisions',
    category: 'Dataset Integrity',
    description: 'Evaluates vision dataset containing duplicates.',
    expected_risk: 'HIGH',
    expected_confidence: 'HIGH',
    detectors_targeted: ['DI-01'],
    expected_layer: 'Dataset Integrity',
    expected_finding_type: 'Exact byte duplicates & DCT perceptual clusters',
    complexity: 'Level 2 · Perceptual Clustering',
    is_deterministic_corpus: true,
    payload: {
      title: 'Demo: Dataset Duplicate Analysis',
      dataset_path: 'C:/corpus/images',
      dataset_format: 'image_dir',
    },
  },
  {
    id: 'corrupted_model',
    name: 'Parameter Tampering (NaN/Inf)',
    category: 'Model Integrity',
    description: 'Analyzes model with corrupted tensor parameters.',
    expected_risk: 'HIGH',
    expected_confidence: 'HIGH',
    detectors_targeted: ['MI-02', 'MI-04'],
    expected_layer: 'Model Integrity',
    expected_finding_type: 'Non-finite weight corruption (NaN/Inf)',
    complexity: 'Level 3 · Numerical Parameter Tampering',
    is_deterministic_corpus: true,
    payload: {
      title: 'Demo: Corrupted Model Weights',
      model_path: 'C:/corpus/models/corrupt.onnx',
      model_reference_path: 'C:/corpus/models/ref.onnx',
    },
  },
  {
    id: 'trojan_model',
    name: 'Trojan Shortcut Convergence',
    category: 'Model Integrity',
    description: 'Executes adversarial trigger anomaly search.',
    expected_risk: 'HIGH',
    expected_confidence: 'HIGH',
    detectors_targeted: ['MI-01', 'MI-02', 'MI-05'],
    expected_layer: 'Model Integrity',
    expected_finding_type: 'Latent backdoor shortcut trigger',
    complexity: 'Level 4 · Deep Forensic Search',
    is_deterministic_corpus: true,
    payload: {
      title: 'Demo: Trojan Trigger Search',
      model_path: 'C:/corpus/models/trojan.onnx',
    },
  },
  {
    id: 'provenance_attestation',
    name: 'Cryptographic Inference Provenance',
    category: 'Inference Provenance',
    description: 'Validates Ed25519 digital signature and bindings.',
    expected_risk: 'NONE',
    expected_confidence: 'HIGH',
    detectors_targeted: ['PI-01'],
    expected_layer: 'Inference Provenance',
    expected_finding_type: 'Ed25519 signature attestation',
    complexity: 'Level 3 · Cryptographic Attestation',
    is_deterministic_corpus: true,
    payload: {
      title: 'Demo: Signed Inference Provenance',
      provenance_manifest: { manifest_id: 'man-01' },
      provenance_public_key_hex: 'aabbcc',
      actual_model_sha256: '112233',
    },
  },
];

const MOCK_RESULT: AssessmentResultSchema = {
  assessment_id: 'asmt-demo-res-01',
  title: 'Demo: Dataset Duplicate Analysis',
  status: 'complete',
  started_at: '2026-09-13T00:00:00Z',
  completed_at: '2026-09-13T00:01:00Z',
  assets_analyzed: [],
  detectors_executed: ['data.integrity.di01_duplicates'],
  detectors_skipped: [],
  findings_count: 2,
  evidence_count: 2,
  overall_risk: 'medium',
  risk_qualitative: 'Duplicate clusters detected',
  overall_confidence: 'high',
  confidence_qualifier: 'Standard checks pass',
  coverage_fraction: 0.9,
  coverage_gaps: [],
  detector_runs: [],
  limitations: [],
  audit_chain_valid: true,
  error: null,
};

describe('PRAMAAN Analyst-Facing Demo Mode Suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(client, 'getCapabilities').mockResolvedValue(MOCK_CAPS);
    vi.spyOn(client, 'getDemos').mockResolvedValue({ total: 5, demos: MOCK_DEMOS });
  });

  it('renders Mode Switcher and defaults cleanly to Custom Assessment', async () => {
    render(
      <MemoryRouter initialEntries={['/new']}>
        <NewAssessment />
      </MemoryRouter>
    );

    // Mode Switcher buttons
    expect(await screen.findByRole('button', { name: /Custom Assessment/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Demo Mode \(Corpus Scenarios\)/i })).toBeDefined();

    // In custom mode, single primary mode switcher is active, large preset grid is not rendered
    expect(screen.queryByText('Deterministic Offline Corpus Scenarios')).toBeNull();
    expect(screen.queryByText(/Switch to Demo Mode/i)).toBeNull();
  });

  it('switches to Demo Mode, rendering all 5 curated preset cards with metadata', async () => {
    render(
      <MemoryRouter initialEntries={['/new?mode=demo']}>
        <NewAssessment />
      </MemoryRouter>
    );

    // Banner and designation
    expect(await screen.findByText('Deterministic Offline Corpus Scenarios')).toBeDefined();
    expect(screen.getByText('5 Curated Scenarios')).toBeDefined();

    // 5 Presets
    expect(screen.getByText('Clean Reference Baseline')).toBeDefined();
    expect(screen.getByText('Dataset Duplicates & Collisions')).toBeDefined();
    expect(screen.getByText('Parameter Tampering (NaN/Inf)')).toBeDefined();
    expect(screen.getByText('Trojan Shortcut Convergence')).toBeDefined();
    expect(screen.getByText('Cryptographic Inference Provenance')).toBeDefined();

    // Verify truth indicators (complexity, layer, expected detection)
    expect(screen.getByText('Level 1 · Reference Baseline')).toBeDefined();
    expect(screen.getByText('Level 4 · Deep Forensic Search')).toBeDefined();
    expect(screen.getByText('Exact byte duplicates & DCT perceptual clusters')).toBeDefined();
  });

  it('loads a demo preset on click and provides 1-click Execute Demo Assessment', async () => {
    const createSpy = vi.spyOn(client, 'createAssessment').mockResolvedValue(MOCK_RESULT);

    render(
      <MemoryRouter initialEntries={['/new?mode=demo']}>
        <NewAssessment />
      </MemoryRouter>
    );

    expect(await screen.findByText('Dataset Duplicates & Collisions')).toBeDefined();

    // Click "Load Scenario" on the duplicate dataset card
    const loadButtons = screen.getAllByRole('button', { name: /Load Scenario/i });
    fireEvent.click(loadButtons[1]); // 2nd preset is duplicate_data

    // Preset loaded bar appears
    expect(await screen.findByText('Scenario Loaded:')).toBeDefined();
    expect(screen.getByRole('button', { name: /Execute Demo Assessment/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Clear Selection/i })).toBeDefined();

    // The title field in the form is updated
    const titleInput = screen.getByLabelText(/Assessment Title/i) as HTMLInputElement;
    expect(titleInput.value).toBe('Demo: Dataset Duplicate Analysis');

    // 1-Click execution
    const execBtn = screen.getByRole('button', { name: /Execute Demo Assessment/i });
    fireEvent.click(execBtn);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Demo: Dataset Duplicate Analysis',
          dataset_path: 'C:/corpus/images',
          dataset_format: 'image_dir',
        })
      );
    });
  });

  it('clears loaded preset and allows returning to custom assessment creation', async () => {
    render(
      <MemoryRouter initialEntries={['/new?mode=demo']}>
        <NewAssessment />
      </MemoryRouter>
    );

    expect(await screen.findByText('Clean Reference Baseline')).toBeDefined();

    // Load first preset
    const loadButtons = screen.getAllByRole('button', { name: /Load Scenario/i });
    fireEvent.click(loadButtons[0]);

    expect(await screen.findByText('Scenario Loaded:')).toBeDefined();

    // Clear selection
    const clearBtn = screen.getByRole('button', { name: /Clear Selection/i });
    fireEvent.click(clearBtn);

    expect(screen.queryByText('Scenario Loaded:')).toBeNull();
    const titleInput = screen.getByLabelText(/Assessment Title/i) as HTMLInputElement;
    expect(titleInput.value).toBe('');

    // Switch back to custom mode
    const customTab = screen.getByRole('button', { name: /Custom Assessment/i });
    fireEvent.click(customTab);

    expect(screen.queryByText('Deterministic Offline Corpus Scenarios')).toBeNull();
  });

  it('renders Deterministic Offline Corpus banner on AssessmentResult after demo completion', async () => {
    vi.spyOn(client, 'getAssessment').mockResolvedValue(MOCK_RESULT);

    render(
      <MemoryRouter initialEntries={['/assessments/asmt-demo-res-01/result']}>
        <Routes>
          <Route path="/assessments/:id/result" element={<AssessmentResult />} />
        </Routes>
      </MemoryRouter>
    );

    // Deterministic Offline Corpus banner is visible
    expect(await screen.findByText('Deterministic Offline Corpus Scenario')).toBeDefined();
    expect(screen.getByText('AIR-GAPPED · AUTHENTIC DETECTORS')).toBeDefined();
    expect(screen.getByRole('link', { name: /Create Custom Assessment/i })).toBeDefined();
  });

  it('does not render Deterministic Offline Corpus banner on standard non-demo assessment', async () => {
    const standardResult: AssessmentResultSchema = {
      ...MOCK_RESULT,
      title: 'Operational In-Field Validation (Run 4)',
    };
    vi.spyOn(client, 'getAssessment').mockResolvedValue(standardResult);

    render(
      <MemoryRouter initialEntries={['/assessments/asmt-std-01/result']}>
        <Routes>
          <Route path="/assessments/:id/result" element={<AssessmentResult />} />
        </Routes>
      </MemoryRouter>
    );

    // Title should be visible, but demo banner should NOT be present
    expect(await screen.findByText('Operational In-Field Validation (Run 4)')).toBeDefined();
    expect(screen.queryByText('Deterministic Offline Corpus Scenario')).toBeNull();
  });
});
