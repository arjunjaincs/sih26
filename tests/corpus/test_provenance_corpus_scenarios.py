"""
PRAMAAN v1 — Phase 17 Provenance Assurance Corpus Test Suite.

Automated validation suite demonstrating that PRAMAAN can:
1. bind an input image to its hash
2. bind a model identity/hash
3. bind preprocessing configuration
4. bind inference configuration
5. bind output hash
6. sign the canonical manifest
7. verify the signature
8. detect altered manifests
9. detect altered outputs
10. detect replay
11. detect sequence anomalies
12. integrate provenance evidence into the assessment/audit workflow
13. explicitly represent limitations where replay cannot be detected

Tests Covered:
  Test A: Valid provenance (01_clean_provenance)
  Test B: Tampering scenarios (02, 03, 04, 05)
  Test C: Duplicate replay (06)
  Test D: Sequence regression (07)
  Test E: Sequence gap (08)
  Test F: Fresh nonce limitation (09)
  Test G: Audit integration (10)
  Test H: Signature binding & SEC-01 regression protection (11)
  Test I: Malformed input fail-closed (12)
  Test J: Persistence & restart (13)
  Test K: Deterministic corpus generation
  Test L: SHA-256 correctness & canonicalization
  Test M: FastAPI API E2E
  Test N: Security & network isolation
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.assessment.models import AssessmentRequest
from backend.assessment.orchestrator import AssessmentService
from backend.audit.service import AuditService
from backend.audit.verifier import ChainVerifier
from backend.detectors.base import DetectorContext
from backend.detectors.provenance.pi01_integrity import (
    PI01Context,
    PI01ProvenanceIntegrityDetector,
)
from backend.domain.entities import ProvenanceManifest
from backend.domain.enums import AssessmentState, RiskLevel, Severity
from backend.infra.crypto import canonical_json, hash_bytes
from backend.infra.db import (
    AuditPayloadRepository,
    AuditRepository,
    FindingRepository,
    ProvenanceRepository,
    open_db,
)
from backend.provenance.signing import (
    canonicalize_manifest,
    digest_manifest,
    sign_manifest,
    verify_manifest,
)
from backend.tools.provenance_corpus_generator import (
    DEFAULT_CORPUS_ROOT,
    ProvenanceCorpusGenerator,
    _derive_deterministic_keypair,
    validate_provenance_scenario,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def corpus_root() -> Path:
    """Ensure corpus is generated and return its root directory."""
    root = DEFAULT_CORPUS_ROOT.resolve()
    if not (root / "corpus_manifest.json").exists():
        gen = ProvenanceCorpusGenerator(root)
        gen.generate_all()
    return root


@pytest.fixture
def test_db(tmp_path: Path) -> sqlite3.Connection:
    """Provide an isolated, schema-migrated SQLite connection."""
    db_path = tmp_path / "pramaan_test.db"
    conn = open_db(db_path)
    yield conn
    conn.close()


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch) -> TestClient:
    """Provide a FastAPI TestClient bound to a clean isolated test database."""
    db_path = tmp_path / "api_test.db"
    open_db(db_path).close()
    monkeypatch.setenv("PRAMAAN_DB_PATH", str(db_path))
    monkeypatch.setenv("PRAMAAN_BLOB_DIR", str(tmp_path / "blobs"))
    app = create_app()
    return TestClient(app)


# ===========================================================================
# Test A: Valid Provenance (01_clean_provenance)
# ===========================================================================

class TestValidProvenance:
    """Scenario 01: Clean Baseline Provenance."""

    def test_clean_provenance_passes_all_checks(self, corpus_root: Path):
        scen_path = corpus_root / "scenarios/01_clean_provenance"
        res = validate_provenance_scenario(scen_path)
        assert res["passed"] is True, f"Validation failure: {res}"
        assert res["observed_risk"] == "none"
        assert res["observed_confidence"] == "high"
        assert "provenance_valid" in res["observed_subcategories"]
        assert res["replay_anomalies"] == []


# ===========================================================================
# Test B: Tampering Scenarios (02, 03, 04, 05)
# ===========================================================================

class TestTamperingScenarios:
    """Scenarios 02, 03, 04, 05: Tampering detection with high confidence."""

    def test_02_input_tampering_detected(self, corpus_root: Path):
        scen_path = corpus_root / "scenarios/02_input_tampering"
        res = validate_provenance_scenario(scen_path)
        assert res["passed"] is True, f"Validation failure: {res}"
        assert res["observed_risk"] == "high"
        assert res["observed_confidence"] == "high"
        assert "input_mismatch" in res["observed_subcategories"]

    def test_03_model_tampering_detected(self, corpus_root: Path):
        scen_path = corpus_root / "scenarios/03_model_tampering"
        res = validate_provenance_scenario(scen_path)
        assert res["passed"] is True, f"Validation failure: {res}"
        assert res["observed_risk"] == "high"
        assert res["observed_confidence"] == "high"
        assert "model_mismatch" in res["observed_subcategories"]

    def test_04_output_tampering_detected(self, corpus_root: Path):
        scen_path = corpus_root / "scenarios/04_output_tampering"
        res = validate_provenance_scenario(scen_path)
        assert res["passed"] is True, f"Validation failure: {res}"
        assert res["observed_risk"] == "high"
        assert res["observed_confidence"] == "high"
        assert "output_mismatch" in res["observed_subcategories"]

    def test_05_manifest_tampering_detected(self, corpus_root: Path):
        scen_path = corpus_root / "scenarios/05_manifest_tampering"
        res = validate_provenance_scenario(scen_path)
        assert res["passed"] is True, f"Validation failure: {res}"
        assert res["observed_risk"] == "high"
        assert res["observed_confidence"] == "high"
        assert "signature_invalid" in res["observed_subcategories"]


# ===========================================================================
# Test C: Duplicate Replay (06_duplicate_replay)
# ===========================================================================

class TestDuplicateReplay:
    """Scenario 06: Replayed nonce and manifest identity."""

    def test_duplicate_replay_detected_by_detector(self, corpus_root: Path):
        scen_path = corpus_root / "scenarios/06_duplicate_replay"
        res = validate_provenance_scenario(scen_path)
        assert res["passed"] is True, f"Validation failure: {res}"
        assert res["observed_risk"] == "medium"
        assert res["observed_confidence"] == "high"
        assert "replay_detected" in res["observed_subcategories"]

    def test_duplicate_replay_via_assessment_service(self, corpus_root: Path, test_db: sqlite3.Connection):
        """ARCH-01 Protection: AssessmentService checks and persists known manifests."""
        scen_path = corpus_root / "scenarios/06_duplicate_replay"
        manifest_dict = json.loads((scen_path / "input/manifest.json").read_text(encoding="utf-8"))
        manifest = ProvenanceManifest.model_validate(manifest_dict)
        pub_bytes = bytes.fromhex((scen_path / "input/public_key.hex").read_text(encoding="utf-8").strip())
        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        input_bytes = (scen_path / "input/input_image.png").read_bytes()
        output_bytes = (scen_path / "input/output.json").read_bytes()
        model_sha = (scen_path / "input/model_sha256.txt").read_text(encoding="utf-8").strip()

        service = AssessmentService(test_db)

        # Run 1: First presentation - accepted and persisted
        res1 = service.run_assessment(AssessmentRequest(
            title="Initial Manifest Submission",
            provenance_manifest=manifest,
            provenance_public_key=pub_key,
            actual_input_bytes=input_bytes,
            actual_output_bytes=output_bytes,
            actual_model_sha256=model_sha,
        ))
        assert res1.status == AssessmentState.COMPLETE
        assert res1.overall_risk == RiskLevel.NONE
        findings1 = FindingRepository(test_db).list_by_assessment(res1.assessment_id)
        assert not any(f.subcategory == "replay_detected" for f in findings1)

        # Run 2: Exact same manifest submitted again - triggers replay detection
        res2 = service.run_assessment(AssessmentRequest(
            title="Replayed Manifest Submission",
            provenance_manifest=manifest,
            provenance_public_key=pub_key,
            actual_input_bytes=input_bytes,
            actual_output_bytes=output_bytes,
            actual_model_sha256=model_sha,
        ))
        assert res2.status == AssessmentState.COMPLETE
        assert res2.overall_risk == RiskLevel.MEDIUM
        findings2 = FindingRepository(test_db).list_by_assessment(res2.assessment_id)
        replay_findings = [f for f in findings2 if f.subcategory == "replay_detected"]
        assert len(replay_findings) >= 1
        assert any("duplicate_manifest_id" in f.title or "duplicate_nonce" in f.title for f in replay_findings)


# ===========================================================================
# Test D: Sequence Regression (07_sequence_regression)
# ===========================================================================

class TestSequenceRegression:
    """Scenario 07: Regressing sequence counter."""

    def test_sequence_regression_detected(self, corpus_root: Path):
        scen_path = corpus_root / "scenarios/07_sequence_regression"
        res = validate_provenance_scenario(scen_path)
        assert res["passed"] is True, f"Validation failure: {res}"
        assert res["observed_risk"] == "medium"
        assert "replay_detected" in res["observed_subcategories"]
        assert any("sequence_regression" in anom for anom in res["replay_anomalies"])


# ===========================================================================
# Test E: Sequence Gap (08_sequence_gap)
# ===========================================================================

class TestSequenceGap:
    """Scenario 08: Missing sequence counter gap."""

    def test_sequence_gap_detected(self, corpus_root: Path):
        scen_path = corpus_root / "scenarios/08_sequence_gap"
        res = validate_provenance_scenario(scen_path)
        assert res["passed"] is True, f"Validation failure: {res}"
        assert res["observed_risk"] == "medium"
        assert "replay_detected" in res["observed_subcategories"]
        assert any("sequence_gap" in anom for anom in res["replay_anomalies"])


# ===========================================================================
# Test F: Fresh Nonce Limitation (09_fresh_nonce_limitation)
# ===========================================================================

class TestFreshNonceLimitation:
    """Scenario 09: Fresh nonce limitation per ADR-003."""

    def test_fresh_nonce_limitation_represented_honestly(self, corpus_root: Path):
        scen_path = corpus_root / "scenarios/09_fresh_nonce_limitation"
        res = validate_provenance_scenario(scen_path)
        assert res["passed"] is True, f"Validation failure: {res}"
        # MUST NOT claim replay detection falsely
        assert res["observed_risk"] == "none"
        assert "provenance_valid" in res["observed_subcategories"]
        assert res["replay_anomalies"] == []

        # Verify ground truth documents this explicit limitation
        gt = json.loads((scen_path / "ground_truth/ground_truth.json").read_text(encoding="utf-8"))
        assert "ADR-003" in gt["documented_limitation"]


# ===========================================================================
# Test G: Audit Integration (10_audit_integration)
# ===========================================================================

class TestAuditIntegration:
    """Scenario 10: Audit chain verification and provenance evidence persistence."""

    def test_audit_integration_end_to_end(self, corpus_root: Path, test_db: sqlite3.Connection):
        scen_path = corpus_root / "scenarios/10_audit_integration"
        manifest_dict = json.loads((scen_path / "input/manifest.json").read_text(encoding="utf-8"))
        manifest = ProvenanceManifest.model_validate(manifest_dict)
        pub_bytes = bytes.fromhex((scen_path / "input/public_key.hex").read_text(encoding="utf-8").strip())
        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        input_bytes = (scen_path / "input/input_image.png").read_bytes()
        output_bytes = (scen_path / "input/output.json").read_bytes()
        model_sha = (scen_path / "input/model_sha256.txt").read_text(encoding="utf-8").strip()

        service = AssessmentService(test_db)
        req = AssessmentRequest(
            title="Audit Integration Assessment",
            provenance_manifest=manifest,
            provenance_public_key=pub_key,
            actual_input_bytes=input_bytes,
            actual_output_bytes=output_bytes,
            actual_model_sha256=model_sha,
        )
        result = service.run_assessment(req)

        assert result.status == AssessmentState.COMPLETE
        assert result.overall_risk == RiskLevel.NONE
        assert result.audit_chain_valid is True

        # Verify audit chain with independent ChainVerifier
        verifier = ChainVerifier(AuditRepository(test_db), AuditPayloadRepository(test_db))
        chain_res = verifier.verify_assessment(result.assessment_id)
        assert chain_res.valid is True
        assert chain_res.events_checked > 0

        # Verify audit events contain the assessment and asset references
        events = AuditRepository(test_db).list_by_assessment(result.assessment_id)
        types = [e.event_type.value for e in events]
        assert "assessment_created" in types
        assert "asset_registered" in types
        assert "detector_complete" in types
        assert "assessment_complete" in types


# ===========================================================================
# Test H: Signature Binding & SEC-01 Regression Protection (11)
# ===========================================================================

class TestSignatureBinding:
    """Scenario 11 & SEC-01: Regression test against signature transplantation."""

    def test_signature_transplant_rejected_on_manifest(self, corpus_root: Path):
        scen_path = corpus_root / "scenarios/11_signature_binding"
        res = validate_provenance_scenario(scen_path)
        assert res["passed"] is True, f"Validation failure: {res}"
        assert res["observed_risk"] == "high"
        assert "signature_invalid" in res["observed_subcategories"]

    def test_sec01_audit_signature_binding_regression(self, test_db: sqlite3.Connection):
        """SEC-01 Regression: Transplanted audit event signature MUST fail verification."""
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key()
        audit_repo = AuditRepository(test_db)
        payload_repo = AuditPayloadRepository(test_db)
        svc = AuditService(audit_repo, payload_repo)

        # Emit legitimate signed event A
        from backend.domain.enums import AuditEventType
        ev_a = svc.emit_event(
            AuditEventType.ASSESSMENT_CREATED,
            payload={"title": "Authentic Assessment", "authorization": "approved"},
            assessment_id="assess-sec01-a",
            actor="analyst-a",
            private_key=priv,
        )
        payload_a = payload_repo.get(ev_a.event_id)
        assert svc.verify_event_signature(ev_a, payload_a, pub) is True

        # Emit unsigned event B
        ev_b = svc.emit_event(
            AuditEventType.ASSESSMENT_CREATED,
            payload={"title": "Unauthorized Rogue Assessment", "authorization": "none"},
            assessment_id="assess-sec01-b",
            actor="attacker",
        )
        payload_b = payload_repo.get(ev_b.event_id)

        # Attacker transplants signature and pre_sig_hash from A into B
        transplanted_payload = dict(payload_b)
        transplanted_payload["__signature"] = payload_a["__signature"]
        transplanted_payload["__pre_sig_hash"] = payload_a["__pre_sig_hash"]
        transplanted_payload["__signing_key_id"] = payload_a["__signing_key_id"]

        # Verification MUST reject the transplant
        assert svc.verify_event_signature(ev_b, transplanted_payload, pub) is False


# ===========================================================================
# Test I: Malformed Input Fail-Closed (12_malformed_provenance)
# ===========================================================================

class TestMalformedProvenance:
    """Scenario 12: Fail-closed handling without leakage."""

    def test_unsigned_manifest_fails_can_run(self, corpus_root: Path):
        scen_path = corpus_root / "scenarios/12_malformed_provenance"
        res = validate_provenance_scenario(scen_path)
        assert res["passed"] is True
        assert res["can_run_ok"] is False
        assert "unsigned" in res["can_run_reason"].lower()

    def test_corrupted_key_bytes_fail_closed(self, corpus_root: Path):
        scen_path = corpus_root / "scenarios/01_clean_provenance"
        manifest_dict = json.loads((scen_path / "input/manifest.json").read_text(encoding="utf-8"))
        manifest = ProvenanceManifest.model_validate(manifest_dict)

        # Invalid key: too short (4 bytes instead of 32)
        with pytest.raises(ValueError):
            Ed25519PublicKey.from_public_bytes(b"dead")


# ===========================================================================
# Test J: Persistence & Restart (13_persistence_restart)
# ===========================================================================

class TestPersistenceRestart:
    """Scenario 13: Provenance replay state survives SQLite connection restart."""

    def test_replay_state_retention_across_restart(self, tmp_path: Path, corpus_root: Path):
        scen_path = corpus_root / "scenarios/13_persistence_restart"
        manifest_dict = json.loads((scen_path / "input/manifest.json").read_text(encoding="utf-8"))
        manifest = ProvenanceManifest.model_validate(manifest_dict)
        pub_bytes = bytes.fromhex((scen_path / "input/public_key.hex").read_text(encoding="utf-8").strip())
        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        input_bytes = (scen_path / "input/input_image.png").read_bytes()
        output_bytes = (scen_path / "input/output.json").read_bytes()
        model_sha = (scen_path / "input/model_sha256.txt").read_text(encoding="utf-8").strip()

        db_path = tmp_path / "persistent_provenance.db"

        # Session 1: Run assessment and persist verified manifest
        db1 = open_db(db_path)
        service1 = AssessmentService(db1)
        res1 = service1.run_assessment(AssessmentRequest(
            title="Session 1 Assessment",
            provenance_manifest=manifest,
            provenance_public_key=pub_key,
            actual_input_bytes=input_bytes,
            actual_output_bytes=output_bytes,
            actual_model_sha256=model_sha,
        ))
        assert res1.status == AssessmentState.COMPLETE
        assert res1.overall_risk == RiskLevel.NONE
        db1.close()

        # Session 2: Fresh connection and service instance
        db2 = open_db(db_path)
        service2 = AssessmentService(db2)

        # Re-submitting the exact same manifest must trigger replay from disk
        res2 = service2.run_assessment(AssessmentRequest(
            title="Session 2 Replay Assessment",
            provenance_manifest=manifest,
            provenance_public_key=pub_key,
            actual_input_bytes=input_bytes,
            actual_output_bytes=output_bytes,
            actual_model_sha256=model_sha,
        ))
        assert res2.status == AssessmentState.COMPLETE
        assert res2.overall_risk == RiskLevel.MEDIUM

        replay_findings = [f for f in FindingRepository(db2).list_by_assessment(res2.assessment_id) if f.subcategory == "replay_detected"]
        assert len(replay_findings) >= 1
        assert any("duplicate_manifest_id" in f.title for f in replay_findings)
        db2.close()


# ===========================================================================
# Test K: Deterministic Corpus Generation
# ===========================================================================

class TestDeterministicGeneration:
    """Verifies that running the corpus generator repeatedly is bit-for-bit idempotent."""

    def test_corpus_regeneration_is_idempotent(self, tmp_path: Path, corpus_root: Path):
        tmp_corpus = tmp_path / "provenance_corpus_repeat"
        gen = ProvenanceCorpusGenerator(tmp_corpus)
        gen.generate_all()

        orig_manifest = json.loads((corpus_root / "corpus_manifest.json").read_text(encoding="utf-8"))
        new_manifest = json.loads((tmp_corpus / "corpus_manifest.json").read_text(encoding="utf-8"))

        assert len(orig_manifest["scenarios"]) == len(new_manifest["scenarios"]) == 13

        # Check that clean scenario manifest produces identical digest
        m_orig = (corpus_root / "scenarios/01_clean_provenance/input/manifest.json").read_bytes()
        m_new = (tmp_corpus / "scenarios/01_clean_provenance/input/manifest.json").read_bytes()
        assert hash_bytes(m_orig) == hash_bytes(m_new)


# ===========================================================================
# Test L: SHA-256 Correctness & Canonicalization
# ===========================================================================

class TestSha256Canonicalization:
    """Verifies canonical JSON serialization and SHA-256 binding invariance."""

    def test_canonical_json_sorting_and_whitespace(self):
        d1 = {"b": 2, "a": 1, "nested": {"y": 20, "x": 10}}
        d2 = {"nested": {"x": 10, "y": 20}, "a": 1, "b": 2}
        assert canonical_json(d1) == canonical_json(d2)
        assert b" " not in canonical_json(d1)
        assert b"\n" not in canonical_json(d1)

    def test_manifest_canonicalization_excludes_digest_and_sig(self):
        priv = Ed25519PrivateKey.generate()
        m = ProvenanceManifest(
            manifest_id="test-id",
            assessment_id="stream-test",
            input_sha256="aa" * 32,
            model_sha256="bb" * 32,
            preprocessing_config={"resize": [224, 224]},
            inference_config={"batch_size": 1},
            output_sha256="cc" * 32,
            timestamp_utc="2026-01-01T00:00:00Z",
            nonce="dd" * 32,
            sequence=0,
        )
        signed = sign_manifest(m, priv)
        assert canonicalize_manifest(m) == canonicalize_manifest(signed)


# ===========================================================================
# Test M: API E2E
# ===========================================================================

class TestApiE2E:
    """FastAPI HTTP API E2E testing with provenance manifests."""

    def test_api_create_assessment_with_provenance(self, api_client: TestClient, corpus_root: Path):
        scen_path = corpus_root / "scenarios/01_clean_provenance"
        manifest_dict = json.loads((scen_path / "input/manifest.json").read_text(encoding="utf-8"))
        pub_key_hex = (scen_path / "input/public_key.hex").read_text(encoding="utf-8").strip()
        input_bytes = (scen_path / "input/input_image.png").read_bytes()
        output_bytes = (scen_path / "input/output.json").read_bytes()
        model_sha = (scen_path / "input/model_sha256.txt").read_text(encoding="utf-8").strip()

        resp = api_client.post(
            "/api/v1/assessments",
            json={
                "title": "API Provenance Assessment",
                "provenance_manifest": manifest_dict,
                "provenance_public_key_hex": pub_key_hex,
                "actual_input_bytes_hex": input_bytes.hex(),
                "actual_output_bytes_hex": output_bytes.hex(),
                "actual_model_sha256": model_sha,
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["overall_risk"] == "none"
        assert data["overall_confidence"] == "high"
        assert data["audit_chain_valid"] is True
        assess_id = data["assessment_id"]

        # Query findings endpoint
        findings_resp = api_client.get(f"/api/v1/assessments/{assess_id}/findings")
        assert findings_resp.status_code == 200
        findings = findings_resp.json()["findings"]
        subcats = [f["subcategory"] for f in findings]
        assert "provenance_valid" in subcats

        # Query audit endpoint
        audit_resp = api_client.get(f"/api/v1/assessments/{assess_id}/audit")
        assert audit_resp.status_code == 200
        audit_data = audit_resp.json()
        assert audit_data["chain_valid"] is True

    def test_api_tampered_manifest_returns_high_risk(self, api_client: TestClient, corpus_root: Path):
        scen_path = corpus_root / "scenarios/05_manifest_tampering"
        manifest_dict = json.loads((scen_path / "input/manifest.json").read_text(encoding="utf-8"))
        pub_key_hex = (scen_path / "input/public_key.hex").read_text(encoding="utf-8").strip()

        resp = api_client.post(
            "/api/v1/assessments",
            json={
                "title": "API Tampered Manifest Assessment",
                "provenance_manifest": manifest_dict,
                "provenance_public_key_hex": pub_key_hex,
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["overall_risk"] == "high"
        assert data["findings_count"] >= 1


# ===========================================================================
# Test N: Security & Network Isolation
# ===========================================================================

class TestSecurityIsolation:
    """Verifies air-gap security, no network socket attempts, and no path leakage."""

    def test_no_absolute_paths_in_evidence_or_findings(self, corpus_root: Path, test_db: sqlite3.Connection):
        scen_path = corpus_root / "scenarios/02_input_tampering"
        manifest_dict = json.loads((scen_path / "input/manifest.json").read_text(encoding="utf-8"))
        manifest = ProvenanceManifest.model_validate(manifest_dict)
        pub_bytes = bytes.fromhex((scen_path / "input/public_key.hex").read_text(encoding="utf-8").strip())
        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        input_bytes = (scen_path / "input/input_image.png").read_bytes()

        svc = AssessmentService(test_db)
        res = svc.run_assessment(AssessmentRequest(
            title="Path Leakage Test",
            provenance_manifest=manifest,
            provenance_public_key=pub_key,
            actual_input_bytes=input_bytes,
        ))
        findings = FindingRepository(test_db).list_by_assessment(res.assessment_id)
        for f in findings:
            assert "C:\\" not in f.description
            assert "/Users/" not in f.description
            assert "C:/" not in f.description

    def test_offline_execution_blocks_network(self, monkeypatch):
        """Ensure no network socket connections can occur during verification."""
        import socket

        def guarded_connect(*args, **kwargs):
            raise RuntimeError("Network access attempted in strictly offline engine!")

        monkeypatch.setattr(socket.socket, "connect", guarded_connect)

        priv, pub = _derive_deterministic_keypair("network_guard")
        m = sign_manifest(
            ProvenanceManifest(
                manifest_id="offline-test",
                assessment_id="stream-offline",
                input_sha256="aa" * 32,
                model_sha256="bb" * 32,
                preprocessing_config={},
                inference_config={},
                output_sha256="cc" * 32,
                timestamp_utc="2026-01-01T00:00:00Z",
                nonce="ee" * 32,
                sequence=0,
            ),
            priv,
        )
        res = verify_manifest(m, pub)
        assert res.valid is True
