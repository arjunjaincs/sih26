"""
Tests for MI-05: Model Trigger & Behavioral Perturbation Search Detector.

Tests cover:
- Protocol compliance and registry inclusion
- can_run validations
- Explicit rejection of non-executable formats (PyTorch state dict -> can_run=False with coverage gap reason)
- Execution on clean ONNX model (evaluating corner patches, center mark, control bias)
- Evidence verification and runner persistence
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.detectors.base import DetectorContext
from backend.detectors.model.mi05_trigger_anomaly import (
    MI05Context,
    MI05TriggerAnomalyDetector,
)
from backend.detectors.registry import DETECTOR_BY_ID
from backend.detectors.runner import run_detector
from backend.domain.enums import ConfidenceLevel, DetectorStatus, RiskLevel, Severity
from backend.infra.db import open_db
from tests.detectors.onnx_writer import (
    make_add_bias_model,
    make_dead_representation_model,
    make_relu_model,
)


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = open_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture
def clean_onnx(tmp_path: Path) -> Path:
    p = tmp_path / "relu_model.onnx"
    p.write_bytes(make_relu_model([1, 4]))
    return p


@pytest.fixture
def pytorch_file(tmp_path: Path) -> Path:
    import torch
    p = tmp_path / "model.pt"
    torch.save({"w": torch.ones(2, 2)}, p)
    return p


class TestMI05MetadataAndCanRun:
    def test_in_registry(self):
        assert "model.integrity.mi05_trigger_anomaly" in DETECTOR_BY_ID
        assert isinstance(DETECTOR_BY_ID["model.integrity.mi05_trigger_anomaly"], MI05TriggerAnomalyDetector)

    def test_metadata(self):
        det = MI05TriggerAnomalyDetector()
        assert det.metadata.detector_id == "model.integrity.mi05_trigger_anomaly"
        assert det.metadata.version == "1.0.0"

    def test_pytorch_state_dict_cannot_run_honest_limitation(
        self, db: sqlite3.Connection, pytorch_file: Path
    ):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi05 = MI05Context(model_path=pytorch_file)
        res = MI05TriggerAnomalyDetector().can_run(ctx)
        assert res.ok is False
        assert "non-executable" in res.reason.lower()

    def test_valid_onnx_can_run(self, db: sqlite3.Connection, clean_onnx: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi05 = MI05Context(model_path=clean_onnx)
        res = MI05TriggerAnomalyDetector().can_run(ctx)
        assert res.ok is True


class TestMI05Execution:
    def test_clean_onnx_trigger_search(self, db: sqlite3.Connection, clean_onnx: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi05 = MI05Context(model_path=clean_onnx)
        output = MI05TriggerAnomalyDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.NONE
        assert output.confidence_level == ConfidenceLevel.HIGH
        assert len(output.findings) >= 1
        assert len(output.evidence) >= 1

        ev_data = output.evidence[0].data
        assert ev_data["clean_pairwise_diversity"] >= 0.0
        assert len(ev_data["perturbation_evaluations"]) >= 4

    def test_bias_add_model_no_false_positive(self, db: sqlite3.Connection, tmp_path: Path):
        p = tmp_path / "bias_model.onnx"
        p.write_bytes(make_add_bias_model(bias_values=[1.0, 1.0, 1.0, 1.0], input_shape=[1, 4]))
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi05 = MI05Context(model_path=p)
        output = MI05TriggerAnomalyDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.NONE
        assert not any(f.subcategory == "suspicious_trigger_convergence" for f in output.findings)

    def test_dead_output_insufficient_diversity_partial(self, db: sqlite3.Connection, tmp_path: Path):
        p = tmp_path / "dead_model.onnx"
        p.write_bytes(make_dead_representation_model(input_shape=[1, 4]))
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi05 = MI05Context(model_path=p)
        output = MI05TriggerAnomalyDetector().run(ctx)

        assert output.status == DetectorStatus.PARTIAL
        assert output.risk_level == RiskLevel.NONE
        assert output.confidence_level == ConfidenceLevel.LOW
        assert len(output.findings) == 1
        finding = output.findings[0]
        assert finding.subcategory == "trigger_analysis_insufficient_diversity"
        assert finding.severity == Severity.INFO
        assert finding.description == (
            "Model output diversity on synthetic probes is insufficient for reliable trigger analysis. "
            "Test with domain-representative input data."
        )

    def test_deterministic_trigger_positive_model_detected(self, db: sqlite3.Connection, tmp_path: Path):
        # 1-element model where patch_top_left sets arr[..., :1] = 1.0, collapsing probe diversity from 0.55 down to 0.0
        p = tmp_path / "trigger_model.onnx"
        p.write_bytes(make_relu_model([1, 1]))
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi05 = MI05Context(model_path=p)
        output = MI05TriggerAnomalyDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.HIGH
        assert output.confidence_level == ConfidenceLevel.HIGH
        suspicious_findings = [f for f in output.findings if f.subcategory == "suspicious_trigger_convergence"]
        assert len(suspicious_findings) == 1
        assert "patch_top_left" in suspicious_findings[0].title
        assert len(output.evidence) >= 1
        assert output.evidence[0].data["clean_pairwise_diversity"] >= 0.05

    def test_runner_persistence(self, db: sqlite3.Connection, clean_onnx: Path):
        from backend.domain.entities import Assessment, Asset, ModelArtifact
        from backend.domain.enums import AccessLevel, AssetType, ModelFramework
        from backend.infra.db import AssessmentRepository, AssetRepository, ModelArtifactRepository

        a = Assessment(title="Test Assessment")
        AssessmentRepository(db).insert(a)
        asset = Asset(
            assessment_id=a.assessment_id,
            asset_type=AssetType.MODEL,
            name="test_model",
            sha256="a" * 64,
            size_bytes=1024,
        )
        AssetRepository(db).insert(asset)
        ma = ModelArtifact(
            model_id=asset.asset_id,
            assessment_id=a.assessment_id,
            framework=ModelFramework.ONNX,
            access_level=AccessLevel.WHITE_BOX,
            source_path=str(clean_onnx),
        )
        ModelArtifactRepository(db).insert(ma)

        ctx = DetectorContext(assessment_id=a.assessment_id, asset_id=asset.asset_id, conn=db)
        ctx.mi05 = MI05Context(model_path=clean_onnx)
        out = run_detector(MI05TriggerAnomalyDetector(), ctx, db)
        assert out.status == DetectorStatus.SUCCESS
