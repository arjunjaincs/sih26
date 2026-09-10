"""
Tests for audit event hashing (backend/audit/hashing.py).

Coverage:
  - compute_payload_digest: deterministic, changes when payload changes
  - compute_event_hash: deterministic, identical event → identical hash
  - compute_event_hash excludes current_hash from its own computation
  - Every hashed field independently causes a different hash when changed
  - assessment_id=None handled correctly (JSON null)
  - verify_event_hash: passes for correct hash, fails for modified events

ANTI-FAKE:
  - Proves that changing any single field changes the hash (real hashing)
  - Proves that the same inputs always produce the same hash (determinism)
"""

from __future__ import annotations

import uuid

import pytest

from backend.audit.hashing import (
    compute_event_hash,
    compute_payload_digest,
    verify_event_hash,
)
from backend.domain.entities import AuditEvent
from backend.domain.enums import AuditEventType
from backend.infra.db import AuditRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    *,
    event_type: AuditEventType = AuditEventType.ASSESSMENT_CREATED,
    assessment_id: str | None = "assess-hash-test",
    actor: str = "system",
    payload_digest: str = "a" * 64,
    previous_hash: str = AuditRepository.GENESIS_HASH,
    timestamp_utc: str = "2026-01-01T00:00:00Z",
    event_id: str | None = None,
) -> AuditEvent:
    """Create an AuditEvent with explicit current_hash (set to empty — filled by caller)."""
    ev = AuditEvent(
        event_type=event_type,
        timestamp_utc=timestamp_utc,
        assessment_id=assessment_id,
        actor=actor,
        payload_digest=payload_digest,
        previous_hash=previous_hash,
        current_hash="",  # Will be replaced
    )
    if event_id is not None:
        ev = ev.model_copy(update={"event_id": event_id})
    return ev


def _with_correct_hash(event: AuditEvent) -> AuditEvent:
    """Return event with correct current_hash set."""
    h = compute_event_hash(event)
    return event.model_copy(update={"current_hash": h})


# ---------------------------------------------------------------------------
# Tests: compute_payload_digest
# ---------------------------------------------------------------------------

class TestPayloadDigest:

    def test_deterministic(self):
        payload = {"a": 1, "b": "hello", "c": [1, 2, 3]}
        d1 = compute_payload_digest(payload)
        d2 = compute_payload_digest(payload)
        assert d1 == d2

    def test_returns_64_hex_chars(self):
        d = compute_payload_digest({"key": "value"})
        assert len(d) == 64
        assert all(c in "0123456789abcdef" for c in d)

    def test_empty_payload_is_valid(self):
        d = compute_payload_digest({})
        assert len(d) == 64

    def test_different_payload_different_digest(self):
        """ANTI-FAKE: changing payload must change digest."""
        d1 = compute_payload_digest({"result": "pass"})
        d2 = compute_payload_digest({"result": "fail"})
        assert d1 != d2

    def test_key_order_independent(self):
        """Dict insertion order must NOT affect digest."""
        d1 = compute_payload_digest({"b": 2, "a": 1})
        d2 = compute_payload_digest({"a": 1, "b": 2})
        assert d1 == d2, "canonical_json must sort keys"

    def test_added_key_changes_digest(self):
        d1 = compute_payload_digest({"a": 1})
        d2 = compute_payload_digest({"a": 1, "b": 2})
        assert d1 != d2

    def test_changed_value_changes_digest(self):
        d1 = compute_payload_digest({"findings_count": 0})
        d2 = compute_payload_digest({"findings_count": 1})
        assert d1 != d2

    def test_nested_dict_change_changes_digest(self):
        d1 = compute_payload_digest({"meta": {"status": "ok"}})
        d2 = compute_payload_digest({"meta": {"status": "tampered"}})
        assert d1 != d2


# ---------------------------------------------------------------------------
# Tests: compute_event_hash
# ---------------------------------------------------------------------------

