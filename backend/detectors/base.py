"""
PRAMAAN detector protocol and supporting types.

Defines the structural Protocol that all detectors must implement.
No concrete implementation lives here — only contracts and context types.

Per ADR-004: detectors implement a Python Protocol (structural subtyping).
No abstract base classes, no plugin framework, no dynamic loading.

Context types carry everything a detector needs:
  - Which assessment and asset are being analyzed
  - The open database connection for reading samples/fingerprints
  - Configuration (thresholds etc.)

Detectors must NOT write to the database themselves — they return
DetectorOutput which the caller persists.  This keeps detectors pure
and testable without a real database.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from backend.domain.entities import DetectorResult, Evidence, Finding
from backend.domain.enums import ConfidenceLevel, DetectorStatus, RiskLevel


# ---------------------------------------------------------------------------
# Detector metadata
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DetectorMetadata:
    """
    Static descriptor for a detector.

    detector_id must be stable across versions — it is stored in the database
    and used to look up past results.  Use the naming convention:
      <domain>.<category>.<short_name>
    e.g.  "data.integrity.di01_duplicates"
    """

    detector_id: str
    version: str
    name: str
    description: str
    applicable_asset_types: frozenset[str]  # Values from AssetType enum


# ---------------------------------------------------------------------------
# Can-run result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CanRunResult:
    """
    Result of a detector's can_run() pre-flight check.

    If ok is False, the detector will be skipped with the given reason.
    Skipped detectors produce a CoverageGap, never a silent pass.
    """

    ok: bool
    reason: str = ""


# ---------------------------------------------------------------------------
# Detector context
# ---------------------------------------------------------------------------

@dataclass
class DetectorContext:
    """
    Everything a detector needs to run.

    Detectors receive a context and return DetectorOutput.
    They do NOT write to the database directly — the caller persists results.
    """

    assessment_id: str
    asset_id: str          # dataset_id or model_id
    conn: sqlite3.Connection | None = None  # Required by DB-querying detectors; None OK for pure detectors

    # Configurable thresholds — detectors should use these, not hardcode values
    phash_threshold: int = 10   # Maximum Hamming distance for near-duplicate pHash
    dhash_threshold: int = 10   # Maximum Hamming distance for near-duplicate dHash

    # Minimum cluster size that generates a Finding (singletons are noise)
    min_cluster_size: int = 2

    # Reference asset (e.g. baseline dataset for DI-04 distribution shift)
    reference_asset_id: str | None = None


# ---------------------------------------------------------------------------
# Detector output
# ---------------------------------------------------------------------------

@dataclass
class DetectorOutput:
    """
    What a detector returns to the caller.

    The caller is responsible for:
      - Persisting findings and evidence
      - Recording the DetectorResult
      - Updating assessment state

    risk_level and confidence_level are the detector's own assessment of
    the evidence it found.  They are NOT aggregated here — aggregation
    belongs to the orchestrator (Phase 5+).
    """

    findings: list[Finding] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.NONE
    confidence_level: ConfidenceLevel = ConfidenceLevel.LOW
    status: DetectorStatus = DetectorStatus.SUCCESS
    error: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def finalize(self) -> "DetectorOutput":
        """Mark the output as complete by setting completed_at."""
        self.completed_at = datetime.now(timezone.utc)
        return self

    def to_detector_result(
        self,
        metadata: DetectorMetadata,
        context: DetectorContext,
    ) -> DetectorResult:
        """Build a DetectorResult record suitable for persistence."""
        duration_ms: int | None = None
        if self.completed_at is not None:
            duration_ms = int(
                (self.completed_at - self.started_at).total_seconds() * 1000
            )
        return DetectorResult(
            assessment_id=context.assessment_id,
            asset_id=context.asset_id,
            detector_id=metadata.detector_id,
            detector_version=metadata.version,
            status=self.status,
            error=self.error,
            findings_count=len(self.findings),
            evidence_count=len(self.evidence),
            duration_ms=duration_ms,
            started_at=self.started_at,
            completed_at=self.completed_at,
        )


# ---------------------------------------------------------------------------
# Detector Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Detector(Protocol):
    """
    Structural protocol for all PRAMAAN detectors.

    Implementations must provide:
      metadata  — static descriptor (id, version, name, etc.)
      can_run() — pre-flight check; returns CanRunResult(ok=False) if skipped
      run()     — the actual analysis; returns DetectorOutput

    Detectors must NOT:
      - Write to the database directly
      - Raise unhandled exceptions (catch and return status=FAILED with error)
      - Return hardcoded findings
      - Fabricate measurements
    """

    @property
    def metadata(self) -> DetectorMetadata: ...

    def can_run(self, context: DetectorContext) -> CanRunResult: ...

    def run(self, context: DetectorContext) -> DetectorOutput: ...
