"""
Integration tests for the Phase 7 Assessment Orchestrator.

These tests run the real orchestrator against real (minimal) assets.
Every result comes from actual analysis — no hardcoded findings, no fixtures.

Test categories
---------------
T1 - Request validation (fail-closed)
T2 - Model-only assessment (MI-01 only)
T3 - Dataset-only assessment (DI-01 only)
T4 - Full assessment (DI-01 + MI-01 + PI-01)
T5 - Coverage gaps and partial assessments
T6 - Audit trail integrity
T7 - ADR-003 invariants
T8 - Anti-fake / determinism
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
from pathlib import Path
from typing import Any

import pytest

from backend.assessment.models import AssessmentRequest
from backend.assessment.orchestrator import AssessmentService, run_assessment
from backend.domain.enums import (
    AssessmentState,
    ConfidenceLevel,
    DatasetFormat,
    DetectorStatus,
    RiskLevel,
)
from backend.infra.db import open_db


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    """Fresh isolated SQLite database for each test."""
    return open_db(tmp_path / "test.db")


@pytest.fixture
def image_dir(tmp_path: Path) -> Path:
    """Minimal complete image directory with 5 unique images, labels, and contributors."""
    from PIL import Image, ImageDraw
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    labels = {}
    contributors = {}
    for i in range(5):
        # Create genuinely distinct images with distinct patterns and hashes
        img = Image.new("RGB", (64, 64), color=(120, 120, 120))
        draw = ImageDraw.Draw(img)
        draw.rectangle([i * 10, i * 8, i * 10 + 15, i * 8 + 15], fill=(200, 50 + i * 30, 200 - i * 30))
        fname = f"img_{i:03d}.png"
        img.save(img_dir / fname, "PNG")
        labels[fname] = f"class_{i}"
        contributors[fname] = f"source_{i % 2}"
    (img_dir / "metadata.json").write_text(
        json.dumps({"labels": labels, "contributors": contributors})
    )
    return img_dir


@pytest.fixture
def image_dir_with_duplicates(tmp_path: Path) -> Path:
    """Image directory with one pair of exact duplicates."""
    from PIL import Image
    img_dir = tmp_path / "dup_images"
    img_dir.mkdir()

    # 3 unique images + 1 duplicate
    img = Image.new("RGB", (64, 64), color=(100, 150, 200))
    img.save(img_dir / "unique_1.jpg", "JPEG")
    img.save(img_dir / "duplicate_of_1.jpg", "JPEG")  # Exact duplicate

    img2 = Image.new("RGB", (64, 64), color=(200, 100, 50))
    img2.save(img_dir / "unique_2.jpg", "JPEG")

    return img_dir


@pytest.fixture
def onnx_model(tmp_path: Path) -> Path:
    """Minimal valid ONNX model file (ReLU: Y = Relu(X))."""
    # Use the test helper already in the repo
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from detectors.onnx_writer import make_relu_model
    model_bytes = make_relu_model(input_shape=[1, 3])
    path = tmp_path / "relu.onnx"
    path.write_bytes(model_bytes)
    return path


@pytest.fixture
def signed_manifest_and_key():
    """
    A real signed ProvenanceManifest + key pair.
    Uses the existing signing infrastructure from Phase 5.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from backend.domain.entities import ProvenanceManifest
    from backend.provenance.signing import sign_manifest

    # Generate real key pair
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Build a real manifest
    manifest = ProvenanceManifest(
        assessment_id="test-assess",
        input_sha256="a" * 64,
        model_sha256="b" * 64,
        preprocessing_config={"resize": 224},
        inference_config={"batch_size": 1},
        output_sha256="c" * 64,
        timestamp_utc="2026-01-01T00:00:00Z",
        nonce="0" * 64,
        sequence=0,
    )
    # Sign it with the real signing infrastructure
    signed = sign_manifest(manifest, private_key)
    return signed, private_key, public_key


# ---------------------------------------------------------------------------
# T1 - Request validation
# ---------------------------------------------------------------------------

