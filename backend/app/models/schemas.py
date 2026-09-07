"""
Pydantic schemas for all PRAMAAN API request/response shapes.
"""
from __future__ import annotations
from enum import Enum
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    CLEAN = "clean"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AttackScenario(str, Enum):
    LABEL_MANIPULATION = "label_manipulation"
    DUPLICATE_FLOODING = "duplicate_flooding"
    BACKDOOR_INJECTION = "backdoor_injection"
    MODEL_SUBSTITUTION = "model_substitution"
    INFERENCE_TAMPERING = "inference_tampering"
    REPLAY_ATTACK = "replay_attack"
    DISTRIBUTION_SHIFT = "distribution_shift"


# ---------------------------------------------------------------------------
# Pipeline state schemas
# ---------------------------------------------------------------------------

class StageFinding(BaseModel):
    finding_id: str
    severity: RiskLevel
    detector: str = Field(description="Algorithm/method used to surface this finding")
    description: str
    evidence_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 prefix of the artifact or sample triggering this finding"
    )
    mitigated: bool = False


class StageState(BaseModel):
    stage_id: str
    stage_name: str
    risk: RiskLevel
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the risk assessment [0-1]")
    coverage_pct: float = Field(ge=0.0, le=100.0, description="Percentage of stage checked")
    findings: List[StageFinding] = []
    audit_hash: str = Field(description="Tamper-evident SHA-256 of this stage's state snapshot")


class PipelineStateResponse(BaseModel):
    pipeline_id: str
    captured_at: datetime
    stages: List[StageState]
    active_scenarios: List[AttackScenario] = []


# ---------------------------------------------------------------------------
# Demo control schemas
# ---------------------------------------------------------------------------

class TriggerResponse(BaseModel):
    status: str
    scenario: AttackScenario
    message: str
    affected_stages: List[str]


class ResetResponse(BaseModel):
    status: str
    message: str


# ---------------------------------------------------------------------------
# Report schemas
# ---------------------------------------------------------------------------

class PipelineSummary(BaseModel):
    overall_risk: RiskLevel
    overall_confidence: float = Field(ge=0.0, le=1.0)
    coverage_pct: float = Field(ge=0.0, le=100.0)


class ReportStage(BaseModel):
    stage_name: str
    risk: RiskLevel
    confidence: float
    findings: List[StageFinding]


class AssuranceReport(BaseModel):
    report_id: str
    generated_at: datetime
    pipeline_summary: PipelineSummary
    stages: List[ReportStage]
    audit_chain_verified: bool
    attack_scenarios_detected: List[AttackScenario]
    analyst_recommendation: str


# ---------------------------------------------------------------------------
# Audit Chain schemas
# ---------------------------------------------------------------------------

class AuditEventType(str, Enum):
    GENESIS = "genesis"
    DATA_INGESTION = "data_ingestion"
    SPECTRAL_SCAN = "spectral_scan"
    MODEL_LOAD = "model_load"
    WEIGHT_HASH = "weight_hash"
    NEURAL_CLEANSE = "neural_cleanse"
    INFERENCE_STREAM = "inference_stream"
    ENTROPY_ANALYSIS = "entropy_analysis"
    FRAME_CACHE = "frame_cache"
    RISK_AGGREGATION = "risk_aggregation"
    ASSURANCE_SEAL = "assurance_seal"
    SECURITY_ALERT = "security_alert"


class AuditEvent(BaseModel):
    block_index: int
    event_id: str
    timestamp: datetime
    stage_name: str
    event_type: AuditEventType
    action: str
    details: str
    prev_hash: str
    current_hash: str
    status: RiskLevel
    tampered: bool = False


class AuditChainResponse(BaseModel):
    chain_id: str
    total_blocks: int
    is_valid: bool
    tampered_block_index: Optional[int] = None
    events: List[AuditEvent]

