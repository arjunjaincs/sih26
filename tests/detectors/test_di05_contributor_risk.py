"""
Tests for DI-05: Contributor / Source Risk Aggregation Detector.

Validates:
  - can_run() pre-flight checks (missing attribution vs present attribution)
  - Clean multi-contributor dataset produces zero findings and NONE risk
  - High concentration of defects from a specific contributor triggers findings (Severity.HIGH/MEDIUM)
  - Global comparison evidence breakdown across all contributors
  - Determinism across repeated runs
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from PIL import Image

from backend.detectors.base import DetectorContext
from backend.detectors.data.di05_contributor_risk import DI05ContributorRiskDetector
from backend.detectors.runner import run_detector
from backend.domain.entities import Assessment, Evidence, Finding
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
    EvidenceRepository,
    FindingRepository,
    SampleRepository,
    open_db,
)
from backend.infra.ingestion import ingest_image_directory, register_dataset


@pytest.fixture
def db(tmp_path: Path):
    return open_db(tmp_path / "test.db")


def _setup_dataset(db, tmp_path: Path, samples_data: list[dict]) -> tuple[str, str, list[str]]:
    assess = Assessment(title="DI-05 Test")
    AssessmentRepository(db).insert(assess)
    img_dir = tmp_path / f"ds_{assess.assessment_id[:8]}"
    img_dir.mkdir(parents=True, exist_ok=True)

    contributors = {}
    for i, s in enumerate(samples_data):
        fname = s.get("file_name", f"img_{i:03d}.png")
        img = Image.new("RGB", (64, 64), color=(i * 20, 100, 150))
        img.save(img_dir / fname, "PNG")
        if "contributor" in s:
            contributors[fname] = s["contributor"]

    if contributors:
        (img_dir / "metadata.json").write_text(json.dumps({"contributors": contributors}))

    asset, dataset = register_dataset(
        assess.assessment_id, "test_dataset", img_dir, DatasetFormat.IMAGE_DIR, db
    )
    ingest_image_directory(img_dir, dataset.dataset_id, db)
    samples = SampleRepository(db).list_by_dataset(dataset.dataset_id)
    return assess.assessment_id, dataset.dataset_id, [s.sample_id for s in samples]


class TestDI05PreFlight:
    def test_can_run_fails_when_dataset_not_found(self, db):
        det = DI05ContributorRiskDetector()
        ctx = DetectorContext(assessment_id="a1", asset_id="nonexistent", conn=db)
        res = det.can_run(ctx)
        assert not res.ok
        assert "not found" in res.reason.lower()

    def test_can_run_fails_when_no_contributor_metadata(self, db, tmp_path: Path):
        data = [{"file_name": f"img_{i}.png"} for i in range(4)]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI05ContributorRiskDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)
        res = det.can_run(ctx)
        assert not res.ok
        assert "no contributor" in res.reason.lower()

    def test_can_run_succeeds_with_contributor_metadata(self, db, tmp_path: Path):
        data = [
            {"file_name": "a.png", "contributor": "alice"},
            {"file_name": "b.png", "contributor": "bob"},
        ]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI05ContributorRiskDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)
        res = det.can_run(ctx)
        assert res.ok
        assert res.reason == ""


class TestDI05DetectionLogic:
    def test_clean_multi_contributor_dataset_produces_no_findings(self, db, tmp_path: Path):
        # Alice has 3 samples, Bob has 3 samples, no defect findings present
        data = [
            {"file_name": f"alice_{i}.png", "contributor": "alice"} for i in range(3)
        ] + [
            {"file_name": f"bob_{i}.png", "contributor": "bob"} for i in range(3)
        ]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI05ContributorRiskDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)

        output = run_detector(det, ctx, db)
        assert output.status == DetectorStatus.SUCCESS
        assert len(output.findings) == 0
        assert output.risk_level == RiskLevel.NONE
        assert output.confidence_level in (ConfidenceLevel.HIGH, ConfidenceLevel.LOW)

    def test_concentrated_defects_by_contributor_flagged(self, db, tmp_path: Path):
        # Alice contributes 4 clean images (0 defects)
        # Bob contributes 4 images, 3 of which are flagged by other detectors
        data = [
            {"file_name": f"alice_{i}.png", "contributor": "alice"} for i in range(4)
        ] + [
            {"file_name": f"bob_{i}.png", "contributor": "bob"} for i in range(4)
        ]
        a_id, ds_id, sample_ids = _setup_dataset(db, tmp_path, data)

        # Bob's samples are sample_ids[4], sample_ids[5], sample_ids[6], sample_ids[7]
        # Simulate prior findings from DI-01 / DI-03 on Bob's samples
        finding_repo = FindingRepository(db)
        evidence_repo = EvidenceRepository(db)

        for i, b_sid in enumerate(sample_ids[4:7]):
            f = Finding(
                finding_id=f"fnd_prior_{i}",
                assessment_id=a_id,
                asset_id=ds_id,
                category=FindingCategory.DATA_INTEGRITY,
                subcategory="trigger_anomaly",
                severity=Severity.HIGH,
                title=f"Prior finding on sample {b_sid}",
                description="Simulated prior anomaly",
                detection_method="PriorDetector",
                detector_id="data.integrity.di03_trigger_anomaly",
            )
            finding_repo.insert(f)
            ev = Evidence(
                evidence_id=f"ev_prior_{i}",
                finding_id=f.finding_id,
                detector_id="data.integrity.di03_trigger_anomaly",
                evidence_type=EvidenceType.ANOMALY,
                description="Simulated prior evidence",
                data={"sample_id": b_sid},
            )
            evidence_repo.insert(ev)

        det = DI05ContributorRiskDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)
        output = run_detector(det, ctx, db)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM)

        bob_findings = [f for f in output.findings if "bob" in f.title.lower() or "bob" in f.description.lower()]
        assert len(bob_findings) >= 1
        bf = bob_findings[0]
        assert bf.severity in (Severity.HIGH, Severity.MEDIUM)
        assert "bob" in bf.title.lower()

        # Alice should NOT have a risk finding
        alice_findings = [f for f in output.findings if "alice" in f.title.lower()]
        assert len(alice_findings) == 0

        # Verify summary evidence breakdown
        evs = EvidenceRepository(db).list_by_finding(bf.finding_id)
        assert len(evs) >= 1
        summary_ev = next((e for e in evs if e.evidence_type == EvidenceType.COMPARISON), None)
        assert summary_ev is not None
        assert "contributors" in summary_ev.data
        assert "bob" in summary_ev.data["contributors"]
        assert summary_ev.data["contributors"]["bob"]["flagged"] == 3

    def test_determinism(self, db, tmp_path: Path):
        data = [
            {"file_name": "a1.png", "contributor": "alice"},
            {"file_name": "b1.png", "contributor": "bob"},
        ]
        a_id, ds_id, _ = _setup_dataset(db, tmp_path, data)
        det = DI05ContributorRiskDetector()
        ctx = DetectorContext(assessment_id=a_id, asset_id=ds_id, conn=db)

        out1 = det.run(ctx)
        out2 = det.run(ctx)
        assert out1.risk_level == out2.risk_level
        assert len(out1.findings) == len(out2.findings)
        assert len(out1.evidence) == len(out2.evidence)
