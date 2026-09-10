"""Tests for PRAMAAN domain entities and enums."""

import pytest
from pydantic import ValidationError

from backend.domain.entities import (
    Assessment,
    Asset,
    AuditEvent,
    ConfidenceAssessment,
    CoverageGap,
    CoverageStatement,
    Dataset,
    Evidence,
    Finding,
    ModelArtifact,
    ProvenanceManifest,
    RiskAssessment,
    Sample,
)
from backend.domain.enums import (
    AccessLevel,
    AssessmentState,
    AssessmentType,
    AssetType,
    AuditEventType,
    ConfidenceLevel,
    DatasetFormat,
    EvidenceType,
    FindingCategory,
    ModelFramework,
    RiskLevel,
    Severity,
)


class TestRiskLevel:
    def test_ordering(self):
        assert RiskLevel.NONE.as_int() < RiskLevel.LOW.as_int()
        assert RiskLevel.LOW.as_int() < RiskLevel.MEDIUM.as_int()
        assert RiskLevel.MEDIUM.as_int() < RiskLevel.HIGH.as_int()
        assert RiskLevel.HIGH.as_int() < RiskLevel.CRITICAL.as_int()

    def test_max_returns_higher(self):
        assert RiskLevel.max(RiskLevel.LOW, RiskLevel.HIGH) == RiskLevel.HIGH
        assert RiskLevel.max(RiskLevel.CRITICAL, RiskLevel.NONE) == RiskLevel.CRITICAL
        assert RiskLevel.max(RiskLevel.MEDIUM, RiskLevel.MEDIUM) == RiskLevel.MEDIUM

    def test_max_commutative(self):
        for a in RiskLevel:
            for b in RiskLevel:
                assert RiskLevel.max(a, b) == RiskLevel.max(b, a)


class TestAssessment:
    def test_defaults_set(self):
        a = Assessment(title="Test Assessment")
        assert a.assessment_id is not None
        assert len(a.assessment_id) == 36  # UUID format
        assert a.state == AssessmentState.CREATED
        assert a.assessment_type == AssessmentType.LIVE
        assert a.created_at is not None
        assert a.started_at is None
        assert a.completed_at is None

    def test_title_required(self):
        with pytest.raises(ValidationError):
            Assessment()  # type: ignore

    def test_unique_ids(self):
        a1 = Assessment(title="A1")
        a2 = Assessment(title="A2")
        assert a1.assessment_id != a2.assessment_id


class TestAsset:
    def test_construct(self):
        a = Asset(
            assessment_id="test-id",
            asset_type=AssetType.DATASET,
            name="my_dataset",
            sha256="a" * 64,
            size_bytes=1024,
        )
        assert a.asset_id is not None
        assert a.size_bytes == 1024

    def test_negative_size_rejected(self):
        with pytest.raises(ValidationError):
            Asset(
                assessment_id="x",
                asset_type=AssetType.DATASET,
                name="x",
                sha256="a" * 64,
                size_bytes=-1,
            )


class TestSample:
    def test_construct_minimal(self):
        s = Sample(
            dataset_id="ds-1",
            file_name="img001.jpg",
            sha256="b" * 64,
            file_size_bytes=512,
        )
        assert s.phash is None
        assert s.dhash is None
        assert s.labels == []

    def test_empty_hash_becomes_none(self):
        s = Sample(
            dataset_id="ds-1",
            file_name="img.jpg",
            sha256="c" * 64,
            file_size_bytes=100,
            phash="",
            dhash="",
        )
        assert s.phash is None
        assert s.dhash is None


class TestFinding:
    def test_source_default(self):
        f = Finding(
            assessment_id="a",
            asset_id="b",
            category=FindingCategory.DATA_INTEGRITY,
            subcategory="duplicate",
            severity=Severity.MEDIUM,
            title="Near-duplicate cluster",
            description="Two images have Hamming distance 3.",
            detection_method="pHash Duplicate Detector",
            detector_id="di.phash_duplicates",
        )
        assert f.source == "LIVE_ANALYSIS"
        assert f.finding_id is not None

    def test_limitations_default_empty(self):
        f = Finding(
            assessment_id="a",
            asset_id="b",
            category=FindingCategory.MODEL_INTEGRITY,
            subcategory="hash_mismatch",
            severity=Severity.CRITICAL,
            title="Hash mismatch",
            description="Model hash does not match declared hash.",
            detection_method="Artifact Fingerprint Detector",
            detector_id="mi.artifact_fingerprint",
        )
        assert f.limitations == []


class TestRiskAssessment:
    def test_construct(self):
        r = RiskAssessment(
            level=RiskLevel.HIGH,
            qualitative="Strong evidence of near-duplicate flooding.",
            methods_applied=["di.phash_duplicates"],
        )
        assert r.level == RiskLevel.HIGH
        assert r.methods_unavailable == []


class TestConfidenceAssessment:
    def test_construct(self):
        c = ConfidenceAssessment(
            level=ConfidenceLevel.MODERATE,
            qualifier="Perceptual hashing completed; embedding analysis not available.",
        )
        assert c.limiting_factors == []


class TestCoverageStatement:
    def test_fraction_calculated(self):
        cs = CoverageStatement(
            total_applicable=3,
            executed=2,
            coverage_fraction=2 / 3,
        )
        assert round(cs.coverage_fraction, 4) == round(2 / 3, 4)

    def test_fraction_validation(self):
        with pytest.raises(ValidationError):
            CoverageStatement(
                total_applicable=1, executed=0, coverage_fraction=1.5
            )


class TestProvenanceManifest:
    def test_construct(self):
        m = ProvenanceManifest(
            assessment_id="a-1",
            input_sha256="a" * 64,
            model_sha256="b" * 64,
            preprocessing_config={"resize": 224},
            inference_config={"top_k": 5},
            output_sha256="c" * 64,
            timestamp_utc="2026-09-10T13:00:00Z",
            nonce="n" * 64,
            sequence=0,
        )
        assert m.manifest_id is not None
        assert m.digest is None  # Set after canonicalization
        assert m.signature is None
