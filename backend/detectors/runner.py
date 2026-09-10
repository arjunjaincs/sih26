"""
PRAMAAN detector runner.

Thin layer that:
  1. Calls can_run() on a detector
  2. Calls run() if allowed
  3. Persists findings, evidence, and the DetectorResult

This is NOT an orchestrator — it runs a single detector against a single
asset.  A future orchestrator will loop over ALL_DETECTORS and assets.

V1 design choice: keep this simple. No async, no multiprocessing.
"""

from __future__ import annotations

import logging
import sqlite3

from backend.detectors.base import Detector, DetectorContext, DetectorOutput
from backend.domain.enums import DetectorStatus
from backend.infra.db import (
    DetectorResultRepository,
    EvidenceRepository,
    FindingRepository,
)

log = logging.getLogger(__name__)


def run_detector(
    detector: Detector,
    context: DetectorContext,
    conn: sqlite3.Connection,
) -> DetectorOutput:
    """
    Run a single detector against a single asset and persist the results.

    Parameters
    ----------
    detector : Detector
        The detector instance to run.
    context : DetectorContext
        Context carrying assessment_id, asset_id, db conn, and thresholds.
    conn : sqlite3.Connection
        Open connection for persisting results (may be the same as context.conn).

    Returns
    -------
    DetectorOutput — the output the detector produced (already persisted).
    """
    meta = detector.metadata
    log.info("Running detector %s v%s against asset %s",
             meta.detector_id, meta.version, context.asset_id)

    # --- Pre-flight check ---------------------------------------------------
    can = detector.can_run(context)
    if not can.ok:
        log.info("Detector %s skipped: %s", meta.detector_id, can.reason)
        output = DetectorOutput(
            status=DetectorStatus.SKIPPED,
            error=can.reason,
        ).finalize()
        _persist_output(output, detector, context, conn)
        return output

    # --- Run ----------------------------------------------------------------
    try:
        output = detector.run(context)
    except Exception as exc:
        log.exception("Detector %s raised an unexpected exception", meta.detector_id)
        output = DetectorOutput(
            status=DetectorStatus.FAILED,
            error=str(exc),
        ).finalize()

    # --- Persist ------------------------------------------------------------
    _persist_output(output, detector, context, conn)
    return output


def _persist_output(
    output: DetectorOutput,
    detector: Detector,
    context: DetectorContext,
    conn: sqlite3.Connection,
) -> None:
    """Persist findings, evidence, and the DetectorResult record."""
    meta = detector.metadata
    finding_repo = FindingRepository(conn)
    evidence_repo = EvidenceRepository(conn)
    result_repo = DetectorResultRepository(conn)

    # Persist findings and their evidence
    for finding in output.findings:
        finding_repo.insert(finding)
        log.debug("Persisted finding %s", finding.finding_id)

    for ev in output.evidence:
        evidence_repo.insert(ev)
        log.debug("Persisted evidence %s", ev.evidence_id)

    # Persist detector run record
    dr = output.to_detector_result(meta, context)
    result_repo.insert(dr)
    log.info(
        "Detector %s: status=%s findings=%d evidence=%d duration=%sms",
        meta.detector_id, output.status.value,
        len(output.findings), len(output.evidence), dr.duration_ms,
    )
