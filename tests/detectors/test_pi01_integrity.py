"""
Tests for PI-01: Inference Provenance Integrity Detector.

Note on DetectorContext: the base dataclass requires a conn (sqlite3.Connection).
Tests that use run_detector() use the db fixture (full schema).  Tests that only
call DETECTOR.run() directly use an in-memory DB with the PRAMAAN schema so the
context is well-formed.

Coverage:
  - metadata correctness
  - can_run(): requires PI01Context, requires signed manifest
  - Valid manifest → provenance_valid INFO finding, NONE risk
  - Invalid signature → HIGH/HIGH finding
  - Per-field tamper tests (input, output, model, preprocessing, inference,
    nonce, timestamp, sequence each independently tampered)
  - Output substitution detection
  - Input substitution detection
  - Replay nonce reuse → finding
  - Sequence gap → finding
  - Coverage gaps: missing binding data → INFO coverage_gap finding
  - Evidence references actual values (not hardcoded)
  - Risk/confidence ADR-003 separation
  - Persistence round-trip via run_detector()
"""

from __future__ import annotations

import uuid
from copy import deepcopy

import pytest

from backend.detectors.provenance.pi01_integrity import (
    PI01Context,
    PI01ProvenanceIntegrityDetector,
)
from backend.detectors.base import DetectorContext, DetectorOutput
from backend.detectors.runner import run_detector
from backend.domain.entities import Assessment, Asset, ProvenanceManifest
from backend.domain.enums import (
    AssetType,
    AssessmentState,
    ConfidenceLevel,
    DetectorStatus,
    FindingCategory,
    RiskLevel,
    Severity,
)
from backend.infra.crypto import (
    generate_nonce,
    generate_signing_key,
    hash_bytes,
    public_key_from_private,
)
from backend.infra.db import (
    AssessmentRepository,
    AssetRepository,
    DetectorResultRepository,
    EvidenceRepository,
    FindingRepository,
    ProvenanceRepository,
)
from backend.provenance.builder import build_and_sign_manifest
from backend.provenance.signing import sign_manifest, verify_manifest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def keypair():
    priv = generate_signing_key()
    pub = public_key_from_private(priv)
    return priv, pub


@pytest.fixture(scope="module")
def other_keypair():
    priv = generate_signing_key()
    pub = public_key_from_private(priv)
    return priv, pub


_INPUT_BYTES = b"test input image bytes [224x224x3]"
_OUTPUT_BYTES = b'{"class": "cat", "confidence": 0.95}'
_MODEL_DATA = b"fake onnx model binary for pi01 tests"
_PRE_CONFIG = {"resize": [224, 224], "normalize": True}
_INF_CONFIG = {"confidence_threshold": 0.5, "top_k": 5}


def _build_signed(keypair, *, sequence=0, assessment_id="pi01-test"):
    priv, _ = keypair
    return build_and_sign_manifest(
        assessment_id=assessment_id,
        input_sha256=hash_bytes(_INPUT_BYTES),
        model_sha256=hash_bytes(_MODEL_DATA),
        output_bytes=_OUTPUT_BYTES,
        preprocessing_config=_PRE_CONFIG,
        inference_config=_INF_CONFIG,
        sequence=sequence,
        private_key=priv,
    )


def _ctx(
    assessment_id,
    asset_id,
    manifest,
    pub_key,
    *,
    actual_input: bytes | None = _INPUT_BYTES,
    actual_output: bytes | None = _OUTPUT_BYTES,
    actual_model_sha: str | None = None,
    known_manifests=None,
) -> DetectorContext:
    if actual_model_sha is None:
        actual_model_sha = hash_bytes(_MODEL_DATA)
    pi01 = PI01Context(
        manifest=manifest,
        public_key=pub_key,
        actual_input_bytes=actual_input,
        actual_output_bytes=actual_output,
        actual_model_sha256=actual_model_sha,
        known_manifests=known_manifests or [],
    )
    ctx = DetectorContext(
        assessment_id=assessment_id,
        asset_id=asset_id,
    )
    ctx.pi01 = pi01  # type: ignore[attr-defined]
    return ctx


DETECTOR = PI01ProvenanceIntegrityDetector()