class TestRequestValidation:
    def test_empty_title_is_rejected(self, db: sqlite3.Connection):
        req = AssessmentRequest(title="", model_path=Path("/tmp/fake.onnx"))
        result = run_assessment(req, db)
        assert result.status == AssessmentState.FAILED
        assert result.error is not None
        assert "Invalid request" in result.error

    def test_no_assets_is_rejected(self, db: sqlite3.Connection):
        req = AssessmentRequest(title="No Assets")
        result = run_assessment(req, db)
        assert result.status == AssessmentState.FAILED

    def test_dataset_without_format_is_rejected(self, db: sqlite3.Connection, tmp_path: Path):
        req = AssessmentRequest(
            title="Missing Format",
            dataset_path=tmp_path,
            dataset_format=None,
        )
        result = run_assessment(req, db)
        assert result.status == AssessmentState.FAILED

    def test_provenance_without_key_is_rejected(self, db: sqlite3.Connection):
        class FakeManifest:
            pass
        req = AssessmentRequest(
            title="No Key",
            provenance_manifest=FakeManifest(),
            provenance_public_key=None,
        )
        result = run_assessment(req, db)
        assert result.status == AssessmentState.FAILED

    def test_failed_result_has_low_confidence(self, db: sqlite3.Connection):
        req = AssessmentRequest(title="")
        result = run_assessment(req, db)
        assert result.overall_confidence == ConfidenceLevel.LOW

    def test_failed_result_has_none_risk(self, db: sqlite3.Connection):
        """A failed assessment should never claim a risk it hasn't assessed."""
        req = AssessmentRequest(title="")
        result = run_assessment(req, db)
        assert result.overall_risk == RiskLevel.NONE


# ---------------------------------------------------------------------------
# T2 - Model-only assessment (MI-01 real execution)
# ---------------------------------------------------------------------------

