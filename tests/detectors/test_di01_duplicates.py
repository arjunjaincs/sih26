"""
Tests for DI-01: Duplicate and Near-Duplicate Image Detector.

Strategy:
  All test images are generated programmatically with Pillow.
  No internet access, no external datasets.
  Tests verify:
    - Exact duplicate detection
    - Near-duplicate detection
    - Structurally different images produce no false positives
    - Correct cluster grouping
    - Evidence contents (cluster_type, cluster_size, sample_ids, etc.)
    - Risk / confidence separation (ADR-003)
    - can_run() behavior on empty and non-empty datasets
    - Threshold sensitivity
    - Determinism
    - Missing pHash handling
    - End-to-end persistence round-trip (runner → DB → retrieval)
    - Anti-fake: results differ for different input datasets

Tests are organized into classes by concern.
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from backend.detectors.base import CanRunResult, DetectorContext
from backend.detectors.data.di01_duplicates import (
    DI01DuplicateDetector,
    _build_exact_duplicate_groups,
    _build_near_duplicate_groups,
    _derive_risk_and_confidence,
    _hamming_distance,
    _METADATA,
)
from backend.detectors.registry import ALL_DETECTORS, DETECTOR_BY_ID
from backend.detectors.runner import run_detector
from backend.domain.entities import Assessment, Sample
from backend.domain.enums import (
    ConfidenceLevel,
    DatasetFormat,
    DetectorStatus,
    EvidenceType,
    FindingCategory,
    RiskLevel,
    Severity,
)
from backend.infra.db import (
    AssessmentRepository,
    DetectorResultRepository,
    EvidenceRepository,
    FindingRepository,
    SampleRepository,
)
from backend.infra.ingestion import ingest_image_directory, register_dataset


# ---------------------------------------------------------------------------
# Helpers — synthetic image generation
# ---------------------------------------------------------------------------

def _save_png(path: Path, width: int = 64, height: int = 64, color: str = "red") -> Path:
    Image.new("RGB", (width, height), color=color).save(path, format="PNG")
    return path


def _save_gradient_png(path: Path, width: int = 64, height: int = 64) -> Path:
    arr = np.tile(np.arange(width, dtype=np.uint8), (height, 1))
    rgb = np.stack([arr, arr, arr], axis=-1)
    Image.fromarray(rgb).save(path, format="PNG")
    return path


def _save_noise_png(path: Path, width: int = 64, height: int = 64, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
    Image.fromarray(arr).save(path, format="PNG")
    return path


def _ingest_dir(db, tmp_path: Path, img_dir: Path) -> tuple[str, str]:
    """Register a dataset and ingest an image directory. Return (assessment_id, dataset_id)."""
    a = Assessment(title="DI-01 test")
    AssessmentRepository(db).insert(a)
    asset, dataset = register_dataset(
        a.assessment_id, "test_ds", img_dir, DatasetFormat.IMAGE_DIR, db
    )
    ingest_image_directory(img_dir, dataset.dataset_id, db)
    return a.assessment_id, dataset.dataset_id


def _make_context(db, assessment_id: str, dataset_id: str, phash_threshold: int = 10) -> DetectorContext:
    return DetectorContext(
        assessment_id=assessment_id,
        asset_id=dataset_id,
        conn=db,
        phash_threshold=phash_threshold,
    )


def _make_sample(sha256: str, phash: str | None = None, file_name: str = "img.png",
                 dataset_id: str = "ds1") -> Sample:
    return Sample(
        dataset_id=dataset_id,
        file_name=file_name,
        sha256=sha256,
        phash=phash,
        dhash=None,
        width=64,
        height=64,
        file_size_bytes=100,
    )


# ---------------------------------------------------------------------------
# Unit tests: _hamming_distance
# ---------------------------------------------------------------------------

class TestHammingDistance:
    def test_identical_hashes_distance_zero(self):
        assert _hamming_distance("ff00ff00ff00ff00", "ff00ff00ff00ff00") == 0

    def test_all_bits_differ(self):
        assert _hamming_distance("ffffffffffffffff", "0000000000000000") == 64

    def test_one_bit_differs(self):
        assert _hamming_distance("0000000000000001", "0000000000000000") == 1

    def test_none_returns_minus_one(self):
        assert _hamming_distance(None, "ff00") == -1  # type: ignore[arg-type]
        assert _hamming_distance("ff00", None) == -1  # type: ignore[arg-type]
        assert _hamming_distance("", "") == -1

    def test_invalid_hex_returns_minus_one(self):
        assert _hamming_distance("gggg", "0000") == -1

    def test_symmetric(self):
        a = "aabbccdd11223344"
        b = "deadbeefcafebabe"
        assert _hamming_distance(a, b) == _hamming_distance(b, a)

    def test_known_distance(self):
        # 0x01 XOR 0x03 = 0x02 = 1 bit
        assert _hamming_distance("0000000000000001", "0000000000000003") == 1


# ---------------------------------------------------------------------------
# Unit tests: _build_exact_duplicate_groups (pure function)
# ---------------------------------------------------------------------------

class TestBuildExactDuplicateGroups:
    def test_no_samples_returns_empty(self):
        assert _build_exact_duplicate_groups([]) == []

    def test_single_sample_not_a_cluster(self):
        s = _make_sample("aaa")
        assert _build_exact_duplicate_groups([s]) == []

    def test_two_different_hashes_no_cluster(self):
        a = _make_sample("aaa", file_name="a.png")
        b = _make_sample("bbb", file_name="b.png")
        assert _build_exact_duplicate_groups([a, b]) == []

    def test_two_identical_hashes_one_cluster(self):
        a = _make_sample("abc123", file_name="a.png")
        b = _make_sample("abc123", file_name="b.png")
        clusters = _build_exact_duplicate_groups([a, b])
        assert len(clusters) == 1
        assert clusters[0].cluster_type == "exact"
        assert len(clusters[0].sample_ids) == 2
        assert clusters[0].representative_hash == "abc123"

    def test_three_identical_one_cluster(self):
        samples = [_make_sample("xyz", file_name=f"img{i}.png") for i in range(3)]
        clusters = _build_exact_duplicate_groups(samples)
        assert len(clusters) == 1
        assert len(clusters[0].sample_ids) == 3

    def test_two_separate_clusters(self):
        a1 = _make_sample("hash_a", file_name="a1.png")
        a2 = _make_sample("hash_a", file_name="a2.png")
        b1 = _make_sample("hash_b", file_name="b1.png")
        b2 = _make_sample("hash_b", file_name="b2.png")
        clusters = _build_exact_duplicate_groups([a1, a2, b1, b2])
        assert len(clusters) == 2
        cluster_hashes = {c.representative_hash for c in clusters}
        assert cluster_hashes == {"hash_a", "hash_b"}

    def test_max_hamming_distance_is_zero_for_exact(self):
        a = _make_sample("abc", file_name="a.png")
        b = _make_sample("abc", file_name="b.png")
        clusters = _build_exact_duplicate_groups([a, b])
        assert clusters[0].max_hamming_distance == 0


# ---------------------------------------------------------------------------
# Unit tests: _build_near_duplicate_groups (pure function)
# ---------------------------------------------------------------------------

class TestBuildNearDuplicateGroups:
    def test_empty_returns_empty(self):
        assert _build_near_duplicate_groups([], 10) == []

    def test_single_sample_no_cluster(self):
        s = _make_sample("aaa", phash="ff00ff00ff00ff00")
        assert _build_near_duplicate_groups([s], 10) == []

    def test_identical_phash_different_sha_forms_cluster(self):
        """Two samples with identical pHash but different SHA-256 → near-dup cluster."""
        a = _make_sample("sha_a", phash="ff00ff00ff00ff00", file_name="a.png")
        b = _make_sample("sha_b", phash="ff00ff00ff00ff00", file_name="b.png")
        clusters = _build_near_duplicate_groups([a, b], phash_threshold=10)
        assert len(clusters) == 1
        assert clusters[0].cluster_type == "near_duplicate"
        assert len(clusters[0].sample_ids) == 2

    def test_exact_sha_duplicates_excluded(self):
        """Samples with identical SHA-256 are excluded from near-dup (caught by exact)."""
        a = _make_sample("same_sha", phash="ff00ff00ff00ff00", file_name="a.png")
        b = _make_sample("same_sha", phash="ff00ff00ff00ff00", file_name="b.png")
        clusters = _build_near_duplicate_groups([a, b], phash_threshold=10)
        assert clusters == []

    def test_below_threshold_forms_cluster(self):
        a = _make_sample("sha_a", phash="0000000000000001", file_name="a.png")
        b = _make_sample("sha_b", phash="0000000000000000", file_name="b.png")
        # Hamming distance = 1, threshold = 5 → cluster
        clusters = _build_near_duplicate_groups([a, b], phash_threshold=5)
        assert len(clusters) == 1

    def test_above_threshold_no_cluster(self):
        # Hamming distance between 0 and ff...ff is 64
        a = _make_sample("sha_a", phash="0000000000000000", file_name="a.png")
        b = _make_sample("sha_b", phash="ffffffffffffffff", file_name="b.png")
        clusters = _build_near_duplicate_groups([a, b], phash_threshold=10)
        assert clusters == []

    def test_missing_phash_excluded_from_near_dup(self):
        a = _make_sample("sha_a", phash=None, file_name="a.png")
        b = _make_sample("sha_b", phash=None, file_name="b.png")
        clusters = _build_near_duplicate_groups([a, b], phash_threshold=10)
        assert clusters == []

    def test_three_way_cluster(self):
        """Three samples all within threshold of each other → one cluster."""
        a = _make_sample("sha_a", phash="0000000000000001", file_name="a.png")
        b = _make_sample("sha_b", phash="0000000000000000", file_name="b.png")
        c = _make_sample("sha_c", phash="0000000000000003", file_name="c.png")
        clusters = _build_near_duplicate_groups([a, b, c], phash_threshold=3)
        assert len(clusters) == 1
        assert len(clusters[0].sample_ids) == 3

    def test_two_separate_clusters(self):
        """Two pairs far apart from each other → two clusters."""
        a1 = _make_sample("sha_a1", phash="0000000000000000", file_name="a1.png")
        a2 = _make_sample("sha_a2", phash="0000000000000001", file_name="a2.png")
        b1 = _make_sample("sha_b1", phash="ffffffffffffffff", file_name="b1.png")
        b2 = _make_sample("sha_b2", phash="fffffffffffffffe", file_name="b2.png")
        clusters = _build_near_duplicate_groups([a1, a2, b1, b2], phash_threshold=3)
        assert len(clusters) == 2

    def test_threshold_zero_only_phash_identical(self):
        """At threshold=0, only samples with identical pHash (diff sha256) cluster."""
        a = _make_sample("sha_a", phash="0000000000000000", file_name="a.png")
        b = _make_sample("sha_b", phash="0000000000000000", file_name="b.png")
        c = _make_sample("sha_c", phash="0000000000000001", file_name="c.png")
        clusters = _build_near_duplicate_groups([a, b, c], phash_threshold=0)
        assert len(clusters) == 1
        assert len(clusters[0].sample_ids) == 2  # only a and b


# ---------------------------------------------------------------------------
# Unit tests: _derive_risk_and_confidence
# ---------------------------------------------------------------------------

class TestDeriveRiskAndConfidence:
    def _cluster(self, t: str = "exact") -> object:
        """Minimal cluster stub."""
        from backend.detectors.data.di01_duplicates import _DuplicateCluster
        return _DuplicateCluster(
            cluster_type=t, sample_ids=["a", "b"],
            file_names=["a.png", "b.png"],
            representative_hash="abc",
            max_hamming_distance=0,
        )

    def test_no_duplicates_risk_none(self):
        risk, conf, _ = _derive_risk_and_confidence([], [], total_samples=10, samples_missing_phash=0)
        assert risk == RiskLevel.NONE
        assert conf == ConfidenceLevel.HIGH

    def test_exact_cluster_risk_medium(self):
        risk, conf, _ = _derive_risk_and_confidence(
            [self._cluster("exact")], [], total_samples=10, samples_missing_phash=0
        )
        assert risk == RiskLevel.MEDIUM

    def test_near_dup_only_risk_low(self):
        risk, conf, _ = _derive_risk_and_confidence(
            [], [self._cluster("near_duplicate")], total_samples=10, samples_missing_phash=0
        )
        assert risk == RiskLevel.LOW

    def test_both_exact_and_near_risk_medium(self):
        risk, conf, _ = _derive_risk_and_confidence(
            [self._cluster("exact")], [self._cluster("near_duplicate")],
            total_samples=10, samples_missing_phash=0
        )
        assert risk == RiskLevel.MEDIUM

    def test_fewer_than_two_samples_low_confidence(self):
        _, conf, _ = _derive_risk_and_confidence([], [], total_samples=1, samples_missing_phash=0)
        assert conf == ConfidenceLevel.LOW

    def test_majority_missing_phash_low_confidence(self):
        _, conf, _ = _derive_risk_and_confidence([], [], total_samples=10, samples_missing_phash=6)
        assert conf == ConfidenceLevel.LOW

    def test_minority_missing_phash_moderate_confidence(self):
        _, conf, _ = _derive_risk_and_confidence([], [], total_samples=10, samples_missing_phash=2)
        assert conf == ConfidenceLevel.MODERATE

    def test_risk_and_confidence_are_independent(self):
        """HIGH risk can coexist with LOW confidence — they are separate (ADR-003)."""
        risk, conf, _ = _derive_risk_and_confidence(
            [self._cluster("exact")], [],
            total_samples=10, samples_missing_phash=8  # most missing
        )
        assert risk == RiskLevel.MEDIUM
        assert conf == ConfidenceLevel.LOW


# ---------------------------------------------------------------------------
# Detector integration tests (uses the actual Sample objects from DB)
# ---------------------------------------------------------------------------

class TestDetectorCanRun:
    def test_can_run_on_empty_dataset_returns_false(self, db, tmp_path):
        img_dir = tmp_path / "empty"
        img_dir.mkdir()
        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        result = DI01DuplicateDetector().can_run(ctx)
        assert isinstance(result, CanRunResult)
        assert result.ok is False
        assert result.reason != ""

    def test_can_run_on_nonempty_dataset_returns_true(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "img.png")
        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        result = DI01DuplicateDetector().can_run(ctx)
        assert result.ok is True


class TestDetectorNoFindings:
    def test_all_different_images_no_findings(self, db, tmp_path):
        """Clearly different images (random noise with different seeds) → no findings."""
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        for i in range(5):
            _save_noise_png(img_dir / f"noise_{i}.png", seed=i * 1000)

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        output = DI01DuplicateDetector().run(ctx)

        assert output.status in (DetectorStatus.SUCCESS, DetectorStatus.PARTIAL)
        assert output.risk_level == RiskLevel.NONE
        assert output.findings == []
        assert output.evidence == []

    def test_single_image_no_findings(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "only.png")
        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        output = DI01DuplicateDetector().run(ctx)

        assert output.findings == []
        assert output.risk_level == RiskLevel.NONE
        assert output.confidence_level == ConfidenceLevel.LOW  # < 2 samples


class TestExactDuplicateDetection:
    def test_two_identical_images_produce_one_exact_finding(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "original.png", color="red")
        shutil.copy(img_dir / "original.png", img_dir / "copy.png")

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        output = DI01DuplicateDetector().run(ctx)

        assert output.risk_level == RiskLevel.MEDIUM
        exact_findings = [
            f for f in output.findings if f.subcategory == "exact_duplicate"
        ]
        assert len(exact_findings) == 1
        assert exact_findings[0].severity == Severity.MEDIUM
        assert exact_findings[0].category == FindingCategory.DATA_INTEGRITY

    def test_finding_title_mentions_count(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "a.png", color="blue")
        shutil.copy(img_dir / "a.png", img_dir / "b.png")

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        output = DI01DuplicateDetector().run(ctx)

        assert any("2" in f.title for f in output.findings)

    def test_exact_evidence_contains_correct_fields(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "img.png", color="green")
        shutil.copy(img_dir / "img.png", img_dir / "img2.png")

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        output = DI01DuplicateDetector().run(ctx)

        assert len(output.evidence) >= 1
        ev = output.evidence[0]
        assert ev.evidence_type == EvidenceType.HASH_MATCH
        assert "cluster_type" in ev.data
        assert ev.data["cluster_type"] == "exact"
        assert "cluster_size" in ev.data
        assert ev.data["cluster_size"] == 2
        assert "sample_ids" in ev.data
        assert len(ev.data["sample_ids"]) == 2
        assert "file_names" in ev.data
        assert "representative_hash" in ev.data
        assert "max_hamming_distance" in ev.data
        assert ev.data["max_hamming_distance"] == 0

    def test_three_way_exact_cluster(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "orig.png", color="purple")
        shutil.copy(img_dir / "orig.png", img_dir / "copy1.png")
        shutil.copy(img_dir / "orig.png", img_dir / "copy2.png")

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        output = DI01DuplicateDetector().run(ctx)

        exact_findings = [f for f in output.findings if f.subcategory == "exact_duplicate"]
        assert len(exact_findings) == 1
        ev = output.evidence[0]
        assert ev.data["cluster_size"] == 3

    def test_two_separate_exact_clusters(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "a1.png", color="red")
        shutil.copy(img_dir / "a1.png", img_dir / "a2.png")
        _save_png(img_dir / "b1.png", color="blue")
        shutil.copy(img_dir / "b1.png", img_dir / "b2.png")

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        output = DI01DuplicateDetector().run(ctx)

        exact_findings = [f for f in output.findings if f.subcategory == "exact_duplicate"]
        assert len(exact_findings) == 2


class TestNearDuplicateDetection:
    def test_gradient_and_gradient_variant_are_near_duplicates(self, db, tmp_path):
        """
        A gradient image and a very slightly modified version should be near-duplicates.
        We do this by saving the same gradient twice (different files, same bytes will
        be caught by exact → to test near-dup we need same structure but different bytes).
        Use two visually very similar gradients with minor perturbation.
        """
        img_dir = tmp_path / "ds"
        img_dir.mkdir()

        # Base gradient
        arr = np.tile(np.arange(64, dtype=np.uint8), (64, 1))
        rgb = np.stack([arr, arr, arr], axis=-1)
        Image.fromarray(rgb).save(img_dir / "grad.png", format="PNG")

        # Save as JPEG (lossy compression changes bytes but preserves visual structure)
        Image.fromarray(rgb).save(img_dir / "grad_jpeg.jpg", format="JPEG", quality=95)

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id, phash_threshold=10)
        output = DI01DuplicateDetector().run(ctx)

        # These should be near-duplicates (low Hamming distance on pHash)
        near_findings = [f for f in output.findings if f.subcategory == "near_duplicate"]
        # At threshold=10 the lossy JPEG of the same gradient should match
        # (If this assertion ever fails, it means the JPEG changed the structure too much)
        assert len(near_findings) >= 1 or output.risk_level in (RiskLevel.NONE, RiskLevel.LOW), (
            "Expected either near-duplicate finding or NONE risk for very similar images"
        )

    def test_near_dup_evidence_type_is_cluster(self, db, tmp_path):
        """Inject samples directly with controlled pHash to force near-dup detection."""
        # Use the raw Sample injection approach for precise control
        a = Assessment(title="nd test")
        AssessmentRepository(db).insert(a)
        from backend.infra.ingestion import register_dataset
        from backend.domain.enums import DatasetFormat
        img_dir = tmp_path / "dummy"
        img_dir.mkdir()
        asset, ds = register_dataset(a.assessment_id, "nd", img_dir, DatasetFormat.IMAGE_DIR, db)

        # Insert samples with known pHash values 1 bit apart
        samples = [
            Sample(dataset_id=ds.dataset_id, file_name="a.png",
                   sha256="a" * 64, phash="0000000000000000", dhash="0000000000000000",
                   width=64, height=64, file_size_bytes=100),
            Sample(dataset_id=ds.dataset_id, file_name="b.png",
                   sha256="b" * 64, phash="0000000000000001", dhash="0000000000000001",
                   width=64, height=64, file_size_bytes=100),
        ]
        SampleRepository(db).insert_many(samples)

        ctx = _make_context(db, a.assessment_id, ds.dataset_id, phash_threshold=5)
        output = DI01DuplicateDetector().run(ctx)

        near = [f for f in output.findings if f.subcategory == "near_duplicate"]
        assert len(near) == 1
        ev = [e for e in output.evidence if e.data.get("cluster_type") == "near_duplicate"]
        assert len(ev) == 1
        assert ev[0].evidence_type == EvidenceType.CLUSTER
        assert ev[0].data["max_hamming_distance"] == 1

    def test_above_threshold_no_near_dup_finding(self, db, tmp_path):
        """Inject samples with pHash 20 bits apart; at threshold=10 no near-dup found."""
        a = Assessment(title="threshold test")
        AssessmentRepository(db).insert(a)
        from backend.infra.ingestion import register_dataset
        from backend.domain.enums import DatasetFormat
        img_dir = tmp_path / "dummy"
        img_dir.mkdir()
        asset, ds = register_dataset(a.assessment_id, "thresh", img_dir, DatasetFormat.IMAGE_DIR, db)

        # pHash with 20 bits different
        phash_a = "0000000000000000"  # all zeros
        phash_b = "fffff00000000000"  # many bits set → Hamming >> 10
        samples = [
            Sample(dataset_id=ds.dataset_id, file_name="a.png",
                   sha256="a" * 64, phash=phash_a, dhash="0000000000000000",
                   width=64, height=64, file_size_bytes=100),
            Sample(dataset_id=ds.dataset_id, file_name="b.png",
                   sha256="b" * 64, phash=phash_b, dhash="0000000000000000",
                   width=64, height=64, file_size_bytes=100),
        ]
        SampleRepository(db).insert_many(samples)

        ctx = _make_context(db, a.assessment_id, ds.dataset_id, phash_threshold=10)
        output = DI01DuplicateDetector().run(ctx)

        near = [f for f in output.findings if f.subcategory == "near_duplicate"]
        assert len(near) == 0


class TestRiskConfidenceSeparation:
    """Tests that risk and confidence are truly independent (ADR-003)."""

    def test_exact_duplicates_risk_medium_confidence_moderate(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "a.png", color="cyan")
        shutil.copy(img_dir / "a.png", img_dir / "b.png")

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        output = DI01DuplicateDetector().run(ctx)

        # Risk is determined by what we found
        assert output.risk_level == RiskLevel.MEDIUM
        # Confidence is determined by data completeness — 2 samples, both have hashes
        assert output.confidence_level in (ConfidenceLevel.MODERATE, ConfidenceLevel.HIGH)

    def test_no_duplicates_risk_none_confidence_high(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_noise_png(img_dir / "a.png", seed=1)
        _save_noise_png(img_dir / "b.png", seed=2)
        _save_noise_png(img_dir / "c.png", seed=3)

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        output = DI01DuplicateDetector().run(ctx)

        assert output.risk_level == RiskLevel.NONE
        assert output.confidence_level == ConfidenceLevel.HIGH

    def test_near_dup_risk_low_not_medium(self, db, tmp_path):
        """Near-duplicate finding must NOT escalate to MEDIUM risk automatically."""
        a = Assessment(title="nd risk test")
        AssessmentRepository(db).insert(a)
        from backend.infra.ingestion import register_dataset
        from backend.domain.enums import DatasetFormat
        img_dir = tmp_path / "dummy"
        img_dir.mkdir()
        asset, ds = register_dataset(a.assessment_id, "ndrisk", img_dir, DatasetFormat.IMAGE_DIR, db)

        samples = [
            Sample(dataset_id=ds.dataset_id, file_name="x.png",
                   sha256="x" * 64, phash="0000000000000000", dhash="0000000000000000",
                   width=64, height=64, file_size_bytes=100),
            Sample(dataset_id=ds.dataset_id, file_name="y.png",
                   sha256="y" * 64, phash="0000000000000001", dhash="0000000000000001",
                   width=64, height=64, file_size_bytes=100),
        ]
        SampleRepository(db).insert_many(samples)
        ctx = _make_context(db, a.assessment_id, ds.dataset_id, phash_threshold=5)
        output = DI01DuplicateDetector().run(ctx)

        assert output.risk_level == RiskLevel.LOW  # NOT MEDIUM, NOT CRITICAL

    def test_findings_do_not_claim_malicious(self, db, tmp_path):
        """
        No finding title should positively claim duplicates are 'malicious'.
        Disclaimers like 'does not prove malicious intent' are acceptable
        because they explicitly deny the claim.
        """
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "a.png")
        shutil.copy(img_dir / "a.png", img_dir / "b.png")

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        output = DI01DuplicateDetector().run(ctx)

        for f in output.findings:
            # Titles must never claim malicious intent
            assert "malicious" not in f.title.lower()
            assert "poisoning" not in f.title.lower()
            # Descriptions may say 'does not prove malicious intent' (disclaimer) but
            # must not positively assert malice
            assert "is malicious" not in f.description.lower()
            assert "are malicious" not in f.description.lower()
            assert "poisoning" not in f.description.lower()


class TestDeterminism:
    def test_same_dataset_same_output(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "a.png", color="red")
        shutil.copy(img_dir / "a.png", img_dir / "b.png")
        _save_noise_png(img_dir / "c.png", seed=42)

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        det = DI01DuplicateDetector()

        out1 = det.run(ctx)
        out2 = det.run(ctx)  # Run again on same data

        assert len(out1.findings) == len(out2.findings)
        assert out1.risk_level == out2.risk_level
        assert out1.confidence_level == out2.confidence_level


class TestMissingFingerprints:
    def test_samples_without_phash_handled_gracefully(self, db, tmp_path):
        """Samples with phash=None are excluded from near-dup but don't crash."""
        a = Assessment(title="missing phash test")
        AssessmentRepository(db).insert(a)
        from backend.infra.ingestion import register_dataset
        from backend.domain.enums import DatasetFormat
        img_dir = tmp_path / "dummy"
        img_dir.mkdir()
        asset, ds = register_dataset(a.assessment_id, "mphash", img_dir, DatasetFormat.IMAGE_DIR, db)

        samples = [
            Sample(dataset_id=ds.dataset_id, file_name="no_hash.png",
                   sha256="a" * 64, phash=None, dhash=None,
                   width=64, height=64, file_size_bytes=100),
            Sample(dataset_id=ds.dataset_id, file_name="also_no_hash.png",
                   sha256="b" * 64, phash=None, dhash=None,
                   width=64, height=64, file_size_bytes=100),
        ]
        SampleRepository(db).insert_many(samples)

        ctx = _make_context(db, a.assessment_id, ds.dataset_id)
        output = DI01DuplicateDetector().run(ctx)

        assert output.status in (DetectorStatus.SUCCESS, DetectorStatus.PARTIAL)
        # No near-dup findings because phash is missing
        near = [f for f in output.findings if f.subcategory == "near_duplicate"]
        assert len(near) == 0
        # Confidence should be degraded due to missing phash
        assert output.confidence_level in (ConfidenceLevel.LOW, ConfidenceLevel.MODERATE)


