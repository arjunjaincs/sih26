"""
Tests for Read-Only Audit Export in PRAMAAN.

Covers:
- GET /api/v1/assessments/{assessment_id}/audit/export
- Valid audit chain export with intact cryptographic linkages
- Tampered audit chain detection (truthful verification results in export)
- Signed audit events (signature_status="verified" and "invalid")
- Assessment with no events / limited events (chain_valid=True, 0 events)
- Missing assessment (404 Not Found)
- Zero mutation guarantee (audit chain strictly unmodified after export)
- Path censorship and secret scrubbing (no server paths or credentials in export)
- Complete required metadata (assessment ID, schema/version, event IDs, timestamps,
  pre-hashes, hashes, genesis info, verification results)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_db
from backend.audit.hashing import compute_event_hash, compute_payload_digest
from backend.audit.service import AuditService
from backend.domain.entities import Assessment, AuditEvent
from backend.domain.enums import AssessmentState, AuditEventType
from backend.infra.crypto import (
    generate_signing_key,
    public_key_from_private,
    sign,
)
from backend.infra.db import (
    AssessmentRepository,
    AuditPayloadRepository,
    AuditRepository,
)


@pytest.fixture
def client(db: sqlite3.Connection) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


def _create_test_assessment(
    db: sqlite3.Connection,
    assessment_id: str = "asmt-audit-001",
    version: str = "1.0.0",
) -> str:
    now = datetime.now(timezone.utc)
    AssessmentRepository(db).insert(
        Assessment(
            assessment_id=assessment_id,
            title="Audit Export Verification Assessment",
            state=AssessmentState.COMPLETE,
            software_version=version,
            created_at=now,
            started_at=now,
            completed_at=now,
        )
    )
    return assessment_id


def _seed_valid_audit_chain(
    db: sqlite3.Connection,
    assessment_id: str,
    event_count: int = 4,
) -> list[AuditEvent]:
    audit_repo = AuditRepository(db)
    payload_repo = AuditPayloadRepository(db)

    types = [
        AuditEventType.ASSESSMENT_CREATED,
        AuditEventType.ASSET_REGISTERED,
        AuditEventType.ANALYSIS_STARTED,
        AuditEventType.ASSESSMENT_COMPLETE,
    ]

    events = []
    prev_hash = audit_repo.last_hash()

    for i in range(event_count):
        etype = types[i % len(types)]
        event_id = f"evt-export-{i:03d}"
        iso_ts = f"2026-09-13T01:0{i}:00Z"
        payload = {"step": i, "details": f"Lifecycle step {i}"}
        payload_digest = compute_payload_digest(payload)

        evt = AuditEvent(
            event_id=event_id,
            assessment_id=assessment_id,
            event_type=etype,
            actor="analyst-system",
            timestamp_utc=iso_ts,
            payload_digest=payload_digest,
            previous_hash=prev_hash,
            current_hash="",
        )
        evt.current_hash = compute_event_hash(evt)
        audit_repo.append(evt)
        payload_repo.insert(event_id, payload)
        prev_hash = evt.current_hash
        events.append(evt)

    return events


class TestAuditExportEndpoint:
    """Test GET /api/v1/assessments/{assessment_id}/audit/export."""

    def test_valid_audit_chain_export(self, client: TestClient, db: sqlite3.Connection):
        """Valid audit chain produces a structured verification artifact with chain_valid=True."""
        asmt_id = _create_test_assessment(db, "asmt-valid-001")
        _seed_valid_audit_chain(db, asmt_id, event_count=4)

        resp = client.get(f"/api/v1/assessments/{asmt_id}/audit/export")
        assert resp.status_code == 200

        # Verify headers
        assert resp.headers["content-type"].startswith("application/json")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "asmt-val" in resp.headers.get("content-disposition", "")

        data = resp.json()

        # Schema & Version metadata
        assert data["export_format"] == "pramaan-audit-export-v1"
        assert "AT-01" in data["specification"]
        assert data["pramaan_version"] == "1.0.0"
        assert data["is_verification_artifact"] is True
        assert data["assessment_id"] == asmt_id
        assert "exported_at_utc" in data

        # Genesis Information
        assert data["genesis"]["genesis_hash"] == "0" * 64
        assert data["genesis"]["is_first_event_genesis_linked"] is True

        # Chain Verification Result
        verification = data["verification"]
        assert verification["chain_valid"] is True
        assert verification["events_checked"] == 4
        assert verification["failure_count"] == 0
        assert verification["failures"] == []
        assert verification["first_invalid_event_id"] is None

        # Summary
        summary = data["summary"]
        assert summary["total_events"] == 4
        assert summary["first_event_id"] == "evt-export-000"
        assert summary["last_event_id"] == "evt-export-003"
        assert len(summary["first_event_hash"]) == 64
        assert len(summary["last_event_hash"]) == 64

        # Events sequence
        events = data["events"]
        assert len(events) == 4
        for idx, evt in enumerate(events, start=1):
            assert evt["sequence"] == idx
            assert evt["event_id"] == f"evt-export-{idx-1:03d}"
            assert evt["assessment_id"] == asmt_id
            assert evt["actor"] == "analyst-system"
            assert len(evt["current_hash"]) == 64
            assert len(evt["previous_hash"]) == 64
            assert len(evt["payload_digest"]) == 64
            assert evt["signature_status"] == "unsigned"
            assert evt["payload"]["step"] == idx - 1

    def test_tampered_audit_chain_detection(self, client: TestClient, db: sqlite3.Connection):
        """Tampered audit chain is truthfully reported with chain_valid=False and failure details."""
        asmt_id = _create_test_assessment(db, "asmt-tampered-001")
        _seed_valid_audit_chain(db, asmt_id, event_count=4)

        # Tamper with an event's hash directly in SQLite
        db.execute(
            "UPDATE audit_events SET current_hash=? WHERE event_id=?",
            ("f" * 64, "evt-export-001"),
        )
        db.commit()

        resp = client.get(f"/api/v1/assessments/{asmt_id}/audit/export")
        assert resp.status_code == 200

        data = resp.json()
        verification = data["verification"]
        assert verification["chain_valid"] is False
        assert verification["failure_count"] > 0
        assert verification["first_invalid_event_id"] == "evt-export-001"
        assert len(verification["failures"]) > 0

    def test_signed_audit_events_verification(self, client: TestClient, db: sqlite3.Connection):
        """Export verifies Ed25519 signatures on events and reports signature_status."""
        asmt_id = _create_test_assessment(db, "asmt-signed-001")
        audit_service = AuditService(AuditRepository(db), AuditPayloadRepository(db))

        priv_key = generate_signing_key()
        pub_key = public_key_from_private(priv_key)
        pub_hex = pub_key.public_bytes_raw().hex()

        # Append a signed event using AuditService
        signed_evt = audit_service.emit_event(
            event_type=AuditEventType.ASSESSMENT_CREATED,
            actor="authority-signer",
            assessment_id=asmt_id,
            payload={"action": "assessment_initialized", "scope": "full_battery"},
            private_key=priv_key,
        )

        resp = client.get(f"/api/v1/assessments/{asmt_id}/audit/export")
        assert resp.status_code == 200
        data = resp.json()

        assert data["verification"]["chain_valid"] is True
        events = data["events"]
        assert len(events) == 1
        exported_signed = events[0]

        assert exported_signed["signature_status"] == "verified"
        assert exported_signed["signing_key_id"] == pub_hex
        assert exported_signed["signature"] is not None
        assert exported_signed["pre_signature_hash"] is not None
        assert len(exported_signed["signature"]) == 128  # Ed25519 hex is 64 bytes = 128 chars

        # Internal metadata keys should not pollute user payload
        assert "__signature" not in exported_signed["payload"]
        assert "__signing_key_id" not in exported_signed["payload"]
        assert "__pre_sig_hash" not in exported_signed["payload"]
        assert exported_signed["payload"]["action"] == "assessment_initialized"

    def test_signed_event_tampered_signature_detected(self, client: TestClient, db: sqlite3.Connection):
        """If signature or signed payload is altered, signature_status is 'invalid'."""
        asmt_id = _create_test_assessment(db, "asmt-bad-sig-001")
        audit_service = AuditService(AuditRepository(db), AuditPayloadRepository(db))

        priv_key = generate_signing_key()

        signed_evt = audit_service.emit_event(
            event_type=AuditEventType.ASSESSMENT_CREATED,
            actor="authority-signer",
            assessment_id=asmt_id,
            payload={"action": "init"},
            private_key=priv_key,
        )

        # Corrupt the signature in payload table
        row = db.execute(
            "SELECT payload_json FROM audit_event_payloads WHERE event_id=?",
            (signed_evt.event_id,),
        ).fetchone()
        payload = json.loads(row["payload_json"])
        payload["__signature"] = "deadbeef" * 16  # corrupt signature
        db.execute(
            "UPDATE audit_event_payloads SET payload_json=? WHERE event_id=?",
            (json.dumps(payload), signed_evt.event_id),
        )
        db.commit()

        resp = client.get(f"/api/v1/assessments/{asmt_id}/audit/export")
        assert resp.status_code == 200
        data = resp.json()

        exported_evt = data["events"][0]
        assert exported_evt["signature_status"] == "invalid"

    def test_assessment_with_no_events(self, client: TestClient, db: sqlite3.Connection):
        """Assessment with no audit events exports safely with 0 events and valid chain status."""
        asmt_id = _create_test_assessment(db, "asmt-empty-001")

        resp = client.get(f"/api/v1/assessments/{asmt_id}/audit/export")
        assert resp.status_code == 200

        data = resp.json()
        assert data["assessment_id"] == asmt_id
        assert data["verification"]["chain_valid"] is True
        assert data["verification"]["events_checked"] == 0
        assert data["summary"]["total_events"] == 0
        assert data["summary"]["first_event_id"] is None
        assert data["events"] == []
        assert data["genesis"]["is_first_event_genesis_linked"] is None

    def test_missing_assessment_returns_404(self, client: TestClient):
        """Requesting export for a nonexistent assessment returns 404."""
        resp = client.get("/api/v1/assessments/nonexistent-id-99999/audit/export")
        assert resp.status_code == 404

    def test_read_only_guarantee_no_audit_mutation(self, client: TestClient, db: sqlite3.Connection):
        """Exporting must never mutate, insert, update, or delete audit events."""
        asmt_id = _create_test_assessment(db, "asmt-readonly-001")
        _seed_valid_audit_chain(db, asmt_id, event_count=3)

        count_events_before = db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
        count_payloads_before = db.execute("SELECT COUNT(*) FROM audit_event_payloads").fetchone()[0]
        rows_before = db.execute("SELECT * FROM audit_events ORDER BY rowid ASC").fetchall()

        resp = client.get(f"/api/v1/assessments/{asmt_id}/audit/export")
        assert resp.status_code == 200

        count_events_after = db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
        count_payloads_after = db.execute("SELECT COUNT(*) FROM audit_event_payloads").fetchone()[0]
        rows_after = db.execute("SELECT * FROM audit_events ORDER BY rowid ASC").fetchall()

        assert count_events_before == count_events_after
        assert count_payloads_before == count_payloads_after
        for r_before, r_after in zip(rows_before, rows_after):
            assert dict(r_before) == dict(r_after)

    def test_no_secrets_and_path_censorship(self, client: TestClient, db: sqlite3.Connection):
        """Ensures absolute filesystem paths and secrets are scrubbed from exported payloads."""
        asmt_id = _create_test_assessment(db, "asmt-scrub-001")
        audit_repo = AuditRepository(db)
        payload_repo = AuditPayloadRepository(db)

        dirty_payload = {
            "source_path": r"C:\Users\SecretAdmin\models\confidential_weights.onnx",
            "posix_path": "/home/ubuntu/production/data/train.csv",
            "api_key": "sk-1234567890abcdef1234567890abcdef",
            "access_token": "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
            "safe_property": "resnet_architecture",
        }
        digest = compute_payload_digest(dirty_payload)

        evt = AuditEvent(
            event_id="evt-scrub-001",
            assessment_id=asmt_id,
            event_type=AuditEventType.ANALYSIS_STARTED,
            actor="admin",
            timestamp_utc="2026-09-13T01:00:00Z",
            payload_digest=digest,
            previous_hash=audit_repo.last_hash(),
            current_hash="",
        )
        evt.current_hash = compute_event_hash(evt)
        audit_repo.append(evt)
        payload_repo.insert(evt.event_id, dirty_payload)

        resp = client.get(f"/api/v1/assessments/{asmt_id}/audit/export")
        assert resp.status_code == 200

        raw_text = resp.text
        # No absolute paths leaked
        assert r"C:\Users\SecretAdmin" not in raw_text
        assert "/home/ubuntu/production" not in raw_text
        # No secrets leaked
        assert "sk-1234567890" not in raw_text
        assert "ghp_abcdef" not in raw_text

        # Clean properties retained
        data = resp.json()
        payload = data["events"][0]["payload"]
        assert payload["safe_property"] == "resnet_architecture"
        # Secret keys stripped
        assert "api_key" not in payload
        assert "access_token" not in payload