# ---------------------------------------------------------------------------
# Tests: Metadata
# ---------------------------------------------------------------------------

class TestMetadata:

    def test_detector_id(self):
        assert DETECTOR.metadata.detector_id == "inference.provenance.pi01_integrity"

    def test_version(self):
        assert DETECTOR.metadata.version == "1.0.0"

    def test_name_contains_pi01(self):
        assert "PI-01" in DETECTOR.metadata.name

    def test_applicable_asset_types_contains_inference_bundle(self):
        assert "inference_bundle" in DETECTOR.metadata.applicable_asset_types


# ---------------------------------------------------------------------------
# Tests: can_run()
# ---------------------------------------------------------------------------

class TestCanRun:

    def test_requires_pi01_context(self):
        """No pi01 attribute → can_run must return False."""
        ctx = DetectorContext(assessment_id="a", asset_id="b")
        result = DETECTOR.can_run(ctx)
        assert result.ok is False
        assert "PI01Context" in result.reason or "pi01" in result.reason.lower()

    def test_requires_signed_manifest(self, keypair):
        """Unsigned manifest (no digest/signature) → can_run must return False."""
        _, pub = keypair
        unsigned = ProvenanceManifest(
            assessment_id="a",
            input_sha256="a" * 64,
            model_sha256="b" * 64,
            preprocessing_config={},
            inference_config={},
            output_sha256="c" * 64,
            timestamp_utc="2026-01-01T00:00:00Z",
            nonce=generate_nonce(),
            sequence=0,
        )
        ctx = DetectorContext(assessment_id="a", asset_id="b")
        ctx.pi01 = PI01Context(manifest=unsigned, public_key=pub)  # type: ignore
        result = DETECTOR.can_run(ctx)
        assert result.ok is False
        assert "unsigned" in result.reason.lower() or "sign" in result.reason.lower()

    def test_signed_manifest_can_run(self, keypair):
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("a", "b", manifest, pub)
        result = DETECTOR.can_run(ctx)
        assert result.ok is True


# ---------------------------------------------------------------------------
# Tests: Valid provenance (happy path)
# ---------------------------------------------------------------------------

class TestValidProvenance:

    def test_valid_manifest_status_success(self, keypair):
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub)
        output = DETECTOR.run(ctx)
        assert output.status != DetectorStatus.FAILED
        assert output.error is None

    def test_valid_manifest_risk_none(self, keypair):
        """Valid signature + all bindings → NONE risk."""
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub)
        output = DETECTOR.run(ctx)
        assert output.risk_level == RiskLevel.NONE

    def test_valid_manifest_confidence_high(self, keypair):
        """Full binding data supplied → HIGH confidence."""
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub)
        output = DETECTOR.run(ctx)
        assert output.confidence_level == ConfidenceLevel.HIGH

    def test_valid_manifest_has_provenance_valid_finding(self, keypair):
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub)
        output = DETECTOR.run(ctx)
        subcats = {f.subcategory for f in output.findings}
        assert "provenance_valid" in subcats

    def test_valid_manifest_no_integrity_findings(self, keypair):
        """No tampering → no signature_invalid / input_mismatch / etc."""
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub)
        output = DETECTOR.run(ctx)
        bad_subcats = {"signature_invalid", "input_mismatch", "model_mismatch",
                       "output_mismatch", "replay_detected"}
        found_bad = {f.subcategory for f in output.findings} & bad_subcats
        assert found_bad == set(), f"Should have no integrity findings, got: {found_bad}"

    def test_valid_manifest_evidence_references_actual_manifest_id(self, keypair):
        """ANTI-FAKE: evidence data must reference the actual manifest ID."""
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub)
        output = DETECTOR.run(ctx)
        for ev in output.evidence:
            assert ev.data.get("manifest_id") == manifest.manifest_id, (
                "Evidence must reference the actual manifest_id, not a hardcoded value"
            )


# ---------------------------------------------------------------------------
# Tests: Signature failure
# ---------------------------------------------------------------------------

