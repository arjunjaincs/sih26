import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { Evidence } from './pages/Evidence';
import * as client from './api/client';
import type { EvidenceResponse, EvidencePreviewResponse } from './types/api';

vi.mock('./api/client', async () => {
  const actual = await vi.importActual<typeof client>('./api/client');
  return {
    ...actual,
    getEvidence: vi.fn(),
    getEvidencePreview: vi.fn(),
  };
});

const MOCK_IMAGE_PREVIEW: EvidencePreviewResponse = {
  evidence_id: 'ev-img-01',
  assessment_id: 'asmt-preview-test',
  finding_id: 'f-di-01',
  detector_id: 'DI-01',
  evidence_type: 'cluster',
  preview_type: 'image_cluster',
  title: 'Perceptual Duplicate Cluster (2 images)',
  images: [
    {
      sample_id: 's-01',
      file_name: 'original_scan.jpg',
      preview_url: '/api/v1/assessments/asmt-preview-test/evidence/ev-img-01/samples/s-01/preview-file',
      width: 512,
      height: 512,
      size_bytes: 45000,
      sha256: 'a1b2c3d4e5f678901234567890abcdef12345678',
      caption: 'Original training image (original_scan.jpg)',
    },
    {
      sample_id: 's-02',
      file_name: 'duplicate_crop.jpg',
      preview_url: '/api/v1/assessments/asmt-preview-test/evidence/ev-img-01/samples/s-02/preview-file',
      width: 512,
      height: 512,
      size_bytes: 45200,
      sha256: 'b2c3d4e5f678901234567890abcdef1234567890',
      caption: 'Duplicate image crop (duplicate_crop.jpg)',
    },
  ],
  structured_content: {
    cluster_id: 1,
    hamming_distance: 2,
    similarity_score: 0.98,
  },
};

const MOCK_UNSUPPORTED_PREVIEW: EvidencePreviewResponse = {
  evidence_id: 'ev-onnx-01',
  assessment_id: 'asmt-preview-test',
  finding_id: 'f-mi-01',
  detector_id: 'MI-01',
  evidence_type: 'measurement',
  preview_type: 'unsupported',
  size_bytes: 25000000,
  title: 'Binary Evidence Artifact',
  unsupported_reason: 'Binary model weights or serialized tensor artifact (.onnx / .pt) cannot be previewed inline for security and memory safety. Inspect layer structure below.',
  artifact_sha256: 'c3d4e5f678901234567890abcdef1234567890ab',
  structured_content: {
    model_format: 'ONNX',
    graph_layers: 48,
    parameter_count: 11200000,
  },
};

const MOCK_TEXT_PREVIEW: EvidencePreviewResponse = {
  evidence_id: 'ev-text-01',
  assessment_id: 'asmt-preview-test',
  finding_id: 'f-aud-01',
  detector_id: 'AUD-01',
  evidence_type: 'measurement',
  preview_type: 'structured_text',
  mime_type: 'text/plain',
  size_bytes: 90000,
  title: 'System Execution Audit Log',
  artifact_sha256: 'd4e5f678901234567890abcdef1234567890abcd',
  text_content: '2026-09-12T10:00:00Z [INFO] Engine initialized\n2026-09-12T10:00:01Z [INFO] Starting detector DI-01',
  truncated: true,
};

const MOCK_EVIDENCE_LIST: EvidenceResponse = {
  assessment_id: 'asmt-preview-test',
  count: 3,
  evidence: [
    {
      evidence_id: 'ev-img-01',
      finding_id: 'f-di-01',
      detector_id: 'DI-01',
      evidence_type: 'cluster',
      description: 'Perceptual duplicate cluster of 2 images detected.',
      data: {
        cluster_id: 1,
        sample_ids: ['s-01', 's-02'],
      },
      artifact_sha256: null,
    },
    {
      evidence_id: 'ev-onnx-01',
      finding_id: 'f-mi-01',
      detector_id: 'MI-01',
      evidence_type: 'measurement',
      description: 'Layer weight checksum mismatch.',
      data: {
        model_format: 'ONNX',
        graph_layers: 48,
      },
      artifact_sha256: 'c3d4e5f678901234567890abcdef1234567890ab',
    },
    {
      evidence_id: 'ev-text-01',
      finding_id: 'f-aud-01',
      detector_id: 'AUD-01',
      evidence_type: 'measurement',
      description: 'Execution log stream.',
      data: {},
      artifact_sha256: 'd4e5f678901234567890abcdef1234567890abcd',
    },
  ],
};

