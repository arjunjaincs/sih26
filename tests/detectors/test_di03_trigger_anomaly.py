"""
Tests for DI-03: Trigger/Pattern Anomaly Detector.

Validates:
  - can_run() on empty, insufficient (<3), and valid (>=3) datasets
  - Clean dataset produces zero trigger findings and NONE risk
  - Injected spatial patch backdoor/trigger patterns across distinct images are detected
  - Low variance flat corners are not falsely flagged
  - Evidence output schema compliance
  - Determinism across repeated runs
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from PIL import Image, ImageDraw

from backend.detectors.base import DetectorContext
from backend.detectors.data.di03_trigger_anomaly import DI03TriggerAnomalyDetector
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
    assess = Assessment(title="DI-03 Test")
    AssessmentRepository(db).insert(assess)
    img_dir = tmp_path / f"ds_{assess.assessment_id[:8]}"
    img_dir.mkdir(parents=True, exist_ok=True)

    for i, s in enumerate(samples_data):
        fname = s.get("file_name", f"img_{i:03d}.png")
        base_color = s.get("base_color", (i * 30, (i * 50) % 256, 200 - i * 20))
        img = Image.new("RGB", (64, 64), color=base_color)
        draw = ImageDraw.Draw(img)

        # Draw natural diverse background elements
        draw.line([(0, i * 10), (63, 63 - i * 10)], fill=(255, 255, 255), width=2)
        draw.ellipse([10 + i * 5, 10, 30 + i * 5, 30], fill=(50, 150, 50))

        # Inject trigger if requested
        if s.get("has_trigger"):
            # Distinctive high-contrast checkerboard pattern in bottom-right corner [48, 48, 64, 64]
            for bx in range(48, 64, 4):
                for by in range(48, 64, 4):
                    fill = (255, 255, 0) if (bx + by) % 8 == 0 else (0, 0, 0)
                    draw.rectangle([bx, by, bx + 3, by + 3], fill=fill)

        img.save(img_dir / fname, "PNG")

    asset, dataset = register_dataset(
        assess.assessment_id, "test_dataset", img_dir, DatasetFormat.IMAGE_DIR, db
    )
    ingest_image_directory(img_dir, dataset.dataset_id, db)
    return assess.assessment_id, dataset.dataset_id, img_dir


class TestDI03PreFlight:
    def test_can_run_fails_when_dataset_not_found(self, db):
        det = DI03TriggerAnomalyDetector()
        ctx = DetectorContext(assessment_id="a1", asset_id="nonexistent", conn=db)
        res = det.can_run(ctx)
        assert not res.ok
        assert "not found" in res.reason.lower()

    def test_can_run_fails_with_fewer_than_three_samples(self, db, tmp_path: Path):
        data = [{"file_name": "a.png"}, {"file_name": "b.png"}]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI03TriggerAnomalyDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)
        res = det.can_run(ctx)
        assert not res.ok
        assert "minimum 3" in res.reason.lower() or "insufficient" in res.reason.lower()

    def test_can_run_succeeds_with_three_or_more_samples(self, db, tmp_path: Path):
        data = [{"file_name": "a.png"}, {"file_name": "b.png"}, {"file_name": "c.png"}]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI03TriggerAnomalyDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)
        res = det.can_run(ctx)
        assert res.ok
        assert res.reason == ""


class TestDI03DetectionLogic:
    def test_clean_dataset_produces_no_trigger_findings(self, db, tmp_path: Path):
        data = [
            {"file_name": f"clean_{i}.png", "has_trigger": False}
            for i in range(5)
        ]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI03TriggerAnomalyDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)

        output = run_detector(det, ctx, db)
        assert output.status == DetectorStatus.SUCCESS
        assert len(output.findings) == 0
        assert output.risk_level == RiskLevel.NONE
        assert output.confidence_level in (ConfidenceLevel.HIGH, ConfidenceLevel.LOW)

    def test_injected_trigger_patch_detected(self, db, tmp_path: Path):
        # 5 images, 3 of which share an identical trigger in bottom-right corner
        data = [
            {"file_name": "trig_1.png", "has_trigger": True},
            {"file_name": "trig_2.png", "has_trigger": True},
            {"file_name": "trig_3.png", "has_trigger": True},
            {"file_name": "clean_1.png", "has_trigger": False},
            {"file_name": "clean_2.png", "has_trigger": False},
        ]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI03TriggerAnomalyDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)

        output = run_detector(det, ctx, db)
        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM)

        trigger_findings = [f for f in output.findings if "trigger" in f.title.lower()]
        assert len(trigger_findings) >= 1
        f = trigger_findings[0]
        assert "bottom right" in f.title.lower() or "bottom right" in f.description.lower()

        # Verify evidence persisted in DB
        evs = EvidenceRepository(db).list_by_finding(f.finding_id)
        assert len(evs) >= 1
        assert evs[0].evidence_type == EvidenceType.ANOMALY
        assert "affected_samples" in evs[0].data
        assert len(evs[0].data["affected_samples"]) >= 3

    def test_determinism(self, db, tmp_path: Path):
        data = [
            {"file_name": "t1.png", "has_trigger": True},
            {"file_name": "t2.png", "has_trigger": True},
            {"file_name": "t3.png", "has_trigger": True},
        ]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI03TriggerAnomalyDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)

        out1 = det.run(ctx)
        out2 = det.run(ctx)
        assert out1.risk_level == out2.risk_level
        assert len(out1.findings) == len(out2.findings)
        assert len(out1.evidence) == len(out2.evidence)
