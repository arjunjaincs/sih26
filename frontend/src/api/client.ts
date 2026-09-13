/**
 * PRAMAAN API client.
 * Single module for all HTTP calls — no per-component fetch.
 */

import type {
  AuditResponse,
  AssessmentCreateRequest,
  AssessmentListResponse,
  AssessmentResultSchema,
  AIChatRequest,
  AIChatResponse,
  AIModelsResponse,
  AIStatusResponse,
  ConnectionTestResponse,
  CapabilitiesResponse,
  DemoListResponse,
  EvidencePreviewResponse,
  EvidenceResponse,
  FindingsResponse,
  GlobalSearchResponse,
  HealthResponse,
  ProvenanceResponse,
  UploadResponse,
} from '../types/api';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

// ---------------------------------------------------------------------------
// Error classes
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  code: string;
  detail?: string | null;

  constructor(status: number, code: string, message: string, detail?: string | null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export class NetworkError extends Error {
  constructor(cause?: unknown) {
    super('Could not reach the PRAMAAN backend. Is the local service running?');
    this.name = 'NetworkError';
    if (cause instanceof Error) this.cause = cause;
  }
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      ...options,
    });
  } catch (err) {
    throw new NetworkError(err);
  }

  if (!response.ok) {
    let code = 'api_error';
    let message = `HTTP ${response.status}`;
    let detail: string | undefined;
    try {
      const body = await response.json() as { error?: string; message?: string; detail?: string };
      code = body.error ?? code;
      message = body.message ?? message;
      detail = body.detail;
    } catch {
      message = response.statusText || message;
    }
    throw new ApiError(response.status, code, message, detail);
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health');
}

export function getCapabilities(): Promise<CapabilitiesResponse> {
  return apiFetch<CapabilitiesResponse>('/api/v1/capabilities');
}

