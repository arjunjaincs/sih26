"""
Tests for ARCH-01: PI-01 Replay Detection in Normal Assessment Orchestration.

Verifies that:
- PI-01 replay detection (duplicate manifest_id, duplicate nonce, sequence regression, sequence gap)
  actively participates in normal assessment execution.
- Known manifests are queried from ProvenanceRepository across assessments.
- Verified manifests are persisted to SQLite so replay state survives service restarts.
- Forged/tampered manifests do not poison the replay history.
- Cross-assessment legitimate manifests do not trigger false sequence regression.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.assessment.models import AssessmentRequest
from backend.assessment.orchestrator import AssessmentService
from backend.domain.entities import ProvenanceManifest
from backend.domain.enums import AssessmentState, RiskLevel, Severity
from backend.infra.crypto import generate_nonce, hash_bytes
from backend.infra.db import FindingRepository, ProvenanceRepository, open_db


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def key_pair():
    """Generate an Ed25519 key pair for testing."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    return priv, pub


def _make_signed_manifest(
    private_key: Ed25519PrivateKey,
    *,
    assessment_id: str = "stream-default",
    manifest_id: str | None = None,
    nonce: str | None = None,
    sequence: int = 0,
    corrupt_signature: bool = False,
) -> ProvenanceManifest:
    """Build and sign a valid ProvenanceManifest."""
    from backend.provenance.signing import sign_manifest

    manifest = ProvenanceManifest(
        manifest_id=manifest_id or str(uuid.uuid4()),
        assessment_id=assessment_id,
        input_sha256=hash_bytes(b"test-input-bytes"),
        model_sha256=hash_bytes(b"test-model-bytes"),
        preprocessing_config={"resize": [224, 224]},
        inference_config={"batch_size": 1},
        output_sha256=hash_bytes(b"test-output-bytes"),
        timestamp_utc="2026-01-01T00:00:00Z",
        nonce=nonce or generate_nonce(),
        sequence=sequence,
    )
    signed = sign_manifest(manifest, private_key)
    if corrupt_signature:
        signed = signed.model_copy(update={"signature": "00" * 64})
    return signed


def _get_findings_by_subcategory(db: sqlite3.Connection, result, subcategory: str):
    """Filter all findings from an assessment result by subcategory."""
    all_findings = FindingRepository(db).list_by_assessment(result.assessment_id)
    return [f for f in all_findings if f.subcategory == subcategory]


# ---------------------------------------------------------------------------
# Tests A through K: Orchestrated Replay Detection
# ---------------------------------------------------------------------------

