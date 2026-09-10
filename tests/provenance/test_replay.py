"""
Tests for provenance replay and consistency detection.

Coverage:
  - Fresh event with unique nonce → no anomalies
  - Duplicate nonce → replay detected
  - Duplicate manifest_id → replay detected
  - Correct sequence continuation → no anomaly
  - Sequence regression (candidate.sequence < max_known + 1) → anomaly
  - Sequence gap (candidate.sequence > max_known + 1) → anomaly
  - Empty known_manifests → no sequence anomaly
  - Documented limitations tested by explicit comments

Limitations documented (per module docstring):
  - Cross-assessment replay is NOT detected
  - An attacker generating a fresh nonce for a replayed event avoids nonce detection
  - Timestamp ordering is NOT cryptographically enforced
"""

from __future__ import annotations

import uuid

import pytest

from backend.domain.entities import ProvenanceManifest
from backend.infra.crypto import generate_nonce
from backend.provenance.replay import detect_replay, ReplayAnomaly


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _manifest(
    *,
    manifest_id: str | None = None,
    nonce: str | None = None,
    sequence: int = 0,
    assessment_id: str = "assess-replay-test",
) -> ProvenanceManifest:
    """Create a minimal ProvenanceManifest for replay tests."""
    return ProvenanceManifest(
        manifest_id=manifest_id or str(uuid.uuid4()),
        assessment_id=assessment_id,
        input_sha256="a" * 64,
        model_sha256="b" * 64,
        preprocessing_config={},
        inference_config={},
        output_sha256="c" * 64,
        timestamp_utc="2026-01-01T00:00:00Z",
        nonce=nonce or generate_nonce(),
        sequence=sequence,
    )


def _anomaly_types(anomalies: list[ReplayAnomaly]) -> list[str]:
    return [a.anomaly_type for a in anomalies]


# ---------------------------------------------------------------------------
# Tests: No anomalies (happy path)
# ---------------------------------------------------------------------------

class TestNoAnomalies:

    def test_fresh_event_no_known_manifests(self):
        """First event against empty history → no anomalies."""
        candidate = _manifest(sequence=0)
        anomalies = detect_replay(candidate, known_manifests=[])
        assert anomalies == []

    def test_fresh_event_unique_nonce_correct_sequence(self):
        """Second event with unique nonce and correct sequence → no anomalies."""
        prior = _manifest(sequence=0)
        candidate = _manifest(sequence=1)  # Fresh nonce, correct next sequence
        anomalies = detect_replay(candidate, known_manifests=[prior])
        assert anomalies == []

    def test_multiple_fresh_events(self):
        """Chain of correctly sequenced events → no anomalies."""
        knowns = [_manifest(sequence=i) for i in range(5)]
        candidate = _manifest(sequence=5)
        anomalies = detect_replay(candidate, known_manifests=knowns)
        assert anomalies == []


# ---------------------------------------------------------------------------
# Tests: Duplicate nonce
# ---------------------------------------------------------------------------