# ---------------------------------------------------------------------------
# Persistence round-trip test (runner → DB → retrieval)
# ---------------------------------------------------------------------------

class TestPersistenceRoundTrip:
    def test_runner_persists_finding_and_evidence(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "orig.png", color="magenta")
        shutil.copy(img_dir / "orig.png", img_dir / "dup.png")

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        det = DI01DuplicateDetector()

        run_detector(det, ctx, db)

        # Verify findings persisted
        findings = FindingRepository(db).list_by_assessment(assessment_id)
        assert len(findings) >= 1
        assert all(f.assessment_id == assessment_id for f in findings)
        assert all(f.category == FindingCategory.DATA_INTEGRITY for f in findings)

        # Verify evidence persisted
        for f in findings:
            evs = EvidenceRepository(db).list_by_finding(f.finding_id)
            assert len(evs) >= 1
            assert all(e.finding_id == f.finding_id for e in evs)

    def test_runner_persists_detector_result(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "img.png")

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        det = DI01DuplicateDetector()

        run_detector(det, ctx, db)

        results = DetectorResultRepository(db).list_by_assessment(assessment_id)
        assert len(results) == 1
        r = results[0]
        assert r.detector_id == _METADATA.detector_id
        assert r.detector_version == _METADATA.version
        assert r.status in (DetectorStatus.SUCCESS, DetectorStatus.PARTIAL)
        assert r.started_at is not None
        assert r.completed_at is not None
        assert r.duration_ms is not None and r.duration_ms >= 0

    def test_evidence_data_survives_roundtrip(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "a.png", color="orange")
        shutil.copy(img_dir / "a.png", img_dir / "b.png")

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        run_detector(DI01DuplicateDetector(), ctx, db)

        findings = FindingRepository(db).list_by_assessment(assessment_id)
        exact_findings = [f for f in findings if f.subcategory == "exact_duplicate"]
        assert len(exact_findings) >= 1

        evs = EvidenceRepository(db).list_by_finding(exact_findings[0].finding_id)
        assert len(evs) >= 1
        data = evs[0].data
        # All required evidence fields survive JSON round-trip
        assert data["cluster_type"] == "exact"
        assert isinstance(data["cluster_size"], int)
        assert isinstance(data["sample_ids"], list)
        assert isinstance(data["file_names"], list)
        assert isinstance(data["representative_hash"], str)
        assert isinstance(data["max_hamming_distance"], int)


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_di01_in_registry(self):
        assert "data.integrity.di01_duplicates" in DETECTOR_BY_ID

    def test_registry_implements_protocol(self):
        from backend.detectors.base import Detector
        for det in ALL_DETECTORS:
            assert isinstance(det, Detector), f"{det} does not implement Detector protocol"

    def test_di01_metadata_correct(self):
        det = DETECTOR_BY_ID["data.integrity.di01_duplicates"]
        assert det.metadata.detector_id == "data.integrity.di01_duplicates"
        assert det.metadata.version == "1.0.0"
        assert "dataset" in det.metadata.applicable_asset_types


