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
}

export interface CapabilitiesResponse {
  detectors: DetectorCapabilitySchema[];
  supported_dataset_formats: string[];
  supported_model_formats: string[];
  pramaan_version: string;
}

// ---------------------------------------------------------------------------
// Assessment request
// ---------------------------------------------------------------------------

export interface AssessmentCreateRequest {
  title: string;
  assessment_id?: string | null;
  dataset_path?: string | null;
  dataset_format?: string | null; // 'image_dir' | 'coco_json'
  model_path?: string | null;
  model_reference_fingerprint?: Record<string, unknown> | null;
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
// Assessment result (returned by POST /api/v1/assessments)
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
}

// ---------------------------------------------------------------------------
// Assessment summary (returned by GET /api/v1/assessments/{id})
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