function renderEvidencePage(assessmentId = 'asmt-preview-test') {
  return render(
    <MemoryRouter initialEntries={[`/assessments/${assessmentId}/evidence`]}>
      <Routes>
        <Route path="/assessments/:id/evidence" element={<Evidence />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('Evidence Preview Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });

    vi.mocked(client.getEvidence).mockResolvedValue(MOCK_EVIDENCE_LIST);
    vi.mocked(client.getEvidencePreview).mockImplementation(async (_asmtId, evId) => {
      if (evId === 'ev-img-01') return MOCK_IMAGE_PREVIEW;
      if (evId === 'ev-onnx-01') return MOCK_UNSUPPORTED_PREVIEW;
      if (evId === 'ev-text-01') return MOCK_TEXT_PREVIEW;
      return {
        evidence_id: evId,
        assessment_id: 'asmt-preview-test',
        finding_id: 'f-gen-01',
        detector_id: 'GEN',
        evidence_type: 'measurement',
        preview_type: 'structured',
        title: 'Structured Preview',
      };
    });
  });

  it('renders all evidence cards with default Artifact Preview tab', async () => {
    renderEvidencePage();

    await waitFor(() => {
      expect(screen.getByText('Evidence Artifacts')).toBeInTheDocument();
      expect(screen.getByText('3 artifacts recorded')).toBeInTheDocument();
    });

    // Check that the duplicate cluster preview title is rendered
    await waitFor(() => {
      expect(screen.getByText('Perceptual Duplicate Cluster (2 images)')).toBeInTheDocument();
      expect(screen.getByText('(2 verified samples)')).toBeInTheDocument();
    });

    // Check images in cluster are listed
    expect(screen.getByText('original_scan.jpg')).toBeInTheDocument();
    expect(screen.getByText('duplicate_crop.jpg')).toBeInTheDocument();
    expect(screen.getAllByText(/512×512/i).length).toBeGreaterThan(0);
  });

  it('renders unsupported binary artifact card with security alert and explanation', async () => {
    renderEvidencePage();

    await waitFor(() => {
      expect(screen.getByText('Binary Artifact — Direct Preview Unavailable')).toBeInTheDocument();
    });

    expect(screen.getByText(/Binary model weights or serialized tensor artifact/)).toBeInTheDocument();
    expect(screen.getByText('View Structural Breakdown')).toBeInTheDocument();
  });

  it('switches to Structural Breakdown tab when button is clicked on unsupported card', async () => {
    renderEvidencePage();

    await waitFor(() => {
      expect(screen.getByText('Binary Artifact — Direct Preview Unavailable')).toBeInTheDocument();
    });

    const breakdownBtn = screen.getByText('View Structural Breakdown');
    fireEvent.click(breakdownBtn);

    // Should switch to structured inspector displaying parameters
    await waitFor(() => {
      expect(screen.getByText(/graph layers/i)).toBeInTheDocument();
      expect(screen.getByText('48')).toBeInTheDocument();
    });
  });

  it('renders bounded text preview with truncation warning tag', async () => {
    renderEvidencePage();

    await waitFor(() => {
      expect(screen.getByText('System Execution Audit Log')).toBeInTheDocument();
      expect(screen.getByText('Bounded Preview (Truncated to 64KB)')).toBeInTheDocument();
    });

    expect(screen.getByText(/2026-09-12T10:00:00Z \[INFO\] Engine initialized/)).toBeInTheDocument();
  });

  it('opens and closes the image Lightbox modal on inspect click', async () => {
    renderEvidencePage();

    await waitFor(() => {
      expect(screen.getByText('original_scan.jpg')).toBeInTheDocument();
    });

    // Find inspect button on the image card
    const inspectBtns = screen.getAllByTitle('Inspect full resolution image');
    expect(inspectBtns.length).toBeGreaterThan(0);
    fireEvent.click(inspectBtns[0]);

    // Lightbox modal should appear
    await waitFor(() => {
      expect(screen.getByText('High-Resolution Image Inspector')).toBeInTheDocument();
      expect(screen.getAllByText('original_scan.jpg').length).toBeGreaterThan(0);
    });

    // Close button
    const closeBtn = screen.getByTitle(/close/i);
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByText('High-Resolution Image Inspector')).not.toBeInTheDocument();
    });
  });

  it('switches between Artifact Preview, Structured Inspector, and Raw JSON tabs', async () => {
    renderEvidencePage();

    await waitFor(() => {
      expect(screen.getByText('Perceptual Duplicate Cluster (2 images)')).toBeInTheDocument();
    });

    // Find tabs on the first card
    const structuredTabBtns = screen.getAllByRole('button', { name: /Structured Inspector/i });
    fireEvent.click(structuredTabBtns[0]);

    await waitFor(() => {
      expect(screen.getByText(/cluster id/i)).toBeInTheDocument();
      expect(screen.getByText('1')).toBeInTheDocument();
    });

    const rawTabBtns = screen.getAllByRole('button', { name: /Raw JSON/i });
    fireEvent.click(rawTabBtns[0]);

    // Check JSON content is displayed
    await waitFor(() => {
      expect(screen.getByText(/"cluster_id": 1/)).toBeInTheDocument();
    });
  });

  it('supports copying hashes and json payloads', async () => {
    renderEvidencePage();

    await waitFor(() => {
      expect(screen.getByText('original_scan.jpg')).toBeInTheDocument();
    });

    const copyBtns = screen.getAllByTitle(/Copy/i);
    expect(copyBtns.length).toBeGreaterThan(0);
    fireEvent.click(copyBtns[0]);

    expect(navigator.clipboard.writeText).toHaveBeenCalled();
  });
});