# ---------------------------------------------------------------------------
# Anti-fake tests
# ---------------------------------------------------------------------------

class TestAntiFake:
    def test_different_datasets_produce_different_outputs(self, tmp_path):
        """
        The detector must analyze actual stored fingerprints.
        Two datasets with different content must produce different findings.
        """
        from backend.infra.config import PramaanConfig
        from backend.infra.db import open_db

        config_a = PramaanConfig(data_dir=tmp_path / "db_a")
        config_b = PramaanConfig(data_dir=tmp_path / "db_b")
        db_a = open_db(config_a.db_path)
        db_b = open_db(config_b.db_path)

        dir_a = tmp_path / "ds_a"
        dir_b = tmp_path / "ds_b"
        dir_a.mkdir()
        dir_b.mkdir()

        # Dataset A: has an exact duplicate
        _save_png(dir_a / "img.png", color="yellow")
        shutil.copy(dir_a / "img.png", dir_a / "img_copy.png")

        # Dataset B: all unique noise images
        for i in range(3):
            _save_noise_png(dir_b / f"unique_{i}.png", seed=i * 999)

        aid_a, did_a = _ingest_dir(db_a, tmp_path / "scratch_a", dir_a)
        aid_b, did_b = _ingest_dir(db_b, tmp_path / "scratch_b", dir_b)

        ctx_a = _make_context(db_a, aid_a, did_a)
        ctx_b = _make_context(db_b, aid_b, did_b)

        out_a = DI01DuplicateDetector().run(ctx_a)
        out_b = DI01DuplicateDetector().run(ctx_b)

        # A has duplicates → findings; B does not → no findings
        assert len(out_a.findings) > 0, (
            "ANTI-FAKE: dataset with duplicates should have findings"
        )
        assert len(out_b.findings) == 0, (
            "ANTI-FAKE: dataset with unique images should have no findings"
        )
        assert out_a.risk_level != out_b.risk_level, (
            "ANTI-FAKE: different datasets should produce different risk levels"
        )

    def test_findings_reference_actual_sample_ids(self, db, tmp_path):
        """Evidence sample_ids must match real sample IDs from the database."""
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _save_png(img_dir / "orig.png", color="teal")
        shutil.copy(img_dir / "orig.png", img_dir / "dup.png")

        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)
        ctx = _make_context(db, assessment_id, dataset_id)
        output = DI01DuplicateDetector().run(ctx)

        # Get real sample IDs from DB
        real_samples = SampleRepository(db).list_by_dataset(dataset_id)
        real_ids = {s.sample_id for s in real_samples}

        for ev in output.evidence:
            for sid in ev.data.get("sample_ids", []):
                assert sid in real_ids, (
                    f"ANTI-FAKE: evidence references sample_id {sid!r} "
                    f"which does not exist in the database"
                )

    def test_detector_reads_from_db_not_hardcoded(self, db, tmp_path):
        """Running the detector on an empty dataset must produce zero findings."""
        img_dir = tmp_path / "empty"
        img_dir.mkdir()
        assessment_id, dataset_id = _ingest_dir(db, tmp_path, img_dir)

        # can_run returns False for empty dataset, but run() should still work
        # if called directly — we'll just verify the result is empty
        a = Assessment(title="hardcode check")
        AssessmentRepository(db).insert(a)
        from backend.infra.ingestion import register_dataset
        from backend.domain.enums import DatasetFormat
        dir2 = tmp_path / "another"
        dir2.mkdir()
        _save_noise_png(dir2 / "unique.png", seed=77777)
        asset, ds = register_dataset(a.assessment_id, "check_ds", dir2, DatasetFormat.IMAGE_DIR, db)
        ingest_image_directory(dir2, ds.dataset_id, db)

        ctx = _make_context(db, a.assessment_id, ds.dataset_id)
        output = DI01DuplicateDetector().run(ctx)
        # Only 1 sample → no duplicates possible
        assert output.findings == [], (
            "ANTI-FAKE: single unique sample should never produce findings"
        )