class TestInvalidSignature:

    def test_wrong_key_risk_high(self, keypair, other_keypair):
        """Wrong public key → HIGH risk."""
        _, wrong_pub = other_keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, wrong_pub)
        output = DETECTOR.run(ctx)
        assert output.risk_level == RiskLevel.HIGH

    def test_wrong_key_confidence_high(self, keypair, other_keypair):
        """Invalid signature is strong evidence → HIGH confidence."""
        _, wrong_pub = other_keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, wrong_pub)
        output = DETECTOR.run(ctx)
        assert output.confidence_level == ConfidenceLevel.HIGH

    def test_wrong_key_signature_invalid_finding(self, keypair, other_keypair):
        _, wrong_pub = other_keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, wrong_pub)
        output = DETECTOR.run(ctx)
        subcats = {f.subcategory for f in output.findings}
        assert "signature_invalid" in subcats

    def test_signature_invalid_finding_severity_high(self, keypair, other_keypair):
        _, wrong_pub = other_keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, wrong_pub)
        output = DETECTOR.run(ctx)
        sig_findings = [f for f in output.findings if f.subcategory == "signature_invalid"]
        assert len(sig_findings) >= 1
        assert sig_findings[0].severity == Severity.HIGH

    def test_corrupted_signature_fails(self, keypair):
        _, pub = keypair
        manifest = _build_signed(keypair)
        corrupted = manifest.model_copy(update={"signature": "0" * 128})
        ctx = _ctx("assess", "asset", corrupted, pub)
        output = DETECTOR.run(ctx)
        assert output.risk_level == RiskLevel.HIGH
        sig_findings = [f for f in output.findings if f.subcategory == "signature_invalid"]
        assert len(sig_findings) >= 1


# ---------------------------------------------------------------------------
# Tests: Per-field tamper detection (ANTI-FAKE)
# ---------------------------------------------------------------------------

class TestPerFieldTamper:
    """
    ANTI-FAKE: each test modifies exactly ONE signed field and proves
    that PI-01 produces a signature_invalid finding.
    This proves the signing is real — not hardcoded.
    """

    def _tamper_and_run(self, keypair, **updates):
        _, pub = keypair
        manifest = _build_signed(keypair)
        tampered = manifest.model_copy(update=updates)
        ctx = _ctx("assess", "asset", tampered, pub)
        output = DETECTOR.run(ctx)
        return output

    def test_tamper_input_sha256(self, keypair):
        output = self._tamper_and_run(keypair, input_sha256="f" * 64)
        subcats = {f.subcategory for f in output.findings}
        assert "signature_invalid" in subcats
        assert output.risk_level == RiskLevel.HIGH

    def test_tamper_model_sha256(self, keypair):
        output = self._tamper_and_run(keypair, model_sha256="e" * 64)
        subcats = {f.subcategory for f in output.findings}
        assert "signature_invalid" in subcats

    def test_tamper_output_sha256(self, keypair):
        output = self._tamper_and_run(keypair, output_sha256="d" * 64)
        subcats = {f.subcategory for f in output.findings}
        assert "signature_invalid" in subcats

    def test_tamper_nonce(self, keypair):
        output = self._tamper_and_run(keypair, nonce=generate_nonce())
        subcats = {f.subcategory for f in output.findings}
        assert "signature_invalid" in subcats

    def test_tamper_timestamp(self, keypair):
        output = self._tamper_and_run(keypair, timestamp_utc="2099-01-01T00:00:00Z")
        subcats = {f.subcategory for f in output.findings}
        assert "signature_invalid" in subcats

    def test_tamper_sequence(self, keypair):
        output = self._tamper_and_run(keypair, sequence=9999)
        subcats = {f.subcategory for f in output.findings}
        assert "signature_invalid" in subcats

    def test_tamper_preprocessing_config(self, keypair):
        output = self._tamper_and_run(keypair, preprocessing_config={"resize": [512, 512]})
        subcats = {f.subcategory for f in output.findings}
        assert "signature_invalid" in subcats

    def test_tamper_inference_config(self, keypair):
        output = self._tamper_and_run(keypair, inference_config={"confidence_threshold": 0.99})
        subcats = {f.subcategory for f in output.findings}
        assert "signature_invalid" in subcats

    def test_tamper_pramaan_version(self, keypair):
        output = self._tamper_and_run(keypair, pramaan_version="9.9.9")
        subcats = {f.subcategory for f in output.findings}
        assert "signature_invalid" in subcats


