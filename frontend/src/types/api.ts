/**
 * API response types matching the FastAPI backend schemas exactly.
 * These types map 1:1 with backend/app/models/schemas.py
 */

export type RiskLevel = 'clean' | 'low' | 'medium' | 'high' | 'critical'

export type AttackScenario =
  | 'label_manipulation'
  | 'duplicate_flooding'
  | 'backdoor_injection'
  | 'model_substitution'
  | 'inference_tampering'
  | 'replay_attack'
  | 'distribution_shift'

export interface StageFinding {
  finding_id: string
  severity: RiskLevel
  detector: string
  description: string
  evidence_hash?: string | null
  mitigated: boolean
}

export interface ApiStageState {
  stage_id: string
  stage_name: string
  risk: RiskLevel
  confidence: number
  coverage_pct: number
  findings: StageFinding[]
  audit_hash: string
}

export interface PipelineStateResponse {
  pipeline_id: string
  captured_at: string
  stages: ApiStageState[]
  active_scenarios: AttackScenario[]
}

export interface TriggerResponse {
  status: string
  scenario: AttackScenario
  message: string
  affected_stages: string[]
}

export interface ResetResponse {
  status: string
  message: string
}

export interface PipelineSummary {
  overall_risk: RiskLevel
  overall_confidence: number
  coverage_pct: number
}

export interface ReportStage {
  stage_name: string
  risk: RiskLevel
  confidence: number
  findings: StageFinding[]
}

export interface AssuranceReport {
  report_id: string
  generated_at: string
  pipeline_summary: PipelineSummary
  stages: ReportStage[]
  audit_chain_verified: boolean
  attack_scenarios_detected: AttackScenario[]
  analyst_recommendation: string
}

export type AuditEventType =
  | 'genesis'
  | 'data_ingestion'
  | 'spectral_scan'
  | 'model_load'
  | 'weight_hash'
  | 'neural_cleanse'
  | 'inference_stream'
  | 'entropy_analysis'
  | 'frame_cache'
  | 'risk_aggregation'
  | 'assurance_seal'
  | 'security_alert'

export interface AuditEvent {
  block_index: number
  event_id: string
  timestamp: string
  stage_name: string
  event_type: AuditEventType
  action: string
  details: string
  prev_hash: string
  current_hash: string
  status: RiskLevel
  tampered: boolean
}

export interface AuditChainResponse {
  chain_id: string
  total_blocks: number
  is_valid: boolean
  tampered_block_index?: number | null
  events: AuditEvent[]
}

