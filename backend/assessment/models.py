"""
PRAMAAN Assessment Orchestrator — data models.

Defines the input contract (AssessmentRequest) and output contract
(AssessmentResult) for the orchestrator.

Design rules
------------
- These are plain dataclasses with no database or file-system I/O.
- They are distinct from the domain entities in backend/domain/entities.py;
  the domain entities record what is stored in the DB, these hold what the
  orchestrator needs to receive / return.
- CoverageGapRecord is richer than the domain CoverageGap — it carries
  enough detail for analyst action, not just for persistence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.domain.enums import (
    AssessmentState,
    ConfidenceLevel,
    DatasetFormat,
    RiskLevel,
)


# ---------------------------------------------------------------------------
# CoverageGapRecord
# ---------------------------------------------------------------------------

@dataclass
class CoverageGapRecord:
    """
    A structured record of a detection capability that could not be exercised.

    This is a richer version of the domain CoverageGap — it carries all the
    information an analyst needs to understand *why* a method was skipped and
    what they should do about it.

    Schema
    ------
    detector_id       — stable ID of the skipped detector
    detector_name     — human-readable name
    reason            — machine-readable reason code, e.g. "no_model_provided"
    required_capability — what PRAMAAN would need to run this detector
    observed_capability — what PRAMAAN actually has access to
    impact            — what assurance is missing, e.g. "model_integrity_not_assessed"
    recommended_action — what the analyst/operator should do
    """

    detector_id: str
    detector_name: str
    reason: str
    required_capability: str
    observed_capability: str
    impact: str
    recommended_action: str

    def to_dict(self) -> dict[str, str]:
        return {
            "detector_id": self.detector_id,
            "detector_name": self.detector_name,
            "reason": self.reason,
            "required_capability": self.required_capability,
            "observed_capability": self.observed_capability,
            "impact": self.impact,
            "recommended_action": self.recommended_action,
        }


# ---------------------------------------------------------------------------
# AssessmentRequest
# ---------------------------------------------------------------------------

@dataclass
class AssessmentRequest:
    """
    Everything the orchestrator needs to run a PRAMAAN assessment.

    At least one of dataset_path, model_path, or provenance_manifest must be
    provided; otherwise the orchestrator will fail-closed.

    Dataset
    -------
    dataset_path    — absolute path to an image directory or COCO JSON file
    dataset_format  — IMAGE_DIR or COCO_JSON; required when dataset_path is set

    Model
    -----
    model_path      — absolute path to a .onnx, .pt, or .pth model file
    model_reference_fingerprint
                    — optional dict from a previous MI-01 fingerprint_recorded
                      evidence.  When present, MI-01 will compare against it.

    Provenance
    ----------
    provenance_manifest     — a signed ProvenanceManifest (digest+signature set)
    provenance_public_key   — Ed25519PublicKey to verify the signature
    actual_input_bytes      — raw input bytes for binding verification (optional)
    actual_output_bytes     — canonical output bytes for binding verification (optional)
    actual_model_sha256     — SHA-256 of the model used for inference (optional)

    Thresholds
    ----------
    phash_threshold, dhash_threshold — Hamming distance thresholds for DI-01
    min_cluster_size                 — min cluster size for DI-01 findings
    """

    title: str
    assessment_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Dataset
    dataset_path: Path | None = None
    dataset_format: DatasetFormat | None = None
    dataset_reference_path: Path | None = None
    dataset_reference_format: DatasetFormat | None = None

    # Model
    model_path: Path | None = None
    model_reference_path: Path | None = None
    model_reference_fingerprint: dict[str, Any] | None = None

    # Provenance
    provenance_manifest: Any | None = None           # ProvenanceManifest; Any to avoid circular import
    provenance_public_key: Any | None = None          # Ed25519PublicKey; Any to avoid circular import
    actual_input_bytes: bytes | None = None
    actual_output_bytes: bytes | None = None
    actual_model_sha256: str | None = None

    # DI-01 thresholds
    phash_threshold: int = 10
    dhash_threshold: int = 10
    min_cluster_size: int = 2

    def validate(self) -> list[str]:
        """
        Return a list of validation error messages.

        An empty list means the request is valid.
        A non-empty list means the orchestrator must fail-closed.
        """
        errors: list[str] = []

        if not self.title or not self.title.strip():
            errors.append("title must not be empty")

        has_any = (
            self.dataset_path is not None
            or self.model_path is not None
            or self.provenance_manifest is not None
        )
        if not has_any:
            errors.append(
                "at least one of dataset_path, model_path, or provenance_manifest must be provided"
            )

        if self.dataset_path is not None and self.dataset_format is None:
            errors.append(
                "dataset_format must be provided when dataset_path is set"
            )

        if self.provenance_manifest is not None and self.provenance_public_key is None:
            errors.append(
                "provenance_public_key is required when provenance_manifest is provided"
            )

        return errors


# ---------------------------------------------------------------------------
# DetectorRunRecord
# ---------------------------------------------------------------------------

@dataclass
class DetectorRunRecord:
    """
    Records the outcome of running a single detector.
    Used internally by the orchestrator to track execution.
    """

    detector_id: str
    detector_name: str
    asset_id: str
    applicable: bool
    ran: bool                  # True iff can_run() returned True and we executed it
    status: str                # DetectorStatus.value
    risk_level: str            # RiskLevel.value
    confidence_level: str      # ConfidenceLevel.value
    findings_count: int
    evidence_count: int
    error: str | None
    coverage_gap: CoverageGapRecord | None  # Set when applicable=True but ran=False


# ---------------------------------------------------------------------------
# AssessmentResult
# ---------------------------------------------------------------------------

@dataclass
class AssessmentResult:
    """
    Structured result of a completed PRAMAAN assessment.

    This is suitable for serialization to JSON for API/frontend consumption.
    It is NOT stored directly in the DB — the individual records (findings,
    evidence, detector_results) are the persistent truth.

    Fields
    ------
    assessment_id         — the stable UUID for this assessment
    title                 — human-readable label
    status                — COMPLETE or FAILED
    started_at            — UTC timestamp
    completed_at          — UTC timestamp
    assets_analyzed       — list of asset_ids that were analyzed
    detectors_executed    — detector_ids where can_run()=True and execution ran
    detectors_skipped     — applicable detector_ids that could not run
    findings_count        — total findings produced by all detectors
    evidence_count        — total evidence items produced by all detectors
    overall_risk          — max risk across all detectors (ADR-003)
    risk_qualitative      — one-sentence summary of the risk determination
    overall_confidence    — confidence in the risk assessment (ADR-003)
    confidence_qualifier  — why this confidence level was assigned
    coverage_fraction     — fraction of applicable detectors that executed
    coverage_gaps         — structured limitations for detectors that didn't run
    detector_runs         — per-detector execution records
    limitations           — aggregate list of known limitations
    audit_chain_valid     — True/False/None (None = not verified)
    error                 — non-None iff status is FAILED
    """

    assessment_id: str
    title: str
    status: AssessmentState
    started_at: datetime
    completed_at: datetime
    assets_analyzed: list[str]
    detectors_executed: list[str]
    detectors_skipped: list[str]
    findings_count: int
    evidence_count: int
    overall_risk: RiskLevel
    risk_qualitative: str
    overall_confidence: ConfidenceLevel
    confidence_qualifier: str
    coverage_fraction: float
    coverage_gaps: list[CoverageGapRecord]
    detector_runs: list[DetectorRunRecord]
    limitations: list[str]
    audit_chain_valid: bool | None
    error: str | None

    def to_dict(self) -> dict:
        return {
            "assessment_id": self.assessment_id,
            "title": self.title,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "assets_analyzed": self.assets_analyzed,
            "detectors_executed": self.detectors_executed,
            "detectors_skipped": self.detectors_skipped,
            "findings_count": self.findings_count,
            "evidence_count": self.evidence_count,
            "overall_risk": self.overall_risk.value,
            "risk_qualitative": self.risk_qualitative,
            "overall_confidence": self.overall_confidence.value,
            "confidence_qualifier": self.confidence_qualifier,
            "coverage_fraction": round(self.coverage_fraction, 4),
            "coverage_gaps": [g.to_dict() for g in self.coverage_gaps],
            "limitations": self.limitations,
            "audit_chain_valid": self.audit_chain_valid,
            "error": self.error,
        }