# ---------------------------------------------------------------------------
# Tests: Binding mismatch detection (substitution)
# ---------------------------------------------------------------------------

class TestBindingMismatches:

    def test_input_substitution_detected(self, keypair):
        """ANTI-FAKE: supplying wrong input bytes → input_mismatch finding."""
        _, pub = keypair
        manifest = _build_signed(keypair)
        # Manifest bound _INPUT_BYTES; we supply different bytes
        ctx = _ctx("assess", "asset", manifest, pub,
                   actual_input=b"substituted input bytes")
        output = DETECTOR.run(ctx)
        subcats = {f.subcategory for f in output.findings}
        assert "input_mismatch" in subcats
        assert output.risk_level == RiskLevel.HIGH

    def test_output_substitution_detected(self, keypair):
        """ANTI-FAKE: supplying wrong output bytes → output_mismatch finding."""
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub,
                   actual_output=b"substituted output bytes")
        output = DETECTOR.run(ctx)
        subcats = {f.subcategory for f in output.findings}
        assert "output_mismatch" in subcats
        assert output.risk_level == RiskLevel.HIGH

    def test_model_substitution_detected(self, keypair):
        """ANTI-FAKE: supplying wrong model SHA → model_mismatch finding."""
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub,
                   actual_model_sha="f" * 64)
        output = DETECTOR.run(ctx)
        subcats = {f.subcategory for f in output.findings}
        assert "model_mismatch" in subcats
        assert output.risk_level == RiskLevel.HIGH

    def test_binding_mismatch_evidence_contains_expected_and_observed(self, keypair):
        """Evidence must record both expected and observed hash values."""
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub,
                   actual_output=b"wrong output")
        output = DETECTOR.run(ctx)
        mismatch_ev = [
            ev for ev in output.evidence
            if ev.data.get("check") == "output_binding"
            and ev.data.get("result") == "FAIL"
        ]
        assert len(mismatch_ev) >= 1
        ev = mismatch_ev[0]
        assert "expected" in ev.data
        assert "observed" in ev.data
        assert ev.data["expected"] != ev.data["observed"]
        # Expected must be the hash from the manifest
        assert ev.data["expected"] == manifest.output_sha256

    def test_valid_sig_does_not_clear_binding_mismatch(self, keypair):
        """
        Core invariant: valid signature + wrong output → output_mismatch finding.
        The signature proving the record is intact does NOT prove the output is correct.
        """
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub,
                   actual_output=b"attacker substituted output")
        output = DETECTOR.run(ctx)
        # Signature check passes (manifest was not tampered)
        sig_pass = [f for f in output.findings if f.subcategory == "provenance_valid"]
        output_fail = [f for f in output.findings if f.subcategory == "output_mismatch"]
        assert len(output_fail) >= 1, (
            "Output mismatch must be detected even when signature is valid"
        )


# ---------------------------------------------------------------------------
# Tests: Replay detection
# ---------------------------------------------------------------------------

