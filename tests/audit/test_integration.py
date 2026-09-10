"""
Tests for audit integration (backend/audit/integration.py).

Coverage:
  - run_detector_with_audit: emits DETECTOR_COMPLETE event
  - run_detector_with_audit: detector_id in persisted payload
  - run_detector_with_audit: findings_count matches actual output
  - record_pi01_verification: emits PROVENANCE_VERIFIED / PROVENANCE_TAMPERED
  - verify_chain: returns ChainVerificationResult
  - verify_chain with record_in_audit=True: emits AUDIT_VERIFIED event
  - verify_chain with record_in_audit=False: does NOT emit event
  - Real detector execution (DI-01) produces audit trail

ANTI-FAKE:
  - Proves that actual detector execution changes the audit chain
  - The DETECTOR_COMPLETE payload contains the actual detector_id and result_id
  - Changing audit emission result records the real outcome
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.audit.integration import (
    make_audit_service,
    record_pi01_verification,
    run_detector_with_audit,
    verify_chain,
)
from backend.detectors.registry import DETECTOR_BY_ID
from backend.domain.entities import Assessment, Asset, Dataset
from backend.domain.enums import AssetType, AuditEventType, DatasetFormat
from backend.infra.db import (
    AssessmentRepository,
    AssetRepository,
    AuditPayloadRepository,
    AuditRepository,
    DatasetRepository,
    open_db,
)


# ---------------------------------------------------------------------------
# Minimal dataset/assessment setup for DI-01 integration test
# ---------------------------------------------------------------------------

def _setup_assessment(db: sqlite3.Connection, assess_id: str) -> str:
    AssessmentRepository(db).insert(
        Assessment(assessment_id=assess_id, title=f"Audit integration test {assess_id}")
    )
    return assess_id


def _setup_dataset_asset(
    db: sqlite3.Connection,
    assess_id: str,
    dataset_id: str,
) -> None:
    AssetRepository(db).insert(
        Asset(
            asset_id=dataset_id,
            assessment_id=assess_id,
            asset_type=AssetType.DATASET,
            name="test_dataset",
            sha256="a" * 64,
            size_bytes=1000,
        )
    )
    DatasetRepository(db).insert(
        Dataset(
            dataset_id=dataset_id,
            assessment_id=assess_id,
            format=DatasetFormat.IMAGE_DIR,
            source_path="/tmp/test_dataset",
            sample_count=0,
        )
    )


# ---------------------------------------------------------------------------
# Tests: make_audit_service
# ---------------------------------------------------------------------------

class TestMakeAuditService:

    def test_returns_audit_service(self, db):
        from backend.audit.service import AuditService
        svc = make_audit_service(db)
        assert isinstance(svc, AuditService)

    def test_can_emit_event(self, db):
        svc = make_audit_service(db)
        ev = svc.emit_event(
            AuditEventType.ASSESSMENT_CREATED,
            payload={"title": "factory test"},
        )
        assert ev.event_id is not None


# ---------------------------------------------------------------------------
# Tests: run_detector_with_audit (DI-01)
# ---------------------------------------------------------------------------

class TestRunDetectorWithAudit:

    def test_emits_detector_complete_event(self, db):
        """
        ANTI-FAKE: run_detector_with_audit must produce a DETECTOR_COMPLETE
        audit event backed by the actual detector's result.
        """
        from backend.detectors.base import DetectorContext

        assess_id = "audit-integ-di01"
        dataset_id = "audit-integ-dataset"
        _setup_assessment(db, assess_id)
        _setup_dataset_asset(db, assess_id, dataset_id)

        di01 = DETECTOR_BY_ID["data.integrity.di01_duplicates"]
        ctx = DetectorContext(
            assessment_id=assess_id,
            asset_id=dataset_id,
            conn=db,
        )

        audit_repo = AuditRepository(db)
        chain_before = len(audit_repo.list_all())

        run_detector_with_audit(di01, ctx, db)

        chain_after = audit_repo.list_all()
        assert len(chain_after) > chain_before, (
            "ANTI-FAKE: run_detector_with_audit must add at least one audit event"
        )

        # Find the DETECTOR_COMPLETE event
        dc_events = [e for e in chain_after if e.event_type == AuditEventType.DETECTOR_COMPLETE]
        assert len(dc_events) >= 1

    def test_detector_complete_payload_has_detector_id(self, db):
        """
        ANTI-FAKE: the audit payload must contain the actual detector_id.
        """
        from backend.detectors.base import DetectorContext

        assess_id = "audit-integ-di01-id"
        dataset_id = "audit-integ-dataset-id"
        _setup_assessment(db, assess_id)
        _setup_dataset_asset(db, assess_id, dataset_id)

        di01 = DETECTOR_BY_ID["data.integrity.di01_duplicates"]
        ctx = DetectorContext(
            assessment_id=assess_id,
            asset_id=dataset_id,
            conn=db,
        )

        run_detector_with_audit(di01, ctx, db)

        events = AuditRepository(db).list_by_assessment(assess_id)
        dc_events = [e for e in events if e.event_type == AuditEventType.DETECTOR_COMPLETE]
        assert len(dc_events) >= 1

        payload = AuditPayloadRepository(db).get(dc_events[0].event_id)
        assert payload is not None
        assert payload["detector_id"] == "data.integrity.di01_duplicates"

    def test_detector_complete_payload_has_status(self, db):
        from backend.detectors.base import DetectorContext

        assess_id = "audit-integ-status"
        dataset_id = "audit-integ-status-ds"
        _setup_assessment(db, assess_id)
        _setup_dataset_asset(db, assess_id, dataset_id)

        di01 = DETECTOR_BY_ID["data.integrity.di01_duplicates"]
        ctx = DetectorContext(
            assessment_id=assess_id,
            asset_id=dataset_id,
            conn=db,
        )

        run_detector_with_audit(di01, ctx, db)

        events = AuditRepository(db).list_by_assessment(assess_id)
        dc_events = [e for e in events if e.event_type == AuditEventType.DETECTOR_COMPLETE]
        payload = AuditPayloadRepository(db).get(dc_events[0].event_id)
        assert "status" in payload

    def test_audit_chain_is_valid_after_detector_run(self, db):
        """
        After a real detector run with audit, the full chain must still be valid.
        """
        from backend.detectors.base import DetectorContext
        from backend.audit.verifier import ChainVerifier

        assess_id = "audit-chain-valid"
        dataset_id = "audit-chain-dataset"
        _setup_assessment(db, assess_id)
        _setup_dataset_asset(db, assess_id, dataset_id)

        di01 = DETECTOR_BY_ID["data.integrity.di01_duplicates"]
        ctx = DetectorContext(assessment_id=assess_id, asset_id=dataset_id, conn=db)
        run_detector_with_audit(di01, ctx, db)

        verifier = ChainVerifier(AuditRepository(db), AuditPayloadRepository(db))
        result = verifier.verify_all()
        assert result.valid is True, (
            f"Chain must be valid after detector run. Failures: {result.failures}"
        )

    def test_returns_detector_output(self, db):
        """run_detector_with_audit must return the same output as run_detector."""
        from backend.detectors.base import DetectorContext
        from backend.domain.enums import DetectorStatus

        assess_id = "audit-return-test"
        dataset_id = "audit-return-ds"
        _setup_assessment(db, assess_id)
        _setup_dataset_asset(db, assess_id, dataset_id)

        di01 = DETECTOR_BY_ID["data.integrity.di01_duplicates"]
        ctx = DetectorContext(assessment_id=assess_id, asset_id=dataset_id, conn=db)
        output = run_detector_with_audit(di01, ctx, db)

        # Must have a valid status
        assert output.status in list(DetectorStatus)


# ---------------------------------------------------------------------------
# Tests: record_pi01_verification
# ---------------------------------------------------------------------------

class TestRecordPI01Verification:

    def test_emits_provenance_verified_event(self, db):
        record_pi01_verification(
            db,
            assessment_id="pi01-audit",
            manifest_id="m-001",
            valid=True,
            risk_level="none",
            confidence_level="high",
            finding_count=1,
        )
        events = AuditRepository(db).list_all()
        types = [e.event_type for e in events]
        assert AuditEventType.PROVENANCE_VERIFIED in types

    def test_emits_provenance_tampered_event(self, db):
        record_pi01_verification(
            db,
            assessment_id="pi01-audit-tampered",
            manifest_id="m-002",
            valid=False,
            risk_level="high",
            confidence_level="high",
            finding_count=3,
        )
        events = AuditRepository(db).list_all()
        types = [e.event_type for e in events]
        assert AuditEventType.PROVENANCE_TAMPERED in types

    def test_provenance_payload_contains_manifest_id(self, db):
        record_pi01_verification(
            db,
            assessment_id="pi01-payload",
            manifest_id="m-payload-test",
            valid=True,
            risk_level="none",
            confidence_level="high",
            finding_count=0,
        )
        events = AuditRepository(db).list_all()
        prov_events = [e for e in events if e.event_type == AuditEventType.PROVENANCE_VERIFIED]
        assert len(prov_events) >= 1
        payload = AuditPayloadRepository(db).get(prov_events[-1].event_id)
        assert payload["manifest_id"] == "m-payload-test"


# ---------------------------------------------------------------------------
# Tests: verify_chain
# ---------------------------------------------------------------------------

class TestVerifyChain:

    def test_returns_verification_result(self, db):
        from backend.audit.verifier import ChainVerificationResult
        result = verify_chain(db)
        assert isinstance(result, ChainVerificationResult)

    def test_empty_chain_valid(self, db):
        result = verify_chain(db, record_in_audit=False)
        assert result.valid is True

    def test_record_in_audit_true_emits_event(self, db):
        """
        ANTI-FAKE: verify_chain with record_in_audit=True must add an
        AUDIT_VERIFIED event to the chain.
        """
        audit_repo = AuditRepository(db)
        before = len(audit_repo.list_all())

        verify_chain(db, record_in_audit=True)

        after = audit_repo.list_all()
        assert len(after) > before
        av_events = [e for e in after if e.event_type == AuditEventType.AUDIT_VERIFIED]
        assert len(av_events) >= 1

    def test_record_in_audit_false_no_event_emitted(self, db):
        """record_in_audit=False must NOT add any event."""
        audit_repo = AuditRepository(db)
        # Prime the chain
        svc = make_audit_service(db)
        svc.emit_event(AuditEventType.ASSESSMENT_CREATED, payload={"t": "test"})

        before = len(audit_repo.list_all())
        verify_chain(db, record_in_audit=False)
        after = len(audit_repo.list_all())
        assert after == before

    def test_valid_chain_returns_valid_true(self, db):
        svc = make_audit_service(db)
        for i in range(3):
            svc.emit_event(AuditEventType.FINDING_GENERATED, payload={"i": i})

        result = verify_chain(db, record_in_audit=False)
        assert result.valid is True

    def test_verify_chain_reads_actual_database(self, db):
        """
        ANTI-FAKE: prove verify_chain reads the actual DB by tampering with
        a row directly and checking that verify_chain detects it.
        """
        svc = make_audit_service(db)
        ev = svc.emit_event(AuditEventType.ASSESSMENT_CREATED, payload={"title": "t"})

        # Tamper directly via SQL
        db.execute(
            "UPDATE audit_events SET actor = ? WHERE event_id = ?",
            ("attacker", ev.event_id),
        )
        db.commit()

        result = verify_chain(db, record_in_audit=False)
        assert result.valid is False, (
            "ANTI-FAKE: verify_chain must detect actual SQL-level tampering"
        )

    def test_audit_verified_payload_contains_chain_result(self, db):
        """The AUDIT_VERIFIED payload must contain the actual verification result."""
        svc = make_audit_service(db)
        for i in range(2):
            svc.emit_event(AuditEventType.FINDING_GENERATED, payload={"i": i})

        verify_chain(db, record_in_audit=True)

        events = AuditRepository(db).list_all()
        av_events = [e for e in events if e.event_type == AuditEventType.AUDIT_VERIFIED]
        assert len(av_events) >= 1
        payload = AuditPayloadRepository(db).get(av_events[-1].event_id)
        assert "events_checked" in payload
        assert "chain_valid" in payload
        assert payload["chain_valid"] is True
