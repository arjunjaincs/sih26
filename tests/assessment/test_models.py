"""
Unit tests for AssessmentRequest model validation.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from backend.assessment.models import (
    AssessmentRequest,
    AssessmentResult,
    CoverageGapRecord,
    DetectorRunRecord,
)
from backend.domain.enums import (
    AssessmentState,
    ConfidenceLevel,
    DatasetFormat,
    DetectorStatus,
    RiskLevel,
)


# ---------------------------------------------------------------------------
# AssessmentRequest.validate()
# ---------------------------------------------------------------------------

class TestAssessmentRequestValidation:
    def test_empty_title_fails(self, tmp_path):
        req = AssessmentRequest(
            title="",
            dataset_path=tmp_path,
            dataset_format=DatasetFormat.IMAGE_DIR,
        )
        errors = req.validate()
        assert any("title" in e for e in errors)

    def test_whitespace_only_title_fails(self, tmp_path):
        req = AssessmentRequest(
            title="   ",
            dataset_path=tmp_path,
            dataset_format=DatasetFormat.IMAGE_DIR,
        )
        errors = req.validate()
        assert any("title" in e for e in errors)

    def test_no_assets_fails(self):
        req = AssessmentRequest(title="Test Assessment")
        errors = req.validate()
        assert any("dataset_path" in e or "model_path" in e or "provenance" in e
                   for e in errors)

    def test_dataset_without_format_fails(self, tmp_path):
        req = AssessmentRequest(
            title="Test",
            dataset_path=tmp_path,
            dataset_format=None,
        )
        errors = req.validate()
        assert any("dataset_format" in e for e in errors)

    def test_dataset_with_format_passes(self, tmp_path):
        req = AssessmentRequest(
            title="Test",
            dataset_path=tmp_path,
            dataset_format=DatasetFormat.IMAGE_DIR,
        )
        assert req.validate() == []

    def test_model_only_passes(self, tmp_path):
        model_file = tmp_path / "model.onnx"
        model_file.write_bytes(b"fake")
        req = AssessmentRequest(title="Test", model_path=model_file)
        assert req.validate() == []

    def test_provenance_without_key_fails(self):
        class FakeManifest:
            pass
        req = AssessmentRequest(
            title="Test",
            provenance_manifest=FakeManifest(),
            provenance_public_key=None,
        )
        errors = req.validate()
        assert any("provenance_public_key" in e for e in errors)

    def test_provenance_with_key_passes(self):
        class FakeManifest:
            pass
        class FakeKey:
            pass
        req = AssessmentRequest(
            title="Test",
            provenance_manifest=FakeManifest(),
            provenance_public_key=FakeKey(),
        )
        assert req.validate() == []

    def test_auto_generated_assessment_id(self):
        req = AssessmentRequest(title="Test", model_path=Path("/fake/model.onnx"))
        assert req.assessment_id
        # Should be a valid UUID
        uuid.UUID(req.assessment_id)

    def test_all_three_assets_passes(self, tmp_path):
        class FakeManifest:
            pass
        class FakeKey:
            pass
        req = AssessmentRequest(
            title="Test",
            dataset_path=tmp_path,
            dataset_format=DatasetFormat.IMAGE_DIR,
            model_path=tmp_path / "model.onnx",
            provenance_manifest=FakeManifest(),
            provenance_public_key=FakeKey(),
        )
        assert req.validate() == []

    def test_multiple_errors_reported(self):
        req = AssessmentRequest(title="")
        errors = req.validate()
        # Both title and missing asset errors
        assert len(errors) >= 2


# ---------------------------------------------------------------------------
# CoverageGapRecord
# ---------------------------------------------------------------------------

class TestCoverageGapRecord:
    def test_to_dict_has_required_keys(self):
        gap = CoverageGapRecord(
            detector_id="test.detector",
            detector_name="Test Detector",
            reason="not_available",
            required_capability="some cap",
            observed_capability="none",
            impact="not_assessed",
            recommended_action="do something",
        )
        d = gap.to_dict()
        for key in [
            "detector_id", "detector_name", "reason",
            "required_capability", "observed_capability",
            "impact", "recommended_action",
        ]:
            assert key in d, f"Key {key!r} missing from to_dict()"

    def test_to_dict_values_match(self):
        gap = CoverageGapRecord(
            detector_id="d1",
            detector_name="D1",
            reason="r1",
            required_capability="c1",
            observed_capability="c2",
            impact="i1",
            recommended_action="a1",
        )
        d = gap.to_dict()
        assert d["detector_id"] == "d1"
        assert d["reason"] == "r1"
        assert d["impact"] == "i1"


# ---------------------------------------------------------------------------
# AssessmentResult.to_dict()
# ---------------------------------------------------------------------------

class TestAssessmentResultToDict:
    def _make_result(self) -> AssessmentResult:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return AssessmentResult(
            assessment_id="test-id",
            title="Test Assessment",
            status=AssessmentState.COMPLETE,
            started_at=now,
            completed_at=now,
            assets_analyzed=["asset-1"],
            detectors_executed=["di01"],
            detectors_skipped=[],
            findings_count=2,
            evidence_count=5,
            overall_risk=RiskLevel.LOW,
            risk_qualitative="Low-severity observations.",
            overall_confidence=ConfidenceLevel.HIGH,
            confidence_qualifier="Full coverage.",
            coverage_fraction=1.0,
            coverage_gaps=[],
            detector_runs=[],
            limitations=[],
            audit_chain_valid=True,
            error=None,
        )

    def test_to_dict_is_json_serializable(self):
        import json
        result = self._make_result()
        d = result.to_dict()
        # Should not raise
        json.dumps(d)

    def test_to_dict_has_required_top_level_keys(self):
        result = self._make_result()
        d = result.to_dict()
        for key in [
            "assessment_id", "title", "status", "overall_risk",
            "overall_confidence", "coverage_fraction", "findings_count",
            "evidence_count", "limitations", "audit_chain_valid",
        ]:
            assert key in d, f"Key {key!r} missing from to_dict()"

    def test_risk_and_confidence_are_separate_fields(self):
        """ADR-003: risk and confidence must be distinct fields."""
        result = self._make_result()
        d = result.to_dict()
        assert "overall_risk" in d
        assert "overall_confidence" in d
        assert d["overall_risk"] != d["overall_confidence"]

    def test_failed_result_has_error_field(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        result = AssessmentResult(
            assessment_id="fail-id",
            title="Fail",
            status=AssessmentState.FAILED,
            started_at=now,
            completed_at=now,
            assets_analyzed=[],
            detectors_executed=[],
            detectors_skipped=[],
            findings_count=0,
            evidence_count=0,
            overall_risk=RiskLevel.NONE,
            risk_qualitative="Assessment failed.",
            overall_confidence=ConfidenceLevel.LOW,
            confidence_qualifier="No evidence.",
            coverage_fraction=0.0,
            coverage_gaps=[],
            detector_runs=[],
            limitations=["Error: something broke"],
            audit_chain_valid=None,
            error="something broke",
        )
        d = result.to_dict()
        assert d["error"] == "something broke"
        assert d["status"] == "failed"

    def test_coverage_fraction_rounded(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        result = AssessmentResult(
            assessment_id="test",
            title="T",
            status=AssessmentState.COMPLETE,
            started_at=now,
            completed_at=now,
            assets_analyzed=[],
            detectors_executed=[],
            detectors_skipped=[],
            findings_count=0,
            evidence_count=0,
            overall_risk=RiskLevel.NONE,
            risk_qualitative="q",
            overall_confidence=ConfidenceLevel.HIGH,
            confidence_qualifier="c",
            coverage_fraction=0.6666666666666,
            coverage_gaps=[],
            detector_runs=[],
            limitations=[],
            audit_chain_valid=None,
            error=None,
        )
        d = result.to_dict()
        # Should be rounded to 4 decimal places
        assert d["coverage_fraction"] == 0.6667
