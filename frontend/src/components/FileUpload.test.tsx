import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { FileUpload } from './FileUpload';
import * as client from '../api/client';
import type { UploadResponse } from '../types/api';

describe('FileUpload component', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders empty dropzone state with browse text and helpText', () => {
    render(
      <FileUpload
        assetType="model"
        helpText="Supported formats: .onnx, .pt"
        value={null}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText(/Click to browse/i)).toBeDefined();
    expect(screen.getByText('Supported formats: .onnx, .pt')).toBeDefined();
  });

  it('renders uploaded asset details when value is provided', () => {
    const mockValue: UploadResponse = {
      asset_id: 'ast-model-99',
      original_filename: 'yolov8n.onnx',
      size_bytes: 6500000,
      sha256: 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
      format: 'onnx',
      asset_type: 'model',
      uploaded_at: '2026-09-11T12:00:00Z',
    };

    render(
      <FileUpload
        assetType="model"
        value={mockValue}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText('yolov8n.onnx')).toBeDefined();
    expect(screen.getByText(/SHA-256: abcdef123456/i)).toBeDefined();
    expect(screen.getByText(/^onnx$/i)).toBeDefined();
    expect(screen.getByTitle('Replace file')).toBeDefined();
    expect(screen.getByLabelText('Remove uploaded file')).toBeDefined();
  });

  it('triggers onChange(null) when remove button is clicked', () => {
    const handleChange = vi.fn();
    const mockValue: UploadResponse = {
      asset_id: 'ast-dataset-1',
      original_filename: 'archive.zip',
      size_bytes: 1048576,
      sha256: '11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff',
      format: 'zip',
      asset_type: 'dataset',
      uploaded_at: '2026-09-11T12:00:00Z',
    };

    render(
      <FileUpload
        assetType="dataset"
        value={mockValue}
        onChange={handleChange}
      />
    );

    const removeBtn = screen.getByLabelText('Remove uploaded file');
    fireEvent.click(removeBtn);

    expect(handleChange).toHaveBeenCalledWith(null);
  });

  it('uploads file successfully and invokes onChange with API response', async () => {
    const handleChange = vi.fn();
    const mockUploadRes: UploadResponse = {
      asset_id: 'ast-uploaded-new',
      original_filename: 'model.onnx',
      size_bytes: 2048,
      sha256: 'aabbccdd99887766554433221100',
      format: 'onnx',
      asset_type: 'model',
      uploaded_at: '2026-09-11T12:00:00Z',
    };

    vi.spyOn(client, 'uploadAsset').mockResolvedValueOnce(mockUploadRes);

    const { container } = render(
      <FileUpload
        assetType="model"
        value={null}
        onChange={handleChange}
      />
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).toBeDefined();

    const file = new File(['fake-model-binary'], 'model.onnx', { type: 'application/octet-stream' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(client.uploadAsset).toHaveBeenCalledWith(file, 'model');
      expect(handleChange).toHaveBeenCalledWith(mockUploadRes);
    });
  });

  it('displays error message when uploadAsset rejects', async () => {
    const handleChange = vi.fn();
    vi.spyOn(client, 'uploadAsset').mockRejectedValueOnce(
      new Error('File exceeds maximum size limit of 250 MB')
    );

    const { container } = render(
      <FileUpload
        assetType="model"
        value={null}
        onChange={handleChange}
      />
    );

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['huge-content'], 'huge_model.onnx');
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText('File exceeds maximum size limit of 250 MB')).toBeDefined();
    });
    expect(handleChange).toHaveBeenCalledWith(null);
  });
});
