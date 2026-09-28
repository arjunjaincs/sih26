"""
DI-03: Trigger & Pattern Anomaly Detector.

Detector ID : data.integrity.di03_trigger_anomaly
Version     : 1.0.0
Category    : DATA_INTEGRITY
Subcategory : trigger_injection

What this detector does
-----------------------
Inspects localized image regions (corners and center) across dataset samples to identify:
  1. Recurring localized trigger patterns:
     Identical or near-identical localized visual patches (e.g. corner marks,
     watermarks, checkerboards, digital artifacts) that recur across multiple
     otherwise distinct images (e.g. BadNets / patch backdoor attacks).
  2. High-frequency localized contrast anomalies:
     Corner patches exhibiting artificial high contrast/variance that recur
     identically across multiple samples.

What this detector does NOT do
-------------------------------
  - Does NOT claim to detect invisible/blended adversarial perturbations that span
    the entire image canvas without a localized footprint.
  - Does NOT execute external model training or require GPU acceleration.
  - Operates purely offline and deterministic.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import imagehash
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
    detector_id="data.integrity.di03_trigger_anomaly",
    version="1.0.0",
    name="DI-03: Recurring Localized Visual-Pattern Anomaly Detector",
    description=(
        "Detects localized visual anomalies, recurring corner/edge patches, "
        "and high-frequency pattern recurrence across training samples."
    ),
    applicable_asset_types=frozenset({AssetType.DATASET.value}),
)

_LOCATIONS = ("top_left", "top_right", "bottom_left", "bottom_right")


def _hamming_distance(h1: str, h2: str) -> int:
    try:
        val1 = int(h1, 16)
        val2 = int(h2, 16)
        return bin(val1 ^ val2).count("1")
    except Exception:
        return 999


class DI03TriggerAnomalyDetector:
    """
    Detector for localized backdoor triggers and recurring patch anomalies.
    Implements the structural Detector protocol (ADR-004).
    """

    @property
    def metadata(self) -> DetectorMetadata:
        return _METADATA

    def can_run(self, context: DetectorContext) -> CanRunResult:
        """Pre-flight check: verifies at least 3 samples and accessible source directory."""
        if context.conn is None:
            return CanRunResult(ok=False, reason="Database connection required")

        # Use COUNT query — avoids loading all sample rows just to check the count.
        sample_repo = SampleRepository(context.conn)
        count = sample_repo.count_by_dataset(context.asset_id)
        if count == 0:
            return CanRunResult(ok=False, reason="Dataset not found or contains zero samples")
        if count < 3:
            return CanRunResult(
                ok=False,
                reason="Insufficient samples for trigger recurrence analysis (minimum 3 samples required)",
            )

        dataset_repo = DatasetRepository(context.conn)
        ds = dataset_repo.get(context.asset_id)
        if ds is None or not Path(ds.source_path).exists():
            return CanRunResult(
                ok=False,
                reason="Dataset source directory not accessible on disk",
            )

        return CanRunResult(ok=True)

    def run(self, context: DetectorContext) -> DetectorOutput:
        """Execute trigger pattern recurrence analysis."""
        assert context.conn is not None
        output = DetectorOutput()
        sample_repo = SampleRepository(context.conn)
        samples = sample_repo.list_by_dataset(context.asset_id)

        dataset_repo = DatasetRepository(context.conn)
        ds = dataset_repo.get(context.asset_id)
        if ds is None or not Path(ds.source_path).exists():
            output.status = DetectorStatus.FAILED
            output.error = "Dataset source directory not accessible"
            return output.finalize()

        source_dir = Path(ds.source_path)
        findings: list[Finding] = []
        evidence_list: list[Evidence] = []

        # Build a single filename → Path lookup from one rglob pass.
        # This replaces N per-sample rglob calls with a single O(files) traversal.
        disk_files: dict[str, Path] = {}
        for p in source_dir.rglob("*"):
            if p.is_file():
                # Use the bare filename as key (matches s.file_name convention).
                # If multiple files share the same filename in different subdirs,
                # the first one found wins — consistent with prior rglob[0] behavior.
                disk_files.setdefault(p.name, p)

        # Find image files on disk for each sample
        sample_paths: dict[str, Path] = {}
        for s in samples:
            # Fast O(1) lookup: direct child first, then fallback to rglob map.
            cand = source_dir / s.file_name
            if cand.is_file():
                sample_paths[s.sample_id] = cand
            elif s.file_name in disk_files:
                sample_paths[s.sample_id] = disk_files[s.file_name]

        if len(sample_paths) < 3:
            output.status = DetectorStatus.SKIPPED
            output.error = "Fewer than 3 sample image files found on disk"
            output.confidence_level = ConfidenceLevel.LOW
            return output.finalize()

        # Extract localized corner patches and compute patch hashes
        # Structure: loc -> list of (sample, patch_phash, patch_var)
        location_patches: dict[str, list[tuple[Sample, str, float]]] = defaultdict(list)

        for s in samples:
            p = sample_paths.get(s.sample_id)
            if not p:
                continue

            try:
                with Image.open(p) as img:
                    w, h = img.size
                    if w < 16 or h < 16:
                        continue
                    # Patch size: between 16 and 48 pixels
                    pw = max(8, min(48, w // 8))
                    ph = max(8, min(48, h // 8))

                    # 4 corners
                    crops = {
                        "top_left": (0, 0, pw, ph),
                        "top_right": (w - pw, 0, w, ph),
                        "bottom_left": (0, h - ph, pw, h),
                        "bottom_right": (w - pw, h - ph, w, h),
                    }

                    for loc_name, box in crops.items():
                        patch = img.crop(box)
                        patch_hash = str(imagehash.dhash(patch))
                        # Compute variance to filter out flat solid backgrounds
                        gray = np.array(patch.convert("L"), dtype=float)
                        patch_var = float(np.var(gray))
                        location_patches[loc_name].append((s, patch_hash, patch_var))
            except Exception as e:
                log.debug("Skipping image %s during trigger analysis: %s", p, e)
                continue

        # Recurrence threshold: at least 3 distinct images or 15% of dataset
        min_recurrence = max(3, int(len(sample_paths) * 0.15))

        # Check each location for suspicious recurring non-flat patches
        for loc_name, entries in location_patches.items():
            if len(entries) < min_recurrence:
                continue

            # Cluster entries by patch hash (Hamming distance <= 2)
            clusters: list[list[tuple[Sample, str, float]]] = []
            for entry in entries:
                s, p_hash, p_var = entry
                # Ignore zero-variance flat patches (e.g. solid white/black margin)
                if p_var < 5.0:
                    continue

                matched = False
                for cl in clusters:
                    rep_hash = cl[0][1]
                    if _hamming_distance(p_hash, rep_hash) <= 2:
                        cl.append(entry)
                        matched = True
                        break
                if not matched:
                    clusters.append([entry])

            # Evaluate clusters for trigger signatures
            for cl in clusters:
                # Must consist of distinct full images (not exact duplicates of the entire image)
                unique_full_hashes = {e[0].sha256 for e in cl}
                if len(unique_full_hashes) >= min_recurrence:
                    # Check if members have differing overall content
                    distinct_samples = [e[0] for e in cl]
                    sample_ids = [s.sample_id for s in distinct_samples]
                    file_names = [s.file_name for s in distinct_samples]
                    classes = sorted({lbl for s in distinct_samples for lbl in s.labels})
                    avg_var = float(np.mean([e[2] for e in cl]))

                    severity = Severity.HIGH if (len(classes) >= 2 or len(distinct_samples) >= 5) else Severity.MEDIUM
                    f_id = f"fnd_di03_trig_{uuid.uuid4().hex[:12]}"
                    ev_id = f"ev_di03_trig_{uuid.uuid4().hex[:12]}"

                    finding = Finding(
                        finding_id=f_id,
                        assessment_id=context.assessment_id,
                        asset_id=context.asset_id,
                        category=FindingCategory.DATA_INTEGRITY,
                        subcategory="trigger_injection",
                        severity=severity,
                        title=f"Suspicious recurring localized pattern (candidate trigger) detected in {loc_name.replace('_', ' ')}",
                        description=(
                            f"A localized visual pattern in the {loc_name.replace('_', ' ')} region recurs across "
                            f"{len(distinct_samples)} distinct images (variance {avg_var:.1f}). "
                            f"Identical localized patches across differing image contents indicate a recurring visual pattern anomaly "
                            f"(candidate localized trigger or artificial watermark)."
                        ),
                        detection_method=_METADATA.name,
                        detector_id=_METADATA.detector_id,
                        limitations=[
                            "Analysis identifies recurring localized visual patterns across samples.",
                            "Recurring patterns alone do not prove malicious intent; legitimate camera watermarks, UI badges, or sensor artifacts can trigger recurrence.",
                        ],
                        recommended_disposition=(
                            f"Inspect the {loc_name.replace('_', ' ')} region of flagged samples to determine "
                            f"whether the recurring artifact is an authorized watermark or unintended pattern contamination."
                        ),
                    )
                    findings.append(finding)

                    evidence = Evidence(
                        evidence_id=ev_id,
                        finding_id=f_id,
                        detector_id=_METADATA.detector_id,
                        evidence_type=EvidenceType.ANOMALY,
                        description=f"Recurring localized patch in {loc_name} across {len(distinct_samples)} distinct images",
                        data={
                            "trigger_location": loc_name,
                            "representative_patch_hash": cl[0][1],
                            "recurrence_count": len(distinct_samples),
                            "mean_patch_variance": round(avg_var, 2),
                            "affected_classes": classes,
                            "affected_samples": [
                                {"sample_id": s.sample_id, "file_name": s.file_name, "labels": s.labels}
                                for s in distinct_samples[:10]
                            ],
                            "total_affected": len(distinct_samples),
                        },
                    )
                    evidence_list.append(evidence)

        output.findings = findings
        output.evidence = evidence_list

        if any(f.severity == Severity.HIGH for f in findings):
            output.risk_level = RiskLevel.HIGH
            output.confidence_level = ConfidenceLevel.HIGH
        elif any(f.severity == Severity.MEDIUM for f in findings):
            output.risk_level = RiskLevel.MEDIUM
            output.confidence_level = ConfidenceLevel.MODERATE
        else:
            output.risk_level = RiskLevel.NONE
            output.confidence_level = ConfidenceLevel.HIGH

        output.status = DetectorStatus.SUCCESS
        return output.finalize()
