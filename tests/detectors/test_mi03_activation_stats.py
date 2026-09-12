"""
Tests for MI-03: Model Activation & Representation Statistics Detector.

Tests cover:
- Protocol compliance and registry inclusion
- can_run validations
- Explicit rejection of non-executable formats (PyTorch state dict -> can_run=False with coverage gap explanation)
- Execution on clean ONNX model (zeros, ones, gradient, noise)
- Dead representation / activation collapse detection
- Evidence verification and runner persistence
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.detectors.base import DetectorContext
from backend.detectors.model.mi03_activation_stats import (
    MI03ActivationStatsDetector,
    MI03Context,
)
from backend.detectors.registry import DETECTOR_BY_ID
from backend.detectors.runner import run_detector
from backend.domain.enums import ConfidenceLevel, DetectorStatus, RiskLevel
from backend.infra.db import open_db
from tests.detectors.onnx_writer import (
    make_add_bias_model,
    make_dead_representation_model,
    make_multi_layer_model,
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
def multi_layer_onnx(tmp_path: Path) -> Path:
    p = tmp_path / "multi_model.onnx"
    p.write_bytes(make_multi_layer_model([1, 4]))
    return p


@pytest.fixture
def dead_repr_onnx(tmp_path: Path) -> Path:
    p = tmp_path / "dead_model.onnx"
    p.write_bytes(make_dead_representation_model([1, 4]))
    return p


@pytest.fixture
def pytorch_file(tmp_path: Path) -> Path:
    import torch
    p = tmp_path / "model.pt"
    torch.save({"w": torch.ones(2, 2)}, p)
    return p


class TestMI03MetadataAndCanRun:
    def test_in_registry(self):
        assert "model.integrity.mi03_activation_stats" in DETECTOR_BY_ID
        assert isinstance(DETECTOR_BY_ID["model.integrity.mi03_activation_stats"], MI03ActivationStatsDetector)

    def test_metadata(self):
        det = MI03ActivationStatsDetector()
        assert det.metadata.detector_id == "model.integrity.mi03_activation_stats"
        assert det.metadata.version == "1.0.0"

    def test_pytorch_state_dict_cannot_run_honest_limitation(
        self, db: sqlite3.Connection, pytorch_file: Path
    ):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi03 = MI03Context(model_path=pytorch_file)
        res = MI03ActivationStatsDetector().can_run(ctx)
        assert res.ok is False
        assert "state dict" in res.reason.lower() or "executable" in res.reason.lower()

    def test_valid_onnx_can_run(self, db: sqlite3.Connection, clean_onnx: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi03 = MI03Context(model_path=clean_onnx)
        res = MI03ActivationStatsDetector().can_run(ctx)
        assert res.ok is True


class TestMI03Execution:
    def test_clean_onnx_activations_output_only_fallback(self, db: sqlite3.Connection, clean_onnx: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi03 = MI03Context(model_path=clean_onnx)
        output = MI03ActivationStatsDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.NONE
        # In current environment, onnx compiler package is absent -> output-only fallback with MODERATE confidence
        assert output.confidence_level == ConfidenceLevel.MODERATE
        assert len(output.findings) >= 1
        assert len(output.evidence) >= 1

        ev_data = output.evidence[0].data
        assert ev_data["monitored_layer_count"] >= 1
        assert ev_data["intermediate_layers_captured"] is False
        assert ev_data["analysis_scope"] == "output_only"
        assert len(ev_data["layer_samples"]) >= 4

        finding = output.findings[0]
        expected_limitation = (
            "Intermediate layer extraction requires the 'onnx' compiler package; "
            "current environment captures output-layer statistics only. "
            "Install 'onnx' for full intermediate activation monitoring."
        )
        assert expected_limitation in finding.limitations
        assert "output activation profile" in finding.title.lower()

    def test_clean_onnx_with_intermediate_captured(
        self, db: sqlite3.Connection, clean_onnx: Path, monkeypatch
    ):
        from backend.detectors.model import mi03_activation_stats

        orig_fn = mi03_activation_stats._analyze_activations_onnx
        def mock_analyze(path):
            summaries, _ = orig_fn(path)
            return summaries, True

        monkeypatch.setattr(mi03_activation_stats, "_analyze_activations_onnx", mock_analyze)

        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi03 = MI03Context(model_path=clean_onnx)
        output = MI03ActivationStatsDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.NONE
        assert output.confidence_level == ConfidenceLevel.HIGH
        assert output.evidence[0].data["intermediate_layers_captured"] is True
        assert output.evidence[0].data["analysis_scope"] == "intermediate_and_output"
        assert "monitored layers" in output.findings[0].title.lower()

    def test_multi_layer_activations(self, db: sqlite3.Connection, multi_layer_onnx: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi03 = MI03Context(model_path=multi_layer_onnx)
        output = MI03ActivationStatsDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.NONE

    def test_dead_representation_flags_medium_risk(
        self, db: sqlite3.Connection, dead_repr_onnx: Path
    ):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi03 = MI03Context(model_path=dead_repr_onnx)
        output = MI03ActivationStatsDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.MEDIUM
        assert any(f.subcategory == "activation_collapse" for f in output.findings)

    def test_runner_execution(self, db: sqlite3.Connection, clean_onnx: Path):
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
        ctx.mi03 = MI03Context(model_path=clean_onnx)
        out = run_detector(MI03ActivationStatsDetector(), ctx, db)
        assert out.status == DetectorStatus.SUCCESS