class TestReplayOrchestration:

    def test_a_first_valid_manifest_no_replay(self, tmp_path: Path, key_pair):
        """Test A: First valid manifest presentation has no replay anomalies."""
        priv, pub = key_pair
        db = open_db(tmp_path / "pramaan.db")
        service = AssessmentService(db)

        m1 = _make_signed_manifest(priv, assessment_id="stream-a", sequence=0)
        req = AssessmentRequest(
            title="Assessment A1",
            provenance_manifest=m1,
            provenance_public_key=pub,
        )
        result = service.run_assessment(req)

        assert result.status == AssessmentState.COMPLETE
        replay_findings = _get_findings_by_subcategory(db, result, "replay_detected")
        assert replay_findings == [], "Initial manifest must not trigger replay"
        assert result.overall_risk == RiskLevel.NONE

        # Confirm persisted in repository
        repo = ProvenanceRepository(db)
        stored = repo.get(m1.manifest_id)
        assert stored is not None
        assert stored.manifest_id == m1.manifest_id

    def test_b_same_manifest_resubmitted_detects_replay(self, tmp_path: Path, key_pair):
        """Test B: Re-submitting the exact same manifest triggers duplicate_manifest_id."""
        priv, pub = key_pair
        db = open_db(tmp_path / "pramaan.db")
        service = AssessmentService(db)

        m1 = _make_signed_manifest(priv, assessment_id="stream-b", sequence=0)

        # First run: accepted
        req1 = AssessmentRequest(
            title="Assessment B1",
            provenance_manifest=m1,
            provenance_public_key=pub,
        )
        result1 = service.run_assessment(req1)
        assert result1.status == AssessmentState.COMPLETE
        assert _get_findings_by_subcategory(db, result1, "replay_detected") == []

        # Second run with identical manifest: replayed!
        req2 = AssessmentRequest(
            title="Assessment B2 (Replay)",
            provenance_manifest=m1,
            provenance_public_key=pub,
        )
        result2 = service.run_assessment(req2)
        assert result2.status == AssessmentState.COMPLETE

        replay_findings = _get_findings_by_subcategory(db, result2, "replay_detected")
        assert len(replay_findings) >= 1
        assert any("duplicate_manifest_id" in f.title for f in replay_findings)
        assert any(f.severity == Severity.HIGH for f in replay_findings)
        assert result2.overall_risk == RiskLevel.MEDIUM

    def test_c_same_nonce_in_different_manifest_detects_reuse(self, tmp_path: Path, key_pair):
        """Test C: Fresh manifest reusing an existing nonce triggers duplicate_nonce."""
        priv, pub = key_pair
        db = open_db(tmp_path / "pramaan.db")
        service = AssessmentService(db)

        reused_nonce = generate_nonce()
        m1 = _make_signed_manifest(priv, assessment_id="stream-c1", nonce=reused_nonce, sequence=0)
        m2 = _make_signed_manifest(priv, assessment_id="stream-c2", nonce=reused_nonce, sequence=0)
        assert m1.manifest_id != m2.manifest_id

        # First run
        result1 = service.run_assessment(AssessmentRequest(
            title="Assessment C1",
            provenance_manifest=m1,
            provenance_public_key=pub,
        ))
        assert _get_findings_by_subcategory(db, result1, "replay_detected") == []

        # Second run with different manifest reusing nonce
        result2 = service.run_assessment(AssessmentRequest(
            title="Assessment C2 (Nonce Reuse)",
            provenance_manifest=m2,
            provenance_public_key=pub,
        ))
        replay_findings = _get_findings_by_subcategory(db, result2, "replay_detected")
        assert len(replay_findings) >= 1
        assert any("duplicate_nonce" in f.title for f in replay_findings)
        assert any(f.severity == Severity.HIGH for f in replay_findings)

    def test_d_sequence_regression_detected(self, tmp_path: Path, key_pair):
        """Test D: Regressing sequence in the same stream triggers sequence_regression."""
        priv, pub = key_pair
        db = open_db(tmp_path / "pramaan.db")
        service = AssessmentService(db)

        stream_id = "stream-regress"
        m0 = _make_signed_manifest(priv, assessment_id=stream_id, sequence=0)
        result0 = service.run_assessment(AssessmentRequest(
            title="Assessment D0",
            provenance_manifest=m0,
            provenance_public_key=pub,
        ))
        assert _get_findings_by_subcategory(db, result0, "replay_detected") == []

        # Next event in same stream presents sequence=0 instead of expected 1
        m_regress = _make_signed_manifest(priv, assessment_id=stream_id, sequence=0)
        result_regress = service.run_assessment(AssessmentRequest(
            title="Assessment D1 (Regression)",
            provenance_manifest=m_regress,
            provenance_public_key=pub,
        ))
        replay_findings = _get_findings_by_subcategory(db, result_regress, "replay_detected")
        assert len(replay_findings) >= 1
        assert any("sequence_regression" in f.title for f in replay_findings)
        assert any(f.severity == Severity.MEDIUM for f in replay_findings)

    def test_e_sequence_gap_detected(self, tmp_path: Path, key_pair):
        """Test E: Skipping sequence numbers triggers sequence_gap."""
        priv, pub = key_pair
        db = open_db(tmp_path / "pramaan.db")
        service = AssessmentService(db)

        stream_id = "stream-gap"
        m0 = _make_signed_manifest(priv, assessment_id=stream_id, sequence=0)
        result0 = service.run_assessment(AssessmentRequest(
            title="Assessment E0",
            provenance_manifest=m0,
            provenance_public_key=pub,
        ))
        assert _get_findings_by_subcategory(db, result0, "replay_detected") == []

        # Next event presents sequence=4 instead of expected 1
        m_gap = _make_signed_manifest(priv, assessment_id=stream_id, sequence=4)
        result_gap = service.run_assessment(AssessmentRequest(
            title="Assessment E1 (Gap)",
            provenance_manifest=m_gap,
            provenance_public_key=pub,
        ))
        replay_findings = _get_findings_by_subcategory(db, result_gap, "replay_detected")
        assert len(replay_findings) >= 1
        assert any("sequence_gap" in f.title for f in replay_findings)
        assert any(f.severity == Severity.MEDIUM for f in replay_findings)

    def test_f_different_legitimate_manifest_no_false_replay(self, tmp_path: Path, key_pair):
        """Test F: Fresh legitimate manifest in new stream does NOT trigger false replay."""
        priv, pub = key_pair
        db = open_db(tmp_path / "pramaan.db")
        service = AssessmentService(db)

        # Assessment 1
        m1 = _make_signed_manifest(priv, assessment_id="stream-f1", sequence=0)
        result1 = service.run_assessment(AssessmentRequest(
            title="Assessment F1",
            provenance_manifest=m1,
            provenance_public_key=pub,
        ))
        assert _get_findings_by_subcategory(db, result1, "replay_detected") == []

        # Assessment 2: completely new stream, starting at sequence=0
        m2 = _make_signed_manifest(priv, assessment_id="stream-f2", sequence=0)
        result2 = service.run_assessment(AssessmentRequest(
            title="Assessment F2 (Fresh Stream)",
            provenance_manifest=m2,
            provenance_public_key=pub,
        ))
        replay_findings = _get_findings_by_subcategory(db, result2, "replay_detected")
        assert replay_findings == [], "New legitimate stream must not trigger sequence regression"
        assert result2.overall_risk == RiskLevel.NONE

    def test_g_replay_detection_persists_across_restarts(self, tmp_path: Path, key_pair):
        """Test G: Replay history is stored in SQLite and persists across service restarts."""
        priv, pub = key_pair
        db_path = tmp_path / "persistent_pramaan.db"

        # Session 1: run assessment and close connection
        db1 = open_db(db_path)
        service1 = AssessmentService(db1)
        m1 = _make_signed_manifest(priv, assessment_id="stream-persist", sequence=0)
        res1 = service1.run_assessment(AssessmentRequest(
            title="Session 1",
            provenance_manifest=m1,
            provenance_public_key=pub,
        ))
        assert res1.status == AssessmentState.COMPLETE
        db1.close()

        # Session 2: brand new connection and service instance
        db2 = open_db(db_path)
        service2 = AssessmentService(db2)

        # Attempt to replay m1
        res2 = service2.run_assessment(AssessmentRequest(
            title="Session 2 (Replay after restart)",
            provenance_manifest=m1,
            provenance_public_key=pub,
        ))
        replay_findings = _get_findings_by_subcategory(db2, res2, "replay_detected")
        db2.close()

        assert len(replay_findings) >= 1
        assert any("duplicate_manifest_id" in f.title for f in replay_findings)

    def test_h_forged_manifest_not_persisted(self, tmp_path: Path, key_pair):
        """Test H: Forged signature manifest is rejected and NOT saved to poison replay history."""
        priv, pub = key_pair
        db = open_db(tmp_path / "pramaan.db")
        service = AssessmentService(db)

        m_forged = _make_signed_manifest(
            priv, assessment_id="stream-forged", sequence=0, corrupt_signature=True
        )
        res = service.run_assessment(AssessmentRequest(
            title="Forged Manifest Assessment",
            provenance_manifest=m_forged,
            provenance_public_key=pub,
        ))

        # Must report signature invalid
        sig_findings = _get_findings_by_subcategory(db, res, "signature_invalid")
        assert len(sig_findings) >= 1

        # Must NOT be persisted in repository
        repo = ProvenanceRepository(db)
        assert repo.get(m_forged.manifest_id) is None
        assert repo.list_all() == []

    def test_i_replayed_manifest_not_duplicated_in_repo(self, tmp_path: Path, key_pair):
        """Test I: Replayed manifest does not create duplicate entries in repository."""
        priv, pub = key_pair
        db = open_db(tmp_path / "pramaan.db")
        service = AssessmentService(db)

        m1 = _make_signed_manifest(priv, assessment_id="stream-dup", sequence=0)
        service.run_assessment(AssessmentRequest(
            title="Run 1",
            provenance_manifest=m1,
            provenance_public_key=pub,
        ))
        repo = ProvenanceRepository(db)
        assert len(repo.list_all()) == 1

        # Replay attempt
        service.run_assessment(AssessmentRequest(
            title="Run 2 (Replay)",
            provenance_manifest=m1,
            provenance_public_key=pub,
        ))
        assert len(repo.list_all()) == 1

    def test_j_valid_sequence_progression_in_same_stream(self, tmp_path: Path, key_pair):
        """Test J: Monotonic sequence progression (0 -> 1) passes without replay anomalies."""
        priv, pub = key_pair
        db = open_db(tmp_path / "pramaan.db")
        service = AssessmentService(db)

        stream_id = "stream-progression"
        m0 = _make_signed_manifest(priv, assessment_id=stream_id, sequence=0)
        m1 = _make_signed_manifest(priv, assessment_id=stream_id, sequence=1)

        res0 = service.run_assessment(AssessmentRequest(
            title="Stream Event 0",
            provenance_manifest=m0,
            provenance_public_key=pub,
        ))
        assert _get_findings_by_subcategory(db, res0, "replay_detected") == []

        res1 = service.run_assessment(AssessmentRequest(
            title="Stream Event 1",
            provenance_manifest=m1,
            provenance_public_key=pub,
        ))
        assert _get_findings_by_subcategory(db, res1, "replay_detected") == []
        assert res1.overall_risk == RiskLevel.NONE

        repo = ProvenanceRepository(db)
        assert len(repo.list_by_assessment(stream_id)) == 2

    def test_k_assessment_without_manifest_runs_normally(self, tmp_path: Path):
        """Test K: Assessment without provenance manifest runs unaffected."""
        db = open_db(tmp_path / "pramaan.db")
        service = AssessmentService(db)

        req = AssessmentRequest(
            title="Dataset-only or Empty Assessment",
            dataset_path=None,
            model_path=None,
            provenance_manifest=None,
        )
        # Without any assets it will fail closed
        result = service.run_assessment(req)
        assert result.status == AssessmentState.FAILED
        assert "at least one of dataset_path, model_path, or provenance_manifest must be provided" in (result.error or "")
