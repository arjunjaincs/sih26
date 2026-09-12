"""
PRAMAAN v1 — Assurance Report Data Models.

Defines the normalized, structured presentation model for offline PDF
assurance reports. Separates risk, confidence, coverage, findings, evidence,
provenance, and audit trail per PRAMAAN architecture principles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReportAssessmentMeta:
    """Core assessment run metadata."""
    assessment_id: str
    title: str
    status: str
    software_version: str
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    overall_risk: str = "NONE"
    risk_qualitative: str = ""
    overall_confidence: str = "HIGH"
    confidence_qualifier: str = ""
    coverage_fraction: float = 1.0
    error: str | None = None


@dataclass
class ReportAssetItem:
    """Asset analyzed during assessment."""
    asset_id: str
    asset_type: str
    name: str
    sha256: str
    size_bytes: int
    format: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportDetectorItem:
    """Summary of a detector execution or applicability check."""
    detector_id: str
    detector_name: str
    category: str
    status: str           # SUCCESS, PARTIAL, FAILED, NOT_APPLICABLE
    risk_level: str
    confidence_level: str
    findings_count: int
    evidence_count: int
    error: str | None = None


@dataclass
class ReportEvidenceItem:
    """Individual evidence record bound to a finding."""
    evidence_id: str
    detector_id: str
    evidence_type: str
    description: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportFindingItem:
    """An evidence-backed finding."""
    finding_id: str
    asset_id: str
    detector_id: str
    category: str
    subcategory: str
    severity: str
    title: str
    description: str
    limitations: list[str] = field(default_factory=list)
    recommended_disposition: str = ""
    evidence: list[ReportEvidenceItem] = field(default_factory=list)


@dataclass
class ReportCoverageGapItem:
    """Structured record of an unexercised capability."""
    detector_id: str
    detector_name: str
    reason: str
    required_capability: str
    observed_capability: str
    impact: str
    recommended_action: str


@dataclass
class ReportProvenanceItem:
    """Inference provenance and output binding record."""
    manifest_id: str
    assessment_id: str
    input_sha256: str
    model_sha256: str
    output_sha256: str
    preprocessing_config: dict[str, Any]
    inference_config: dict[str, Any]
    timestamp_utc: str
    nonce: str
    sequence: int
    digest: str | None = None
    signature_status: str = "NOT_PROVIDED"   # VERIFIED, FAILED, NOT_PROVIDED
    replay_status: str = "CLEAN"             # CLEAN, ANOMALY_DETECTED, NOT_EVALUATED
    anomalies: list[str] = field(default_factory=list)


@dataclass
class ReportAuditItem:
    """Tamper-evident audit chain verification status."""
    chain_valid: bool
    events_checked: int
    first_invalid_event_id: str | None = None
    failures: list[str] = field(default_factory=list)
    first_event_hash: str | None = None
    last_event_hash: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AssuranceReportData:
    """Comprehensive data container for PDF report generation."""
    meta: ReportAssessmentMeta
    assets: list[ReportAssetItem] = field(default_factory=list)
    detectors: list[ReportDetectorItem] = field(default_factory=list)
    findings: list[ReportFindingItem] = field(default_factory=list)
    coverage_gaps: list[ReportCoverageGapItem] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    provenance: ReportProvenanceItem | None = None
    audit: ReportAuditItem | None = None
    recommended_disposition: str = "REVIEW"
    disposition_rationale: str = ""
    generated_at_utc: str = ""
    report_schema_version: str = "1.0.0"
