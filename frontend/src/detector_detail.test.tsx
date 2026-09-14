import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DetectorDetailModal } from './components/DetectorDetailModal';
import { DETECTOR_SPECS, getDetectorDetail, normalizeDetectorCode } from './lib/detectorRegistry';
import { DetectorMatrix } from './components/DetectorMatrix';
import { MemoryRouter } from 'react-router-dom';

describe('normalizeDetectorCode Canonical Resolution', () => {
  it('correctly distinguishes MI-05 and DI-03 without trigger_anomaly collisions', () => {
    expect(normalizeDetectorCode('model.integrity.mi05_trigger_anomaly')).toBe('MI-05');
    expect(normalizeDetectorCode('data.integrity.di03_trigger_anomaly')).toBe('DI-03');

    const mi05Detail = getDetectorDetail('model.integrity.mi05_trigger_anomaly');
    expect(mi05Detail.code).toBe('MI-05');
    expect(mi05Detail.pillar).toBe('Model Integrity');

    const di03Detail = getDetectorDetail('data.integrity.di03_trigger_anomaly');
    expect(di03Detail.code).toBe('DI-03');
    expect(di03Detail.pillar).toBe('Dataset Integrity');
  });

  it('correctly resolves all canonical 11 detectors plus audit ledger', () => {
    const canonicalMap: Record<string, string> = {
      'data.integrity.di01_duplicates': 'DI-01',
      'data.integrity.di02_label_integrity': 'DI-02',
      'data.integrity.di03_trigger_anomaly': 'DI-03',
      'data.integrity.di04_feature_distribution': 'DI-04',
      'data.integrity.di05_contributor_split': 'DI-05',
      'model.integrity.mi01_fingerprint': 'MI-01',
      'model.integrity.mi02_parameter_integrity': 'MI-02',
      'model.integrity.mi03_activation_distribution': 'MI-03',
      'model.integrity.mi04_reference_comparison': 'MI-04',
      'model.integrity.mi05_trigger_anomaly': 'MI-05',
      'inference.provenance.pi01_integrity': 'PI-01',
      'audit.ledger.at01_trail': 'AT-01',
    };

    for (const [id, expectedCode] of Object.entries(canonicalMap)) {
      expect(normalizeDetectorCode(id)).toBe(expectedCode);
      const detail = getDetectorDetail(id);
      expect(detail.code).toBe(expectedCode);
    }
  });
});

