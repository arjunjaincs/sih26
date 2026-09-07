export type RiskLevel = 'clean' | 'low' | 'medium' | 'high' | 'critical'

export interface StageFinding {
  finding_id: string
  severity: RiskLevel
  detector: string
  description: string
  evidence_hash?: string
  mitigated: boolean
}

export interface StageMetric {
  label: string
  value: string
}

export interface StageState {
  stage_id: string
  stage_number: string
  stage_name: string
  stage_subtitle: string
  risk: RiskLevel
  confidence: number // 0 to 1
  coverage_pct: number // 0 to 100
  findings: StageFinding[]
  audit_hash: string
  metrics: StageMetric[]
  summary: string
}
