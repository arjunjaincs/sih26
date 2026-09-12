"""
Tests for DI-04: Distribution & Out-of-Distribution (OOD) Detector.

Validates:
  - can_run() pre-flight checks (<5 samples vs >=5 samples)
  - Clean in-distribution dataset produces zero findings and NONE risk
  - Detection of significant statistical distribution outliers (aspect ratio or color/luminance shift)
  - Evidence schema compliance (standardized median/IQR distances)
  - Deterministic execution across repeated runs
"""

from __future__ import annotations

from pathlib import Path
import pytest
from PIL import Image

from backend.detectors.base import DetectorContext
from backend.detectors.data.di04_ood_distribution import DI04DistributionOODDetector
from backend.detectors.runner import run_detector
from backend.domain.entities import Assessment
from backend.domain.enums import (
    ConfidenceLevel,
    DatasetFormat,
    DetectorStatus,
    EvidenceType,
    RiskLevel,
    Severity,
)
from backend.infra.db import (
    AssessmentRepository,
    EvidenceRepository,
    open_db,
)
from backend.infra.ingestion import ingest_image_directory, register_dataset


@pytest.fixture
def db(tmp_path: Path):
    return open_db(tmp_path / "test.db")


def _setup_dataset(db, tmp_path: Path, samples_data: list[dict]) -> tuple[str, str, Path]:
    assess = Assessment(title="DI-04 Test")
    AssessmentRepository(db).insert(assess)
    img_dir = tmp_path / f"ds_{assess.assessment_id[:8]}"
    img_dir.mkdir(parents=True, exist_ok=True)

    for i, s in enumerate(samples_data):
        fname = s.get("file_name", f"img_{i:03d}.png")
        size = s.get("size", (64, 64))
        color = s.get("color", (128, 128, 128))
        img = Image.new("RGB", size, color=color)
        img.save(img_dir / fname, "PNG")

    asset, dataset = register_dataset(
        assess.assessment_id, "test_dataset", img_dir, DatasetFormat.IMAGE_DIR, db
    )
    ingest_image_directory(img_dir, dataset.dataset_id, db)
    return assess.assessment_id, dataset.dataset_id, img_dir


class TestDI04PreFlight:
    def test_can_run_fails_when_dataset_not_found(self, db):
        det = DI04DistributionOODDetector()
        ctx = DetectorContext(assessment_id="a1", asset_id="nonexistent", conn=db)
        res = det.can_run(ctx)
        assert not res.ok
        assert "not found" in res.reason.lower()

    def test_can_run_fails_with_fewer_than_five_samples(self, db, tmp_path: Path):
        data = [{"file_name": f"img_{i}.png"} for i in range(4)]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI04DistributionOODDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)
        res = det.can_run(ctx)
        assert not res.ok
        assert "minimum 5" in res.reason.lower() or "insufficient" in res.reason.lower()

    def test_can_run_succeeds_with_five_or_more_samples(self, db, tmp_path: Path):
        data = [{"file_name": f"img_{i}.png"} for i in range(5)]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI04DistributionOODDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)
        res = det.can_run(ctx)
        assert res.ok
        assert res.reason == ""


class TestDI04DetectionLogic:
    def test_clean_in_distribution_dataset_produces_no_findings(self, db, tmp_path: Path):
        # 8 tightly clustered images in dimension and color
        data = [
            {"file_name": f"in_dist_{i}.png", "size": (64, 64), "color": (120 + i * 2, 125 - i * 2, 130)}
            for i in range(8)
        ]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI04DistributionOODDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)

        output = run_detector(det, ctx, db)
        assert output.status == DetectorStatus.SUCCESS
        assert len(output.findings) == 0
        assert output.risk_level == RiskLevel.NONE
        assert output.confidence_level in (ConfidenceLevel.HIGH, ConfidenceLevel.LOW)

    def test_ood_sample_detected(self, db, tmp_path: Path):
        # 8 normal square medium-gray images, plus 1 extreme aspect ratio / inverted image
        data = [
            {"file_name": f"norm_{i}.png", "size": (64, 64), "color": (120, 120, 120)}
            for i in range(8)
        ]
        data.append(
            {"file_name": "ood_tall.png", "size": (16, 128), "color": (255, 10, 10)}
        )
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI04DistributionOODDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)

        output = run_detector(det, ctx, db)
        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level != RiskLevel.NONE

        ood_findings = [f for f in output.findings if "ood_tall.png" in f.title or "ood_tall.png" in f.description]
        assert len(ood_findings) >= 1
        f = ood_findings[0]
        assert f.severity in (Severity.LOW, Severity.MEDIUM)

        # Verify evidence persisted in DB
        evs = EvidenceRepository(db).list_by_finding(f.finding_id)
        assert len(evs) >= 1
        assert evs[0].evidence_type == EvidenceType.STATISTICAL_TEST
        assert "distance" in evs[0].data

    def test_determinism(self, db, tmp_path: Path):
        data = [
            {"file_name": f"s_{i}.png", "size": (64, 64), "color": (100, 100, 100)}
            for i in range(6)
        ]
        data.append({"file_name": "ood.png", "size": (16, 128), "color": (250, 0, 0)})
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI04DistributionOODDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)

        out1 = det.run(ctx)
        out2 = det.run(ctx)
        assert out1.risk_level == out2.risk_level
        assert len(out1.findings) == len(out2.findings)
        assert len(out1.evidence) == len(out2.evidence)
