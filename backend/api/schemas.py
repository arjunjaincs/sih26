"""
PRAMAAN API Pydantic schemas.

These are the explicit wire-format types for the HTTP API.
They are DERIVED from domain/assessment models, not duplicates of their logic.

Design rules
------------
- All fields are serialization-only (no detection logic lives here).
- No internal Python objects (enums, dataclasses) are exposed directly.
- All enum values are surfaced as strings (their .value).
- Timestamps are ISO 8601 strings.
- Evidence data dict is passed through as-is (structured, no raw bytes).
- Pydantic v2 is used throughout (model_config, model_validator).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Error schema
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """Structured API error — never a raw exception or stack trace."""

    model_config = ConfigDict(populate_by_name=True)

    error: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable description")
    detail: str | None = Field(default=None, description="Optional additional context")


# ---------------------------------------------------------------------------
# Health schema
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = Field(description="'ok' when the service is available")
    version: str
    db_path: str = Field(description="Absolute path to the active database file")


# ---------------------------------------------------------------------------
# Capabilities schema
# ---------------------------------------------------------------------------

class DetectorCapabilitySchema(BaseModel):
    detector_id: str
    version: str
    name: str
    description: str
    applicable_asset_types: list[str]
    available: bool = Field(
        description="True if can_run() pre-flight checks pass on a minimal context"
    )


class CapabilitiesResponse(BaseModel):
    detectors: list[DetectorCapabilitySchema]
    supported_dataset_formats: list[str]
    supported_model_formats: list[str]
    pramaan_version: str


# ---------------------------------------------------------------------------
# Assessment request schema (incoming)
# ---------------------------------------------------------------------------

class AssessmentCreateRequest(BaseModel):
    """
    JSON body for POST /api/v1/assessments.

    All paths must be absolute paths on the local filesystem.
    The API validates them against trusted roots and size limits
    before passing to AssessmentService.

    At least one of dataset_path, model_path, or provenance_manifest_path
    must be present.
    """

    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(min_length=1, max_length=256)
    assessment_id: str | None = Field(
        default=None,
        description="Optional stable UUID; auto-generated if omitted",
    )

    # Dataset
    dataset_path: str | None = Field(
        default=None,
        description="Absolute path to image directory or COCO JSON file",
    )
    dataset_format: str | None = Field(
        default=None,
        description="'image_dir' or 'coco_json'",
    )

    # Model
    model_path: str | None = Field(
        default=None,
        description="Absolute path to .onnx / .pt / .pth model file",
    )
    model_reference_fingerprint: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional prior MI-01 fingerprint_recorded evidence dict "
            "for comparison. When present, MI-01 will compare and detect changes."
        ),
    )

    # DI-01 thresholds
    phash_threshold: int = Field(default=10, ge=0, le=64)
    dhash_threshold: int = Field(default=10, ge=0, le=64)
    min_cluster_size: int = Field(default=2, ge=2)


# ---------------------------------------------------------------------------
# Coverage gap schema
# ---------------------------------------------------------------------------

class CoverageGapSchema(BaseModel):
    detector_id: str
    detector_name: str
    reason: str
    required_capability: str
    observed_capability: str
    impact: str
    recommended_action: str


# ---------------------------------------------------------------------------
# Detector run schema
# ---------------------------------------------------------------------------

class DetectorRunSchema(BaseModel):
    detector_id: str
    detector_name: str
    asset_id: str
    applicable: bool
    ran: bool
    status: str
    risk_level: str
    confidence_level: str
    findings_count: int
    evidence_count: int
    error: str | None


# ---------------------------------------------------------------------------
# Assessment result schema (outgoing)
# ---------------------------------------------------------------------------

class AssessmentResultSchema(BaseModel):
    """
    API response for a completed or failed assessment.

    Derived from AssessmentResult (Phase 7) — no detection logic added.
    """

    assessment_id: str
    title: str
    status: str
    started_at: str
    completed_at: str
    assets_analyzed: list[str]
    detectors_executed: list[str]
    detectors_skipped: list[str]
    findings_count: int
    evidence_count: int
    overall_risk: str
    risk_qualitative: str
    overall_confidence: str
    confidence_qualifier: str
    coverage_fraction: float
    coverage_gaps: list[CoverageGapSchema]
    detector_runs: list[DetectorRunSchema]
    limitations: list[str]
    audit_chain_valid: bool | None
    error: str | None


# ---------------------------------------------------------------------------
# Assessment summary (for GET /assessments/{id} using DB record)
# ---------------------------------------------------------------------------

class AssessmentSummarySchema(BaseModel):
    """
    Returned by GET /api/v1/assessments/{assessment_id}.
    Derived from the Assessment DB entity + persisted findings/evidence counts.
    """

    assessment_id: str
    title: str
    status: str
    software_version: str
    created_at: str
    started_at: str | None
    completed_at: str | None
    error: str | None
    findings_count: int
    evidence_count: int


# ---------------------------------------------------------------------------
# Finding schema
# ---------------------------------------------------------------------------

class FindingSchema(BaseModel):
    finding_id: str
    assessment_id: str
    asset_id: str
    category: str
    subcategory: str
    severity: str
    title: str
    description: str
    detection_method: str
    detector_id: str
    limitations: list[str]
    recommended_disposition: str | None
    created_at: str


class FindingsResponse(BaseModel):
    assessment_id: str
    count: int
    findings: list[FindingSchema]


# ---------------------------------------------------------------------------
# Evidence schema
# ---------------------------------------------------------------------------

class EvidenceSchema(BaseModel):
    evidence_id: str
    finding_id: str
    detector_id: str
    evidence_type: str
    description: str
    # data is passed through as structured JSON — no raw bytes
    data: dict[str, Any] | None
    # artifact_path is deliberately OMITTED from response (filesystem path privacy)
    artifact_sha256: str | None


class EvidenceResponse(BaseModel):
    assessment_id: str
    count: int
    evidence: list[EvidenceSchema]


# ---------------------------------------------------------------------------
# Audit schema
# ---------------------------------------------------------------------------

class AuditEventSchema(BaseModel):
    event_id: str
    event_type: str
    timestamp_utc: str
    actor: str
    current_hash: str
    previous_hash: str
    # payload is deliberately omitted (may contain signing key IDs — keep opaque)


class AuditResponse(BaseModel):
    assessment_id: str
    chain_valid: bool
    events_checked: int
    failures: list[str]
    first_invalid_event_id: str | None
    events: list[AuditEventSchema]
