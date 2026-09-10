"""
PRAMAAN assessment risk/confidence/coverage aggregation.

Pure functions — no database access, no file I/O, no randomness.
These functions are the single authoritative place for converting
per-detector outputs into an assessment-level risk/confidence/coverage result.

ADR-003 Rules (strictly enforced)
-----------------------------------
1. Risk and confidence are ALWAYS separate values.
2. Risk = the worst observation we saw.
3. Confidence = how well we covered the applicable analysis space.
4. Never collapse risk+confidence into a single number.
5. "no findings" is not the same as "no risk" if confidence is LOW.
6. "detector unavailable" → coverage gap + reduced confidence, NOT clean result.

Coverage Definition
-------------------
    coverage_fraction = executed_applicable / total_applicable

Where:
  - executed_applicable: detectors that are applicable AND completed (SUCCESS or PARTIAL)
  - total_applicable: all detectors that are applicable (ran or not)
  - Not-applicable detectors are excluded from both numerator and denominator

This means:
  - An unavailable applicable detector REDUCES coverage (and reduces confidence).
  - A non-applicable detector does NOT affect coverage (it is irrelevant).
  - A failed applicable detector is counted in total_applicable but NOT in executed.
"""

from __future__ import annotations

from backend.assessment.models import CoverageGapRecord
from backend.detectors.base import DetectorOutput
from backend.domain.enums import ConfidenceLevel, DetectorStatus, RiskLevel


# ---------------------------------------------------------------------------
# Risk ordering (used since RiskLevel is a plain StrEnum with no ordering)
# ---------------------------------------------------------------------------

_RISK_ORDER: dict[str, int] = {
    RiskLevel.NONE.value:     0,
    RiskLevel.LOW.value:      1,
    RiskLevel.MEDIUM.value:   2,
    RiskLevel.HIGH.value:     3,
    RiskLevel.CRITICAL.value: 4,
}

_ORDER_TO_RISK: dict[int, RiskLevel] = {v: k for k, v in {  # type: ignore[misc]
    RiskLevel.NONE:     0,
    RiskLevel.LOW:      1,
    RiskLevel.MEDIUM:   2,
    RiskLevel.HIGH:     3,
    RiskLevel.CRITICAL: 4,
}.items()}