class TestEventHash:

    def test_deterministic(self):
        """ANTI-FAKE: same event must always produce same hash."""
        ev = _make_event(event_id="fixed-id-001")
        h1 = compute_event_hash(ev)
        h2 = compute_event_hash(ev)
        assert h1 == h2

    def test_returns_64_hex_chars(self):
        ev = _make_event()
        h = compute_event_hash(ev)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_does_not_include_current_hash(self):
        """
        CRITICAL: current_hash must NOT be included in its own computation.
        Two events identical except for stored current_hash must hash identically.
        """
        ev = _make_event(event_id="crit-test")
        ev1 = ev.model_copy(update={"current_hash": "a" * 64})
        ev2 = ev.model_copy(update={"current_hash": "b" * 64})
        assert compute_event_hash(ev1) == compute_event_hash(ev2), (
            "current_hash must be excluded from hash computation"
        )

    # --- Per-field tamper tests ---
    # ANTI-FAKE: changing any single hashed field must change the hash.

    def test_different_event_id_different_hash(self):
        e1 = _make_event(event_id=str(uuid.uuid4()))
        e2 = _make_event(event_id=str(uuid.uuid4()))
        assert compute_event_hash(e1) != compute_event_hash(e2)

    def test_different_event_type_different_hash(self):
        e1 = _make_event(event_type=AuditEventType.ASSESSMENT_CREATED)
        e2 = _make_event(event_type=AuditEventType.DETECTOR_COMPLETE)
        # Ensure same event_id
        e2 = e2.model_copy(update={"event_id": e1.event_id})
        assert compute_event_hash(e1) != compute_event_hash(e2)

    def test_different_timestamp_different_hash(self):
        base = _make_event(event_id="ts-test")
        e1 = base.model_copy(update={"timestamp_utc": "2026-01-01T00:00:00Z"})
        e2 = base.model_copy(update={"timestamp_utc": "2026-12-31T23:59:59Z"})
        assert compute_event_hash(e1) != compute_event_hash(e2)

    def test_different_assessment_id_different_hash(self):
        base = _make_event(event_id="assess-test")
        e1 = base.model_copy(update={"assessment_id": "assess-A"})
        e2 = base.model_copy(update={"assessment_id": "assess-B"})
        assert compute_event_hash(e1) != compute_event_hash(e2)

    def test_null_vs_non_null_assessment_id_different_hash(self):
        base = _make_event(event_id="null-test")
        e1 = base.model_copy(update={"assessment_id": None})
        e2 = base.model_copy(update={"assessment_id": "some-assess"})
        assert compute_event_hash(e1) != compute_event_hash(e2)

    def test_different_actor_different_hash(self):
        base = _make_event(event_id="actor-test")
        e1 = base.model_copy(update={"actor": "system"})
        e2 = base.model_copy(update={"actor": "analyst"})
        assert compute_event_hash(e1) != compute_event_hash(e2)

    def test_different_payload_digest_different_hash(self):
        base = _make_event(event_id="pd-test")
        e1 = base.model_copy(update={"payload_digest": "a" * 64})
        e2 = base.model_copy(update={"payload_digest": "b" * 64})
        assert compute_event_hash(e1) != compute_event_hash(e2)

    def test_different_previous_hash_different_hash(self):
        base = _make_event(event_id="ph-test")
        e1 = base.model_copy(update={"previous_hash": "0" * 64})
        e2 = base.model_copy(update={"previous_hash": "f" * 64})
        assert compute_event_hash(e1) != compute_event_hash(e2)


# ---------------------------------------------------------------------------
# Tests: verify_event_hash
# ---------------------------------------------------------------------------

class TestVerifyEventHash:

    def test_correct_hash_passes(self):
        ev = _with_correct_hash(_make_event())
        assert verify_event_hash(ev) is True

    def test_wrong_stored_hash_fails(self):
        """ANTI-FAKE: a tampered current_hash field must fail verification."""
        ev = _make_event()
        ev = ev.model_copy(update={"current_hash": "f" * 64})  # Wrong hash
        assert verify_event_hash(ev) is False

    def test_tampered_payload_digest_fails(self):
        """ANTI-FAKE: changing payload_digest after hashing must fail verify."""
        ev = _with_correct_hash(_make_event())
        # Tamper: change payload_digest but keep the old (now wrong) current_hash
        tampered = ev.model_copy(update={"payload_digest": "c" * 64})
        assert verify_event_hash(tampered) is False

    def test_tampered_timestamp_fails(self):
        ev = _with_correct_hash(_make_event())
        tampered = ev.model_copy(update={"timestamp_utc": "2099-01-01T00:00:00Z"})
        assert verify_event_hash(tampered) is False

    def test_tampered_previous_hash_fails(self):
        ev = _with_correct_hash(_make_event())
        tampered = ev.model_copy(update={"previous_hash": "e" * 64})
        assert verify_event_hash(tampered) is False

    def test_tampered_assessment_id_fails(self):
        ev = _with_correct_hash(_make_event())
        tampered = ev.model_copy(update={"assessment_id": "attacker-assessment"})
        assert verify_event_hash(tampered) is False

    def test_tampered_actor_fails(self):
        ev = _with_correct_hash(_make_event())
        tampered = ev.model_copy(update={"actor": "attacker"})
        assert verify_event_hash(tampered) is False

    def test_tampered_event_type_fails(self):
        ev = _with_correct_hash(_make_event(event_type=AuditEventType.ASSESSMENT_CREATED))
        tampered = ev.model_copy(update={"event_type": AuditEventType.ASSESSMENT_FAILED})
        assert verify_event_hash(tampered) is False