class TestReplayDetection:

    def test_duplicate_nonce_replay_finding(self, keypair):
        _, pub = keypair
        manifest1 = _build_signed(keypair, sequence=0)
        # Create manifest2 that reuses manifest1's nonce
        from backend.domain.entities import ProvenanceManifest
        manifest2_unsigned = ProvenanceManifest(
            assessment_id=manifest1.assessment_id,
            input_sha256=hash_bytes(_INPUT_BYTES),
            model_sha256=hash_bytes(_MODEL_DATA),
            preprocessing_config=_PRE_CONFIG,
            inference_config=_INF_CONFIG,
            output_sha256=hash_bytes(_OUTPUT_BYTES),
            timestamp_utc="2026-01-01T00:01:00Z",
            nonce=manifest1.nonce,  # Same nonce!
            sequence=1,
        )
        priv, _ = keypair
        manifest2 = sign_manifest(manifest2_unsigned, priv)

        ctx = _ctx(
            "assess", "asset", manifest2, pub,
            known_manifests=[manifest1],
        )
        output = DETECTOR.run(ctx)
        subcats = {f.subcategory for f in output.findings}
        assert "replay_detected" in subcats

    def test_sequence_gap_replay_finding(self, keypair):
        _, pub = keypair
        priv, _ = keypair
        # Known manifests: sequence 0, 1, 2
        knowns = []
        for seq in range(3):
            knowns.append(_build_signed(keypair, sequence=seq))

        # Candidate skips to sequence 5 (gap)
        candidate_unsigned = ProvenanceManifest(
            assessment_id="assess",
            input_sha256=hash_bytes(_INPUT_BYTES),
            model_sha256=hash_bytes(_MODEL_DATA),
            preprocessing_config=_PRE_CONFIG,
            inference_config=_INF_CONFIG,
            output_sha256=hash_bytes(_OUTPUT_BYTES),
            timestamp_utc="2026-01-01T00:05:00Z",
            nonce=generate_nonce(),
            sequence=5,  # Gap: expected 3
        )
        candidate = sign_manifest(candidate_unsigned, priv)

        ctx = _ctx("assess", "asset", candidate, pub, known_manifests=knowns)
        output = DETECTOR.run(ctx)
        subcats = {f.subcategory for f in output.findings}
        assert "replay_detected" in subcats

    def test_replay_risk_medium(self, keypair):
        """Replay/sequence anomaly → MEDIUM risk (not HIGH like tampered sig)."""
        priv, pub = keypair
        manifest1 = _build_signed(keypair, sequence=0)

        # Use same nonce but sign properly
        manifest2_unsigned = ProvenanceManifest(
            assessment_id=manifest1.assessment_id,
            input_sha256=hash_bytes(_INPUT_BYTES),
            model_sha256=hash_bytes(_MODEL_DATA),
            preprocessing_config=_PRE_CONFIG,
            inference_config=_INF_CONFIG,
            output_sha256=hash_bytes(_OUTPUT_BYTES),
            timestamp_utc="2026-01-01T00:02:00Z",
            nonce=manifest1.nonce,
            sequence=1,
        )
        manifest2 = sign_manifest(manifest2_unsigned, priv)
        ctx = _ctx("assess", "asset", manifest2, pub, known_manifests=[manifest1])
        output = DETECTOR.run(ctx)
        assert output.risk_level == RiskLevel.MEDIUM

    def test_replay_evidence_contains_anomaly_type(self, keypair):
        priv, pub = keypair
        manifest1 = _build_signed(keypair, sequence=0)
        manifest2_unsigned = ProvenanceManifest(
            assessment_id=manifest1.assessment_id,
            input_sha256=hash_bytes(_INPUT_BYTES),
            model_sha256=hash_bytes(_MODEL_DATA),
            preprocessing_config=_PRE_CONFIG,
            inference_config=_INF_CONFIG,
            output_sha256=hash_bytes(_OUTPUT_BYTES),
            timestamp_utc="2026-01-01T00:03:00Z",
            nonce=manifest1.nonce,
            sequence=1,
        )
        manifest2 = sign_manifest(manifest2_unsigned, priv)
        ctx = _ctx("assess", "asset", manifest2, pub, known_manifests=[manifest1])
        output = DETECTOR.run(ctx)
        replay_ev = [
            ev for ev in output.evidence
            if ev.data.get("check") == "replay_detection"
        ]
        assert len(replay_ev) >= 1
        assert "anomaly_type" in replay_ev[0].data
        assert replay_ev[0].data["anomaly_type"] == "duplicate_nonce"


# ---------------------------------------------------------------------------
# Tests: Coverage gaps
# ---------------------------------------------------------------------------

