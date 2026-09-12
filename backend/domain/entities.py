"""
PRAMAAN domain entities.

All Pydantic models used across the domain layer.  No FastAPI, no SQLite,
no filesystem access in this module — pure data shapes and validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from backend.domain.enums import (
    AccessLevel,
    AssetType,
    AssessmentState,
    AssessmentType,
    AuditEventType,
    ConfidenceLevel,
    DatasetFormat,
    DetectorStatus,
    EvidenceType,
    FindingCategory,
    ModelFramework,
    RiskLevel,
    Severity,
)


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


class RiskAssessment(BaseModel):
    """
    Estimated threat level derived from observed evidence.

    risk_level alone is insufficient — read the qualitative description and
    methods_applied to understand what evidence supports this assessment.
    """

    level: RiskLevel
    qualitative: str = Field(description="One-sentence summary of the risk assessment")
    methods_applied: list[str] = Field(
        default_factory=list,
        description="Detection methods that contributed to this assessment",
    )
    methods_unavailable: list[str] = Field(
        default_factory=list,
        description="Detection methods that could not run (see CoverageStatement for details)",
    )


class ConfidenceAssessment(BaseModel):
    """
    Degree of trust in the associated RiskAssessment.

    LOW confidence does NOT mean the asset is safe — it means we gathered
    insufficient evidence to know.
    """

    level: ConfidenceLevel
    qualifier: str = Field(description="Why this confidence level was assigned")
    limiting_factors: list[str] = Field(
        default_factory=list,
        description="Factors that prevent higher confidence",
    )


class CoverageStatement(BaseModel):
    """
    Records which detection methods ran and which did not, and why.
    """

    total_applicable: int = Field(ge=0)
    executed: int = Field(ge=0)
    coverage_fraction: float = Field(ge=0.0, le=1.0)
    gaps: list[CoverageGap] = Field(default_factory=list)


class CoverageGap(BaseModel):
    """A detection method that could not run and the reason why."""

    detector_id: str
    reason: str
    risk_implication: str


# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------


class Assessment(BaseModel):
    """Top-level unit of work in PRAMAAN."""

    assessment_id: str = Field(default_factory=_new_id)
    assessment_type: AssessmentType = AssessmentType.LIVE
    title: str
    description: str | None = None
    state: AssessmentState = AssessmentState.CREATED
    software_version: str = "1.0.0"
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    model_config = {"from_attributes": True}


class Asset(BaseModel):
    """
    Anything submitted to PRAMAAN for evaluation.

    Assets are the root of all analysis — every finding references an asset.
    """

    asset_id: str = Field(default_factory=_new_id)
    assessment_id: str
    asset_type: AssetType
    name: str
    sha256: str = Field(description="SHA-256 hex digest of the file/directory")
    size_bytes: int = Field(ge=0)
    registered_at: datetime = Field(default_factory=_utcnow)

    model_config = {"from_attributes": True}


class Dataset(BaseModel):
    """
    A structured collection of images, optionally with annotations.
    Corresponds to a registered Asset of type DATASET.
    """

    dataset_id: str  # Same as asset_id
    assessment_id: str
    format: DatasetFormat
    source_path: str = Field(description="Path of the original source directory or file")
    sample_count: int = Field(ge=0)
    class_names: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class Sample(BaseModel):
    """A single image within a Dataset."""

    sample_id: str = Field(default_factory=_new_id)
    dataset_id: str
    file_name: str = Field(description="Original filename as found in the dataset")
    sha256: str = Field(description="SHA-256 hex digest of the image bytes")
    phash: str | None = Field(default=None, description="Perceptual hash (64-bit, hex)")
    dhash: str | None = Field(default=None, description="Difference hash (64-bit, hex)")
    width: int | None = None
    height: int | None = None
    file_size_bytes: int = Field(ge=0)
    labels: list[str] = Field(default_factory=list, description="Assigned class labels")
    contributor: str | None = Field(default=None, description="Contributor or source origin if known")

    model_config = {"from_attributes": True}

    @field_validator("phash", "dhash", mode="before")
    @classmethod
    def _none_for_empty(cls, v: Any) -> Any:
        if v == "":
            return None
        return v


class ModelArtifact(BaseModel):
    """
    A model file submitted for integrity analysis.
    Corresponds to a registered Asset of type MODEL.
    """

    model_id: str  # Same as asset_id
    assessment_id: str
    framework: ModelFramework
    access_level: AccessLevel = AccessLevel.BLACK_BOX
    source_path: str = Field(description="Path of the original model file")
    declared_sha256: str | None = Field(
        default=None,
        description="Operator-supplied expected hash; None if not provided",
    )

    model_config = {"from_attributes": True}


class Evidence(BaseModel):
    """
    A discrete piece of evidence supporting a finding.

    Evidence must always contain real measurements from real analysis.
    Never populate evidence data with hardcoded constants.
    """

    evidence_id: str = Field(default_factory=_new_id)
    finding_id: str
    detector_id: str
    evidence_type: EvidenceType
    description: str
    data: dict[str, Any] = Field(
        description="Structured measurement data — must come from actual analysis"
    )
    artifact_path: str | None = None  # Blob-store path to any associated artifact
    artifact_sha256: str | None = None

    model_config = {"from_attributes": True}


class Finding(BaseModel):
    """
    An analyst-readable integrity conclusion produced by a detector.

    Every finding must be backed by at least one Evidence item.
    The source field must be LIVE_ANALYSIS for all non-demo assessments.
    """

    finding_id: str = Field(default_factory=_new_id)
    assessment_id: str
    asset_id: str
    category: FindingCategory
    subcategory: str
    severity: Severity
    title: str
    description: str
    detection_method: str = Field(description="Human-readable name of the detector")
    detector_id: str
    limitations: list[str] = Field(default_factory=list)
    recommended_disposition: str = ""
    source: str = "LIVE_ANALYSIS"  # Always LIVE_ANALYSIS in V1
    created_at: datetime = Field(default_factory=_utcnow)

    model_config = {"from_attributes": True}


class DetectorResult(BaseModel):
    """
    Records the outcome of running a single detector against a single asset.

    Distinct from a Finding — a detector may complete successfully but produce
    zero findings (i.e., nothing suspicious was detected).
    """

    result_id: str = Field(default_factory=_new_id)
    assessment_id: str
    asset_id: str
    detector_id: str
    detector_version: str
    status: DetectorStatus
    error: str | None = None
    findings_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    duration_ms: int | None = None
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProvenanceManifest(BaseModel):
    """
    Cryptographic binding of an inference execution.

    A manifest ties together the specific input, model, configuration, and
    output so that any post-hoc alteration to any bound element will cause
    verification to fail.

    The canonical_bytes field holds the deterministic serialization that was
    hashed and signed.  The signature field holds the Ed25519 signature over
    sha256(canonical_bytes).
    """

    manifest_id: str = Field(default_factory=_new_id)
    manifest_version: str = "1"
    assessment_id: str
    input_sha256: str
    model_sha256: str
    preprocessing_config: dict[str, Any]
    inference_config: dict[str, Any]
    output_sha256: str
    timestamp_utc: str = Field(description="ISO 8601 UTC timestamp with Z suffix")
    nonce: str = Field(description="Random 32-byte hex string")
    sequence: int = Field(ge=0, description="Monotonic per-assessment sequence counter")
    pramaan_version: str = "1.0.0"

    # Set after canonicalization
    digest: str | None = Field(
        default=None, description="SHA-256 hex digest of the canonical bytes"
    )
    signature: str | None = Field(
        default=None, description="Ed25519 signature (hex) over the digest"
    )

    model_config = {"from_attributes": True}


class AuditEvent(BaseModel):
    """
    A single event in the tamper-evident audit chain.

    current_hash is H(previous_hash || event_id || timestamp_utc || event_type || payload_digest)
    using the canonical form of each field.
    """

    event_id: str = Field(default_factory=_new_id)
    event_type: AuditEventType
    timestamp_utc: str = Field(description="ISO 8601 UTC timestamp with Z suffix")
    assessment_id: str | None = None
    actor: str = "system"
    payload_digest: str = Field(description="SHA-256 of the JSON-serialized event payload")
    previous_hash: str
    current_hash: str

    model_config = {"from_attributes": True}
