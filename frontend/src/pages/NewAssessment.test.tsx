import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { NewAssessment } from './NewAssessment';
import * as client from '../api/client';
import type { CapabilitiesResponse, AssessmentResultSchema } from '../types/api';

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
  supported_dataset_formats: ['image_dir', 'coco_json'],
  supported_model_formats: ['.onnx', '.pt'],
  pramaan_version: '1.0.0',
};

const MOCK_RESULT: AssessmentResultSchema = {
  assessment_id: 'asmt-test-123',
  title: 'Test Assessment',
  status: 'complete',
  started_at: '2026-09-11T12:00:00Z',
  completed_at: '2026-09-11T12:01:00Z',
  assets_analyzed: [],
  detectors_executed: [],
  detectors_skipped: [],
  findings_count: 0,
  evidence_count: 0,
  overall_risk: 'none',
  risk_qualitative: 'Clean assessment.',
  overall_confidence: 'high',
  confidence_qualifier: 'All standard checks passed.',
  coverage_fraction: 1.0,
  coverage_gaps: [],
  detector_runs: [],
  limitations: [],
  audit_chain_valid: true,
  error: null,
};

describe('NewAssessment page', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders default upload mode for model and dataset', async () => {
    vi.spyOn(client, 'getCapabilities').mockResolvedValueOnce(MOCK_CAPS);

    render(
      <MemoryRouter>
        <NewAssessment />
      </MemoryRouter>
    );

    expect(await screen.findByText('Duplicate Image Detector')).toBeDefined();
    expect(screen.getByText('New Assessment')).toBeDefined();
    // Both model and dataset should have mode toggles with "Upload File" selected
    const uploadButtons = screen.getAllByRole('button', { name: 'Upload File' });
    expect(uploadButtons.length).toBe(2);

    const localButtons = screen.getAllByRole('button', { name: 'Local Path (Advanced)' });
    expect(localButtons.length).toBe(2);
  });

  it('allows switching to Local Path mode for air-gapped/local workstation entry', async () => {
    vi.spyOn(client, 'getCapabilities').mockResolvedValueOnce(MOCK_CAPS);

    render(
      <MemoryRouter>
        <NewAssessment />
      </MemoryRouter>
    );

    expect(await screen.findByText('Duplicate Image Detector')).toBeDefined();
    const localButtons = screen.getAllByRole('button', { name: 'Local Path (Advanced)' });
    // Switch model to local path mode
    fireEvent.click(localButtons[0]);

    expect(screen.getByPlaceholderText('e.g. C:/models/classifier.onnx')).toBeDefined();
  });

  it('validates required fields before submitting', async () => {
    vi.spyOn(client, 'getCapabilities').mockResolvedValueOnce(MOCK_CAPS);

    render(
      <MemoryRouter>
        <NewAssessment />
      </MemoryRouter>
    );

    const runBtn = screen.getByRole('button', { name: /Run Assessment/i });
    expect(runBtn).toBeDefined();

    // Enter title only, no assets
    const titleInput = screen.getByLabelText(/Assessment Title/i);
    fireEvent.change(titleInput, { target: { value: 'Incomplete Test' } });

    fireEvent.click(runBtn);

    expect(await screen.findByText('Provide at least one model or dataset asset.')).toBeDefined();
  });

  it('submits assessment with model_path and dataset_path in local mode', async () => {
    vi.spyOn(client, 'getCapabilities').mockResolvedValueOnce(MOCK_CAPS);
    const createSpy = vi.spyOn(client, 'createAssessment').mockResolvedValueOnce(MOCK_RESULT);

    render(
      <MemoryRouter>
        <NewAssessment />
      </MemoryRouter>
    );

    // Title
    const titleInput = screen.getByLabelText(/Assessment Title/i);
    fireEvent.change(titleInput, { target: { value: 'Local Model Assessment' } });

    // Switch model to local mode
    const localButtons = screen.getAllByRole('button', { name: 'Local Path (Advanced)' });
    fireEvent.click(localButtons[0]);

    const modelPathInput = screen.getByPlaceholderText('e.g. C:/models/classifier.onnx');
    fireEvent.change(modelPathInput, { target: { value: 'C:/models/resnet50.onnx' } });

    const runBtn = screen.getByRole('button', { name: /Run Assessment/i });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Local Model Assessment',
          model_path: 'C:/models/resnet50.onnx',
          model_asset_id: null,
        })
      );
    });
  });

  it('submits assessment with asset_ids when files are uploaded', async () => {
    vi.spyOn(client, 'getCapabilities').mockResolvedValueOnce(MOCK_CAPS);
    const createSpy = vi.spyOn(client, 'createAssessment').mockResolvedValueOnce(MOCK_RESULT);

    vi.spyOn(client, 'uploadAsset').mockResolvedValueOnce({
      asset_id: 'ast-model-upload-42',
      original_filename: 'model.onnx',
      size_bytes: 512,
      sha256: 'deadbeef1234',
      format: 'onnx',
      asset_type: 'model',
      uploaded_at: '2026-09-11T12:00:00Z',
    });

    const { container } = render(
      <MemoryRouter>
        <NewAssessment />
      </MemoryRouter>
    );

    // Title
    const titleInput = screen.getByLabelText(/Assessment Title/i);
    fireEvent.change(titleInput, { target: { value: 'Uploaded Model Assessment' } });

    // Upload model file
    const fileInputs = container.querySelectorAll('input[type="file"]');
    const modelFileInput = fileInputs[0] as HTMLInputElement;
    const fakeFile = new File(['binary'], 'model.onnx');
    fireEvent.change(modelFileInput, { target: { files: [fakeFile] } });

    await waitFor(() => {
      expect(screen.getByText('model.onnx')).toBeDefined();
    });

    const runBtn = screen.getByRole('button', { name: /Run Assessment/i });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Uploaded Model Assessment',
          model_asset_id: 'ast-model-upload-42',
          model_path: null,
        })
      );
    });
  });
});
