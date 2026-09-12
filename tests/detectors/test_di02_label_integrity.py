"""
Tests for DI-02: Label Integrity & Systematic Mislabelling Detector.

Validates:
  - can_run() on empty, unannotated, single-labeled, and properly labeled datasets
  - Clean dataset produces zero integrity findings and NONE risk
  - Detection of near-duplicate label conflicts (Severity.HIGH)
  - Detection of class centroid outliers / candidate label flips (Severity.MEDIUM)
  - Deterministic execution across repeated runs
  - Proper evidence payload structure with machine-readable metadata
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from PIL import Image, ImageDraw

from backend.detectors.base import DetectorContext
from backend.detectors.data.di02_label_integrity import DI02LabelIntegrityDetector
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
    """Helper to create a directory, write images + metadata.json, and ingest."""
    assess = Assessment(title="DI-02 Test")
    AssessmentRepository(db).insert(assess)
    img_dir = tmp_path / f"ds_{assess.assessment_id[:8]}"
    img_dir.mkdir(parents=True, exist_ok=True)

    labels = {}
    contributors = {}
    for i, s in enumerate(samples_data):
        fname = s.get("file_name", f"img_{i:03d}.png")
        color = s.get("color", (100, 100, 100))
        img = Image.new("RGB", (64, 64), color=color)
        draw = ImageDraw.Draw(img)

        # Draw distinct geometric patterns if specified
        pattern = s.get("pattern")
        if pattern == "horizontal":
            step = s.get("step", 8)
            for y in range(0, 64, step):
                draw.line([(0, y), (63, y)], fill=(255, 255, 255), width=2)
        elif pattern == "vertical":
            step = s.get("step", 8)
            offset = s.get("offset", 0)
            for x in range(offset, 64, step):
                draw.line([(x, 0), (x, 63)], fill=(255, 255, 255), width=2)
        elif pattern == "diagonal":
            for d in range(-64, 64, 12):
                draw.line([(0, d), (63, d + 63)], fill=(255, 255, 255), width=2)
        elif "shape" in s:
            draw.rectangle(s["shape"], fill=s.get("shape_color", (200, 200, 200)))

        img.save(img_dir / fname, "PNG")
        if "label" in s:
            labels[fname] = s["label"]
        if "contributor" in s:
            contributors[fname] = s["contributor"]

    meta = {}
    if labels:
        meta["labels"] = labels
    if contributors:
        meta["contributors"] = contributors
    if meta:
        (img_dir / "metadata.json").write_text(json.dumps(meta))

    asset, dataset = register_dataset(
        assess.assessment_id, "test_dataset", img_dir, DatasetFormat.IMAGE_DIR, db
    )
    ingest_image_directory(img_dir, dataset.dataset_id, db)
    return assess.assessment_id, dataset.dataset_id, img_dir


class TestDI02PreFlight:
    def test_can_run_fails_when_dataset_not_found(self, db):
        det = DI02LabelIntegrityDetector()
        ctx = DetectorContext(assessment_id="a1", asset_id="nonexistent", conn=db)
        res = det.can_run(ctx)
        assert not res.ok
        assert "not found" in res.reason.lower()

    def test_can_run_fails_when_no_labels_present(self, db, tmp_path: Path):
        data = [{"color": (i * 40, 100, 100)} for i in range(3)]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI02LabelIntegrityDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)
        res = det.can_run(ctx)
        assert not res.ok
        assert "no label annotations" in res.reason.lower()

    def test_can_run_fails_when_only_one_labeled_sample(self, db, tmp_path: Path):
        data = [{"color": (100, 100, 100), "label": "cat"}]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI02LabelIntegrityDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)
        res = det.can_run(ctx)
        assert not res.ok
        assert "need >= 2" in res.reason.lower()

    def test_can_run_succeeds_with_two_or_more_labeled_samples(self, db, tmp_path: Path):
        data = [
            {"color": (100, 100, 100), "label": "cat"},
            {"color": (150, 150, 150), "label": "dog"},
        ]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI02LabelIntegrityDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)
        res = det.can_run(ctx)
        assert res.ok
        assert res.reason == ""


class TestDI02DetectionLogic:
    def test_clean_dataset_produces_no_findings(self, db, tmp_path: Path):
        # 3 horizontal pattern images labeled 'horizontal'
        # 3 vertical pattern images labeled 'vertical'
        data = [
            {"pattern": "horizontal", "color": (100, 100, 100), "label": "horizontal"},
            {"pattern": "horizontal", "color": (110, 110, 110), "label": "horizontal"},
            {"pattern": "horizontal", "color": (120, 120, 120), "label": "horizontal"},
            {"pattern": "vertical", "color": (100, 100, 100), "label": "vertical"},
            {"pattern": "vertical", "color": (110, 110, 110), "label": "vertical"},
            {"pattern": "vertical", "color": (120, 120, 120), "label": "vertical"},
        ]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI02LabelIntegrityDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)

        output = run_detector(det, ctx, db)
        assert output.status == DetectorStatus.SUCCESS
        assert len(output.findings) == 0
        assert output.risk_level == RiskLevel.NONE
        assert output.confidence_level in (ConfidenceLevel.HIGH, ConfidenceLevel.LOW)

    def test_near_duplicate_label_conflict_detected(self, db, tmp_path: Path):
        # Two identical pattern images with conflicting labels
        data = [
            {"file_name": "cat_1.png", "pattern": "diagonal", "color": (100, 150, 200), "label": "cat"},
            {"file_name": "dog_dup.png", "pattern": "diagonal", "color": (100, 150, 200), "label": "dog"}, # duplicate pattern, conflicting label!
            {"file_name": "bird_1.png", "pattern": "horizontal", "color": (50, 50, 50), "label": "bird"},
        ]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI02LabelIntegrityDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)

        output = run_detector(det, ctx, db)
        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.HIGH

        conflict_findings = [f for f in output.findings if "conflict" in f.title.lower()]
        assert len(conflict_findings) >= 1
        f = conflict_findings[0]
        assert f.severity == Severity.HIGH
        assert "cat" in f.description and "dog" in f.description

        # Verify evidence persisted in DB
        evs = EvidenceRepository(db).list_by_finding(f.finding_id)
        assert len(evs) >= 1
        assert evs[0].evidence_type == EvidenceType.ANOMALY
        assert "sample_1" in evs[0].data and "sample_2" in evs[0].data

    def test_centroid_outlier_label_flip_detected(self, db, tmp_path: Path):
        # Class 'horiz' has 4 horizontal images and 1 vertical pattern mislabelled as 'horiz'
        # Class 'vert' has 4 vertical images
        data = [
            {"file_name": "h1.png", "pattern": "horizontal", "color": (100, 100, 100), "label": "horiz"},
            {"file_name": "h2.png", "pattern": "horizontal", "color": (110, 110, 110), "label": "horiz"},
            {"file_name": "h3.png", "pattern": "horizontal", "color": (120, 120, 120), "label": "horiz"},
            {"file_name": "h4.png", "pattern": "horizontal", "color": (130, 130, 130), "label": "horiz"},
            # Candidate flip: visually vertical, but labeled 'horiz'
            {"file_name": "flipped.png", "pattern": "vertical", "offset": 3, "color": (100, 100, 100), "label": "horiz"},
            {"file_name": "v1.png", "pattern": "vertical", "color": (100, 100, 100), "label": "vert"},
            {"file_name": "v2.png", "pattern": "vertical", "color": (110, 110, 110), "label": "vert"},
            {"file_name": "v3.png", "pattern": "vertical", "color": (120, 120, 120), "label": "vert"},
            {"file_name": "v4.png", "pattern": "vertical", "color": (130, 130, 130), "label": "vert"},
        ]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI02LabelIntegrityDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)

        output = run_detector(det, ctx, db)
        assert output.status == DetectorStatus.SUCCESS
        flip_findings = [f for f in output.findings if "flipped.png" in f.title or "flipped.png" in f.description]
        assert len(flip_findings) >= 1
        f = flip_findings[0]
        assert f.severity in (Severity.MEDIUM, Severity.HIGH)
        assert "vert" in f.description

    def test_determinism(self, db, tmp_path: Path):
        data = [
            {"file_name": "a.png", "pattern": "diagonal", "color": (10, 20, 30), "label": "c1"},
            {"file_name": "b.png", "pattern": "diagonal", "color": (10, 20, 30), "label": "c2"},
        ]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI02LabelIntegrityDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)

        out1 = det.run(ctx)
        out2 = det.run(ctx)
        assert out1.risk_level == out2.risk_level
        assert len(out1.findings) == len(out2.findings)
        assert len(out1.evidence) == len(out2.evidence)