def _risk_max(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    """Return the higher of two RiskLevel values."""
    return a if _RISK_ORDER.get(a.value, 0) >= _RISK_ORDER.get(b.value, 0) else b


# ---------------------------------------------------------------------------
# Risk aggregation
# ---------------------------------------------------------------------------

def aggregate_risk(outputs: list[DetectorOutput]) -> tuple[RiskLevel, str]:
    """
    Determine the highest risk level observed across all detector outputs.

    Returns (RiskLevel, qualitative_description).

    Design
    ------
    - Uses the per-detector risk_level already aggregated by each detector.
    - If no detectors ran (outputs is empty), returns NONE with explicit note.
    - NONE risk with LOW confidence is a valid state — do not confuse them.

    This function ONLY looks at what detectors *observed*, not at whether they
    could run. Coverage gaps are handled by aggregate_confidence().
    """
    _skipped = {
        DetectorStatus.SKIPPED,
        DetectorStatus.NOT_APPLICABLE,
        DetectorStatus.UNAVAILABLE,
    }

    if not outputs:
        return (
            RiskLevel.NONE,
            "No detectors executed. Risk cannot be assessed — see coverage gaps.",
        )

    ran_outputs = [o for o in outputs if o.status not in _skipped]

    if not ran_outputs:
        return (
            RiskLevel.NONE,
            "All applicable detectors were unavailable. Risk cannot be assessed — see coverage gaps.",
        )

    max_risk = RiskLevel.NONE
    for o in ran_outputs:
        max_risk = _risk_max(max_risk, o.risk_level)

    # Build qualitative description
    if max_risk == RiskLevel.NONE:
        total_findings = sum(len(o.findings) for o in ran_outputs)
        if total_findings == 0:
            qualitative = (
                f"No integrity issues detected across {len(ran_outputs)} "
                f"executed detector(s)."
            )
        else:
            qualitative = (
                "Findings present but all assessed as informational/no risk "
                "by the executed detector(s)."
            )
    elif max_risk == RiskLevel.LOW:
        qualitative = "Low-severity integrity observations detected. Analyst review recommended."
    elif max_risk == RiskLevel.MEDIUM:
        qualitative = "Medium-severity integrity issues detected. Investigation required."
    elif max_risk == RiskLevel.HIGH:
        qualitative = "High-severity integrity failures detected. Immediate review required."
    else:
        qualitative = "Critical-severity integrity failures detected. Do not trust this asset."

    return max_risk, qualitative


# ---------------------------------------------------------------------------
# Confidence aggregation
# ---------------------------------------------------------------------------

def aggregate_confidence(
    outputs: list[DetectorOutput],
    gaps: list[CoverageGapRecord],
    coverage_fraction: float,
) -> tuple[ConfidenceLevel, str, list[str]]:
    """
    Determine overall confidence based on evidence completeness.

    Returns (ConfidenceLevel, qualifier_string, limiting_factors).

    Confidence is INDEPENDENT of risk (ADR-003). LOW confidence means
    "we don't know enough" — it does NOT mean "the asset is probably safe".

    Algorithm
    ---------
    Start at HIGH.
    Reduce based on observed limiting factors:
      - coverage_fraction < 1.0        → at most MODERATE
      - any output PARTIAL              → at most MODERATE
      - all outputs FAILED/UNAVAILABLE  → LOW
      - no outputs at all              → LOW
      - any output FAILED (not PARTIAL) → at most MODERATE
    """
    _skipped = {
        DetectorStatus.SKIPPED,
        DetectorStatus.NOT_APPLICABLE,
        DetectorStatus.UNAVAILABLE,
    }

    limiting: list[str] = []

    if not outputs:
        limiting.append("No detectors executed — no evidence gathered.")
        return ConfidenceLevel.LOW, "No evidence gathered.", limiting

    ran_outputs = [o for o in outputs if o.status not in _skipped]

    if not ran_outputs:
        limiting.append("All applicable detectors were unavailable or skipped.")
        for g in gaps:
            limiting.append(f"{g.detector_name}: {g.reason}")
        return (
            ConfidenceLevel.LOW,
            "All applicable detectors unavailable — no analysis performed.",
            limiting,
        )

    # Check for coverage gaps
    if gaps:
        for g in gaps:
            limiting.append(
                f"{g.detector_name} could not run ({g.reason}): {g.impact}"
            )

    # Check for partial/failed detectors
    has_partial = any(o.status == DetectorStatus.PARTIAL for o in ran_outputs)
    has_failed = any(o.status == DetectorStatus.FAILED for o in ran_outputs)

    if has_partial:
        limiting.append(
            "One or more detectors completed with partial coverage "
            "(framework limitations or missing optional capabilities)."
        )
    if has_failed:
        limiting.append("One or more detectors failed during execution.")

    # Check detector-level confidence (some detectors set LOW themselves)
    low_conf_detectors = [
        o for o in ran_outputs if o.confidence_level == ConfidenceLevel.LOW
    ]
    if low_conf_detectors:
        limiting.append(
            f"{len(low_conf_detectors)} detector(s) reported LOW confidence "
            "(insufficient data or analysis limitations)."
        )

    # Derive level
    if (
        coverage_fraction >= 1.0
        and not gaps
        and not has_partial
        and not has_failed
        and not low_conf_detectors
    ):
        level = ConfidenceLevel.HIGH
        qualifier = (
            f"All {len(ran_outputs)} applicable detector(s) completed successfully "
            f"with full coverage."
        )
    elif coverage_fraction > 0.5 and not has_failed and not low_conf_detectors:
        level = ConfidenceLevel.MODERATE
        qualifier = (
            f"{len(ran_outputs)} detector(s) executed "
            f"({coverage_fraction:.0%} coverage). "
            + ("Some limitations apply." if limiting else "")
        )
    else:
        level = ConfidenceLevel.LOW
        qualifier = (
            f"Coverage is {coverage_fraction:.0%}. "
            f"Significant limitations apply — risk assessment may be incomplete."
        )

    return level, qualifier, limiting


# ---------------------------------------------------------------------------
# Coverage calculation
# ---------------------------------------------------------------------------

def compute_coverage(
    total_applicable: int,
    executed_applicable: int,
) -> float:
    """
    Compute coverage fraction.

    coverage = executed_applicable / total_applicable

    Parameters
    ----------
    total_applicable   : number of applicable detectors (ran or not)
    executed_applicable: number of applicable detectors that completed (SUCCESS or PARTIAL)

    Returns
    -------
    float in [0.0, 1.0]. Returns 1.0 if total_applicable is 0 (nothing applicable
    → nothing was missed).
    """
    if total_applicable == 0:
        return 1.0  # Nothing applicable → full "coverage" of the empty set
    return min(1.0, executed_applicable / total_applicable)


# ---------------------------------------------------------------------------
# Limitation derivation
# ---------------------------------------------------------------------------

def derive_limitations(
    gaps: list[CoverageGapRecord],
    outputs: list[DetectorOutput],
) -> list[str]:
    """
    Build an ordered list of known limitations for the assessment result.

    This is the narrative list suitable for analysts and reports.
    """
    limitations: list[str] = []

    # From coverage gaps
    for g in gaps:
        limitations.append(
            f"{g.detector_name} was not run ({g.reason}). "
            f"Impact: {g.impact}. "
            f"Recommended action: {g.recommended_action}"
        )

    # From individual detector limitations
    for o in outputs:
        for finding in o.findings:
            for lim in finding.limitations:
                if lim and lim not in limitations:
                    limitations.append(lim)

    # From partial detector status
    partial_detectors = [
        o for o in outputs if o.status == DetectorStatus.PARTIAL
    ]
    if partial_detectors:
        limitations.append(
            "One or more detectors ran with partial analysis. "
            "Some aspects of the asset could not be fully assessed."
        )

    # From failed detector status
    failed_detectors = [
        o for o in outputs if o.status == DetectorStatus.FAILED
    ]
    if failed_detectors:
        limitations.append(
            f"{len(failed_detectors)} detector(s) failed during execution. "
            "The failure is recorded but the cause must be investigated before "
            "the assessment result can be considered complete."
        )

    return limitations
