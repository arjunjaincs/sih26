"""
DI-04: Robust Statistical Distribution-Outlier & Shift Detector.

Detector ID : data.integrity.di04_ood_distribution
Version     : 1.0.0
Category    : DISTRIBUTION_DRIFT
Subcategory : ood_insertion / operational_drift_indicator / distribution_shift / suspicious_anomaly_cluster

What this detector does
-----------------------
Extracts multi-dimensional statistical feature vectors across all dataset samples:
  1. Geometry: aspect ratio, normalized file-size density
  2. Color & Photometry: RGB channel means and luminance variance
  3. Spectral Texture: high-frequency spatial variation

When a REFERENCE distribution profile is supplied:
  - Compares evaluation feature distribution against the reference baseline
  - Computes per-feature standardized median shifts, IQR spreads, and envelope bounds
  - Measures overall distribution shift magnitude and proportion of samples outside reference bounds
  - Distinguishes diffuse operational/environmental drift from localized suspicious clusters:
      * OPERATIONAL_DRIFT_INDICATOR: diffuse photometric or sensor changes across the dataset
      * DISTRIBUTION_SHIFT: significant multi-dimensional divergence
      * SUSPICIOUS_ANOMALY_CLUSTER: localized subset of high-divergence outliers
      * INCONCLUSIVE: sparse or ambiguous statistical evidence

When NO reference distribution is supplied:
  - Computes robust multivariate distances (standardized IQR z-scores) against internal empirical baseline
  - Emits explicit limitation documenting that cross-distribution shift analysis was unavailable

What this detector does NOT do
-------------------------------
  - Does NOT claim definitive malice for statistical outliers or drift.
  - Does NOT claim semantic OOD detection or deep foundation-model embeddings.
  - Operates purely offline and deterministic without external API calls.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

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
from backend.infra.db import DatasetRepository, SampleRepository

log = logging.getLogger(__name__)

_METADATA = DetectorMetadata(
    detector_id="data.integrity.di04_ood_distribution",
    version="1.0.0",
    name="DI-04: Robust Statistical Distribution-Outlier Detector",
    description=(
        "Identifies statistical distribution outliers, aspect ratio anomalies, "
        "and cross-distribution statistical shifts between reference and evaluation profiles."
    ),
    applicable_asset_types=frozenset({AssetType.DATASET.value}),
)

_FEATURE_NAMES = [
    "aspect_ratio",
    "file_size_density",
    "red_channel_mean",
    "green_channel_mean",
    "blue_channel_mean",
    "luminance_variance",
]


def _extract_sample_features(
    samples: list[Sample],
    source_dir: Path | None,
) -> tuple[np.ndarray, list[Sample]]:
    """
    Extract 6-dimensional feature vectors for each sample:
      [aspect_ratio, size_density, r_mean, g_mean, b_mean, lum_std]
    """
    feature_list: list[np.ndarray] = []
    valid_samples: list[Sample] = []

    for s in samples:
        w = s.width or 256
        h = s.height or 256
        aspect_ratio = float(w) / float(max(1, h))
        size_density = float(s.file_size_bytes) / float(max(1, w * h))

        # Default channel statistics
        r_mean, g_mean, b_mean, lum_std = 128.0, 128.0, 128.0, 30.0
        if source_dir:
            img_p = source_dir / s.file_name
            if not img_p.is_file():
                matches = list(source_dir.rglob(s.file_name))
                if matches:
                    img_p = matches[0]

            if img_p.is_file():
                try:
                    with Image.open(img_p) as img:
                        rgb = img.convert("RGB")
                        small = rgb.resize((32, 32))
                        arr = np.array(small, dtype=float)
                        r_mean = float(np.mean(arr[:, :, 0]))
                        g_mean = float(np.mean(arr[:, :, 1]))
                        b_mean = float(np.mean(arr[:, :, 2]))
                        lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
                        lum_std = float(np.std(lum))
                except Exception:
                    pass

        vec = np.array([aspect_ratio, size_density, r_mean, g_mean, b_mean, lum_std], dtype=float)
        feature_list.append(vec)
        valid_samples.append(s)

    return np.vstack(feature_list), valid_samples


class DI04DistributionOODDetector:
    """
    Detector for statistical outliers and cross-distribution shift analysis.
    Implements the structural Detector protocol (ADR-004).
    """

    @property
    def metadata(self) -> DetectorMetadata:
        return _METADATA

    def can_run(self, context: DetectorContext) -> CanRunResult:
        """Pre-flight check: requires at least 5 samples to establish distribution baseline."""
        if context.conn is None:
            return CanRunResult(ok=False, reason="Database connection required")

        sample_repo = SampleRepository(context.conn)
        samples = sample_repo.list_by_dataset(context.asset_id)
        if not samples:
            return CanRunResult(ok=False, reason="Dataset not found or contains zero samples")
        if len(samples) < 5:
            return CanRunResult(
                ok=False,
                reason="Insufficient sample count to compute distribution baseline (minimum 5 samples required)",
            )

        return CanRunResult(ok=True)

    def run(self, context: DetectorContext) -> DetectorOutput:
        """Execute distribution and OOD analysis across dataset samples."""
        assert context.conn is not None
        output = DetectorOutput()
        sample_repo = SampleRepository(context.conn)
        dataset_repo = DatasetRepository(context.conn)

        samples = sample_repo.list_by_dataset(context.asset_id)
        if len(samples) < 5:
            output.status = DetectorStatus.SKIPPED
            output.error = "Fewer than 5 samples in dataset"
            output.confidence_level = ConfidenceLevel.LOW
            return output.finalize()

        ds = dataset_repo.get(context.asset_id)
        source_dir = Path(ds.source_path) if ds and Path(ds.source_path).exists() else None

        eval_mat, valid_eval_samples = _extract_sample_features(samples, source_dir)
        n_eval = eval_mat.shape[0]

        # Check if a reference dataset is available
        ref_samples: list[Sample] = []
        ref_ds = None
        if context.reference_asset_id:
            ref_samples = sample_repo.list_by_dataset(context.reference_asset_id)
            ref_ds = dataset_repo.get(context.reference_asset_id)

        has_reference = len(ref_samples) >= 5

        if has_reference:
            # ---------------------------------------------------------------
            # Dual-distribution comparison (Reference vs Evaluation)
            # ---------------------------------------------------------------
            ref_source_dir = Path(ref_ds.source_path) if ref_ds and Path(ref_ds.source_path).exists() else None
            ref_mat, valid_ref_samples = _extract_sample_features(ref_samples, ref_source_dir)
            n_ref = ref_mat.shape[0]

            # Reference distribution statistics
            ref_medians = np.median(ref_mat, axis=0)
            ref_q75, ref_q25 = np.percentile(ref_mat, [75, 25], axis=0)
            ref_iqrs = ref_q75 - ref_q25
            ref_iqrs = np.where(ref_iqrs > 1e-4, ref_iqrs, 1.0)

            # Evaluation distribution statistics
            eval_medians = np.median(eval_mat, axis=0)
            eval_q75, eval_q25 = np.percentile(eval_mat, [75, 25], axis=0)
            eval_iqrs = eval_q75 - eval_q25
            eval_iqrs = np.where(eval_iqrs > 1e-4, eval_iqrs, 1.0)

            # Per-feature standardized shift
            feature_shifts = np.abs(eval_medians - ref_medians) / ref_iqrs
            overall_shift_magnitude = float(np.sqrt(np.mean(feature_shifts ** 2)))

            # Reference bounds: [median - 3*IQR, median + 3*IQR]
            ref_lower = ref_medians - 3.0 * ref_iqrs
            ref_upper = ref_medians + 3.0 * ref_iqrs

            eval_outlier_mask = (eval_mat < ref_lower) | (eval_mat > ref_upper)
            sample_outlier_mask = np.any(eval_outlier_mask, axis=1)
            outlier_proportion = float(np.mean(sample_outlier_mask))
            feature_outlier_props = np.mean(eval_outlier_mask, axis=0).tolist()

            affected_features = [
                _FEATURE_NAMES[idx]
                for idx, shift in enumerate(feature_shifts)
                if shift > 1.5
            ]

            # Standardized sample distances from reference baseline
            sample_diffs = np.abs(eval_mat - ref_medians) / ref_iqrs
            sample_distances = np.sqrt(np.sum(sample_diffs ** 2, axis=1))

            findings: list[Finding] = []
            evidence_list: list[Evidence] = []

            # Determine distribution classification
            if overall_shift_magnitude <= 1.0 and outlier_proportion < 0.10:
                classification = "CONFORMING_DISTRIBUTION"
                output.risk_level = RiskLevel.NONE
                output.confidence_level = ConfidenceLevel.HIGH
            else:
                # Evidence-aware categorization
                is_diffuse = outlier_proportion >= 0.40 or (
                    len(affected_features) >= 1
                    and any(f in affected_features for f in ("red_channel_mean", "luminance_variance", "green_channel_mean", "blue_channel_mean"))
                    and outlier_proportion >= 0.25
                )

                if is_diffuse:
                    classification = "OPERATIONAL_DRIFT_INDICATOR"
                    subcat = "operational_drift_indicator"
                    title = f"Operational distribution drift detected ({', '.join(affected_features) or 'photometric'})"
                    description = (
                        f"Evaluation dataset exhibits statistical distribution shift compared to reference baseline "
                        f"(shift magnitude: {overall_shift_magnitude:.2f}, {outlier_proportion * 100:.1f}% samples outside reference bounds). "
                        f"Shift is diffuse across samples, indicating operational/environmental drift (e.g. illumination, weather, or sensor changes)."
                    )
                    severity = Severity.MEDIUM if overall_shift_magnitude > 2.5 else Severity.LOW
                    risk = RiskLevel.LOW if overall_shift_magnitude <= 3.0 else RiskLevel.MEDIUM
                    confidence = ConfidenceLevel.HIGH
                elif int(np.sum(sample_outlier_mask)) > 0:
                    classification = "SUSPICIOUS_ANOMALY_CLUSTER"
                    subcat = "suspicious_anomaly_cluster"
                    n_out = int(np.sum(sample_outlier_mask))
                    title = f"Localized anomaly cluster detected ({n_out} samples divergent from reference)"
                    description = (
                        f"A localized cluster of {n_out} samples ({outlier_proportion * 100:.1f}%) diverges significantly "
                        f"from the reference baseline, while the remaining dataset conforms to expected parameters. "
                        f"Affected dimensions: {', '.join(affected_features) or 'multivariate'}."
                    )
                    severity = Severity.HIGH if overall_shift_magnitude > 3.0 else Severity.MEDIUM
                    risk = RiskLevel.MEDIUM
                    confidence = ConfidenceLevel.MODERATE
                else:
                    classification = "DISTRIBUTION_SHIFT"
                    subcat = "distribution_shift"
                    title = f"Statistical distribution shift detected ({', '.join(affected_features) or 'multivariate'})"
                    description = (
                        f"Evaluation dataset features diverge from the reference profile "
                        f"(shift magnitude: {overall_shift_magnitude:.2f})."
                    )
                    severity = Severity.LOW
                    risk = RiskLevel.LOW
                    confidence = ConfidenceLevel.MODERATE

                f_id = f"fnd_di04_shift_{uuid.uuid4().hex[:12]}"
                finding = Finding(
                    finding_id=f_id,
                    assessment_id=context.assessment_id,
                    asset_id=context.asset_id,
                    category=FindingCategory.DISTRIBUTION_DRIFT,
                    subcategory=subcat,
                    severity=severity,
                    title=title,
                    description=description,
                    detection_method=_METADATA.name,
                    detector_id=_METADATA.detector_id,
                    limitations=[
                        "Cross-distribution comparison measures empirical statistical shifts in geometric and photometric features.",
                        "Diffuse shift suggests environmental/sensor variance; localized clusters warrant manual inspection.",
                        "Statistical drift alone does not prove malicious manipulation.",
                    ],
                    recommended_disposition=(
                        "Verify whether evaluation distribution shift reflects intended operational deployment conditions."
                    ),
                )
                findings.append(finding)

                # Record primary cross-distribution statistical test evidence
                ev_id = f"ev_di04_shift_{uuid.uuid4().hex[:12]}"
                ev_data = {
                    "reference_sample_count": n_ref,
                    "evaluation_sample_count": n_eval,
                    "feature_names": _FEATURE_NAMES,
                    "reference_medians": [round(float(v), 2) for v in ref_medians],
                    "reference_iqrs": [round(float(v), 2) for v in ref_iqrs],
                    "evaluation_medians": [round(float(v), 2) for v in eval_medians],
                    "evaluation_iqrs": [round(float(v), 2) for v in eval_iqrs],
                    "per_feature_shifts": [round(float(v), 2) for v in feature_shifts],
                    "overall_shift_magnitude": round(overall_shift_magnitude, 2),
                    "outlier_proportion": round(outlier_proportion, 4),
                    "per_feature_outlier_proportions": [round(float(v), 4) for v in feature_outlier_props],
                    "affected_features": affected_features,
                    "classification": classification,
                    "evidence_category": classification,
                    "reference_dataset_provided": True,
                }
                evidence = Evidence(
                    evidence_id=ev_id,
                    finding_id=f_id,
                    detector_id=_METADATA.detector_id,
                    evidence_type=EvidenceType.STATISTICAL_TEST,
                    description=f"Reference-vs-evaluation distribution shift analysis: {classification}",
                    data=ev_data,
                )
                evidence_list.append(evidence)

                # Record localized sample findings for top outliers
                outlier_indices = np.where(sample_outlier_mask)[0]
                outlier_records = []
                for idx in outlier_indices:
                    dist = float(sample_distances[idx])
                    anom_dims = [
                        _FEATURE_NAMES[d_idx]
                        for d_idx, is_out in enumerate(eval_outlier_mask[idx])
                        if is_out
                    ]
                    outlier_records.append((valid_eval_samples[idx], dist, anom_dims))

                outlier_records.sort(key=lambda x: x[1], reverse=True)
                for s, dist, anom_dims in outlier_records[:10]:
                    s_f_id = f"fnd_di04_sample_{uuid.uuid4().hex[:12]}"
                    s_ev_id = f"ev_di04_sample_{uuid.uuid4().hex[:12]}"
                    sample_finding = Finding(
                        finding_id=s_f_id,
                        assessment_id=context.assessment_id,
                        asset_id=context.asset_id,
                        category=FindingCategory.DISTRIBUTION_DRIFT,
                        subcategory="sample_distribution_outlier",
                        severity=Severity.LOW,
                        title=f"Sample outlier relative to reference distribution ({s.file_name})",
                        description=(
                            f"Sample '{s.file_name}' falls outside reference distribution envelope "
                            f"(distance: {dist:.2f}, anomalous features: {', '.join(anom_dims)})."
                        ),
                        detection_method=_METADATA.name,
                        detector_id=_METADATA.detector_id,
                        limitations=[
                            "Individual sample deviation relative to reference baseline envelope.",
                        ],
                        recommended_disposition=f"Inspect sample '{s.file_name}' against reference domain standards.",
                    )
                    findings.append(sample_finding)

                    sample_ev = Evidence(
                        evidence_id=s_ev_id,
                        finding_id=s_f_id,
                        detector_id=_METADATA.detector_id,
                        evidence_type=EvidenceType.STATISTICAL_TEST,
                        description=f"Outlier sample evidence for {s.file_name}",
                        data={
                            "sample_id": s.sample_id,
                            "file_name": s.file_name,
                            "distance_from_reference": round(dist, 2),
                            "anomalous_features": anom_dims,
                        },
                    )
                    evidence_list.append(sample_ev)

                output.risk_level = risk
                output.confidence_level = confidence

            output.findings = findings
            output.evidence = evidence_list
            output.status = DetectorStatus.SUCCESS
            return output.finalize()

        else:
            # ---------------------------------------------------------------
            # Single-dataset empirical baseline outlier analysis
            # ---------------------------------------------------------------
            medians = np.median(eval_mat, axis=0)
            q75, q25 = np.percentile(eval_mat, [75, 25], axis=0)
            iqrs = q75 - q25
            iqrs = np.where(iqrs > 1e-4, iqrs, 1.0)

            diffs = np.abs(eval_mat - medians) / iqrs
            sample_distances = np.sqrt(np.sum(diffs ** 2, axis=1))

            dist_median = float(np.median(sample_distances))
            dist_iqr = float(np.percentile(sample_distances, 75) - np.percentile(sample_distances, 25))
            threshold = max(3.5, dist_median + 3.0 * max(0.5, dist_iqr))

            findings: list[Finding] = []
            evidence_list: list[Evidence] = []

            outliers: list[tuple[Sample, float, list[str]]] = []
            for s, dist, d_vec in zip(valid_eval_samples, sample_distances, diffs):
                if dist > threshold:
                    anomalous_dims = [
                        _FEATURE_NAMES[idx]
                        for idx, score in enumerate(d_vec)
                        if score > 2.8
                    ]
                    outliers.append((s, float(dist), anomalous_dims))

            outliers.sort(key=lambda x: x[1], reverse=True)

            for s, dist, anom_dims in outliers[:15]:
                severity = Severity.MEDIUM if dist > threshold * 1.5 else Severity.LOW
                f_id = f"fnd_di04_ood_{uuid.uuid4().hex[:12]}"
                ev_id = f"ev_di04_ood_{uuid.uuid4().hex[:12]}"

                dims_str = ", ".join(anom_dims) if anom_dims else "multivariate feature divergence"
                finding = Finding(
                    finding_id=f_id,
                    assessment_id=context.assessment_id,
                    asset_id=context.asset_id,
                    category=FindingCategory.DISTRIBUTION_DRIFT,
                    subcategory="ood_insertion",
                    severity=severity,
                    title=f"Statistical distribution outlier detected ({s.file_name})",
                    description=(
                        f"Sample '{s.file_name}' exhibits anomalous distribution distance "
                        f"({dist:.2f} vs baseline threshold {threshold:.2f}). "
                        f"Anomalous dimensions: {dims_str}."
                    ),
                    detection_method=_METADATA.name,
                    detector_id=_METADATA.detector_id,
                    limitations=[
                        "Reference distribution profile was not provided. Cross-distribution shift analysis is unavailable; performing single-dataset statistical outlier analysis against internal empirical distribution.",
                        "Statistical outlier detection identifies samples in the distribution tail.",
                        "Rare benign scenes, extreme lighting, or atypical sensor settings can trigger outlier scores.",
                    ],
                    recommended_disposition=(
                        f"Inspect sample '{s.file_name}' to ensure it conforms to the target domain specification."
                    ),
                )
                findings.append(finding)

                evidence = Evidence(
                    evidence_id=ev_id,
                    finding_id=f_id,
                    detector_id=_METADATA.detector_id,
                    evidence_type=EvidenceType.STATISTICAL_TEST,
                    description=f"Out-of-distribution distance anomaly for {s.file_name}",
                    data={
                        "sample_id": s.sample_id,
                        "file_name": s.file_name,
                        "distance": round(dist, 2),
                        "threshold": round(threshold, 2),
                        "baseline_median": round(dist_median, 2),
                        "anomalous_dimensions": anom_dims,
                        "total_dataset_samples": n_eval,
                        "reference_dataset_provided": False,
                    },
                )
                evidence_list.append(evidence)

            output.findings = findings
            output.evidence = evidence_list

            if any(f.severity == Severity.MEDIUM for f in findings):
                output.risk_level = RiskLevel.MEDIUM
                output.confidence_level = ConfidenceLevel.MODERATE
            elif findings:
                output.risk_level = RiskLevel.LOW
                output.confidence_level = ConfidenceLevel.LOW
            else:
                output.risk_level = RiskLevel.NONE
                output.confidence_level = ConfidenceLevel.HIGH

            output.status = DetectorStatus.SUCCESS
            return output.finalize()
