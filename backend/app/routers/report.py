"""
/api/report — assurance report generation endpoint.
"""
import random
from datetime import datetime, timezone
from fastapi import APIRouter
from app.models.schemas import (
    AssuranceReport, PipelineSummary, ReportStage, StageFinding, RiskLevel, AttackScenario
)
from app.data.fixtures import build_stages
from app.state import active_scenarios

router = APIRouter(prefix="/report", tags=["report"])

RISK_ORDER = [RiskLevel.CLEAN, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]


def _worst_risk(risks: list[RiskLevel]) -> RiskLevel:
    return max(risks, key=lambda r: RISK_ORDER.index(r))


def _compose_recommendation(
    overall_risk: RiskLevel,
    scenarios: list[AttackScenario],
    stages: list[dict],
) -> str:
    """
    Dynamically compose an analyst recommendation paragraph based on current
    risk level. Four template variants keyed to risk severity.
    """
    scenario_names = [s.value.replace("_", " ") for s in scenarios]
    scenario_str = (
        ", ".join(f"'{n}'" for n in scenario_names) if scenario_names
        else "no active adversarial scenarios"
    )
    critical_stages = [
        s["stage_name"] for s in stages
        if s["risk"] in (RiskLevel.CRITICAL, RiskLevel.HIGH)
    ]
    stage_str = ", ".join(critical_stages) if critical_stages else "no stages"

    if overall_risk == RiskLevel.CRITICAL:
        return (
            f"CRITICAL RISK — IMMEDIATE ACTION REQUIRED. The pipeline has entered a critically "
            f"compromised state with confirmed adversarial activity ({scenario_str}) affecting "
            f"the following stages: {stage_str}. Evidence gathered by Neural Cleanse weight-space "
            f"inversion and STRIP run-time entropy analysis provides high-confidence confirmation "
            f"of active exploitation. The pipeline MUST NOT be used for operational inference "
            f"until a full forensic audit, model re-certification, and clean-room retraining "
            f"cycle have been completed and independently verified. Notify the security authority "
            f"and preserve all current artefacts for post-incident analysis."
        )
    elif overall_risk == RiskLevel.HIGH:
        return (
            f"HIGH RISK — OPERATIONAL SUSPENSION RECOMMENDED. Significant integrity violations "
            f"have been detected ({scenario_str}) across {stage_str}. While a confirmed "
            f"end-to-end exploit chain has not been fully established, the spectral signature "
            f"anomalies and runtime entropy deviations observed are inconsistent with benign "
            f"operational variance. Suspend deployment in mission-critical contexts pending "
            f"a targeted forensic review. Model re-validation against the certified training "
            f"checkpoint and a STRIP-guided clean-data sweep are the recommended immediate steps."
        )
    elif overall_risk == RiskLevel.MEDIUM:
        return (
            f"MEDIUM RISK — ELEVATED MONITORING ADVISED. The pipeline exhibits detectable "
            f"anomalies ({scenario_str}) that warrant investigation but do not yet constitute "
            f"confirmed adversarial exploitation. Distribution drift and perceptual-hash "
            f"deduplication findings suggest data quality and representativeness issues "
            f"that will degrade model generalisation over time. Recommend scheduling a "
            f"retraining cycle with cleaned and re-balanced data within the next maintenance "
            f"window. Increase STRIP monitoring frequency to hourly cadence until resolved."
        )
    else:
        return (
            "CLEAN STATE — PIPELINE CERTIFIED. All five stages of the PRAMAAN assurance "
            "pipeline have passed cryptographic integrity verification, spectral signature "
            "analysis, and STRIP run-time entropy monitoring within nominal thresholds. "
            "The audit chain is intact and tamper-evident. The model and inference pipeline "
            "are authorised for continued operational use. Scheduled re-verification is "
            "recommended within 30 days or following any model update event."
        )


@router.get("/generate", response_model=AssuranceReport)
def generate_report() -> AssuranceReport:
    """Generate a full structured assurance report reflecting current pipeline state."""
    scenarios = list(active_scenarios)
    raw_stages = build_stages(scenarios)

    report_stages = []
    all_risks = []
    all_confidences = []
    all_coverages = []

    for s in raw_stages:
        findings = [StageFinding(**f) for f in s["findings"]]
        report_stages.append(ReportStage(
            stage_name=s["stage_name"],
            risk=s["risk"],
            confidence=s["confidence"],
            findings=findings,
        ))
        all_risks.append(s["risk"])
        all_confidences.append(s["confidence"])
        all_coverages.append(s["coverage_pct"])

    overall_risk = _worst_risk(all_risks)
    overall_confidence = round(sum(all_confidences) / len(all_confidences), 3)
    overall_coverage = round(sum(all_coverages) / len(all_coverages), 1)

    # Audit chain is broken if any CRITICAL or HIGH stage exists unmitigated
    any_critical_unmitigated = any(
        f["mitigated"] is False
        for s in raw_stages
        for f in s["findings"]
        if s["risk"] in (RiskLevel.CRITICAL, RiskLevel.HIGH)
    )
    audit_chain_verified = not any_critical_unmitigated

    report_id_suffix = str(abs(hash(str(scenarios) + str(datetime.now(timezone.utc).date()))))[:4]
    report_id = f"PRAMAAN-{datetime.now(timezone.utc).year}-{report_id_suffix}"

    recommendation = _compose_recommendation(overall_risk, scenarios, raw_stages)

    return AssuranceReport(
        report_id=report_id,
        generated_at=datetime.now(timezone.utc),
        pipeline_summary=PipelineSummary(
            overall_risk=overall_risk,
            overall_confidence=overall_confidence,
            coverage_pct=overall_coverage,
        ),
        stages=report_stages,
        audit_chain_verified=audit_chain_verified,
        attack_scenarios_detected=scenarios,
        analyst_recommendation=recommendation,
    )
