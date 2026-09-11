import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Capabilities } from '../pages/Capabilities';

const MOCK_CAPS = {
  detectors: [
    {
      detector_id: 'DI-01',
      version: '1.0',
      name: 'Duplicate Image Detector',
      description: 'Detects duplicate and near-duplicate images.',
      applicable_asset_types: ['dataset', 'image'],
      available: true,
    },
    {
      detector_id: 'MI-01',
      version: '1.0',
      name: 'Model Fingerprint Verifier',
      description: 'Cryptographic fingerprinting of model files.',
      applicable_asset_types: ['model'],
      available: false,
    },
  ],
  supported_dataset_formats: ['image_dir', 'coco_json'],
  supported_model_formats: ['.onnx', '.pt'],
  pramaan_version: '1.0.0',
};

vi.mock('../api/client', () => ({
  getCapabilities: vi.fn(() => Promise.resolve(MOCK_CAPS)),
  NetworkError: class NetworkError extends Error { name = 'NetworkError'; },
}));

describe('Capabilities page', () => {
  afterEach(() => vi.clearAllMocks());

  it('renders detector names after loading', async () => {
    render(
      <MemoryRouter>
        <Capabilities />
      </MemoryRouter>,
    );
    expect(await screen.findByText('Duplicate Image Detector')).toBeDefined();
    expect(await screen.findByText('Model Fingerprint Verifier')).toBeDefined();
  });

  it('shows availability status', async () => {
    render(
      <MemoryRouter>
        <Capabilities />
      </MemoryRouter>,
    );
    const available = await screen.findAllByText('Available');
    const unavailable = await screen.findAllByText('Unavailable');
    expect(available.length).toBeGreaterThan(0);
    expect(unavailable.length).toBeGreaterThan(0);
  });

  it('shows supported format counts', async () => {
    render(<MemoryRouter><Capabilities /></MemoryRouter>);
    expect(await screen.findByText(/image_dir/)).toBeDefined();
  });
});