export function createAssessment(req: AssessmentCreateRequest): Promise<AssessmentResultSchema> {
  return apiFetch<AssessmentResultSchema>('/api/v1/assessments', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export function getAssessment(id: string): Promise<AssessmentResultSchema> {
  return apiFetch<AssessmentResultSchema>(`/api/v1/assessments/${encodeURIComponent(id)}`);
}

export function listAssessments(): Promise<AssessmentListResponse> {
  return apiFetch<AssessmentListResponse>('/api/v1/assessments');
}

export function getFindings(id: string): Promise<FindingsResponse> {
  return apiFetch<FindingsResponse>(`/api/v1/assessments/${encodeURIComponent(id)}/findings`);
}

export function getEvidence(id: string): Promise<EvidenceResponse> {
  return apiFetch<EvidenceResponse>(`/api/v1/assessments/${encodeURIComponent(id)}/evidence`);
}

export function getEvidencePreview(
  assessmentId: string,
  evidenceId: string
): Promise<EvidencePreviewResponse> {
  return apiFetch<EvidencePreviewResponse>(
    `/api/v1/assessments/${encodeURIComponent(assessmentId)}/evidence/${encodeURIComponent(evidenceId)}/preview`
  );
}

export function getAudit(id: string): Promise<AuditResponse> {
  return apiFetch<AuditResponse>(`/api/v1/assessments/${encodeURIComponent(id)}/audit`);
}

export function getProvenance(id: string): Promise<ProvenanceResponse> {
  return apiFetch<ProvenanceResponse>(`/api/v1/assessments/${encodeURIComponent(id)}/provenance`);
}

export function getDemos(): Promise<DemoListResponse> {
  return apiFetch<DemoListResponse>('/api/v1/demos');
}

export function getReportUrl(id: string): string {
  return `${BASE_URL}/api/v1/assessments/${encodeURIComponent(id)}/report`;
}

export async function downloadReport(id: string, filename?: string): Promise<void> {
  const url = getReportUrl(id);
  let response: Response;
  try {
    response = await fetch(url, { method: 'GET' });
  } catch (err) {
    throw new NetworkError(err);
  }

  if (!response.ok) {
    throw new ApiError(response.status, 'report_download_failed', 'Failed to generate or download assurance report.');
  }

  const blob = await response.blob();
  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  const safeShortId = id.slice(0, 8);
  a.download = filename || `pramaan_assurance_report_${safeShortId}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(blobUrl);
}

export function getExportJsonUrl(id: string): string {
  return `${BASE_URL}/api/v1/assessments/${encodeURIComponent(id)}/export/json`;
}

export async function exportAssessmentJson(id: string, filename?: string): Promise<void> {
  const url = getExportJsonUrl(id);
  let response: Response;
  try {
    response = await fetch(url, { method: 'GET' });
  } catch (err) {
    throw new NetworkError(err);
  }

  if (!response.ok) {
    throw new ApiError(response.status, 'export_json_failed', 'Failed to generate or export assessment assurance package JSON.');
  }

  const blob = await response.blob();
  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  const safeShortId = id.slice(0, 8);
  a.download = filename || `pramaan_assurance_export_${safeShortId}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(blobUrl);
}

export function getExportAuditJsonUrl(id: string): string {
  return `${BASE_URL}/api/v1/assessments/${encodeURIComponent(id)}/audit/export`;
}

export async function exportAuditJson(id: string, filename?: string): Promise<void> {
  const url = getExportAuditJsonUrl(id);
  let response: Response;
  try {
    response = await fetch(url, { method: 'GET' });
  } catch (err) {
    throw new NetworkError(err);
  }

  if (!response.ok) {
    throw new ApiError(response.status, 'export_audit_failed', 'Failed to generate or export verified audit trail JSON.');
  }

  const blob = await response.blob();
  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  const safeShortId = id.slice(0, 8);
  a.download = filename || `pramaan_audit_export_${safeShortId}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(blobUrl);
}


export async function uploadAsset(
  file: File,
  assetType?: 'model' | 'dataset',
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (assetType) {
    formData.append('asset_type', assetType);
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/v1/uploads`, {
      method: 'POST',
      body: formData,
    });
  } catch (err) {
    throw new NetworkError(err);
  }

  if (!response.ok) {
    let code = 'upload_error';
    let message = `HTTP ${response.status}`;
    let detail: string | undefined;
    try {
      const body = await response.json() as { error?: string; message?: string; detail?: string | { error?: string; message?: string } };
      if (typeof body.detail === 'object' && body.detail !== null) {
        code = body.detail.error ?? code;
        message = body.detail.message ?? message;
      } else {
        code = body.error ?? code;
        message = body.message ?? message;
        detail = typeof body.detail === 'string' ? body.detail : undefined;
      }
    } catch {
      message = response.statusText || message;
    }
    throw new ApiError(response.status, code, message, detail);
  }

  return response.json() as Promise<UploadResponse>;
}

// ---------------------------------------------------------------------------
// Phase 20: AI Copilot
// ---------------------------------------------------------------------------

export function getAIStatus(): Promise<AIStatusResponse> {
  return apiFetch<AIStatusResponse>('/api/v1/ai/status');
}

export function getAIModels(): Promise<AIModelsResponse> {
  return apiFetch<AIModelsResponse>('/api/v1/ai/models');
}

export function testAIConnection(): Promise<ConnectionTestResponse> {
  return apiFetch<ConnectionTestResponse>('/api/v1/ai/test', {
    method: 'POST',
  });
}

export function chatWithCopilot(
  assessmentId: string,
  request: AIChatRequest,
): Promise<AIChatResponse> {
  return apiFetch<AIChatResponse>(
    `/api/v1/assessments/${encodeURIComponent(assessmentId)}/ai/chat`,
    {
      method: 'POST',
      body: JSON.stringify(request),
    },
  );
}

export function explainFindingWithCopilot(
  assessmentId: string,
  findingId: string,
  userQuery?: string,
): Promise<AIChatResponse> {
  return apiFetch<AIChatResponse>(
    `/api/v1/assessments/${encodeURIComponent(assessmentId)}/findings/${encodeURIComponent(findingId)}/ai/explain`,
    {
      method: 'POST',
      body: JSON.stringify({ user_query: userQuery }),
    },
  );
}

// ---------------------------------------------------------------------------
// Global Search
// ---------------------------------------------------------------------------

export function searchAll(query: string, limit: number = 10): Promise<GlobalSearchResponse> {
  const params = new URLSearchParams();
  params.set('q', query);
  params.set('limit', String(limit));
  return apiFetch<GlobalSearchResponse>(`/api/v1/search?${params.toString()}`);
}
