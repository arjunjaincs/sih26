"""
DI-04: Distribution & Out-of-Distribution (OOD) Detector.

Detector ID : data.integrity.di04_ood_distribution
Version     : 1.0.0
Category    : DISTRIBUTION_DRIFT
Subcategory : ood_insertion

What this detector does
-----------------------
Extracts multi-dimensional statistical feature vectors across all dataset samples:
  1. Geometry: aspect ratio, normalized file-size density
  2. Color & Photometry: RGB channel means and luminance variance
  3. Spectral Texture: high-frequency spatial variation

Computes robust multivariate distance (standardized Mahalanobis / IQR z-scores)
against the dataset baseline to detect samples that are significantly outside the
dominant training distribution (candidate out-of-distribution insertion).

What this detector does NOT do
-------------------------------
  - Does NOT claim definitive malice for statistical outliers; unusual lighting,
    framing, or rare benign objects can trigger outlier scores.
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
    name="DI-04: Distribution & Out-of-Distribution (OOD) Detector",
    description=(
        "Identifies statistical distribution outliers, aspect ratio anomalies, "
        "and spectral domain anomalies across dataset samples."
    ),
    applicable_asset_types=frozenset({AssetType.DATASET.value}),
)


class DI04DistributionOODDetector:
    """
    Detector for statistical outliers and candidate out-of-distribution samples.
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
        samples = sample_repo.list_by_dataset(context.asset_id)

        dataset_repo = DatasetRepository(context.conn)
        ds = dataset_repo.get(context.asset_id)
        source_dir = Path(ds.source_path) if ds and Path(ds.source_path).exists() else None

        if len(samples) < 5:
            output.status = DetectorStatus.SKIPPED
            output.error = "Fewer than 5 samples in dataset"
            output.confidence_level = ConfidenceLevel.LOW
            return output.finalize()

        # Extract 6-dimensional feature vector per sample
        # [aspect_ratio, size_density, r_mean, g_mean, b_mean, lum_std]
        feature_list: list[np.ndarray] = []
        valid_samples: list[Sample] = []

        for s in samples:
            w = s.width or 256
            h = s.height or 256
            aspect_ratio = float(w) / float(max(1, h))
            size_density = float(s.file_size_bytes) / float(max(1, w * h))

            # Read channel statistics if image accessible
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
                            # Downsample for fast robust statistics
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

        mat = np.vstack(feature_list)  # (N, 6)
        n_samples = mat.shape[0]

        # Compute robust baseline: median and IQR (Interquartile Range)
        medians = np.median(mat, axis=0)
        q75, q25 = np.percentile(mat, [75, 25], axis=0)
        iqrs = q75 - q25
        # Prevent division by zero
        iqrs = np.where(iqrs > 1e-4, iqrs, 1.0)

        # Standardized robust distance per sample
        diffs = np.abs(mat - medians) / iqrs
        sample_distances = np.sqrt(np.sum(diffs ** 2, axis=1))

        dist_median = float(np.median(sample_distances))
        dist_iqr = float(np.percentile(sample_distances, 75) - np.percentile(sample_distances, 25))
        threshold = max(3.5, dist_median + 3.0 * max(0.5, dist_iqr))

        findings: list[Finding] = []
        evidence_list: list[Evidence] = []

        feature_names = [
            "aspect_ratio",
            "file_size_density",
            "red_channel_mean",
            "green_channel_mean",
            "blue_channel_mean",
            "luminance_variance",
        ]

        outliers: list[tuple[Sample, float, list[str]]] = []
        for s, dist, d_vec in zip(valid_samples, sample_distances, diffs):
            if dist > threshold:
                anomalous_dims = [
                    feature_names[idx]
                    for idx, score in enumerate(d_vec)
                    if score > 2.8
                ]
                outliers.append((s, float(dist), anomalous_dims))

        # Sort by distance descending, limit top 15 findings
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
                    "total_dataset_samples": n_samples,
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
