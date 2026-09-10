"""
PRAMAAN audit trail integration helpers.

Lightweight functions that emit audit events from real PRAMAAN operations.

Design: these functions are called AFTER the primary operation has succeeded
and persisted.  They do NOT replace the primary operation's persistence.
They are optional — if audit emission fails, it should be logged but not
cause the primary operation to fail (fail-open for audit emission, fail-closed
for analysis).

Integration points implemented
--------------------------------
  run_detector_with_audit()  — wraps run_detector(), emits DETECTOR_COMPLETE
  record_pi01_verification() — emits PROVENANCE_VERIFIED / PROVENANCE_TAMPERED
  record_chain_verification() — wraps ChainVerifier.verify_all(), emits AUDIT_VERIFIED

Callers that want audit integration should use these wrappers.
Callers that only want raw persistence should use run_detector() directly.

When to use this module
-----------------------
  Use these helpers when:
  - Running a real detector as part of an assessment
  - Verifying a PI-01 provenance manifest
  - Running a scheduled chain verification

  Do NOT use these helpers for:
  - Unit tests of detectors themselves (use run_detector() directly)
  - Benchmark runs
  - Demo/synthetic fixtures
"""

from __future__ import annotations

import logging
import sqlite3

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.audit.service import AuditService
from backend.audit.verifier import ChainVerifier, ChainVerificationResult
from backend.detectors.base import Detector, DetectorContext, DetectorOutput
from backend.detectors.runner import run_detector
from backend.infra.db import AuditPayloadRepository, AuditRepository

log = logging.getLogger(__name__)


def make_audit_service(conn: sqlite3.Connection) -> AuditService:
    """Convenience factory: build an AuditService from an open connection."""
    return AuditService(
        audit_repo=AuditRepository(conn),
        payload_repo=AuditPayloadRepository(conn),
    )


def run_detector_with_audit(
    detector: Detector,
    context: DetectorContext,
    conn: sqlite3.Connection,
    *,
    private_key: Ed25519PrivateKey | None = None,
) -> DetectorOutput:
    """
    Run a detector and emit a DETECTOR_COMPLETE audit event.

    This is a thin wrapper around run_detector() that adds audit trail
    integration.  The primary detector execution and persistence happen
    exactly as in run_detector() — audit emission is additive.

    Parameters
    ----------
    detector : Detector
        The detector to run.
    context : DetectorContext
        Execution context.
    conn : sqlite3.Connection
        Open database connection for persistence.
    private_key : Ed25519PrivateKey | None
        If provided, the DETECTOR_COMPLETE event will be signed.

    Returns
    -------
    DetectorOutput — same as run_detector().
    """
    # Run the detector normally (persistence included)
    output = run_detector(detector, context, conn)

    # Emit audit event for the completed run
    try:
        meta = detector.metadata
        audit = make_audit_service(conn)

        # Retrieve the result_id from the DetectorResult
        # (run_detector persists it; we need the id to link in audit)
        from backend.infra.db import DetectorResultRepository
        results = DetectorResultRepository(conn).list_by_assessment(context.assessment_id)
        # Find the result for this detector/asset (most recent)
        matching = [
            r for r in results
            if r.detector_id == meta.detector_id and r.asset_id == context.asset_id
        ]
        result_id = matching[-1].result_id if matching else "unknown"

        audit.record_detector_complete(
            assessment_id=context.assessment_id,
            asset_id=context.asset_id,
            detector_id=meta.detector_id,
            detector_version=meta.version,
            status=output.status.value,
            findings_count=len(output.findings),
            evidence_count=len(output.evidence),
            duration_ms=None,  # calculated inside run_detector
            result_id=result_id,
            private_key=private_key,
        )
        log.debug(
            "Audit: DETECTOR_COMPLETE for %s (status=%s findings=%d)",
            meta.detector_id, output.status.value, len(output.findings),
        )
    except Exception as exc:
        # Audit emission failure must not fail the primary operation
        log.warning("Audit emission failed for detector %s: %s", detector.metadata.detector_id, exc)

    return output


def record_pi01_verification(
    conn: sqlite3.Connection,
    *,
    assessment_id: str,
    manifest_id: str,
    valid: bool,
    risk_level: str,
    confidence_level: str,
    finding_count: int,
    actor: str = "system",
    private_key: Ed25519PrivateKey | None = None,
) -> None:
    """
    Record the result of a PI-01 provenance integrity verification in the audit trail.

    Call this after running PI01ProvenanceIntegrityDetector when you want the
    verification result to appear in the tamper-evident audit trail.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    assessment_id : str
        The assessment this verification belongs to.
    manifest_id : str
        The manifest that was verified.
    valid : bool
        True if PI-01 found the provenance valid (no integrity failures).
    risk_level : str
        The risk level string from DetectorOutput.risk_level.value.
    confidence_level : str
        The confidence level string from DetectorOutput.confidence_level.value.
    finding_count : int
        Total findings produced by PI-01 for this run.
    actor : str
        Logical actor (defaults to "system").
    private_key : Ed25519PrivateKey | None
        If provided, the audit event will be signed.
    """
    try:
        audit = make_audit_service(conn)
        audit.record_provenance_verified(
            assessment_id=assessment_id,
            manifest_id=manifest_id,
            valid=valid,
            risk_level=risk_level,
            confidence_level=confidence_level,
            finding_count=finding_count,
            actor=actor,
            private_key=private_key,
        )
    except Exception as exc:
        log.warning("Audit emission failed for PI-01 verification: %s", exc)


def verify_chain(
    conn: sqlite3.Connection,
    *,
    record_in_audit: bool = True,
    assessment_id: str | None = None,
    actor: str = "system",
) -> ChainVerificationResult:
    """
    Verify the audit chain and optionally record the result.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    record_in_audit : bool
        If True, emit an AUDIT_VERIFIED event with the result.
        Defaults to True.
    assessment_id : str | None
        If given, limit verification to this assessment's events only.
        If None, verify the full global chain.
    actor : str
        Logical actor for the AUDIT_VERIFIED event.

    Returns
    -------
    ChainVerificationResult
    """
    audit_repo = AuditRepository(conn)
    payload_repo = AuditPayloadRepository(conn)
    verifier = ChainVerifier(audit_repo, payload_repo)

    if assessment_id is not None:
        result = verifier.verify_assessment(assessment_id)
    else:
        result = verifier.verify_all()

    if record_in_audit:
        try:
            audit = AuditService(audit_repo, payload_repo)
            audit.record_audit_verified(
                assessment_id=assessment_id,
                events_checked=result.events_checked,
                chain_valid=result.valid,
                failure_count=len(result.failures),
                first_invalid_event_id=result.first_invalid_event_id,
                actor=actor,
            )
        except Exception as exc:
            log.warning("Failed to record AUDIT_VERIFIED event: %s", exc)

    return result
