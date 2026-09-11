import { describe, it, expect, vi, afterEach } from 'vitest';
import { getHealth, getCapabilities, createAssessment, uploadAsset, ApiError, NetworkError } from '../api/client';

// Minimal fetch mock helpers
function mockFetch(body: unknown, status = 200) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: async () => body,
  } as Response);
}

function mockFetchNetworkError() {
  return vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('Failed to fetch'));
}

describe('API client', () => {
  afterEach(() => vi.restoreAllMocks());

  describe('getHealth', () => {
    it('returns parsed HealthResponse on 200', async () => {
      mockFetch({ status: 'ok', version: '1.0.0', db_path: '/tmp/pramaan.db' });
      const result = await getHealth();
      expect(result.status).toBe('ok');
      expect(result.version).toBe('1.0.0');
    });

    it('throws NetworkError when fetch fails', async () => {
      mockFetchNetworkError();
      await expect(getHealth()).rejects.toBeInstanceOf(NetworkError);
    });

    it('throws ApiError on 500', async () => {
      mockFetch({ error: 'internal_error', message: 'Internal error' }, 500);
      await expect(getHealth()).rejects.toBeInstanceOf(ApiError);
    });
  });

  describe('getCapabilities', () => {
    it('returns capabilities with detectors list', async () => {
      mockFetch({
        detectors: [{ detector_id: 'DI-01', version: '1.0', name: 'Duplicate Detector', description: 'desc', applicable_asset_types: ['dataset'], available: true }],
        supported_dataset_formats: ['image_dir', 'coco_json'],
        supported_model_formats: ['.onnx'],
        pramaan_version: '1.0.0',
      });
      const result = await getCapabilities();
      expect(result.detectors).toHaveLength(1);
      expect(result.detectors[0].detector_id).toBe('DI-01');
      expect(result.detectors[0].available).toBe(true);
    });
  });

  describe('createAssessment', () => {
    it('sends POST with correct body and returns result schema', async () => {
      const mockResult = {
        assessment_id: 'abc-123',
        title: 'Test',
        status: 'complete',
        started_at: '2026-09-11T10:00:00Z',
        completed_at: '2026-09-11T10:01:00Z',
        assets_analyzed: [],
        detectors_executed: [],
        detectors_skipped: [],
        findings_count: 0,
        evidence_count: 0,
        overall_risk: 'none',
        risk_qualitative: 'No concerns.',
        overall_confidence: 'moderate',
        confidence_qualifier: 'Limited coverage.',
        coverage_fraction: 0.5,
        coverage_gaps: [],
        detector_runs: [],
        limitations: [],
        audit_chain_valid: true,
        error: null,
      };
      const fetchSpy = mockFetch(mockResult, 201);
      const result = await createAssessment({ title: 'Test', dataset_path: '/data', dataset_format: 'image_dir' });
      expect(result.assessment_id).toBe('abc-123');
      expect(result.overall_risk).toBe('none');
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/assessments'),
        expect.objectContaining({ method: 'POST' }),
      );
    });

    it('throws ApiError on 422 validation error', async () => {
      mockFetch({ error: 'invalid_request', message: 'At least one asset required.' }, 422);
      await expect(createAssessment({ title: 'Test' })).rejects.toBeInstanceOf(ApiError);
    });
  });

  describe('uploadAsset', () => {
    it('sends POST multipart request and returns UploadResponse', async () => {
      const mockUploadRes = {
        asset_id: 'ast-12345',
        original_filename: 'model.onnx',
        size_bytes: 1024,
        sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        format: 'onnx',
        asset_type: 'model',
        uploaded_at: '2026-09-11T12:00:00Z',
      };
      const fetchSpy = mockFetch(mockUploadRes, 201);
      const testFile = new File(['fake-onnx-bytes'], 'model.onnx', { type: 'application/octet-stream' });
      const result = await uploadAsset(testFile, 'model');

      expect(result.asset_id).toBe('ast-12345');
      expect(result.original_filename).toBe('model.onnx');
      expect(result.sha256).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/uploads'),
        expect.objectContaining({ method: 'POST' }),
      );
    });

    it('throws ApiError on upload rejection', async () => {
      mockFetch({ detail: { error: 'invalid_format', message: 'Unsupported file format: .exe' } }, 422);
      const testFile = new File(['bad-bytes'], 'malware.exe');
      await expect(uploadAsset(testFile)).rejects.toBeInstanceOf(ApiError);
    });
  });

  describe('ApiError', () => {
    it('has correct status, code, message fields', async () => {
      mockFetch({ error: 'not_found', message: 'Assessment not found', detail: 'id=xyz' }, 404);
      try {
        await getHealth();
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        const e = err as ApiError;
        expect(e.status).toBe(404);
        expect(e.code).toBe('not_found');
        expect(e.message).toBe('Assessment not found');
        expect(e.detail).toBe('id=xyz');
      }
    });
  });
});