describe('DetectorDetailModal Component', () => {
  const allCodes = [
    'DI-01', 'DI-02', 'DI-03', 'DI-04', 'DI-05',
    'MI-01', 'MI-02', 'MI-03', 'MI-04', 'MI-05',
    'PI-01', 'AT-01'
  ];

  it.each(allCodes)('opens and displays all 14 required fields for %s', (code) => {
    const handleClose = vi.fn();
    const { unmount } = render(
      <DetectorDetailModal
        detectorIdOrCode={code}
        onClose={handleClose}
      />
    );

    const spec = DETECTOR_SPECS[code];
    expect(spec).toBeDefined();

    // 1. Detector ID
    expect(screen.getByText(spec.id)).toBeDefined();

    // 2. Name
    expect(screen.getByRole('heading', { level: 2, name: spec.name })).toBeDefined();

    // 3. Assurance Layer / Pillar
    expect(screen.getAllByText(spec.pillar).length).toBeGreaterThan(0);

    // 4. Purpose
    expect(screen.getByText(spec.purpose)).toBeDefined();

    // 5. Applicable Asset Types
    for (const assetType of spec.applicableAssetTypes) {
      expect(screen.getAllByText(assetType).length).toBeGreaterThan(0);
    }

    // 6. Access Requirements
    expect(screen.getByText(spec.accessRequirements)).toBeDefined();

    // 7. Dependencies
    for (const dep of spec.dependencies) {
      expect(screen.getAllByText(dep).length).toBeGreaterThan(0);
    }

    // 8. Supported Formats
    for (const fmt of spec.supportedFormats) {
      expect(screen.getAllByText(fmt).length).toBeGreaterThan(0);
    }

    // 9. What it analyzes
    expect(screen.getByText(spec.whatItAnalyzes)).toBeDefined();

    // 10. Evidence produced
    for (const ev of spec.evidenceProduced) {
      expect(screen.getByText(ev)).toBeDefined();
    }

    // 11. Confidence semantics
    expect(screen.getByText(spec.confidenceSemantics)).toBeDefined();

    // 12. Known limitations
    for (const lim of spec.limitations) {
      expect(screen.getByText(lim)).toBeDefined();
    }

    // 13. Current status
    const statusBadge = screen.getByTestId('detector-status-badge');
    expect(statusBadge.textContent).toBe('AVAILABLE');

    // 14. Reference / method information
    expect(screen.getByText(spec.referenceMethod)).toBeDefined();

    unmount();
  });

  it('clearly displays UNAVAILABLE when a detector is unavailable in runtime', () => {
    const handleClose = vi.fn();
    render(
      <DetectorDetailModal
        detectorIdOrCode="MI-03"
        onClose={handleClose}
        liveCapability={{
          detector_id: 'model.integrity.mi03_activation_stats',
          version: '1.0.0',
          name: 'MI-03: Model Activation & Representation Statistics',
          description: 'Profiles internal intermediate layer activations.',
          applicable_asset_types: ['model'],
          available: false,
        }}
      />
    );

    const statusBadge = screen.getByTestId('detector-status-badge');
    expect(statusBadge.textContent).toBe('UNAVAILABLE');
  });

  it('handles unknown or missing detector gracefully without crashing', () => {
    const handleClose = vi.fn();
    render(
      <DetectorDetailModal
        detectorIdOrCode="NON_EXISTENT_DETECTOR"
        onClose={handleClose}
      />
    );

    expect(screen.getAllByText('NON_EXISTENT_DETECTOR').length).toBeGreaterThan(0);
    const statusBadge = screen.getByTestId('detector-status-badge');
    expect(statusBadge.textContent).toBe('UNAVAILABLE');
    expect(screen.getByText(/No registered detector specification exists/)).toBeDefined();
  });

  it('renders long and complex descriptions safely without HTML injection or corruption', () => {
    const handleClose = vi.fn();
    const dangerousText = '<script>alert("xss")</script> & <b>bold</b> & "quotes"';
    render(
      <DetectorDetailModal
        detectorIdOrCode="CUSTOM-XSS"
        onClose={handleClose}
        liveCapability={{
          detector_id: 'custom.test.xss',
          version: '1.0.0',
          name: dangerousText,
          description: dangerousText,
          applicable_asset_types: ['model'],
          available: true,
          what_it_analyzes: dangerousText,
          confidence_semantics: dangerousText,
          reference_method: dangerousText,
        }}
      />
    );

    // Text is rendered literally as text content, not parsed as HTML
    expect(screen.getAllByText(dangerousText).length).toBeGreaterThan(0);
    // No script element injected
    expect(document.querySelector('script[src="xss"]')).toBeNull();
  });

  it('closes on close button click and Escape key press', () => {
    const handleClose = vi.fn();
    render(
      <DetectorDetailModal
        detectorIdOrCode="DI-02"
        onClose={handleClose}
      />
    );

    const closeBtn = screen.getByTestId('close-detector-modal');
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(2);
  });
});

describe('DetectorMatrix integration with DetectorDetailModal', () => {
  const mockRuns = [
    {
      detector_id: 'data.integrity.di01_duplicates',
      detector_name: 'DI-01: Duplicate / Near-Duplicate Image Detector',
      asset_id: 'asset-1',
      applicable: true,
      ran: true,
      status: 'SUCCESS',
      risk_level: 'NONE',
      confidence_level: 'HIGH',
      findings_count: 0,
      evidence_count: 5,
      error: null,
    },
    {
      detector_id: 'model.integrity.mi05_trigger_anomaly',
      detector_name: 'MI-05: Model Trigger & Behavioral Perturbation Search',
      asset_id: 'asset-2',
      applicable: true,
      ran: true,
      status: 'SUCCESS',
      risk_level: 'HIGH',
      confidence_level: 'HIGH',
      findings_count: 2,
      evidence_count: 4,
      error: null,
    },
  ];

  it('opens detector method details when clicking a detector in the matrix', async () => {
    render(
      <MemoryRouter>
        <DetectorMatrix runs={mockRuns} assessmentId="test-assessment" />
      </MemoryRouter>
    );

    // Matrix tile button for DI-01
    const di01Btn = screen.getByTestId('detector-tile-di-01');
    fireEvent.click(di01Btn);

    // Modal should now be visible with DI-01 details
    expect(await screen.findByRole('dialog')).toBeDefined();
    expect(screen.getByText('data.integrity.di01_duplicates')).toBeDefined();
    expect(screen.getByText(/Exact byte duplicates yield HIGH confidence/)).toBeDefined();

    // Close modal
    const closeBtn = screen.getByTestId('close-detector-modal');
    fireEvent.click(closeBtn);

    // Now click MI-05
    const mi05Btn = screen.getByTestId('detector-tile-mi-05');
    fireEvent.click(mi05Btn);

    expect(await screen.findByRole('dialog')).toBeDefined();
    expect(screen.getByText('model.integrity.mi05_trigger_anomaly')).toBeDefined();
    expect(screen.getAllByText(/CR < 0.15/).length).toBeGreaterThan(0);
  });
});
