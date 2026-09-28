"""
PRAMAAN v1  --  Assurance Report Data Extractor.

Extracts and normalizes assessment data from SQLite repositories or live
AssessmentResult objects into the canonical AssuranceReportData container.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.api.errors import AssessmentNotFound
from backend.assessment.models import AssessmentResult, CoverageGapRecord
from backend.domain.enums import (
    AssetType,
    ConfidenceLevel,
    DetectorStatus,
    FindingCategory,
    RiskLevel,
    Severity,
)
from backend.infra.db import (
    AssessmentRepository,
    AssetRepository,
    AuditPayloadRepository,
    AuditRepository,
    DatasetRepository,
    DetectorResultRepository,
    EvidenceRepository,
    FindingRepository,
    ModelArtifactRepository,
    ProvenanceRepository,
)
from backend.reporting.formatting import censor_paths, generate_recommendation
from backend.reporting.models import (
    AssuranceReportData,
    ReportAssessmentMeta,
    ReportAssetItem,
    ReportAuditItem,
    ReportCoverageGapItem,
    ReportDetectorItem,
    ReportEvidenceItem,
    ReportFindingItem,
    ReportProvenanceItem,
)

# Canonical 11-detector battery definitions
BATTERY_DETECTORS = [
    # Data Integrity
    ("data.integrity.di01_duplicates", "DI-01: Near & Exact Duplicates", "DATA_INTEGRITY"),
    ("data.integrity.di02_label_integrity", "DI-02: Systematic Mislabelling", "DATA_INTEGRITY"),
    ("data.integrity.di03_trigger_anomaly", "DI-03: Recurring Localized Visual-Pattern Anomalies", "DATA_INTEGRITY"),
    ("data.integrity.di04_ood_distribution", "DI-04: Robust Statistical Distribution Outliers & Shift", "DATA_INTEGRITY"),
    ("data.integrity.di05_contributor_risk", "DI-05: Contributor Anomaly Concentration", "DATA_INTEGRITY"),
    # Model Integrity
    ("model.integrity.mi01_fingerprint", "MI-01: Cryptographic Fingerprint", "MODEL_INTEGRITY"),
    ("model.integrity.mi02_parameter_stats", "MI-02: Parameter Numerical Stats", "MODEL_INTEGRITY"),
    ("model.integrity.mi03_activation_stats", "MI-03: Layer Activation Profiles", "MODEL_INTEGRITY"),
    ("model.integrity.mi04_reference_comparison", "MI-04: Reference Differential", "MODEL_INTEGRITY"),
    ("model.integrity.mi05_trigger_anomaly", "MI-05: Suspicious Trigger-Like Behavioral Convergence", "MODEL_INTEGRITY"),
    # Inference / Provenance
    ("inference.provenance.pi01_integrity", "PI-01: Cryptographic Provenance Integrity", "INFERENCE_PROVENANCE"),
]


def extract_report_data_from_db(
    conn: sqlite3.Connection,
    assessment_id: str,
) -> AssuranceReportData:
    """
    Assemble AssuranceReportData from SQLite database repositories.

    Raises:
      AssessmentNotFound: If the assessment_id does not exist.
    """
    asmt_repo = AssessmentRepository(conn)
    record = asmt_repo.get(assessment_id)
    if record is None:
        raise AssessmentNotFound(assessment_id)

    # 1. Audit events & payload lookup
    audit_repo = AuditRepository(conn)
    payload_repo = AuditPayloadRepository(conn)
    events = audit_repo.list_by_assessment(assessment_id)
    event_ids = [e.event_id for e in events]
    payloads = payload_repo.get_all_for_events(event_ids)

    complete_payload: dict[str, Any] = {}
    for ev in reversed(events):
        if ev.event_type.value in ("assessment_complete", "assessment_failed"):
            complete_payload = payloads.get(ev.event_id, {})
            break

    # 2. Findings & Evidence
    finding_repo = FindingRepository(conn)
    evidence_repo = EvidenceRepository(conn)
    db_findings = finding_repo.list_by_assessment(assessment_id)

    report_findings: list[ReportFindingItem] = []
    max_risk_str = complete_payload.get("overall_risk")
    has_high = False
    has_med = False

    for f in db_findings:
        db_ev_list = evidence_repo.list_by_finding(f.finding_id)
        report_ev_list = [
            ReportEvidenceItem(
                evidence_id=e.evidence_id,
                detector_id=e.detector_id,
                evidence_type=e.evidence_type.value,
                description=censor_paths(e.description),
                data=e.data,
            )
            for e in db_ev_list
        ]

        if f.severity in (Severity.HIGH, Severity.CRITICAL):
            has_high = True
        elif f.severity == Severity.MEDIUM:
            has_med = True

        report_findings.append(
            ReportFindingItem(
                finding_id=f.finding_id,
                asset_id=f.asset_id,
                detector_id=f.detector_id,
                category=f.category.value,
                subcategory=f.subcategory,
                severity=f.severity.value,
                title=f.title,
                description=censor_paths(f.description),
                limitations=[censor_paths(lim) for lim in f.limitations],
                recommended_disposition=f.recommended_disposition,
                evidence=report_ev_list,
            )
        )

    # Risk fallback if audit payload missing
    if not max_risk_str:
        if has_high:
            max_risk_str = "HIGH"
        elif has_med:
            max_risk_str = "MEDIUM"
        else:
            max_risk_str = "NONE"

    confidence_str = complete_payload.get("overall_confidence", "HIGH")
    coverage_fraction = float(complete_payload.get("coverage_fraction", 1.0))

    # 3. Assets
    asset_repo = AssetRepository(conn)
    dataset_repo = DatasetRepository(conn)
    model_repo = ModelArtifactRepository(conn)

    db_assets = asset_repo.list_by_assessment(assessment_id)
    report_assets: list[ReportAssetItem] = []

    for a in db_assets:
        fmt = None
        details: dict[str, Any] = {}
        if a.asset_type == AssetType.DATASET:
            ds = dataset_repo.get(a.asset_id)
            if ds:
                fmt = ds.format.value
                details["sample_count"] = ds.sample_count
                details["class_names"] = ds.class_names
        elif a.asset_type == AssetType.MODEL:
            m = model_repo.get(a.asset_id)
            if m:
                fmt = m.framework
                details["access_level"] = m.access_level.value
        report_assets.append(
            ReportAssetItem(
                asset_id=a.asset_id,
                asset_type=a.asset_type.value,
                name=censor_paths(a.name),
                sha256=a.sha256,
                size_bytes=a.size_bytes,
                format=fmt,
                details=details,
            )
        )

    # 4. Detector results & Battery alignment
    det_repo = DetectorResultRepository(conn)
    db_det_results = det_repo.list_by_assessment(assessment_id)
    det_map = {r.detector_id: r for r in db_det_results}

    report_detectors: list[ReportDetectorItem] = []
    for did, dname, cat in BATTERY_DETECTORS:
        if did in det_map:
            r = det_map[did]
            report_detectors.append(
                ReportDetectorItem(
                    detector_id=did,
                    detector_name=dname,
                    category=cat,
                    status=r.status.value,
                    risk_level="HIGH" if any(f.detector_id == did and f.severity in (Severity.HIGH, Severity.CRITICAL) for f in db_findings) else ("MEDIUM" if any(f.detector_id == did and f.severity == Severity.MEDIUM for f in db_findings) else "NONE"),
                    confidence_level="HIGH",
                    findings_count=r.findings_count,
                    evidence_count=r.evidence_count,
                    error=r.error,
                )
            )
        else:
            report_detectors.append(
                ReportDetectorItem(
                    detector_id=did,
                    detector_name=dname,
                    category=cat,
                    status="NOT_APPLICABLE",
                    risk_level="NONE",
                    confidence_level="HIGH",
                    findings_count=0,
                    evidence_count=0,
                    error=None,
                )
            )

    # 5. Coverage gaps & Limitations
    coverage_gaps: list[ReportCoverageGapItem] = []
    limitations: list[str] = []

    for f in db_findings:
        if f.subcategory == "coverage_gap":
            coverage_gaps.append(
                ReportCoverageGapItem(
                    detector_id=f.detector_id,
                    detector_name=f.detection_method,
                    reason=f.title,
                    required_capability="Complete artifact binding or runtime framework",
                    observed_capability="Restricted or partial observation scope",
                    impact="Full cryptographic or operational assurance cannot be asserted",
                    recommended_action=f.recommended_disposition or "Provide complete artifact bindings",
                )
            )
        if f.limitations:
            for lim in f.limitations:
                c_lim = censor_paths(lim)
                if c_lim not in limitations:
                    limitations.append(c_lim)

    # 6. Provenance manifests
    prov_repo = ProvenanceRepository(conn)
    prov_manifests = prov_repo.list_by_assessment(assessment_id)
    report_prov: ReportProvenanceItem | None = None

    if prov_manifests:
        pm = prov_manifests[0]
        sig_stat = "VERIFIED"
        rep_stat = "CLEAN"
        anomalies: list[str] = []

        for f in db_findings:
            if f.subcategory == "signature_invalid":
                sig_stat = "FAILED"
            elif f.subcategory in ("input_mismatch", "model_mismatch", "output_mismatch"):
                sig_stat = "BINDING_MISMATCH"
            elif f.subcategory == "replay_detected":
                rep_stat = "ANOMALY_DETECTED"
                anomalies.append(f.title)

        report_prov = ReportProvenanceItem(
            manifest_id=pm.manifest_id,
            assessment_id=pm.assessment_id,
            input_sha256=pm.input_sha256,
            model_sha256=pm.model_sha256,
            output_sha256=pm.output_sha256,
            preprocessing_config=pm.preprocessing_config,
            inference_config=pm.inference_config,
            timestamp_utc=pm.timestamp_utc,
            nonce=pm.nonce,
            sequence=pm.sequence,
            digest=pm.digest,
            signature_status=sig_stat,
            replay_status=rep_stat,
            anomalies=anomalies,
        )

    # 7. Audit verification
    from backend.audit.verifier import ChainVerifier
    chain_res = ChainVerifier(audit_repo, payload_repo).verify_assessment(assessment_id)
    report_audit = ReportAuditItem(
        chain_valid=chain_res.valid,
        events_checked=chain_res.events_checked,
        first_invalid_event_id=chain_res.first_invalid_event_id,
        failures=[str(f) for f in chain_res.failures],
        first_event_hash=events[0].current_hash if events else None,
        last_event_hash=events[-1].current_hash if events else None,
        events=[
            {
                "event_id": e.event_id,
                "event_type": e.event_type.value,
                "timestamp_utc": e.timestamp_utc,
                "actor": e.actor,
                "current_hash": e.current_hash,
                "previous_hash": e.previous_hash,
            }
            for e in events[:20]  # First 20 events in timeline
        ],
    )

    # 8. Recommendation
    rec_disp, rec_rationale = generate_recommendation(
        overall_risk=max_risk_str,
        overall_confidence=confidence_str,
        coverage_fraction=coverage_fraction,
        findings_count=len(db_findings),
        audit_valid=chain_res.valid,
    )

    meta = ReportAssessmentMeta(
        assessment_id=record.assessment_id,
        title=censor_paths(record.title),
        status=record.state.value,
        software_version=record.software_version or "1.0.0",
        created_at=record.created_at.isoformat(),
        started_at=record.started_at.isoformat() if record.started_at else None,
        completed_at=record.completed_at.isoformat() if record.completed_at else None,
        overall_risk=max_risk_str.upper(),
        risk_qualitative=f"Evaluated risk level: {max_risk_str.upper()}",
        overall_confidence=confidence_str.upper(),
        confidence_qualifier=f"Evidence confidence: {confidence_str.upper()}",
        coverage_fraction=coverage_fraction,
        error=record.error,
    )

    return AssuranceReportData(
        meta=meta,
        assets=report_assets,
        detectors=report_detectors,
        findings=report_findings,
        coverage_gaps=coverage_gaps,
        limitations=limitations,
        provenance=report_prov,
        audit=report_audit,
        recommended_disposition=rec_disp,
        disposition_rationale=rec_rationale,
        generated_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        report_schema_version="1.0.0",
    )


def extract_report_data_from_result(
    result: AssessmentResult,
    conn: sqlite3.Connection | None = None,
) -> AssuranceReportData:
    """
    Assemble AssuranceReportData directly from an in-memory AssessmentResult.
    Falls back to database when connection is provided for rich details.
    """
    if conn is not None:
        try:
            return extract_report_data_from_db(conn, result.assessment_id)
        except Exception:
            pass

    # Direct conversion from dataclass
    meta = ReportAssessmentMeta(
        assessment_id=result.assessment_id,
        title=censor_paths(result.title),
        status=result.status.value,
        software_version="1.0.0",
        created_at=result.started_at.isoformat(),
        started_at=result.started_at.isoformat(),
        completed_at=result.completed_at.isoformat() if result.completed_at else None,
        overall_risk=result.overall_risk.value.upper(),
        risk_qualitative=result.risk_qualitative,
        overall_confidence=result.overall_confidence.value.upper(),
        confidence_qualifier=result.confidence_qualifier,
        coverage_fraction=result.coverage_fraction,
        error=result.error,
    )

    report_detectors: list[ReportDetectorItem] = []
    executed_ids = set(result.detectors_executed)
    run_records = {r.detector_id: r for r in result.detector_runs}

    for did, dname, cat in BATTERY_DETECTORS:
        if did in run_records:
            r = run_records[did]
            st = "SUCCESS" if r.ran else ("NOT_APPLICABLE" if not r.applicable else "FAILED")
            report_detectors.append(
                ReportDetectorItem(
                    detector_id=did,
                    detector_name=dname,
                    category=cat,
                    status=st,
                    risk_level=r.risk_level.value.upper() if hasattr(r.risk_level, "value") else str(r.risk_level).upper(),
                    confidence_level=r.confidence_level.value.upper() if hasattr(r.confidence_level, "value") else str(r.confidence_level).upper(),
                    findings_count=r.findings_count,
                    evidence_count=r.evidence_count,
                    error=r.error,
                )
            )
        else:
            report_detectors.append(
                ReportDetectorItem(
                    detector_id=did,
                    detector_name=dname,
                    category=cat,
                    status="NOT_APPLICABLE",
                    risk_level="NONE",
                    confidence_level="HIGH",
                    findings_count=0,
                    evidence_count=0,
                    error=None,
                )
            )

    rec_disp, rec_rationale = generate_recommendation(
        overall_risk=result.overall_risk.value,
        overall_confidence=result.overall_confidence.value,
        coverage_fraction=result.coverage_fraction,
        findings_count=result.findings_count,
        audit_valid=result.audit_chain_valid,
    )

    coverage_gaps = [
        ReportCoverageGapItem(
            detector_id=g.detector_id,
            detector_name=g.detector_name,
            reason=g.reason,
            required_capability=g.required_capability,
            observed_capability=g.observed_capability,
            impact=g.impact,
            recommended_action=g.recommended_action,
        )
        for g in result.coverage_gaps
    ]

    return AssuranceReportData(
        meta=meta,
        assets=[
            ReportAssetItem(
                asset_id=aid,
                asset_type="evaluated_asset",
                name=f"asset_{aid[:8]}",
                sha256="N/A",
                size_bytes=0,
            )
            for aid in result.assets_analyzed
        ],
        detectors=report_detectors,
        findings=[],
        coverage_gaps=coverage_gaps,
        limitations=[censor_paths(l) for l in result.limitations],
        provenance=None,
        audit=ReportAuditItem(
            chain_valid=result.audit_chain_valid if result.audit_chain_valid is not None else True,
            events_checked=1,
        ),
        recommended_disposition=rec_disp,
        disposition_rationale=rec_rationale,
        generated_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        report_schema_version="1.0.0",
    )
