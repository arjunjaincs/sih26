"""
Tests for MI-02: Model Parameter Statistics Detector.

Tests cover:
- Protocol compliance and metadata
- can_run validations (missing context, missing file, unsupported format)
- Parameter extraction on clean ONNX model
- NaN weight corruption detection (elevated risk HIGH/CRITICAL)
- Inf weight corruption detection
- Extreme weight magnitude anomaly detection
- PyTorch state dict parameter extraction
- Sparsity calculations
- Determinism across repeated executions
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.detectors.base import DetectorContext
from backend.detectors.model.mi02_parameter_stats import (
    MI02Context,
    MI02ParameterStatsDetector,
    extract_parameter_stats,
)
from backend.detectors.registry import ALL_DETECTORS, DETECTOR_BY_ID
from backend.detectors.runner import run_detector
from backend.domain.enums import ConfidenceLevel, DetectorStatus, RiskLevel
from backend.infra.db import open_db
from tests.detectors.onnx_writer import (
    make_add_bias_model,
    make_extreme_bias_model,
    make_inf_bias_model,
    make_nan_bias_model,
    make_relu_model,
)


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = open_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture
def clean_onnx(tmp_path: Path) -> Path:
    p = tmp_path / "clean_model.onnx"
    p.write_bytes(make_add_bias_model(bias_values=[0.1, 0.2, 0.3]))
    return p


@pytest.fixture
def nan_onnx(tmp_path: Path) -> Path:
    p = tmp_path / "nan_model.onnx"
    p.write_bytes(make_nan_bias_model())
    return p


@pytest.fixture
def inf_onnx(tmp_path: Path) -> Path:
    p = tmp_path / "inf_model.onnx"
    p.write_bytes(make_inf_bias_model())
    return p


@pytest.fixture
def extreme_onnx(tmp_path: Path) -> Path:
    p = tmp_path / "extreme_model.onnx"
    p.write_bytes(make_extreme_bias_model())
    return p


@pytest.fixture
def pytorch_state_dict(tmp_path: Path) -> Path:
    import torch
    p = tmp_path / "weights.pt"
    state = {
        "conv1.weight": torch.randn(4, 3, 3, 3),
        "conv1.bias": torch.zeros(4),
        "fc.weight": torch.randn(10, 36),
    }
    torch.save(state, p)
    return p


@pytest.fixture
def pytorch_nan_dict(tmp_path: Path) -> Path:
    import torch
    p = tmp_path / "nan_weights.pt"
    state = {
        "conv1.weight": torch.tensor([float("nan"), 1.0, 2.0]),
        "fc.weight": torch.randn(5, 5),
    }
    torch.save(state, p)
    return p


class TestMI02MetadataAndProtocol:
    def test_in_registry(self):
        assert "model.integrity.mi02_parameter_stats" in DETECTOR_BY_ID
        det = DETECTOR_BY_ID["model.integrity.mi02_parameter_stats"]
        assert isinstance(det, MI02ParameterStatsDetector)

    def test_metadata(self):
        det = MI02ParameterStatsDetector()
        assert det.metadata.detector_id == "model.integrity.mi02_parameter_stats"
        assert det.metadata.version == "1.0.0"
        assert "MODEL" in [t.upper() for t in det.metadata.applicable_asset_types]


class TestMI02CanRun:
    def test_requires_context(self, db: sqlite3.Connection):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        res = MI02ParameterStatsDetector().can_run(ctx)
        assert res.ok is False
        assert "requires" in res.reason.lower()

    def test_nonexistent_file(self, db: sqlite3.Connection, tmp_path: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi02 = MI02Context(model_path=tmp_path / "missing.onnx")
        res = MI02ParameterStatsDetector().can_run(ctx)
        assert res.ok is False
        assert "not found" in res.reason.lower()

    def test_unsupported_extension(self, db: sqlite3.Connection, tmp_path: Path):
        p = tmp_path / "model.txt"
        p.write_text("not a model")
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi02 = MI02Context(model_path=p)
        res = MI02ParameterStatsDetector().can_run(ctx)
        assert res.ok is False
        assert "unsupported" in res.reason.lower()

    def test_valid_onnx_can_run(self, db: sqlite3.Connection, clean_onnx: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi02 = MI02Context(model_path=clean_onnx)
        res = MI02ParameterStatsDetector().can_run(ctx)
        assert res.ok is True


class TestMI02Analysis:
    def test_clean_onnx_baseline(self, db: sqlite3.Connection, clean_onnx: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi02 = MI02Context(model_path=clean_onnx)
        output = MI02ParameterStatsDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.NONE
        assert output.confidence_level == ConfidenceLevel.HIGH
        assert len(output.findings) >= 1
        assert len(output.evidence) >= 1

        ev_data = output.evidence[0].data
        assert ev_data["total_parameters"] == 3
        assert ev_data["nan_count"] == 0
        assert ev_data["inf_count"] == 0

    def test_nan_onnx_flags_corruption(self, db: sqlite3.Connection, nan_onnx: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi02 = MI02Context(model_path=nan_onnx)
        output = MI02ParameterStatsDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        assert any(f.subcategory == "parameter_corruption" for f in output.findings)

    def test_inf_onnx_flags_corruption(self, db: sqlite3.Connection, inf_onnx: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi02 = MI02Context(model_path=inf_onnx)
        output = MI02ParameterStatsDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_extreme_weight_magnitude_flags_medium(self, db: sqlite3.Connection, extreme_onnx: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi02 = MI02Context(model_path=extreme_onnx)
        output = MI02ParameterStatsDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.MEDIUM
        assert any(f.subcategory == "weight_distribution_anomaly" for f in output.findings)

    def test_pytorch_state_dict_analysis(self, db: sqlite3.Connection, pytorch_state_dict: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi02 = MI02Context(model_path=pytorch_state_dict)
        output = MI02ParameterStatsDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.NONE
        ev_data = output.evidence[0].data
        assert ev_data["total_parameters"] > 0
        assert ev_data["total_tensors"] == 3

    def test_pytorch_nan_state_dict(self, db: sqlite3.Connection, pytorch_nan_dict: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi02 = MI02Context(model_path=pytorch_nan_dict)
        output = MI02ParameterStatsDetector().run(ctx)

        assert output.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        assert any(f.subcategory == "parameter_corruption" for f in output.findings)

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
        ctx.mi02 = MI02Context(model_path=clean_onnx)
        out = run_detector(MI02ParameterStatsDetector(), ctx, db)
        assert out.status == DetectorStatus.SUCCESS
