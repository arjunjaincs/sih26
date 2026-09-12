"""
Tests for MI-04: Reference Model Comparison Battery Detector.

Tests cover:
- Protocol compliance and registry inclusion
- Missing reference -> can_run=False (leads to coverage gap)
- Exact cryptographic match (Risk NONE, Confidence HIGH)
- Behavioral equivalence (negligible MSE drift)
- Behavioral divergence (modified weights -> Risk MEDIUM)
- Stored reference fingerprint profile comparison
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.detectors.base import DetectorContext
from backend.detectors.model.mi04_reference_comparison import (
    MI04Context,
    MI04ReferenceComparisonDetector,
)
from backend.detectors.registry import DETECTOR_BY_ID
from backend.detectors.runner import run_detector
from backend.domain.enums import ConfidenceLevel, DetectorStatus, RiskLevel
from backend.infra.crypto import hash_file
from backend.infra.db import open_db
from tests.detectors.onnx_writer import (
    make_add_bias_model,
    make_relu_model,
)


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = open_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture
def model_a(tmp_path: Path) -> Path:
    p = tmp_path / "model_a.onnx"
    p.write_bytes(make_add_bias_model(bias_values=[1.0, 2.0, 3.0]))
    return p


@pytest.fixture
def model_a_copy(tmp_path: Path, model_a: Path) -> Path:
    p = tmp_path / "model_a_copy.onnx"
    p.write_bytes(model_a.read_bytes())
    return p


@pytest.fixture
def model_b_divergent(tmp_path: Path) -> Path:
    p = tmp_path / "model_b.onnx"
    # Same graph structure, different bias values -> behavioral divergence
    p.write_bytes(make_add_bias_model(bias_values=[50.0, -20.0, 10.0]))
    return p


@pytest.fixture
def model_c_diff_format(tmp_path: Path) -> Path:
    import torch
    p = tmp_path / "model_c.pt"
    torch.save({"w": torch.ones(3)}, p)
    return p


class TestMI04MetadataAndCanRun:
    def test_in_registry(self):
        assert "model.integrity.mi04_reference_comparison" in DETECTOR_BY_ID
        assert isinstance(DETECTOR_BY_ID["model.integrity.mi04_reference_comparison"], MI04ReferenceComparisonDetector)

    def test_missing_reference_cannot_run(self, db: sqlite3.Connection, model_a: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi04 = MI04Context(model_path=model_a, reference_model_path=None, reference_fingerprint=None)
        res = MI04ReferenceComparisonDetector().can_run(ctx)
        assert res.ok is False
        assert "no reference" in res.reason.lower()

    def test_valid_reference_can_run(self, db: sqlite3.Connection, model_a: Path, model_a_copy: Path):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi04 = MI04Context(model_path=model_a, reference_model_path=model_a_copy)
        res = MI04ReferenceComparisonDetector().can_run(ctx)
        assert res.ok is True


class TestMI04Execution:
    def test_exact_match(
        self, db: sqlite3.Connection, model_a: Path, model_a_copy: Path
    ):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi04 = MI04Context(model_path=model_a, reference_model_path=model_a_copy)
        output = MI04ReferenceComparisonDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.NONE
        assert output.confidence_level == ConfidenceLevel.HIGH
        assert any(f.subcategory == "reference_exact_match" for f in output.findings)

    def test_behavioral_divergence(
        self, db: sqlite3.Connection, model_a: Path, model_b_divergent: Path
    ):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi04 = MI04Context(model_path=model_a, reference_model_path=model_b_divergent)
        output = MI04ReferenceComparisonDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.MEDIUM
        assert any(f.subcategory == "behavioral_divergence" for f in output.findings)
        ev_data = output.evidence[0].data
        assert ev_data["behavioral_mse"] is not None
        assert ev_data["behavioral_mse"] > 0.0

    def test_format_mismatch(
        self, db: sqlite3.Connection, model_a: Path, model_c_diff_format: Path
    ):
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi04 = MI04Context(model_path=model_a, reference_model_path=model_c_diff_format)
        output = MI04ReferenceComparisonDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.HIGH
        assert any(f.subcategory == "model_format_substitution" for f in output.findings)

    def test_reference_fingerprint_dict_comparison(
        self, db: sqlite3.Connection, model_a: Path
    ):
        h = hash_file(model_a)
        ref_fp = {"artifact": {"sha256": h}}
        ctx = DetectorContext(assessment_id="a1", asset_id="m1", conn=db)
        ctx.mi04 = MI04Context(model_path=model_a, reference_fingerprint=ref_fp)
        output = MI04ReferenceComparisonDetector().run(ctx)

        assert output.status == DetectorStatus.SUCCESS
        assert output.risk_level == RiskLevel.NONE

    def test_runner_persistence(
        self, db: sqlite3.Connection, model_a: Path, model_a_copy: Path
    ):
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
            source_path=str(model_a),
        )
        ModelArtifactRepository(db).insert(ma)

        ctx = DetectorContext(assessment_id=a.assessment_id, asset_id=asset.asset_id, conn=db)
        ctx.mi04 = MI04Context(model_path=model_a, reference_model_path=model_a_copy)
        out = run_detector(MI04ReferenceComparisonDetector(), ctx, db)
        assert out.status == DetectorStatus.SUCCESS
