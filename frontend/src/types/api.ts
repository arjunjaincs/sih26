/**
 * TypeScript mirror of PRAMAAN Pydantic API schemas.
 * Derived from backend/api/schemas.py — do not add frontend logic here.
 */

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

export interface ErrorResponse {
  error: string;
  message: string;
  detail?: string | null;
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  version: string;
  db_path: string;
}

// ---------------------------------------------------------------------------
// Capabilities
// ---------------------------------------------------------------------------

export interface DetectorCapabilitySchema {
  detector_id: string;
  version: string;
  name: string;
  description: string;
  applicable_asset_types: string[];
  available: boolean;
  code?: string | null;
  pillar?: string | null;
  access_requirements?: string | null;
  dependencies?: string[];
  supported_formats?: string[];
  what_it_analyzes?: string | null;
  evidence_produced?: string[];
  confidence_semantics?: string | null;
  limitations?: string[];
  reference_method?: string | null;
}

export interface CapabilitiesResponse {
  detectors: DetectorCapabilitySchema[];
  supported_dataset_formats: string[];
  supported_model_formats: string[];
  pramaan_version: string;
}

// ---------------------------------------------------------------------------
// Upload response
// ---------------------------------------------------------------------------

export interface UploadResponse {
  asset_id: string;
  original_filename: string;
  sha256: string;
  size_bytes: number;
  asset_type: 'model' | 'dataset';
  format?: string | null;
  content_type?: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Assessment request
// ---------------------------------------------------------------------------

export interface AssessmentCreateRequest {
  title: string;
  assessment_id?: string | null;
  dataset_path?: string | null;
  dataset_asset_id?: string | null;
  dataset_format?: string | null; // 'image_dir' | 'coco_json' | 'yolo'
  dataset_reference_path?: string | null;
  dataset_reference_asset_id?: string | null;
  dataset_reference_format?: string | null; // 'image_dir' | 'coco_json' | 'yolo'
  model_path?: string | null;
  model_asset_id?: string | null;
  model_reference_path?: string | null;
  model_reference_asset_id?: string | null;
  model_reference_fingerprint?: Record<string, unknown> | null;
  provenance_manifest?: Record<string, unknown> | null;
  provenance_public_key_hex?: string | null;
  actual_input_bytes_hex?: string | null;
  actual_output_bytes_hex?: string | null;
  actual_model_sha256?: string | null;
  phash_threshold?: number; // 0–64, default 10
  dhash_threshold?: number; // 0–64, default 10
  min_cluster_size?: number; // ≥2, default 2
}

// ---------------------------------------------------------------------------
// Coverage gaps
// ---------------------------------------------------------------------------

export interface CoverageGapSchema {
  detector_id: string;
  detector_name: string;
  reason: string;
  required_capability: string;
  observed_capability: string;
  impact: string;
  recommended_action: string;
}

// ---------------------------------------------------------------------------
// Detector run
// ---------------------------------------------------------------------------

export interface DetectorRunSchema {
  detector_id: string;
  detector_name: string;
  asset_id: string;
  applicable: boolean;
  ran: boolean;
  status: string;
  risk_level: string;
  confidence_level: string;
  findings_count: number;
  evidence_count: number;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Assessment result (returned by POST and GET /api/v1/assessments/{id})
// ---------------------------------------------------------------------------

export interface AssessmentResultSchema {
  assessment_id: string;
  title: string;
  status: string; // 'created' | 'ingesting' | 'analyzing' | 'complete' | 'failed'
  started_at: string;
  completed_at: string;
  assets_analyzed: string[];
  detectors_executed: string[];
  detectors_skipped: string[];
  findings_count: number;
  evidence_count: number;
  overall_risk: string; // 'none' | 'low' | 'medium' | 'high' | 'critical'
  risk_qualitative: string;
  overall_confidence: string; // 'low' | 'moderate' | 'high'
  confidence_qualifier: string;
  coverage_fraction: number; // 0.0–1.0
  coverage_gaps: CoverageGapSchema[];
  detector_runs: DetectorRunSchema[];
  limitations: string[];
  audit_chain_valid: boolean | null;
  error: string | null;
  software_version?: string;
  created_at?: string | null;
}

// ---------------------------------------------------------------------------
// Assessment summary (returned in GET /api/v1/assessments list)
// ---------------------------------------------------------------------------

export interface AssessmentSummarySchema {
  assessment_id: string;
  title: string;
  status: string;
  software_version: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  findings_count: number;
  evidence_count: number;
  overall_risk?: string | null;
  overall_confidence?: string | null;
  coverage_fraction?: number | null;
}

export interface AssessmentListResponse {
  total: number;
  assessments: AssessmentSummarySchema[];
}

// ---------------------------------------------------------------------------
// Provenance schemas
// ---------------------------------------------------------------------------

export interface ProvenanceManifestItem {
  manifest_id: string;
  sequence: number;
  timestamp_utc: string;
  nonce: string;
  input_sha256: string;
  model_sha256: string;
  output_sha256: string;
  signature?: string | null;
  status: 'VERIFIED' | 'FAILED' | 'NOT_PROVIDED' | string;
  replay_status: 'CLEAN' | 'REPLAY_DETECTED' | 'NOT_APPLICABLE' | string;
  binding_status: 'BOUND' | 'MISMATCH' | 'NOT_APPLICABLE' | string;
  public_key_hex?: string | null;
  anomalies: string[];
}

export interface ProvenanceResponse {
  assessment_id: string;
  has_provenance: boolean;
  manifest: ProvenanceManifestItem | null;
  anomalies: string[];
}

// ---------------------------------------------------------------------------
// Demo preset schemas
// ---------------------------------------------------------------------------

export interface DemoPresetSchema {
  id: string;
  name: string;
  category: string;
  description: string;
  expected_risk: string;
  expected_confidence: string;
  detectors_targeted: string[];
  payload: AssessmentCreateRequest;
  expected_layer?: string;
  expected_finding_type?: string;
  complexity?: string;
  is_deterministic_corpus?: boolean;
}

export interface DemoListResponse {
  total: number;
  demos: DemoPresetSchema[];
}


// ---------------------------------------------------------------------------
// Findings
// ---------------------------------------------------------------------------

export interface FindingSchema {
  finding_id: string;
  assessment_id: string;
  asset_id: string;
  category: string; // 'data_integrity' | 'model_integrity' | 'inference_provenance' | 'distribution_drift' | 'coverage'
  subcategory: string;
  severity: string; // 'info' | 'low' | 'medium' | 'high' | 'critical'
  title: string;
  description: string;
  detection_method: string;
  detector_id: string;
  limitations: string[];
  recommended_disposition: string | null;
  created_at: string;
}

export interface FindingsResponse {
  assessment_id: string;
  count: number;
  findings: FindingSchema[];
}

// ---------------------------------------------------------------------------
// Evidence
// ---------------------------------------------------------------------------

export interface EvidenceSchema {
  evidence_id: string;
  finding_id: string;
  detector_id: string;
  evidence_type: string; // 'measurement' | 'comparison' | 'anomaly' | 'hash_mismatch' | 'hash_match' | 'statistical_test' | 'cluster'
  description: string;
  data: Record<string, unknown> | null;
  artifact_sha256: string | null;
}

export interface EvidenceResponse {
  assessment_id: string;
  count: number;
  evidence: EvidenceSchema[];
}

export interface EvidenceImagePreview {
  sample_id?: string | null;
  file_name: string;
  preview_url: string;
  width?: number | null;
  height?: number | null;
  size_bytes?: number | null;
  sha256?: string | null;
  caption?: string | null;
}

export interface EvidencePreviewResponse {
  evidence_id: string;
  assessment_id: string;
  finding_id: string;
  detector_id: string;
  evidence_type: string;
  preview_type: 'image' | 'image_cluster' | 'structured' | 'json' | 'structured_text' | 'unsupported';
  mime_type?: string | null;
  size_bytes?: number | null;
  title: string;
  description: string;
  artifact_sha256?: string | null;
  images: EvidenceImagePreview[];
  text_content?: string | null;
  structured_content?: Record<string, unknown> | null;
  unsupported_reason?: string | null;
  truncated?: boolean;
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

export interface AuditEventSchema {
  event_id: string;
  event_type: string;
  timestamp_utc: string;
  actor: string;
  current_hash: string;
  previous_hash: string;
}

export interface AuditResponse {
  assessment_id: string;
  chain_valid: boolean;
  events_checked: number;
  failures: string[];
  first_invalid_event_id: string | null;
  events: AuditEventSchema[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Risk levels in ascending severity order */
export const RISK_LEVELS = ['none', 'low', 'medium', 'high', 'critical'] as const;
export type RiskLevel = typeof RISK_LEVELS[number];

export const CONFIDENCE_LEVELS = ['low', 'moderate', 'high'] as const;
export type ConfidenceLevel = typeof CONFIDENCE_LEVELS[number];

export const SEVERITY_LEVELS = ['info', 'low', 'medium', 'high', 'critical'] as const;
export type SeverityLevel = typeof SEVERITY_LEVELS[number];

export const DATASET_FORMATS = ['image_dir', 'coco_json'] as const;
export type DatasetFormat = typeof DATASET_FORMATS[number];

export const ASSESSMENT_STATES = ['created', 'ingesting', 'analyzing', 'complete', 'failed'] as const;
export type AssessmentState = typeof ASSESSMENT_STATES[number];

// ---------------------------------------------------------------------------
// Phase 20: AI Copilot
// ---------------------------------------------------------------------------

export type AICopilotScope = 'assessment' | 'finding' | 'provenance' | 'audit';

export type AIProviderStatus = 'connected' | 'not_configured' | 'unavailable' | 'disabled';

export interface AISourceReference {
  type: 'finding' | 'evidence' | 'limitation' | 'detector' | 'provenance' | 'audit' | string;
  id: string;
  label?: string | null;
}

export interface AIChatRequest {
  message: string;
  scope?: AICopilotScope;
  finding_id?: string | null;
}

export interface AIChatResponse {
  answer: string;
  provider: string;
  model: string;
  scope: string;
  grounded: boolean;
  sources: AISourceReference[];
}

export interface AIStatusResponse {
  configured: boolean;
  provider: string;
  model: string;
  status: AIProviderStatus | string;
  has_api_key: boolean;
  privacy_disclosure: string;
  available_models: string[];
}

export interface AIModelsResponse {
  models: string[];
  current_model: string;
}

export interface ConnectionTestResponse {
  ok: boolean;
  message: string;
}

// ---------------------------------------------------------------------------
// Global Search
// ---------------------------------------------------------------------------

export interface SearchResultAssessment {
  assessment_id: string;
  title: string;
  state: string;
  created_at: string;
  target_url: string;
}

export interface SearchResultFinding {
  finding_id: string;
  assessment_id: string;
  title: string;
  detector_id: string;
  detector_code?: string | null;
  severity: string;
  category: string;
  asset_name?: string | null;
  target_url: string;
}

export interface SearchResultEvidence {
  evidence_id: string;
  finding_id: string;
  assessment_id: string;
  detector_id: string;
  detector_code?: string | null;
  evidence_type: string;
  description: string;
  finding_title?: string | null;
  target_url: string;
}

export interface SearchCategoryCounts {
  assessments: number;
  findings: number;
  evidence: number;
}

export interface GlobalSearchResponse {
  query: string;
  total_matches: number;
  counts: SearchCategoryCounts;
  assessments: SearchResultAssessment[];
  findings: SearchResultFinding[];
  evidence: SearchResultEvidence[];
}