class TestDuplicateNonce:

    def test_duplicate_nonce_detected(self):
        """ANTI-FAKE: a repeated nonce must be detected as replay."""
        shared_nonce = generate_nonce()
        prior = _manifest(nonce=shared_nonce, sequence=0)
        candidate = _manifest(nonce=shared_nonce, sequence=1)  # Same nonce!

        anomalies = detect_replay(candidate, known_manifests=[prior])
        assert "duplicate_nonce" in _anomaly_types(anomalies), (
            "Repeated nonce must trigger duplicate_nonce anomaly"
        )

    def test_duplicate_nonce_anomaly_references_correct_manifests(self):
        shared_nonce = generate_nonce()
        prior = _manifest(nonce=shared_nonce, sequence=0)
        candidate = _manifest(nonce=shared_nonce, sequence=1)

        anomalies = detect_replay(candidate, known_manifests=[prior])
        nonce_anomalies = [a for a in anomalies if a.anomaly_type == "duplicate_nonce"]
        assert len(nonce_anomalies) == 1
        a = nonce_anomalies[0]
        assert a.candidate_manifest_id == candidate.manifest_id
        assert a.conflicting_manifest_id == prior.manifest_id

    def test_duplicate_nonce_evidence_contains_nonce(self):
        shared_nonce = generate_nonce()
        prior = _manifest(nonce=shared_nonce, sequence=0)
        candidate = _manifest(nonce=shared_nonce, sequence=1)

        anomalies = detect_replay(candidate, known_manifests=[prior])
        a = next(x for x in anomalies if x.anomaly_type == "duplicate_nonce")
        assert "nonce" in a.evidence
        assert a.evidence["nonce"] == shared_nonce

    def test_unique_nonces_no_anomaly(self):
        """Different nonces → no nonce anomaly."""
        prior = _manifest(nonce=generate_nonce(), sequence=0)
        candidate = _manifest(nonce=generate_nonce(), sequence=1)
        anomalies = detect_replay(candidate, known_manifests=[prior])
        nonce_anomalies = [a for a in anomalies if a.anomaly_type == "duplicate_nonce"]
        assert nonce_anomalies == []

    def test_duplicate_nonce_across_multiple_priors(self):
        """Nonce shared with any prior → detected."""
        shared_nonce = generate_nonce()
        priors = [_manifest(sequence=i) for i in range(4)]
        # Third prior uses the shared nonce
        priors[2] = _manifest(nonce=shared_nonce, sequence=2)

        candidate = _manifest(nonce=shared_nonce, sequence=4)
        anomalies = detect_replay(candidate, known_manifests=priors)
        nonce_anomalies = [a for a in anomalies if a.anomaly_type == "duplicate_nonce"]
        assert len(nonce_anomalies) == 1
        assert nonce_anomalies[0].conflicting_manifest_id == priors[2].manifest_id


# ---------------------------------------------------------------------------
# Tests: Duplicate manifest_id
# ---------------------------------------------------------------------------

class TestDuplicateManifestId:

    def test_duplicate_manifest_id_detected(self):
        """ANTI-FAKE: a repeated manifest_id must be detected."""
        shared_id = str(uuid.uuid4())
        prior = _manifest(manifest_id=shared_id, sequence=0)
        candidate = _manifest(manifest_id=shared_id, sequence=0)

        anomalies = detect_replay(candidate, known_manifests=[prior])
        assert "duplicate_manifest_id" in _anomaly_types(anomalies)

    def test_unique_manifest_ids_no_anomaly(self):
        prior = _manifest(sequence=0)
        candidate = _manifest(sequence=1)  # New UUID
        anomalies = detect_replay(candidate, known_manifests=[prior])
        id_anomalies = [a for a in anomalies if a.anomaly_type == "duplicate_manifest_id"]
        assert id_anomalies == []


# ---------------------------------------------------------------------------
# Tests: Sequence consistency
# ---------------------------------------------------------------------------