class TestCoverageGaps:

    def test_no_binding_data_status_partial(self, keypair):
        """Signature only, no binding data → PARTIAL status."""
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub,
                   actual_input=None, actual_output=None, actual_model_sha=None)
        output = DETECTOR.run(ctx)
        assert output.status == DetectorStatus.PARTIAL

    def test_no_binding_data_risk_none(self, keypair):
        """Valid signature + no binding data → NONE risk (no failure observed)."""
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub,
                   actual_input=None, actual_output=None, actual_model_sha=None)
        output = DETECTOR.run(ctx)
        assert output.risk_level == RiskLevel.NONE

    def test_no_binding_data_confidence_low(self, keypair):
        """Three coverage gaps → LOW confidence."""
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub,
                   actual_input=None, actual_output=None, actual_model_sha=None)
        output = DETECTOR.run(ctx)
        assert output.confidence_level == ConfidenceLevel.LOW

    def test_partial_binding_data_confidence_moderate(self, keypair):
        """One coverage gap → MODERATE confidence."""
        _, pub = keypair
        manifest = _build_signed(keypair)
        # Supply input and model, but not output
        ctx = _ctx("assess", "asset", manifest, pub, actual_output=None)
        output = DETECTOR.run(ctx)
        assert output.confidence_level == ConfidenceLevel.MODERATE

    def test_coverage_gap_finding_generated(self, keypair):
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub,
                   actual_input=None, actual_output=None, actual_model_sha=None)
        output = DETECTOR.run(ctx)
        subcats = {f.subcategory for f in output.findings}
        assert "coverage_gap" in subcats

    def test_coverage_gap_finding_severity_info(self, keypair):
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub,
                   actual_input=None, actual_output=None, actual_model_sha=None)
        output = DETECTOR.run(ctx)
        gap_findings = [f for f in output.findings if f.subcategory == "coverage_gap"]
        assert all(f.severity == Severity.INFO for f in gap_findings)


# ---------------------------------------------------------------------------
# Tests: ADR-003 Risk/Confidence separation
# ---------------------------------------------------------------------------

class TestRiskConfidenceSeparation:

    def test_risk_and_confidence_are_independent_fields(self, keypair):
        """ADR-003: risk and confidence are NEVER combined into one score."""
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub)
        output = DETECTOR.run(ctx)
        # Both must exist as separate attributes
        assert output.risk_level is not None
        assert output.confidence_level is not None
        # They must be typed independently
        assert isinstance(output.risk_level, RiskLevel)
        assert isinstance(output.confidence_level, ConfidenceLevel)

    def test_invalid_sig_high_risk_high_confidence(self, keypair, other_keypair):
        """Signature failure → HIGH risk, HIGH confidence (strong cryptographic evidence)."""
        _, wrong_pub = other_keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, wrong_pub)
        output = DETECTOR.run(ctx)
        assert output.risk_level == RiskLevel.HIGH
        assert output.confidence_level == ConfidenceLevel.HIGH

    def test_valid_no_bindings_none_risk_low_confidence(self, keypair):
        """
        Valid sig + no binding data: risk=NONE (nothing wrong observed)
        but confidence=LOW (not much was actually checked).
        This demonstrates ADR-003: NONE risk + LOW confidence ≠ "safe".
        """
        _, pub = keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, pub,
                   actual_input=None, actual_output=None, actual_model_sha=None)
        output = DETECTOR.run(ctx)
        assert output.risk_level == RiskLevel.NONE
        assert output.confidence_level == ConfidenceLevel.LOW, (
            "ADR-003: LOW confidence does not mean safe — "
            "it means we didn't check enough"
        )

    def test_findings_have_independent_category(self, keypair, other_keypair):
        """Findings use FindingCategory.INFERENCE_PROVENANCE, not a mixed enum."""
        _, wrong_pub = other_keypair
        manifest = _build_signed(keypair)
        ctx = _ctx("assess", "asset", manifest, wrong_pub)
        output = DETECTOR.run(ctx)
        for f in output.findings:
            assert isinstance(f.category, FindingCategory)
            assert f.category == FindingCategory.INFERENCE_PROVENANCE


# ---------------------------------------------------------------------------
# Tests: Persistence round-trip
# ---------------------------------------------------------------------------