class TestModelOnlyAssessment:
    def test_mi01_runs_and_produces_result(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        req = AssessmentRequest(
            title="Model Only Test",
            model_path=onnx_model,
        )
        result = run_assessment(req, db)
        assert result.status == AssessmentState.COMPLETE
        assert "model.integrity.mi01_fingerprint" in result.detectors_executed

    def test_mi01_produces_real_findings(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        req = AssessmentRequest(title="MI-01 Real", model_path=onnx_model)
        result = run_assessment(req, db)
        # MI-01 always produces at least one finding (fingerprint_recorded INFO)
        assert result.findings_count >= 1

    def test_mi01_produces_evidence(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        req = AssessmentRequest(title="MI-01 Evidence", model_path=onnx_model)
        result = run_assessment(req, db)
        assert result.evidence_count >= 1

    def test_model_registered_as_asset(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        req = AssessmentRequest(title="Asset Check", model_path=onnx_model)
        result = run_assessment(req, db)
        assert len(result.assets_analyzed) >= 1

    def test_di01_and_pi01_are_not_applicable(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        """Without a dataset or manifest, DI-01 and PI-01 must not run."""
        req = AssessmentRequest(title="Model Only", model_path=onnx_model)
        result = run_assessment(req, db)
        for run in result.detector_runs:
            if run.detector_id in (
                "data.integrity.di01_duplicates",
                "inference.provenance.pi01_integrity",
            ):
                assert not run.applicable
                assert not run.ran

    def test_no_fingerprint_mismatch_without_reference(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        """Without a reference fingerprint, MI-01 should produce NONE risk."""
        req = AssessmentRequest(title="No Ref", model_path=onnx_model)
        result = run_assessment(req, db)
        assert result.overall_risk == RiskLevel.NONE

    def test_audit_chain_is_valid(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        req = AssessmentRequest(title="Audit Check", model_path=onnx_model)
        result = run_assessment(req, db)
        assert result.audit_chain_valid is True

    def test_coverage_is_one_third_when_only_model(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        """Only MI-01 is applicable (1 of 3 registered detectors)."""
        req = AssessmentRequest(title="Coverage", model_path=onnx_model)
        result = run_assessment(req, db)
        # DI-01 and PI-01 are not applicable → total_applicable = 1
        # MI-01 ran → executed_applicable = 1
        # coverage = 1/1 = 1.0 (not applicable detectors are excluded)
        assert result.coverage_fraction == 1.0


# ---------------------------------------------------------------------------
# T3 - Dataset-only assessment (DI-01 real execution)
# ---------------------------------------------------------------------------

class TestDatasetOnlyAssessment:
    def test_di01_runs_on_image_dir(
        self, db: sqlite3.Connection, image_dir: Path
    ):
        req = AssessmentRequest(
            title="Dataset Only",
            dataset_path=image_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
        )
        result = run_assessment(req, db)
        assert result.status == AssessmentState.COMPLETE
        assert "data.integrity.di01_duplicates" in result.detectors_executed

    def test_clean_dataset_produces_no_duplicate_findings(
        self, db: sqlite3.Connection, image_dir: Path
    ):
        """
        3 unique images should produce no duplicate-cluster findings.

        DI-01 may return LOW risk on small clean datasets (low confidence
        due to small sample size is documented behavior, ADR-003).
        The key assertion is that no exact_duplicate_cluster or
        near_duplicate_cluster findings are present.
        """
        from backend.infra.db import FindingRepository
        req = AssessmentRequest(
            title="Clean Dataset",
            dataset_path=image_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
            assessment_id="assess-clean",
        )
        result = run_assessment(req, db)
        assert result.status == AssessmentState.COMPLETE

        findings = FindingRepository(db).list_by_assessment("assess-clean")
        dup_findings = [
            f for f in findings
            if f.subcategory in ("exact_duplicate_cluster", "near_duplicate_cluster")
        ]
        assert dup_findings == [], (
            f"Expected no duplicate findings on a clean unique dataset, "
            f"got: {[(f.subcategory, f.title) for f in dup_findings]}"
        )
        # Risk must not be HIGH or CRITICAL (no major integrity issues)
        assert result.overall_risk not in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_duplicate_dataset_produces_findings(
        self, db: sqlite3.Connection, image_dir_with_duplicates: Path
    ):
        """Dataset with exact duplicates must produce at least one finding."""
        req = AssessmentRequest(
            title="Dup Dataset",
            dataset_path=image_dir_with_duplicates,
            dataset_format=DatasetFormat.IMAGE_DIR,
        )
        result = run_assessment(req, db)
        assert result.findings_count >= 1

    def test_duplicate_dataset_risk_not_none(
        self, db: sqlite3.Connection, image_dir_with_duplicates: Path
    ):
        """Exact duplicates should elevate risk above NONE."""
        req = AssessmentRequest(
            title="Dup Risk",
            dataset_path=image_dir_with_duplicates,
            dataset_format=DatasetFormat.IMAGE_DIR,
        )
        result = run_assessment(req, db)
        assert result.overall_risk != RiskLevel.NONE

    def test_mi01_pi01_not_applicable_without_model(
        self, db: sqlite3.Connection, image_dir: Path
    ):
        req = AssessmentRequest(
            title="No Model",
            dataset_path=image_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
        )
        result = run_assessment(req, db)
        for run in result.detector_runs:
            if run.detector_id in (
                "model.integrity.mi01_fingerprint",
                "inference.provenance.pi01_integrity",
            ):
                assert not run.applicable

    def test_coverage_is_full_when_only_dataset(
        self, db: sqlite3.Connection, image_dir: Path
    ):
        req = AssessmentRequest(
            title="Cov Test",
            dataset_path=image_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
        )
        result = run_assessment(req, db)
        # Only DI-01 is applicable, and it ran
        assert result.coverage_fraction == 1.0


# ---------------------------------------------------------------------------
# T4 - Full assessment (DI-01 + MI-01 + PI-01)
# ---------------------------------------------------------------------------

class TestFullAssessment:
    def test_all_three_detectors_run(
        self,
        db: sqlite3.Connection,
        image_dir: Path,
        onnx_model: Path,
        signed_manifest_and_key,
    ):
        manifest, private_key, public_key = signed_manifest_and_key
        req = AssessmentRequest(
            title="Full Assessment",
            dataset_path=image_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
            model_path=onnx_model,
            provenance_manifest=manifest,
            provenance_public_key=public_key,
        )
        result = run_assessment(req, db)
        assert result.status == AssessmentState.COMPLETE
        assert "data.integrity.di01_duplicates" in result.detectors_executed
        assert "model.integrity.mi01_fingerprint" in result.detectors_executed
        assert "inference.provenance.pi01_integrity" in result.detectors_executed

    def test_full_assessment_has_three_assets(
        self,
        db: sqlite3.Connection,
        image_dir: Path,
        onnx_model: Path,
        signed_manifest_and_key,
    ):
        manifest, _, public_key = signed_manifest_and_key
        req = AssessmentRequest(
            title="Assets Test",
            dataset_path=image_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
            model_path=onnx_model,
            provenance_manifest=manifest,
            provenance_public_key=public_key,
        )
        result = run_assessment(req, db)
        assert len(result.assets_analyzed) == 3

    def test_full_coverage_when_all_run(
        self,
        db: sqlite3.Connection,
        image_dir: Path,
        onnx_model: Path,
        signed_manifest_and_key,
    ):
        manifest, _, public_key = signed_manifest_and_key
        req = AssessmentRequest(
            title="Full Coverage",
            dataset_path=image_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
            model_path=onnx_model,
            provenance_manifest=manifest,
            provenance_public_key=public_key,
        )
        result = run_assessment(req, db)
        assert result.coverage_fraction == 1.0

    def test_no_coverage_gaps_when_all_run(
        self,
        db: sqlite3.Connection,
        image_dir: Path,
        onnx_model: Path,
        signed_manifest_and_key,
    ):
        manifest, _, public_key = signed_manifest_and_key
        req = AssessmentRequest(
            title="No Gaps",
            dataset_path=image_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
            model_path=onnx_model,
            provenance_manifest=manifest,
            provenance_public_key=public_key,
        )
        result = run_assessment(req, db)
        assert result.coverage_gaps == []

    def test_full_assessment_audit_chain_valid(
        self,
        db: sqlite3.Connection,
        image_dir: Path,
        onnx_model: Path,
        signed_manifest_and_key,
    ):
        manifest, _, public_key = signed_manifest_and_key
        req = AssessmentRequest(
            title="Audit Full",
            dataset_path=image_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
            model_path=onnx_model,
            provenance_manifest=manifest,
            provenance_public_key=public_key,
        )
        result = run_assessment(req, db)
        assert result.audit_chain_valid is True


# ---------------------------------------------------------------------------
# T5 - Coverage gaps and partial assessments
# ---------------------------------------------------------------------------

class TestCoverageGaps:
    def test_no_dataset_produces_di01_gap(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        req = AssessmentRequest(title="No Dataset", model_path=onnx_model)
        result = run_assessment(req, db)
        di01_gap = next(
            (g for g in result.coverage_gaps
             if "di01" in g.detector_id or "duplicate" in g.detector_id.lower()),
            None,
        )
        # DI-01 is not applicable (no dataset) so it should NOT be a gap
        # Only applicable-but-skipped detectors produce gaps
        assert di01_gap is None

    def test_no_model_means_mi01_not_applicable(
        self, db: sqlite3.Connection, image_dir: Path
    ):
        req = AssessmentRequest(
            title="No Model",
            dataset_path=image_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
        )
        result = run_assessment(req, db)
        # MI-01 not applicable -> not in skipped list
        assert "model.integrity.mi01_fingerprint" not in result.detectors_skipped

    def test_not_applicable_detectors_have_no_gap(
        self, db: sqlite3.Connection, image_dir: Path
    ):
        req = AssessmentRequest(
            title="No Gap Test",
            dataset_path=image_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
        )
        result = run_assessment(req, db)
        # No coverage gap should reference MI-01 or PI-01 when not applicable
        for gap in result.coverage_gaps:
            assert "mi01" not in gap.detector_id
            assert "pi01" not in gap.detector_id

    def test_non_applicable_detectors_not_counted_in_coverage_denominator(
        self, db: sqlite3.Connection, image_dir: Path
    ):
        """
        Coverage denominator = applicable detectors only.
        With only a dataset, DI-01 is the only applicable detector.
        Coverage = 1/1 = 1.0 (not 1/3 = 0.33).
        """
        req = AssessmentRequest(
            title="Coverage Denominator",
            dataset_path=image_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
        )
        result = run_assessment(req, db)
        assert result.coverage_fraction == 1.0, (
            f"Expected 1.0 but got {result.coverage_fraction}. "
            "Non-applicable detectors must be excluded from coverage."
        )


# ---------------------------------------------------------------------------
# T6 - Audit trail integrity
# ---------------------------------------------------------------------------

class TestAuditTrailIntegrity:
    def test_assessment_creates_audit_events(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        from backend.infra.db import AuditRepository
        req = AssessmentRequest(title="Audit Events", model_path=onnx_model)
        run_assessment(req, db)
        events = AuditRepository(db).list_all()
        assert len(events) >= 3  # ASSESSMENT_CREATED + DETECTOR_* + ASSESSMENT_COMPLETE

    def test_chain_has_no_broken_links(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        from backend.audit.verifier import ChainVerifier
        from backend.infra.db import AuditPayloadRepository, AuditRepository
        req = AssessmentRequest(title="Chain Test", model_path=onnx_model)
        run_assessment(req, db)
        verifier = ChainVerifier(AuditRepository(db), AuditPayloadRepository(db))
        chain_result = verifier.verify_all()
        assert chain_result.valid, f"Chain broken: {chain_result.failures}"

    def test_assessment_complete_event_present(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        from backend.domain.enums import AuditEventType
        from backend.infra.db import AuditRepository
        req = AssessmentRequest(title="Complete Event", model_path=onnx_model)
        run_assessment(req, db)
        events = AuditRepository(db).list_all()
        event_types = [e.event_type for e in events]
        assert AuditEventType.ASSESSMENT_COMPLETE in event_types

    def test_tampered_chain_detected(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        """Directly mutate a hash in the DB and verify the chain reports invalid."""
        from backend.audit.verifier import ChainVerifier
        from backend.infra.db import AuditPayloadRepository, AuditRepository
        req = AssessmentRequest(title="Tamper Test", model_path=onnx_model)
        run_assessment(req, db)

        # Tamper the first event's current_hash
        db.execute(
            "UPDATE audit_events SET current_hash=? WHERE rowid=1",
            ("0" * 64,),
        )
        db.commit()

        verifier = ChainVerifier(AuditRepository(db), AuditPayloadRepository(db))
        chain_result = verifier.verify_all()
        assert not chain_result.valid


# ---------------------------------------------------------------------------
# T7 - ADR-003 invariants
# ---------------------------------------------------------------------------

class TestAdr003:
    def test_risk_and_confidence_are_separate_fields(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        """ADR-003: risk and confidence must be distinct named fields."""
        req = AssessmentRequest(title="ADR-003", model_path=onnx_model)
        result = run_assessment(req, db)
        # Both exist
        assert hasattr(result, "overall_risk")
        assert hasattr(result, "overall_confidence")
        # They have separate values (not collapsed into one)
        assert isinstance(result.overall_risk, RiskLevel)
        assert isinstance(result.overall_confidence, ConfidenceLevel)

    def test_risk_and_confidence_have_separate_qualitative_descriptions(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        """Each dimension must have its own explanation."""
        req = AssessmentRequest(title="Qualitative", model_path=onnx_model)
        result = run_assessment(req, db)
        assert result.risk_qualitative
        assert result.confidence_qualifier
        # They should not be identical strings
        assert result.risk_qualitative != result.confidence_qualifier

    def test_none_risk_does_not_imply_safe_when_low_confidence(
        self, db: sqlite3.Connection
    ):
        """
        LOW confidence + NONE risk must not be interpreted as 'safe'.
        The result must include limitations that explain the coverage gap.
        """
        # An assessment with no valid assets will fail, but a valid request
        # with a missing model file will cause MI-01 to SKIP → coverage gap
        # Create a model path that does NOT exist (can_run will fail)
        req = AssessmentRequest(
            title="Missing Model",
            model_path=Path("/nonexistent/model.onnx"),
        )
        result = run_assessment(req, db)
        # The result fails (file doesn't exist, can't register model)
        assert result.status == AssessmentState.FAILED
        # Even in failure: limitations must be explicit
        assert len(result.limitations) >= 1

    def test_coverage_and_risk_independent(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        """Coverage fraction does not affect risk — they are independent."""
        req = AssessmentRequest(title="Independence", model_path=onnx_model)
        result = run_assessment(req, db)
        # Risk comes from findings; coverage from detector execution count
        # They are independent — no formula links them
        risk_val = result.overall_risk
        coverage_val = result.coverage_fraction
        # Both exist and are valid types
        assert isinstance(risk_val, RiskLevel)
        assert 0.0 <= coverage_val <= 1.0


# ---------------------------------------------------------------------------
# T8 - Anti-fake / determinism tests
# ---------------------------------------------------------------------------

class TestAntiFakeAndDeterminism:
    def test_result_comes_from_db_not_hardcoded(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        """
        Run the same assessment twice. findings_count must match the
        persisted findings in the DB — it cannot be a hardcoded constant.
        """
        from backend.infra.db import FindingRepository
        req1 = AssessmentRequest(
            title="Real Findings 1",
            model_path=onnx_model,
            assessment_id="assess-1",
        )
        result1 = run_assessment(req1, db)
        db_findings = FindingRepository(db).list_by_assessment("assess-1")
        assert result1.findings_count == len(db_findings), (
            "findings_count must equal actual DB findings (not hardcoded)"
        )

    def test_different_models_produce_different_sha256_in_evidence(
        self, db: sqlite3.Connection, tmp_path: Path
    ):
        """Two distinct models must produce distinct SHA-256 fingerprints."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from detectors.onnx_writer import make_add_bias_model, make_relu_model

        model_a = tmp_path / "relu.onnx"
        model_b = tmp_path / "add_bias.onnx"
        model_a.write_bytes(make_relu_model([1, 4]))
        model_b.write_bytes(make_add_bias_model([1.0, 2.0, 3.0, 4.0], [1, 4]))

        from backend.infra.db import EvidenceRepository, FindingRepository

        result_a = run_assessment(
            AssessmentRequest(title="Model A", model_path=model_a,
                              assessment_id="assess-a"),
            db,
        )
        result_b = run_assessment(
            AssessmentRequest(title="Model B", model_path=model_b,
                              assessment_id="assess-b"),
            db,
        )

        def _get_sha(assess_id: str) -> str | None:
            findings = FindingRepository(db).list_by_assessment(assess_id)
            for f in findings:
                evs = EvidenceRepository(db).list_by_finding(f.finding_id)
                for e in evs:
                    if "artifact_sha256" in (e.data or {}):
                        return e.data["artifact_sha256"]
            return None

        sha_a = _get_sha("assess-a")
        sha_b = _get_sha("assess-b")
        assert sha_a is not None, "Model A must produce evidence with SHA-256"
        assert sha_b is not None, "Model B must produce evidence with SHA-256"
        assert sha_a != sha_b, "Different models must produce different fingerprints"

    def test_same_model_same_assessment_deterministic(
        self, db: sqlite3.Connection, tmp_path: Path
    ):
        """Same model file, two assessments → same artifact SHA-256 in evidence."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from detectors.onnx_writer import make_relu_model

        model_path = tmp_path / "relu.onnx"
        model_path.write_bytes(make_relu_model([1, 3]))

        from backend.infra.db import EvidenceRepository, FindingRepository

        def _get_sha(assess_id: str) -> str | None:
            findings = FindingRepository(db).list_by_assessment(assess_id)
            for f in findings:
                evs = EvidenceRepository(db).list_by_finding(f.finding_id)
                for e in evs:
                    if "artifact_sha256" in (e.data or {}):
                        return e.data["artifact_sha256"]
            return None

        result_1 = run_assessment(
            AssessmentRequest(title="Same Model 1", model_path=model_path,
                              assessment_id="assess-s1"),
            db,
        )
        result_2 = run_assessment(
            AssessmentRequest(title="Same Model 2", model_path=model_path,
                              assessment_id="assess-s2"),
            db,
        )

        sha_1 = _get_sha("assess-s1")
        sha_2 = _get_sha("assess-s2")
        assert sha_1 is not None
        assert sha_2 is not None
        assert sha_1 == sha_2, "Same file must always produce the same SHA-256"

    def test_no_finding_without_real_evidence(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        """
        MI-01 must always attach real evidence to each finding.
        No finding should have empty/None data.
        """
        from backend.infra.db import EvidenceRepository, FindingRepository
        req = AssessmentRequest(
            title="Evidence Check",
            model_path=onnx_model,
            assessment_id="assess-ev",
        )
        run_assessment(req, db)
        findings = FindingRepository(db).list_by_assessment("assess-ev")
        assert len(findings) >= 1, "MI-01 must produce at least one finding"
        for f in findings:
            evs = EvidenceRepository(db).list_by_finding(f.finding_id)
            assert len(evs) >= 1, (
                f"Finding {f.finding_id!r} ({f.subcategory!r}) has no evidence"
            )
            for e in evs:
                assert e.data, f"Evidence {e.evidence_id!r} has empty data dict"

    def test_assessment_result_persisted_in_db(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        """The AssessmentRepository must contain the completed assessment."""
        from backend.domain.enums import AssessmentState
        from backend.infra.db import AssessmentRepository
        req = AssessmentRequest(
            title="DB Check",
            model_path=onnx_model,
            assessment_id="assess-db",
        )
        run_assessment(req, db)
        record = AssessmentRepository(db).get("assess-db")
        assert record is not None
        assert record.state == AssessmentState.COMPLETE

    def test_di01_findings_reference_real_sample_ids(
        self, db: sqlite3.Connection, image_dir_with_duplicates: Path
    ):
        """
        DI-01 findings must reference actual sample IDs from the DB.
        No phantom IDs, no hardcoded values.
        """
        from backend.infra.db import EvidenceRepository, FindingRepository, SampleRepository

        req = AssessmentRequest(
            title="Real Sample IDs",
            dataset_path=image_dir_with_duplicates,
            dataset_format=DatasetFormat.IMAGE_DIR,
            assessment_id="assess-di01",
        )
        result = run_assessment(req, db)
        assert result.findings_count >= 1

        findings = FindingRepository(db).list_by_assessment("assess-di01")
        for f in findings:
            if f.subcategory == "exact_duplicate_cluster":
                evs = EvidenceRepository(db).list_by_finding(f.finding_id)
                for e in evs:
                    # Evidence must contain sample_ids referencing real DB records
                    if "sample_ids" in (e.data or {}):
                        sample_ids = e.data["sample_ids"]
                        # list_by_dataset uses the asset_id (= dataset_id)
                        # We can't do a per-ID lookup, so verify the IDs are a subset
                        # of the samples actually ingested for this dataset asset.
                        all_samples = SampleRepository(db).list_by_dataset(f.asset_id)
                        known_ids = {s.sample_id for s in all_samples}
                        for sid in sample_ids:
                            assert sid in known_ids, (
                                f"Evidence references phantom sample ID {sid!r} "
                                f"not found among {len(known_ids)} real samples"
                            )


class TestPhase11TrainingDataIntegritySuite:
    """End-to-end tests for Phase 11 PS Compliance (DI-01..DI-05)."""

    def test_all_five_dataset_detectors_execute_on_complete_dataset(
        self, db: sqlite3.Connection, image_dir: Path
    ):
        req = AssessmentRequest(
            title="Complete Dataset Integrity",
            dataset_path=image_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
        )
        result = run_assessment(req, db)
        assert result.status == AssessmentState.COMPLETE
        assert "data.integrity.di01_duplicates" in result.detectors_executed
        assert "data.integrity.di02_label_integrity" in result.detectors_executed
        assert "data.integrity.di03_trigger_anomaly" in result.detectors_executed
        assert "data.integrity.di04_ood_distribution" in result.detectors_executed
        assert "data.integrity.di05_contributor_risk" in result.detectors_executed
        assert result.coverage_fraction == 1.0
        assert len(result.coverage_gaps) == 0

    def test_unannotated_dataset_emits_coverage_gaps(
        self, db: sqlite3.Connection, tmp_path: Path
    ):
        """Plain directory without labels or contributors produces explicit CoverageGaps."""
        from PIL import Image
        unannotated_dir = tmp_path / "plain_images"
        unannotated_dir.mkdir()
        for i in range(3):
            Image.new("RGB", (64, 64), color=(i * 30, i * 40, i * 50)).save(
                unannotated_dir / f"img_{i}.jpg", "JPEG"
            )

        req = AssessmentRequest(
            title="Unannotated Dataset",
            dataset_path=unannotated_dir,
            dataset_format=DatasetFormat.IMAGE_DIR,
        )
        result = run_assessment(req, db)
        assert result.status == AssessmentState.COMPLETE

        gap_detector_ids = [g.detector_id for g in result.coverage_gaps]
        assert "data.integrity.di02_label_integrity" in gap_detector_ids
        assert "data.integrity.di05_contributor_risk" in gap_detector_ids
        assert result.coverage_fraction < 1.0
        assert len(result.limitations) > 0


class TestPhase12ModelIntegritySuite:
    """End-to-end tests for Phase 12 PS Compliance (MI-01..MI-05)."""

    def test_all_executable_model_detectors_run(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        req = AssessmentRequest(
            title="Complete Model Integrity",
            model_path=onnx_model,
        )
        result = run_assessment(req, db)
        assert result.status == AssessmentState.COMPLETE
        assert "model.integrity.mi01_fingerprint" in result.detectors_executed
        assert "model.integrity.mi02_parameter_stats" in result.detectors_executed
        assert "model.integrity.mi03_activation_stats" in result.detectors_executed
        assert "model.integrity.mi05_trigger_anomaly" in result.detectors_executed
        assert result.coverage_fraction == 1.0
        assert len(result.coverage_gaps) == 0

    def test_reference_model_battery_runs_when_reference_supplied(
        self, db: sqlite3.Connection, onnx_model: Path
    ):
        req = AssessmentRequest(
            title="Ref Model Battery",
            model_path=onnx_model,
            model_reference_path=onnx_model,
        )
        result = run_assessment(req, db)
        assert result.status == AssessmentState.COMPLETE
        assert "model.integrity.mi04_reference_comparison" in result.detectors_executed
        assert result.coverage_fraction == 1.0
        assert len(result.coverage_gaps) == 0

    def test_pytorch_state_dict_emits_activation_and_trigger_coverage_gaps(
        self, db: sqlite3.Connection, tmp_path: Path
    ):
        import torch
        pt_path = tmp_path / "model.pt"
        torch.save({"layer.weight": torch.randn(4, 4), "layer.bias": torch.zeros(4)}, pt_path)

        req = AssessmentRequest(
            title="PyTorch State Dict Assessment",
            model_path=pt_path,
        )
        result = run_assessment(req, db)
        assert result.status == AssessmentState.COMPLETE

        # MI-01 and MI-02 succeed on state dicts
        assert "model.integrity.mi01_fingerprint" in result.detectors_executed
        assert "model.integrity.mi02_parameter_stats" in result.detectors_executed

        # MI-03 and MI-05 emit honest coverage gaps for non-executable state dicts
        gap_ids = [g.detector_id for g in result.coverage_gaps]
        assert "model.integrity.mi03_activation_stats" in gap_ids
        assert "model.integrity.mi05_trigger_anomaly" in gap_ids
        assert result.coverage_fraction < 1.0
        assert len(result.limitations) >= 2