class TestSequenceConsistency:

    def test_correct_next_sequence_no_anomaly(self):
        """max known = 3, candidate = 4 → correct, no anomaly."""
        knowns = [_manifest(sequence=i) for i in range(4)]
        candidate = _manifest(sequence=4)
        anomalies = detect_replay(candidate, known_manifests=knowns)
        seq_anomalies = [a for a in anomalies if a.anomaly_type in (
            "sequence_gap", "sequence_regression"
        )]
        assert seq_anomalies == []

    def test_sequence_regression_detected(self):
        """max known = 5, candidate sequence = 3 → regression."""
        knowns = [_manifest(sequence=i) for i in range(6)]
        candidate = _manifest(sequence=3)  # Should be 6
        anomalies = detect_replay(candidate, known_manifests=knowns)
        assert "sequence_regression" in _anomaly_types(anomalies)

    def test_sequence_regression_evidence(self):
        knowns = [_manifest(sequence=i) for i in range(6)]
        candidate = _manifest(sequence=2)

        anomalies = detect_replay(candidate, known_manifests=knowns)
        a = next(x for x in anomalies if x.anomaly_type == "sequence_regression")
        assert a.evidence["candidate_sequence"] == 2
        assert a.evidence["max_known_sequence"] == 5
        assert a.evidence["expected_next_sequence"] == 6

    def test_sequence_gap_detected(self):
        """max known = 3, candidate = 7 → gap (sequences 4,5,6 are missing)."""
        knowns = [_manifest(sequence=i) for i in range(4)]
        candidate = _manifest(sequence=7)
        anomalies = detect_replay(candidate, known_manifests=knowns)
        assert "sequence_gap" in _anomaly_types(anomalies)

    def test_sequence_gap_evidence(self):
        knowns = [_manifest(sequence=i) for i in range(4)]
        candidate = _manifest(sequence=7)

        anomalies = detect_replay(candidate, known_manifests=knowns)
        a = next(x for x in anomalies if x.anomaly_type == "sequence_gap")
        assert a.evidence["candidate_sequence"] == 7
        assert a.evidence["max_known_sequence"] == 3
        assert a.evidence["expected_next_sequence"] == 4
        assert a.evidence["gap_size"] == 3  # sequences 4,5,6 missing

    def test_no_sequence_check_with_empty_known_manifests(self):
        """No known manifests → no sequence anomaly can be raised."""
        candidate = _manifest(sequence=999)
        anomalies = detect_replay(candidate, known_manifests=[])
        seq_anomalies = [a for a in anomalies if a.anomaly_type in (
            "sequence_gap", "sequence_regression"
        )]
        assert seq_anomalies == []

    def test_sequence_zero_is_first_valid(self):
        """The very first event (sequence=0) against empty history → no anomaly."""
        candidate = _manifest(sequence=0)
        assert detect_replay(candidate, known_manifests=[]) == []


# ---------------------------------------------------------------------------
# Tests: Multiple anomalies
# ---------------------------------------------------------------------------

class TestMultipleAnomalies:

    def test_duplicate_nonce_and_regression_both_reported(self):
        """
        An event can trigger multiple anomaly types simultaneously.
        Here: duplicate nonce + sequence regression.
        """
        shared_nonce = generate_nonce()
        knowns = [_manifest(sequence=i) for i in range(5)]
        knowns[2] = _manifest(nonce=shared_nonce, sequence=2)

        candidate = _manifest(nonce=shared_nonce, sequence=2)  # Reused nonce + regression
        anomalies = detect_replay(candidate, known_manifests=knowns)

        types = _anomaly_types(anomalies)
        assert "duplicate_nonce" in types
        assert "sequence_regression" in types


# ---------------------------------------------------------------------------
# Limitation documentation tests
# ---------------------------------------------------------------------------

class TestKnownLimitations:

    def test_fresh_nonce_on_replayed_event_not_detected(self):
        """
        DOCUMENTED LIMITATION: An attacker who generates a fresh nonce for a
        replayed event will NOT be detected by nonce comparison alone.
        The only defence is that the signed manifest fields (input/output hashes)
        must also match the original, which PI-01 verifies separately.
        """
        original = _manifest(sequence=0)
        # Attacker creates same logical event but with a fresh nonce
        # (same input/output/model hashes, different nonce)
        # This is NOT detected by replay alone.
        attacker_manifest = _manifest(
            nonce=generate_nonce(),  # Fresh nonce: avoids nonce detection
            sequence=1,
        )
        # Different manifest_id, different nonce → no replay detected
        anomalies = detect_replay(attacker_manifest, known_manifests=[original])
        # Confirm: NOT detected (limitation acknowledged)
        nonce_anomalies = [a for a in anomalies if a.anomaly_type == "duplicate_nonce"]
        assert nonce_anomalies == [], (
            "DOCUMENTED LIMITATION: fresh-nonce replay cannot be detected by nonce comparison. "
            "This test confirms the limitation is real."
        )