class TestPersistence:

    def _setup_db(self, db):
        """Insert prerequisite assessment and asset records with unique IDs."""
        import uuid
        assessment_id = f"pi01-persist-{uuid.uuid4().hex[:8]}"
        asset_id = f"pi01-asset-{uuid.uuid4().hex[:8]}"
        assess = Assessment(
            assessment_id=assessment_id,
            title="PI-01 persistence test",
        )
        asset = Asset(
            asset_id=asset_id,
            assessment_id=assessment_id,
            asset_type=AssetType.INFERENCE_BUNDLE,
            name="test_inference",
            sha256="a" * 64,
            size_bytes=100,
        )
        AssessmentRepository(db).insert(assess)
        AssetRepository(db).insert(asset)
        return assessment_id, asset_id

    def test_run_detector_persists_findings(self, db, keypair):
        assessment_id, asset_id = self._setup_db(db)
        _, pub = keypair
        manifest = _build_signed(keypair, assessment_id=assessment_id)

        ctx = _ctx(assessment_id, asset_id, manifest, pub)
        output = run_detector(DETECTOR, ctx, db)

        findings = FindingRepository(db).list_by_assessment(assessment_id)
        assert len(findings) >= 1

    def test_run_detector_persists_evidence(self, db, keypair):
        assessment_id, asset_id = self._setup_db(db)
        _, pub = keypair
        manifest = _build_signed(keypair, assessment_id=assessment_id)

        ctx = _ctx(assessment_id, asset_id, manifest, pub)
        output = run_detector(DETECTOR, ctx, db)

        # Evidence is linked to findings; at least one should exist
        findings = FindingRepository(db).list_by_assessment(assessment_id)
        for f in findings:
            ev = EvidenceRepository(db).list_by_finding(f.finding_id)
            if f.subcategory in ("provenance_valid", "coverage_gap"):
                assert len(ev) >= 1

    def test_run_detector_persists_detector_result(self, db, keypair):
        assessment_id, asset_id = self._setup_db(db)
        _, pub = keypair
        manifest = _build_signed(keypair, assessment_id=assessment_id)

        ctx = _ctx(assessment_id, asset_id, manifest, pub)
        output = run_detector(DETECTOR, ctx, db)

        results = DetectorResultRepository(db).list_by_assessment(assessment_id)
        pi01_results = [r for r in results if r.detector_id == DETECTOR.metadata.detector_id]
        assert len(pi01_results) >= 1
        assert pi01_results[0].status == output.status

    def test_tamper_finding_persisted(self, db, keypair, other_keypair):
        assessment_id, asset_id = self._setup_db(db)
        _, wrong_pub = other_keypair
        manifest = _build_signed(keypair, assessment_id=assessment_id)

        ctx = _ctx(assessment_id, asset_id, manifest, wrong_pub)
        run_detector(DETECTOR, ctx, db)

        findings = FindingRepository(db).list_by_assessment(assessment_id)
        sig_findings = [f for f in findings if f.subcategory == "signature_invalid"]
        assert len(sig_findings) >= 1

    def test_provenance_manifest_persisted_via_repo(self, db, keypair):
        """ProvenanceRepository round-trip works with a builder-created manifest."""
        import uuid
        priv, _ = keypair
        assessment_id = f"pi01-repo-{uuid.uuid4().hex[:8]}"

        # Insert prerequisite assessment
        AssessmentRepository(db).insert(
            Assessment(assessment_id=assessment_id, title="repo round-trip test")
        )

        manifest = build_and_sign_manifest(
            assessment_id=assessment_id,
            input_sha256=hash_bytes(_INPUT_BYTES),
            model_sha256=hash_bytes(_MODEL_DATA),
            output_bytes=_OUTPUT_BYTES,
            preprocessing_config=_PRE_CONFIG,
            inference_config=_INF_CONFIG,
            sequence=0,
            private_key=priv,
        )

        repo = ProvenanceRepository(db)
        repo.insert(manifest)

        loaded = repo.get(manifest.manifest_id)
        assert loaded is not None
        assert loaded.manifest_id == manifest.manifest_id
        assert loaded.digest == manifest.digest
        assert loaded.signature == manifest.signature
        assert loaded.input_sha256 == manifest.input_sha256
        assert loaded.output_sha256 == manifest.output_sha256
        assert loaded.model_sha256 == manifest.model_sha256
        assert loaded.nonce == manifest.nonce
        assert loaded.preprocessing_config == manifest.preprocessing_config
        assert loaded.inference_config == manifest.inference_config

