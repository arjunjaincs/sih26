"""
DI-05: Contributor & Source Risk Aggregation.

Detector ID : data.integrity.di05_contributor_risk
Version     : 1.0.0
Category    : DATA_INTEGRITY
Subcategory : contributor_risk

What this detector does
-----------------------
When contributor or source group attribution is present in dataset metadata:
  1. Correlates all sample-level defects, near-duplicate floodings, label conflicts,
     and trigger anomalies across their contributing sources.
  2. Computes per-contributor defect rates:
       R_c = (flagged samples from contributor c) / (total samples from contributor c)
  3. Identifies contributors with disproportionately concentrated defects compared to
     the dataset baseline (candidate malicious or degraded pipeline contributor).

What this detector does NOT do
-------------------------------
  - Does NOT invent or synthesize contributor attribution when metadata is absent.
  - If attribution metadata is unavailable, explicitly returns SKIPPED with an
    unambiguous coverage gap explanation.
  - Operates purely offline and deterministic.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from typing import Any

from backend.detectors.base import (
    CanRunResult,
    Detector,
    DetectorContext,
    DetectorMetadata,
    DetectorOutput,
)
from backend.domain.entities import Evidence, Finding, Sample
from backend.domain.enums import (
    AssetType,
    ConfidenceLevel,
    DetectorStatus,
    EvidenceType,
    FindingCategory,
    RiskLevel,
    Severity,
)
from backend.infra.db import EvidenceRepository, FindingRepository, SampleRepository

log = logging.getLogger(__name__)

_METADATA = DetectorMetadata(
    detector_id="data.integrity.di05_contributor_risk",
    version="1.0.0",
    name="DI-05: Contributor/Source Anomaly Concentration Analysis",
    description=(
        "Aggregates sample-level defect and anomaly findings by contributor or source "
        "origin to identify statistical anomaly concentration across sources."
    ),
    applicable_asset_types=frozenset({AssetType.DATASET.value}),
)


class DI05ContributorRiskDetector:
    """
    Detector for aggregating multi-contributor pipeline risk.
    Implements the structural Detector protocol (ADR-004).
    """

    @property
    def metadata(self) -> DetectorMetadata:
        return _METADATA

    def can_run(self, context: DetectorContext) -> CanRunResult:
        """Pre-flight check: verifies dataset contains contributor attribution metadata."""
        if context.conn is None:
            return CanRunResult(ok=False, reason="Database connection required")

        sample_repo = SampleRepository(context.conn)
        samples = sample_repo.list_by_dataset(context.asset_id)
        if not samples:
            return CanRunResult(ok=False, reason="Dataset not found or contains zero samples")

        attributed = [s for s in samples if s.contributor and s.contributor.strip()]
        if not attributed:
            return CanRunResult(
                ok=False,
                reason="Dataset contains no contributor or source attribution metadata",
            )

        return CanRunResult(ok=True)

    def run(self, context: DetectorContext) -> DetectorOutput:
        """Execute contributor-level defect aggregation."""
        assert context.conn is not None
        output = DetectorOutput()
        sample_repo = SampleRepository(context.conn)
        samples = sample_repo.list_by_dataset(context.asset_id)

        attributed = [s for s in samples if s.contributor and s.contributor.strip()]
        if not attributed:
            output.status = DetectorStatus.SKIPPED
            output.error = "No contributor metadata found in dataset samples"
            output.confidence_level = ConfidenceLevel.LOW
            return output.finalize()

        # Group samples by contributor
        samples_by_contrib: dict[str, list[Sample]] = defaultdict(list)
        sample_to_contrib: dict[str, str] = {}
        for s in samples:
            contrib = s.contributor or "unattributed"
            samples_by_contrib[contrib].append(s)
            sample_to_contrib[s.sample_id] = contrib

        # Query all existing findings and evidence for this assessment
        finding_repo = FindingRepository(context.conn)
        evidence_repo = EvidenceRepository(context.conn)
        all_findings = finding_repo.list_by_assessment(context.assessment_id)

        # Collect flagged sample IDs across all findings
        flagged_sample_ids: set[str] = set()
        finding_categories_by_sample: dict[str, list[str]] = defaultdict(list)

        for f in all_findings:
            # Don't self-reference DI-05 findings if re-run
            if f.detector_id == _METADATA.detector_id:
                continue

            evs = evidence_repo.list_by_finding(f.finding_id)
            for ev in evs:
                d = ev.data or {}
                # Check various evidence formats for sample references
                if "sample_ids" in d and isinstance(d["sample_ids"], list):
                    for sid in d["sample_ids"]:
                        flagged_sample_ids.add(str(sid))
                        finding_categories_by_sample[str(sid)].append(f.subcategory or f.category.value)
                if "sample_id" in d:
                    sid = str(d["sample_id"])
                    flagged_sample_ids.add(sid)
                    finding_categories_by_sample[sid].append(f.subcategory or f.category.value)
                if "sample_1" in d and isinstance(d["sample_1"], dict) and "sample_id" in d["sample_1"]:
                    sid = str(d["sample_1"]["sample_id"])
                    flagged_sample_ids.add(sid)
                    finding_categories_by_sample[sid].append(f.subcategory or f.category.value)
                if "sample_2" in d and isinstance(d["sample_2"], dict) and "sample_id" in d["sample_2"]:
                    sid = str(d["sample_2"]["sample_id"])
                    flagged_sample_ids.add(sid)
                    finding_categories_by_sample[sid].append(f.subcategory or f.category.value)
                if "affected_samples" in d and isinstance(d["affected_samples"], list):
                    for it in d["affected_samples"]:
                        if isinstance(it, dict) and "sample_id" in it:
                            sid = str(it["sample_id"])
                            flagged_sample_ids.add(sid)
                            finding_categories_by_sample[sid].append(f.subcategory or f.category.value)

        # Compute contributor statistics
        total_flagged_all = len(flagged_sample_ids)
        total_samples_all = len(samples)
        overall_defect_rate = (total_flagged_all / total_samples_all) if total_samples_all > 0 else 0.0

        contrib_stats: dict[str, dict[str, Any]] = {}
        for contrib, c_samples in samples_by_contrib.items():
            c_sample_ids = {s.sample_id for s in c_samples}
            c_flagged = c_sample_ids.intersection(flagged_sample_ids)
            c_rate = (len(c_flagged) / len(c_sample_ids)) if c_sample_ids else 0.0

            # Collect categories
            cats: set[str] = set()
            for sid in c_flagged:
                cats.update(finding_categories_by_sample.get(sid, []))

            contrib_stats[contrib] = {
                "total_samples": len(c_samples),
                "flagged_samples": len(c_flagged),
                "defect_rate": c_rate,
                "issues": sorted(cats),
            }

        findings: list[Finding] = []
        evidence_list: list[Evidence] = []

        # Identify contributors with disproportionate risk
        for contrib, stats in contrib_stats.items():
            if contrib == "unattributed":
                continue

            n_c = stats["total_samples"]
            f_c = stats["flagged_samples"]
            r_c = stats["defect_rate"]

            # Anomaly condition: >= 2 flagged samples and >= 30% defect rate
            is_anomaly = (f_c >= 2 and r_c >= 0.30)
            if is_anomaly:
                severity = Severity.HIGH if (r_c >= 0.50 and f_c >= 3) else Severity.MEDIUM
                f_id = f"fnd_di05_risk_{uuid.uuid4().hex[:12]}"
                ev_id = f"ev_di05_risk_{uuid.uuid4().hex[:12]}"

                finding = Finding(
                    finding_id=f_id,
                    assessment_id=context.assessment_id,
                    asset_id=context.asset_id,
                    category=FindingCategory.DATA_INTEGRITY,
                    subcategory="contributor_risk",
                    severity=severity,
                    title=f"Disproportionate defect concentration from contributor '{contrib}'",
                    description=(
                        f"Contributor '{contrib}' contributed {n_c} samples, of which {f_c} "
                        f"({r_c:.1%}) were flagged with integrity issues (dataset average: {overall_defect_rate:.1%}). "
                        f"Observed issues: {', '.join(stats['issues']) if stats['issues'] else 'data anomalies'}."
                    ),
                    detection_method=_METADATA.name,
                    detector_id=_METADATA.detector_id,
                    limitations=[
                        "Attribution relies on metadata provided in annotations/directory structure.",
                        "Does not cryptographically prove malicious intent; may indicate a miscalibrated sensor or noisy source.",
                    ],
                    recommended_disposition=(
                        f"Quarantine and conduct thorough manual audit of all submissions from contributor '{contrib}'."
                    ),
                )
                findings.append(finding)

                evidence = Evidence(
                    evidence_id=ev_id,
                    finding_id=f_id,
                    detector_id=_METADATA.detector_id,
                    evidence_type=EvidenceType.STATISTICAL_TEST,
                    description=f"Contributor defect concentration: {contrib} ({f_c}/{n_c} flagged)",
                    data={
                        "contributor": contrib,
                        "total_contributed_samples": n_c,
                        "flagged_samples_count": f_c,
                        "contributor_defect_rate": round(r_c, 3),
                        "dataset_overall_defect_rate": round(overall_defect_rate, 3),
                        "observed_defect_types": stats["issues"],
                    },
                )
        # Attach global summary evidence record to primary finding if any findings exist
        if findings:
            summary_ev_id = f"ev_di05_summary_{uuid.uuid4().hex[:12]}"
            summary_evidence = Evidence(
                evidence_id=summary_ev_id,
                finding_id=findings[0].finding_id,
                detector_id=_METADATA.detector_id,
                evidence_type=EvidenceType.COMPARISON,
                description="Multi-contributor risk breakdown across all identified sources",
                data={
                    "total_contributors": len(contrib_stats),
                    "total_samples": total_samples_all,
                    "total_flagged_samples": total_flagged_all,
                    "overall_defect_rate": round(overall_defect_rate, 3),
                    "contributors": {
                        c: {
                            "samples": s["total_samples"],
                            "flagged": s["flagged_samples"],
                            "defect_rate": round(s["defect_rate"], 3),
                            "issues": s["issues"],
                        }
                        for c, s in contrib_stats.items()
                    },
                },
            )
            evidence_list.append(summary_evidence)

        output.findings = findings
        output.evidence = evidence_list

        if any(f.severity == Severity.HIGH for f in findings):
            output.risk_level = RiskLevel.HIGH
            output.confidence_level = ConfidenceLevel.HIGH
        elif any(f.severity == Severity.MEDIUM for f in findings):
            output.risk_level = RiskLevel.MEDIUM
            output.confidence_level = ConfidenceLevel.HIGH
        else:
            output.risk_level = RiskLevel.NONE
            output.confidence_level = ConfidenceLevel.HIGH

        output.status = DetectorStatus.SUCCESS
        return output.finalize()
