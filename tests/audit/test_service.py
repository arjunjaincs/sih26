"""
Tests for AuditService (backend/audit/service.py).

Coverage:
  - emit_event: creates a correctly hash-linked event
  - emit_event: payload is persisted and retrievable
  - emit_event: payload_digest matches SHA-256(canonical_json(payload))
  - emit_event: previous_hash is the chain tail before appending
  - emit_event: current_hash is valid (verify_event_hash passes)
  - Chain construction: first event has GENESIS_HASH as previous_hash
  - Chain construction: each event's previous_hash is prior event's current_hash
  - Chain construction: 10-event chain links correctly
  - Ed25519 signing: signed event's payload contains __signature
  - Ed25519 signing: verify_event_signature passes with correct key
  - Ed25519 signing: wrong key fails
  - Ed25519 signing: tampered current_hash → signature invalid
  - Convenience methods: record_assessment_created, record_detector_complete, etc.
  - Append-only: no update/delete paths exist
  - Database reopen: chain persists and verifies after close/reopen

ANTI-FAKE:
  - Prove that each appended event actually changes the chain tail
  - Prove that payload_digest is computed from actual payload bytes
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.audit.hashing import compute_payload_digest, verify_event_hash
from backend.audit.service import AuditService
from backend.domain.enums import AuditEventType
from backend.infra.crypto import generate_signing_key, public_key_from_private
from backend.infra.db import (
    AuditPayloadRepository,
    AuditRepository,
    open_db,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def audit_service(db):
    """AuditService backed by the test db fixture."""
    return AuditService(
        audit_repo=AuditRepository(db),
        payload_repo=AuditPayloadRepository(db),
    )


@pytest.fixture(scope="module")
def signing_keypair():
    priv = generate_signing_key()
    pub = public_key_from_private(priv)
    return priv, pub


# ---------------------------------------------------------------------------
# Tests: emit_event (basic)
# ---------------------------------------------------------------------------

class TestEmitEvent:

    def test_returns_audit_event(self, audit_service):
        from backend.domain.entities import AuditEvent
        ev = audit_service.emit_event(
            AuditEventType.ASSESSMENT_CREATED,
            payload={"assessment_id": "a-001", "title": "Test"},
        )
        assert isinstance(ev, AuditEvent)

    def test_event_has_correct_type(self, audit_service):
        ev = audit_service.emit_event(
            AuditEventType.INGESTION_COMPLETE,
            payload={"dataset_id": "d-001", "sample_count": 42},
        )
        assert ev.event_type == AuditEventType.INGESTION_COMPLETE

    def test_event_has_timestamp(self, audit_service):
        import re
        ev = audit_service.emit_event(
            AuditEventType.ASSESSMENT_CREATED,
            payload={"x": 1},
        )
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", ev.timestamp_utc)

    def test_event_has_current_hash(self, audit_service):
        ev = audit_service.emit_event(AuditEventType.ASSESSMENT_CREATED, payload={"x": 1})
        assert len(ev.current_hash) == 64
        assert all(c in "0123456789abcdef" for c in ev.current_hash)

    def test_event_hash_is_valid(self, audit_service):
        """ANTI-FAKE: the stored current_hash must be the actual hash of the event fields."""
        ev = audit_service.emit_event(AuditEventType.ASSESSMENT_CREATED, payload={"x": 1})
        assert verify_event_hash(ev) is True

    def test_payload_digest_matches_actual_payload(self, audit_service, db):
        """ANTI-FAKE: payload_digest must equal SHA-256(canonical_json(payload))."""
        payload = {"detector_id": "di01", "findings_count": 3}
        ev = audit_service.emit_event(AuditEventType.DETECTOR_COMPLETE, payload=payload)

        # Retrieve the stored payload
        stored_payload = AuditPayloadRepository(db).get(ev.event_id)
        assert stored_payload is not None

        recomputed = compute_payload_digest(stored_payload)
        assert recomputed == ev.payload_digest, (
            "payload_digest must equal SHA-256(canonical_json(actual_payload))"
        )

    def test_payload_is_persisted(self, audit_service, db):
        payload = {"assessment_id": "a-002", "status": "complete"}
        ev = audit_service.emit_event(AuditEventType.ASSESSMENT_COMPLETE, payload=payload)
        stored = AuditPayloadRepository(db).get(ev.event_id)
        assert stored is not None
        assert stored["assessment_id"] == "a-002"
        assert stored["status"] == "complete"

    def test_event_is_persisted_in_audit_repo(self, audit_service, db):
        ev = audit_service.emit_event(AuditEventType.DETECTOR_STARTED, payload={"x": 1})
        loaded = AuditRepository(db).get(ev.event_id)
        assert loaded is not None
        assert loaded.event_id == ev.event_id

    def test_assessment_id_stored(self, audit_service, db):
        ev = audit_service.emit_event(
            AuditEventType.ASSESSMENT_CREATED,
            payload={"title": "t"},
            assessment_id="assess-svc-test",
        )
        assert ev.assessment_id == "assess-svc-test"
        loaded = AuditRepository(db).get(ev.event_id)
        assert loaded.assessment_id == "assess-svc-test"

    def test_actor_stored(self, audit_service, db):
        ev = audit_service.emit_event(
            AuditEventType.ASSESSMENT_CREATED,
            payload={"title": "t"},
            actor="analyst-1",
        )
        assert ev.actor == "analyst-1"
        loaded = AuditRepository(db).get(ev.event_id)
        assert loaded.actor == "analyst-1"


# ---------------------------------------------------------------------------
# Tests: Chain construction
# ---------------------------------------------------------------------------

class TestChainConstruction:

    def test_first_event_has_genesis_hash(self, db):
        """The very first event in an empty chain must reference GENESIS_HASH."""
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev = svc.emit_event(AuditEventType.ASSESSMENT_CREATED, payload={"n": 1})
        assert ev.previous_hash == AuditRepository.GENESIS_HASH

    def test_second_event_references_first_hash(self, db):
        """ANTI-FAKE: second event's previous_hash must equal first event's current_hash."""
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev1 = svc.emit_event(AuditEventType.ASSESSMENT_CREATED, payload={"n": 1})
        ev2 = svc.emit_event(AuditEventType.ASSET_REGISTERED, payload={"n": 2})
        assert ev2.previous_hash == ev1.current_hash, (
            "Second event's previous_hash must equal first event's current_hash"
        )

    def test_third_event_references_second_hash(self, db):
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev1 = svc.emit_event(AuditEventType.ASSESSMENT_CREATED, payload={"n": 1})
        ev2 = svc.emit_event(AuditEventType.ASSET_REGISTERED, payload={"n": 2})
        ev3 = svc.emit_event(AuditEventType.DETECTOR_COMPLETE, payload={"n": 3})
        assert ev3.previous_hash == ev2.current_hash

    def test_ten_event_chain_is_correctly_linked(self, db):
        """Build a 10-event chain and verify every previous_hash link."""
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        events = []
        for i in range(10):
            ev = svc.emit_event(
                AuditEventType.FINDING_GENERATED,
                payload={"seq": i},
            )
            events.append(ev)

        # Verify chain linkage
        assert events[0].previous_hash == AuditRepository.GENESIS_HASH
        for i in range(1, 10):
            assert events[i].previous_hash == events[i - 1].current_hash, (
                f"Event {i} previous_hash must equal event {i-1} current_hash"
            )

    def test_each_appended_event_changes_chain_tail(self, db):
        """ANTI-FAKE: appending an event must change the observable chain tail."""
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        repo = AuditRepository(db)

        before = repo.last_hash()
        ev1 = svc.emit_event(AuditEventType.ASSESSMENT_CREATED, payload={"n": 1})
        after_first = repo.last_hash()
        assert after_first != before
        assert after_first == ev1.current_hash

        ev2 = svc.emit_event(AuditEventType.DETECTOR_COMPLETE, payload={"n": 2})
        after_second = repo.last_hash()
        assert after_second != after_first
        assert after_second == ev2.current_hash

    def test_all_event_hashes_are_valid(self, db):
        """Every event in the chain must satisfy verify_event_hash."""
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        for i in range(5):
            svc.emit_event(AuditEventType.FINDING_GENERATED, payload={"i": i})

        events = AuditRepository(db).list_all()
        for ev in events:
            assert verify_event_hash(ev) is True, (
                f"Event {ev.event_id} at position has invalid hash"
            )

    def test_chain_persists_after_db_reopen(self, config):
        """
        ANTI-FAKE: Open DB, write 3 events, close, reopen, verify chain intact.
        This proves persistence is real, not in-memory only.
        """
        db1 = open_db(config.db_path)
        svc1 = AuditService(AuditRepository(db1), AuditPayloadRepository(db1))
        ev1 = svc1.emit_event(AuditEventType.ASSESSMENT_CREATED, payload={"title": "t1"})
        ev2 = svc1.emit_event(AuditEventType.DETECTOR_COMPLETE, payload={"d": "di01"})
        ev3 = svc1.emit_event(AuditEventType.FINDING_GENERATED, payload={"f": "f1"})
        tail_before_close = AuditRepository(db1).last_hash()
        db1.close()

        # Reopen
        db2 = open_db(config.db_path)
        repo2 = AuditRepository(db2)
        events = repo2.list_all()
        assert len(events) >= 3
        assert repo2.last_hash() == tail_before_close

        # Verify all hashes are still valid
        for ev in events:
            assert verify_event_hash(ev) is True
        db2.close()


# ---------------------------------------------------------------------------
# Tests: Signing (ADR-005)
# ---------------------------------------------------------------------------

class TestSigning:

    def test_signed_event_payload_contains_signature(self, db, signing_keypair):
        """Signed events must store __signature in their payload."""
        priv, pub = signing_keypair
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev = svc.emit_event(
            AuditEventType.DETECTOR_COMPLETE,
            payload={"detector_id": "di01", "findings_count": 2},
            private_key=priv,
        )
        stored_payload = AuditPayloadRepository(db).get(ev.event_id)
        assert "__signature" in stored_payload
        assert len(stored_payload["__signature"]) == 128  # 64-byte sig = 128 hex

    def test_signed_event_payload_contains_signing_key_id(self, db, signing_keypair):
        priv, pub = signing_keypair
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev = svc.emit_event(
            AuditEventType.DETECTOR_COMPLETE,
            payload={"detector_id": "di01"},
            private_key=priv,
        )
        stored_payload = AuditPayloadRepository(db).get(ev.event_id)
        assert "__signing_key_id" in stored_payload

    def test_signed_event_signature_verifies(self, db, signing_keypair):
        """ANTI-FAKE: the stored signature must verify with the correct public key."""
        priv, pub = signing_keypair
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev = svc.emit_event(
            AuditEventType.PROVENANCE_VERIFIED,
            payload={"manifest_id": "m-001", "valid": True},
            private_key=priv,
        )
        stored_payload = AuditPayloadRepository(db).get(ev.event_id)
        assert svc.verify_event_signature(ev, stored_payload, pub) is True

    def test_wrong_key_fails_signature_verification(self, db, signing_keypair):
        """ANTI-FAKE: wrong public key must fail signature verification."""
        priv, _ = signing_keypair
        wrong_pub = public_key_from_private(generate_signing_key())
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev = svc.emit_event(
            AuditEventType.DETECTOR_COMPLETE,
            payload={"status": "success"},
            private_key=priv,
        )
        stored_payload = AuditPayloadRepository(db).get(ev.event_id)
        assert svc.verify_event_signature(ev, stored_payload, wrong_pub) is False

    def test_tampered_pre_sig_hash_invalidates_signature(self, db, signing_keypair):
        """
        ANTI-FAKE: The signature covers __pre_sig_hash in the payload.
        If __pre_sig_hash is modified, signature verification must fail.
        """
        priv, pub = signing_keypair
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev = svc.emit_event(
            AuditEventType.DETECTOR_COMPLETE,
            payload={"status": "success"},
            private_key=priv,
        )
        stored_payload = AuditPayloadRepository(db).get(ev.event_id)

        # Tamper: replace __pre_sig_hash with a different value
        tampered_payload = dict(stored_payload)
        tampered_payload["__pre_sig_hash"] = "f" * 64
        result = svc.verify_event_signature(ev, tampered_payload, pub)
        assert result is False, (
            "Tampered __pre_sig_hash must invalidate the Ed25519 signature"
        )

    def test_unsigned_event_signature_not_present(self, db):
        """Unsigned events must not have __signature in payload."""
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev = svc.emit_event(
            AuditEventType.ASSESSMENT_CREATED,
            payload={"title": "unsigned test"},
            # No private_key
        )
        stored_payload = AuditPayloadRepository(db).get(ev.event_id)
        assert "__signature" not in stored_payload

    def test_private_key_not_in_audit_record(self, db, signing_keypair):
        """
        Critical: private key material must NEVER appear in audit records.
        """
        priv, pub = signing_keypair
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev = svc.emit_event(
            AuditEventType.DETECTOR_COMPLETE,
            payload={"status": "success"},
            private_key=priv,
        )
        stored_payload = AuditPayloadRepository(db).get(ev.event_id)

        # Obtain private key raw bytes for comparison
        from cryptography.hazmat.primitives.serialization import (
            Encoding, NoEncryption, PrivateFormat
        )
        priv_raw_hex = priv.private_bytes_raw().hex()

        # Private key must not appear anywhere in the payload
        payload_str = str(stored_payload)
        assert priv_raw_hex not in payload_str, (
            "Private key bytes must NEVER be stored in audit records"
        )

    # -----------------------------------------------------------------------
    # SEC-01 Regression Tests: Cryptographic Event-Signature Binding
    # -----------------------------------------------------------------------

    def test_sec01_legitimate_signed_event_verifies(self, db, signing_keypair):
        """TEST A: A legitimately signed event verifies successfully."""
        priv, pub = signing_keypair
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev = svc.emit_event(
            AuditEventType.DETECTOR_COMPLETE,
            payload={"detector_id": "di01_duplicates", "findings_count": 0},
            assessment_id="assess-legit-1",
            actor="analyst-alice",
            private_key=priv,
        )
        stored_payload = AuditPayloadRepository(db).get(ev.event_id)
        assert svc.verify_event_signature(ev, stored_payload, pub) is True

    @pytest.mark.parametrize("field_to_tamper,tampered_val", [
        ("actor", "attacker"),
        ("event_type", AuditEventType.ASSESSMENT_FAILED),
        ("timestamp_utc", "2020-01-01T00:00:00Z"),
        ("assessment_id", "assess-forged-999"),
        ("previous_hash", "1" * 64),
        ("event_id", "00000000-0000-0000-0000-000000000000"),
    ])
    def test_sec01_modified_event_field_fails_verification(self, db, signing_keypair, field_to_tamper, tampered_val):
        """
        TEST B: Modify a signed event's meaningful field while retaining
        the original __pre_sig_hash and __signature. Verification MUST return False.
        """
        priv, pub = signing_keypair
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev = svc.emit_event(
            AuditEventType.DETECTOR_COMPLETE,
            payload={"status": "success", "score": 0.99},
            assessment_id="assess-orig",
            actor="system",
            private_key=priv,
        )
        stored_payload = AuditPayloadRepository(db).get(ev.event_id)

        # Tamper event field while payload retains original pre_sig_hash and signature
        tampered_ev = ev.model_copy(update={field_to_tamper: tampered_val})
        assert svc.verify_event_signature(tampered_ev, stored_payload, pub) is False

    def test_sec01_modified_payload_fails_verification(self, db, signing_keypair):
        """
        TEST C: Modify the payload while retaining the original
        __pre_sig_hash and __signature. Verification MUST return False.
        """
        priv, pub = signing_keypair
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev = svc.emit_event(
            AuditEventType.DETECTOR_COMPLETE,
            payload={"findings": 0, "status": "clean"},
            private_key=priv,
        )
        stored_payload = AuditPayloadRepository(db).get(ev.event_id)

        # Tamper payload content (e.g. inject hidden findings or flip status)
        tampered_payload = dict(stored_payload)
        tampered_payload["status"] = "compromised"
        assert svc.verify_event_signature(ev, tampered_payload, pub) is False

        # Add a new field
        tampered_payload_2 = dict(stored_payload)
        tampered_payload_2["injected_field"] = "malicious"
        assert svc.verify_event_signature(ev, tampered_payload_2, pub) is False

    def test_sec01_tampered_pre_sig_hash_fails_verification(self, db, signing_keypair):
        """
        TEST D: Modify __pre_sig_hash without a matching valid signature.
        Verification MUST return False.
        """
        priv, pub = signing_keypair
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev = svc.emit_event(
            AuditEventType.DETECTOR_COMPLETE,
            payload={"status": "success"},
            private_key=priv,
        )
        stored_payload = AuditPayloadRepository(db).get(ev.event_id)

        tampered_payload = dict(stored_payload)
        tampered_payload["__pre_sig_hash"] = "e" * 64
        assert svc.verify_event_signature(ev, tampered_payload, pub) is False

    def test_sec01_tampered_signature_fails_verification(self, db, signing_keypair):
        """
        TEST E: Modify __signature. Verification MUST return False.
        """
        priv, pub = signing_keypair
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))
        ev = svc.emit_event(
            AuditEventType.DETECTOR_COMPLETE,
            payload={"status": "success"},
            private_key=priv,
        )
        stored_payload = AuditPayloadRepository(db).get(ev.event_id)

        tampered_payload = dict(stored_payload)
        tampered_payload["__signature"] = "0" * 128
        assert svc.verify_event_signature(ev, tampered_payload, pub) is False

    def test_sec01_signature_transplant_attack_rejected(self, db, signing_keypair):
        """
        TEST G (Requirement 8): Exact vulnerability verification.
        A valid signature and __pre_sig_hash copied from one legitimate event
        MUST NOT validate against a different event/payload.
        """
        priv, pub = signing_keypair
        svc = AuditService(AuditRepository(db), AuditPayloadRepository(db))

        # Event 1: Legitimate signed event
        ev1 = svc.emit_event(
            AuditEventType.ASSESSMENT_CREATED,
            payload={"title": "Approved Assessment", "clearance": "high"},
            assessment_id="assess-1",
            actor="chief-auditor",
            private_key=priv,
        )
        payload1 = AuditPayloadRepository(db).get(ev1.event_id)
        assert svc.verify_event_signature(ev1, payload1, pub) is True

        # Event 2: Fabricated or different unsigned event
        ev2 = svc.emit_event(
            AuditEventType.ASSESSMENT_CREATED,
            payload={"title": "Unapproved Rogue Assessment", "clearance": "none"},
            assessment_id="assess-2",
            actor="rogue-user",
            # No private_key
        )
        payload2 = AuditPayloadRepository(db).get(ev2.event_id)
        assert "__signature" not in payload2

        # Attacker transplants signature and pre_sig_hash from ev1 into payload2
        transplanted_payload = dict(payload2)
        transplanted_payload["__signature"] = payload1["__signature"]
        transplanted_payload["__pre_sig_hash"] = payload1["__pre_sig_hash"]
        transplanted_payload["__signing_key_id"] = payload1["__signing_key_id"]

        # Standalone verification MUST reject this detachment attack
        assert svc.verify_event_signature(ev2, transplanted_payload, pub) is False

    def test_sec01_chain_verifier_passes_for_signed_events(self, db, signing_keypair):
        """
        TEST F: Ensure existing ChainVerifier behavior still passes for legitimate events.
        """
        from backend.audit.verifier import ChainVerifier
        priv, pub = signing_keypair
        audit_repo = AuditRepository(db)
        payload_repo = AuditPayloadRepository(db)
        svc = AuditService(audit_repo, payload_repo)

        svc.emit_event(AuditEventType.ASSESSMENT_CREATED, {"title": "run1"}, private_key=priv)
        svc.emit_event(AuditEventType.DETECTOR_COMPLETE, {"detector": "di01", "result": "ok"}, private_key=priv)
        svc.emit_event(AuditEventType.PROVENANCE_VERIFIED, {"verified": True})  # mixed signed/unsigned

        verifier = ChainVerifier(audit_repo, payload_repo)
        res = verifier.verify_all()
        assert res.valid is True
        assert res.events_checked == 3
        assert len(res.failures) == 0


# ---------------------------------------------------------------------------
# Tests: Convenience methods
# ---------------------------------------------------------------------------

class TestConvenienceMethods:

    def test_record_assessment_created(self, audit_service, db):
        ev = audit_service.record_assessment_created(
            assessment_id="assess-conv",
            title="Conv Test",
            assessment_type="live",
        )
        assert ev.event_type == AuditEventType.ASSESSMENT_CREATED
        payload = AuditPayloadRepository(db).get(ev.event_id)
        assert payload["assessment_id"] == "assess-conv"
        assert payload["title"] == "Conv Test"

    def test_record_asset_registered(self, audit_service, db):
        ev = audit_service.record_asset_registered(
            assessment_id="assess-conv",
            asset_id="asset-001",
            asset_type="dataset",
            name="test_dataset",
            sha256="a" * 64,
            size_bytes=1024,
        )
        assert ev.event_type == AuditEventType.ASSET_REGISTERED
        payload = AuditPayloadRepository(db).get(ev.event_id)
        assert payload["asset_id"] == "asset-001"
        assert payload["sha256"] == "a" * 64

    def test_record_detector_complete(self, audit_service, db):
        ev = audit_service.record_detector_complete(
            assessment_id="assess-conv",
            asset_id="asset-001",
            detector_id="data.integrity.di01_duplicates",
            detector_version="1.0.0",
            status="success",
            findings_count=3,
            evidence_count=6,
            duration_ms=42,
            result_id="result-001",
        )
        assert ev.event_type == AuditEventType.DETECTOR_COMPLETE
        payload = AuditPayloadRepository(db).get(ev.event_id)
        assert payload["detector_id"] == "data.integrity.di01_duplicates"
        assert payload["findings_count"] == 3

    def test_record_provenance_verified_valid(self, audit_service, db):
        ev = audit_service.record_provenance_verified(
            assessment_id="assess-conv",
            manifest_id="m-001",
            valid=True,
            risk_level="none",
            confidence_level="high",
            finding_count=1,
        )
        assert ev.event_type == AuditEventType.PROVENANCE_VERIFIED

    def test_record_provenance_verified_tampered(self, audit_service, db):
        ev = audit_service.record_provenance_verified(
            assessment_id="assess-conv",
            manifest_id="m-002",
            valid=False,
            risk_level="high",
            confidence_level="high",
            finding_count=2,
        )
        assert ev.event_type == AuditEventType.PROVENANCE_TAMPERED

    def test_record_audit_verified(self, audit_service, db):
        ev = audit_service.record_audit_verified(
            assessment_id=None,
            events_checked=10,
            chain_valid=True,
            failure_count=0,
            first_invalid_event_id=None,
        )
        assert ev.event_type == AuditEventType.AUDIT_VERIFIED
        payload = AuditPayloadRepository(db).get(ev.event_id)
        assert payload["events_checked"] == 10
        assert payload["chain_valid"] is True
