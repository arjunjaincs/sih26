"""
Unit tests for backend/assessment/aggregator.py.

Tests pure aggregation logic — no DB, no file I/O.

Coverage
--------
- aggregate_risk: empty, all-skipped, single detector, multiple detectors, max selection
- aggregate_confidence: full coverage, partial, failed, gaps
- compute_coverage: zero applicable, partial, full
- derive_limitations: gap narration, detector limitations
- ADR-003 invariant: risk and confidence are independent
"""

from __future__ import annotations

import pytest

from backend.assessment.aggregator import (
    aggregate_confidence,
    aggregate_risk,
    compute_coverage,
    derive_limitations,
)
from backend.assessment.models import CoverageGapRecord
from backend.detectors.base import DetectorOutput
from backend.domain.entities import Finding, Evidence
from backend.domain.enums import (
    AssetType,
    ConfidenceLevel,
    DetectorStatus,
    EvidenceType,
    FindingCategory,
    RiskLevel,
    Severity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_output(
    status: DetectorStatus = DetectorStatus.SUCCESS,
    risk: RiskLevel = RiskLevel.NONE,
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
    findings: list[Finding] | None = None,
    error: str | None = None,
) -> DetectorOutput:
    o = DetectorOutput(
        status=status,
        risk_level=risk,
        confidence_level=confidence,
        findings=findings or [],
        error=error,
    )
    return o.finalize()


def _make_gap(
    detector_id: str = "test.detector",
    reason: str = "not_available",
) -> CoverageGapRecord:
    return CoverageGapRecord(
        detector_id=detector_id,
        detector_name=detector_id,
        reason=reason,
        required_capability="some capability",
        observed_capability="none",
        impact="analysis_incomplete",
        recommended_action="provide the required asset",
    )


# ---------------------------------------------------------------------------
# aggregate_risk
# ---------------------------------------------------------------------------

class TestAggregateRisk:
    def test_empty_outputs_returns_none_risk(self):
        risk, qual = aggregate_risk([])
        assert risk == RiskLevel.NONE
        assert "No detectors" in qual

    def test_all_skipped_returns_none_risk(self):
        outputs = [
            _make_output(status=DetectorStatus.SKIPPED),
            _make_output(status=DetectorStatus.NOT_APPLICABLE),
            _make_output(status=DetectorStatus.UNAVAILABLE),
        ]
        risk, qual = aggregate_risk(outputs)
        assert risk == RiskLevel.NONE
        assert "unavailable" in qual.lower()

    def test_single_none_risk(self):
        risk, qual = aggregate_risk([_make_output(risk=RiskLevel.NONE)])
        assert risk == RiskLevel.NONE

    def test_single_low_risk(self):
        risk, qual = aggregate_risk([_make_output(risk=RiskLevel.LOW)])
        assert risk == RiskLevel.LOW
        assert "Low" in qual

    def test_single_medium_risk(self):
        risk, qual = aggregate_risk([_make_output(risk=RiskLevel.MEDIUM)])
        assert risk == RiskLevel.MEDIUM
        assert "Medium" in qual or "medium" in qual.lower()

    def test_single_high_risk(self):
        risk, qual = aggregate_risk([_make_output(risk=RiskLevel.HIGH)])
        assert risk == RiskLevel.HIGH

    def test_single_critical_risk(self):
        risk, qual = aggregate_risk([_make_output(risk=RiskLevel.CRITICAL)])
        assert risk == RiskLevel.CRITICAL

    def test_max_across_multiple(self):
        """Max should be HIGH when outputs have NONE, LOW, HIGH."""
        outputs = [
            _make_output(risk=RiskLevel.NONE),
            _make_output(risk=RiskLevel.LOW),
            _make_output(risk=RiskLevel.HIGH),
        ]
        risk, qual = aggregate_risk(outputs)
        assert risk == RiskLevel.HIGH

    def test_max_skipped_not_counted(self):
        """A SKIPPED output with HIGH risk should not count."""
        outputs = [
            _make_output(status=DetectorStatus.SKIPPED, risk=RiskLevel.HIGH),
            _make_output(status=DetectorStatus.SUCCESS, risk=RiskLevel.NONE),
        ]
        risk, _ = aggregate_risk(outputs)
        assert risk == RiskLevel.NONE

    def test_max_between_medium_and_low(self):
        outputs = [
            _make_output(risk=RiskLevel.MEDIUM),
            _make_output(risk=RiskLevel.LOW),
        ]
        risk, _ = aggregate_risk(outputs)
        assert risk == RiskLevel.MEDIUM

    def test_risk_and_qualitative_always_returned_together(self):
        """aggregate_risk always returns a non-empty qualitative string."""
        for rl in RiskLevel:
            risk, qual = aggregate_risk([_make_output(risk=rl)])
            assert isinstance(qual, str)
            assert len(qual) > 0

    def test_qualitative_not_empty_for_no_findings(self):
        risk, qual = aggregate_risk([_make_output(risk=RiskLevel.NONE, findings=[])])
        assert "No integrity issues" in qual or "Findings present" in qual or "No detectors" in qual


# ---------------------------------------------------------------------------
# aggregate_confidence
# ---------------------------------------------------------------------------

class TestAggregateConfidence:
    def test_empty_outputs_low_confidence(self):
        level, qualifier, limiting = aggregate_confidence([], [], 1.0)
        assert level == ConfidenceLevel.LOW
        assert "No evidence" in qualifier

    def test_all_skipped_low_confidence(self):
        outputs = [_make_output(status=DetectorStatus.SKIPPED)]
        level, qualifier, limiting = aggregate_confidence(outputs, [], 0.0)
        assert level == ConfidenceLevel.LOW

    def test_full_coverage_no_gaps_high_confidence(self):
        outputs = [_make_output(status=DetectorStatus.SUCCESS)]
        level, qualifier, limiting = aggregate_confidence(outputs, [], 1.0)
        assert level == ConfidenceLevel.HIGH

    def test_gaps_reduce_confidence(self):
        outputs = [_make_output(status=DetectorStatus.SUCCESS)]
        gaps = [_make_gap()]
        level, qualifier, limiting = aggregate_confidence(outputs, gaps, 0.5)
        # Gaps + partial coverage -> not HIGH
        assert level in (ConfidenceLevel.MODERATE, ConfidenceLevel.LOW)

    def test_partial_detector_at_most_moderate(self):
        outputs = [_make_output(status=DetectorStatus.PARTIAL)]
        level, qualifier, limiting = aggregate_confidence(outputs, [], 1.0)
        assert level != ConfidenceLevel.HIGH

    def test_failed_detector_at_most_moderate(self):
        outputs = [_make_output(status=DetectorStatus.FAILED)]
        level, qualifier, limiting = aggregate_confidence(outputs, [], 0.0)
        # Failed + low coverage -> LOW
        assert level == ConfidenceLevel.LOW

    def test_low_confidence_detector_reduces_overall(self):
        outputs = [_make_output(confidence=ConfidenceLevel.LOW)]
        level, qualifier, limiting = aggregate_confidence(outputs, [], 1.0)
        # The run was successful but the detector self-reported LOW -> at most MODERATE
        assert level != ConfidenceLevel.HIGH

    def test_gaps_appear_in_limiting_factors(self):
        outputs = [_make_output(status=DetectorStatus.SUCCESS)]
        gap = _make_gap("test.detector", "framework_unavailable")
        _, _, limiting = aggregate_confidence(outputs, [gap], 0.5)
        combined = " ".join(limiting)
        assert "test.detector" in combined or "framework_unavailable" in combined

    def test_adr003_confidence_independent_of_risk(self):
        """Confidence can be HIGH while risk is HIGH (we saw something bad, but clearly)."""
        outputs = [_make_output(
            status=DetectorStatus.SUCCESS,
            risk=RiskLevel.HIGH,
            confidence=ConfidenceLevel.HIGH,
        )]
        level, _, _ = aggregate_confidence(outputs, [], 1.0)
        assert level == ConfidenceLevel.HIGH


# ---------------------------------------------------------------------------
# compute_coverage
# ---------------------------------------------------------------------------

class TestComputeCoverage:
    def test_zero_applicable_returns_one(self):
        assert compute_coverage(0, 0) == 1.0

    def test_all_executed(self):
        assert compute_coverage(3, 3) == 1.0

    def test_none_executed(self):
        assert compute_coverage(3, 0) == 0.0

    def test_partial_coverage(self):
        frac = compute_coverage(3, 2)
        assert abs(frac - 2 / 3) < 1e-9

    def test_cannot_exceed_one(self):
        # Defensive: executed > applicable should not cause > 1.0
        assert compute_coverage(2, 5) == 1.0

    def test_single_applicable_ran(self):
        assert compute_coverage(1, 1) == 1.0

    def test_single_applicable_not_ran(self):
        assert compute_coverage(1, 0) == 0.0


# ---------------------------------------------------------------------------
# derive_limitations
# ---------------------------------------------------------------------------

class TestDeriveLimitations:
    def test_empty_inputs(self):
        lims = derive_limitations([], [])
        assert isinstance(lims, list)
        assert len(lims) == 0

    def test_gap_produces_limitation(self):
        gap = _make_gap("test.di01", "no_dataset")
        lims = derive_limitations([gap], [])
        assert len(lims) == 1
        assert "no_dataset" in lims[0]

    def test_partial_detector_produces_limitation(self):
        outputs = [_make_output(status=DetectorStatus.PARTIAL)]
        lims = derive_limitations([], outputs)
        combined = " ".join(lims)
        assert "partial" in combined.lower()

    def test_failed_detector_produces_limitation(self):
        outputs = [_make_output(status=DetectorStatus.FAILED)]
        lims = derive_limitations([], outputs)
        combined = " ".join(lims)
        assert "fail" in combined.lower()

    def test_finding_limitations_included(self):
        finding = Finding(
            assessment_id="a",
            asset_id="b",
            category=FindingCategory.DATA_INTEGRITY,
            subcategory="test",
            severity=Severity.LOW,
            title="t",
            description="d",
            detection_method="m",
            detector_id="d",
            limitations=["This is a known limitation."],
        )
        output = _make_output(findings=[finding])
        lims = derive_limitations([], [output])
        assert "This is a known limitation." in lims

    def test_finding_limitations_deduplicated(self):
        """The same limitation string should not appear twice."""
        lim_text = "Known limitation one."
        finding = Finding(
            assessment_id="a",
            asset_id="b",
            category=FindingCategory.DATA_INTEGRITY,
            subcategory="test",
            severity=Severity.LOW,
            title="t",
            description="d",
            detection_method="m",
            detector_id="d",
            limitations=[lim_text],
        )
        # Two identical findings
        o1 = _make_output(findings=[finding])
        lims = derive_limitations([], [o1, o1])
        assert lims.count(lim_text) == 1

    def test_multiple_gaps_all_appear(self):
        gaps = [_make_gap("d1", "reason_a"), _make_gap("d2", "reason_b")]
        lims = derive_limitations(gaps, [])
        combined = " ".join(lims)
        assert "reason_a" in combined
        assert "reason_b" in combined


# ---------------------------------------------------------------------------
# ADR-003 cross-cutting invariant
# ---------------------------------------------------------------------------

class TestAdr003Invariant:
    """
    ADR-003: Risk and confidence are ALWAYS computed separately and NEVER
    collapsed into a single score.
    """

    def test_none_risk_with_low_confidence_is_valid(self):
        """
        LOW confidence + NONE risk = "we don't know, could be fine or could be bad".
        This is the state when all detectors are unavailable — it is correct.
        NOT the same as "probably safe".
        """
        outputs: list[DetectorOutput] = []
        gaps = [_make_gap("test.di01", "no_dataset")]
        risk, risk_qual = aggregate_risk(outputs)
        confidence, conf_qual, limiting = aggregate_confidence(outputs, gaps, 0.0)
        assert risk == RiskLevel.NONE
        assert confidence == ConfidenceLevel.LOW
        # Both are returned independently
        assert isinstance(risk_qual, str)
        assert isinstance(conf_qual, str)

    def test_high_risk_with_high_confidence_is_valid(self):
        """High risk + high confidence = we clearly saw something bad."""
        outputs = [_make_output(
            status=DetectorStatus.SUCCESS,
            risk=RiskLevel.HIGH,
            confidence=ConfidenceLevel.HIGH,
        )]
        risk, _ = aggregate_risk(outputs)
        confidence, _, _ = aggregate_confidence(outputs, [], 1.0)
        assert risk == RiskLevel.HIGH
        assert confidence == ConfidenceLevel.HIGH

    def test_none_risk_with_high_confidence_is_valid(self):
        """No issues found AND we checked thoroughly."""
        outputs = [_make_output(
            status=DetectorStatus.SUCCESS,
            risk=RiskLevel.NONE,
            confidence=ConfidenceLevel.HIGH,
        )]
        risk, _ = aggregate_risk(outputs)
        confidence, _, _ = aggregate_confidence(outputs, [], 1.0)
        assert risk == RiskLevel.NONE
        assert confidence == ConfidenceLevel.HIGH

    def test_aggregation_is_deterministic(self):
        """Same inputs → same outputs every time."""
        outputs = [
            _make_output(risk=RiskLevel.MEDIUM, confidence=ConfidenceLevel.MODERATE),
            _make_output(risk=RiskLevel.LOW, confidence=ConfidenceLevel.HIGH),
        ]
        results = []
        for _ in range(5):
            risk, _ = aggregate_risk(outputs)
            confidence, _, _ = aggregate_confidence(outputs, [], 0.67)
            results.append((risk, confidence))
        assert len(set(results)) == 1, "Aggregation must be deterministic"
