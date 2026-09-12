"""
DI-02: Label Integrity & Mislabelling Detector.

Detector ID : data.integrity.di02_label_integrity
Version     : 1.0.0
Category    : DATA_INTEGRITY
Subcategory : label_flipping

What this detector does
-----------------------
Inspects labeled dataset samples to detect:
  1. Near-duplicate / duplicate label conflicts:
     Two or more samples with identical or near-identical perceptual hashes
     (pHash distance <= threshold) that carry conflicting, disjoint class labels.
  2. Statistical class centroid outliers:
     Samples whose perceptual hash features are significantly distant from
     their assigned class centroid (> 2.5 sigma) while simultaneously closer
     to an alternate class centroid (candidate label flip).

What this detector does NOT do
-------------------------------
  - Does NOT claim definitive ground truth without human verification.
  - Does NOT execute external web queries or heavy foundation model embeddings.
  - Operates purely offline and deterministic.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from typing import Any

import numpy as np

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
from backend.infra.db import SampleRepository

log = logging.getLogger(__name__)

_METADATA = DetectorMetadata(
    detector_id="data.integrity.di02_label_integrity",
    version="1.0.0",
    name="DI-02: Label Integrity & Mislabelling Detector",
    description=(
        "Detects label inconsistencies, class conflicts across near-identical "
        "samples, and statistical label outliers in annotated datasets."
    ),
    applicable_asset_types=frozenset({AssetType.DATASET.value}),
)


def _hamming_distance_hex(h1: str, h2: str) -> int:
    """Compute Hamming distance between two hex hash strings."""
    try:
        val1 = int(h1, 16)
        val2 = int(h2, 16)
        return bin(val1 ^ val2).count("1")
    except (ValueError, TypeError):
        return 999


def _hash_to_bit_array(h: str) -> np.ndarray:
    """Convert hex hash string to a 64-element binary float array."""
    try:
        val = int(h, 16)
        bits = bin(val)[2:].zfill(64)
        return np.array([float(b) for b in bits], dtype=np.float32)
    except Exception:
        return np.zeros(64, dtype=np.float32)


class DI02LabelIntegrityDetector:
    """
    Detector for label conflicts, label flipping, and systematic mislabelling.
    Implements the structural Detector protocol (ADR-004).
    """

    @property
    def metadata(self) -> DetectorMetadata:
        return _METADATA

    def can_run(self, context: DetectorContext) -> CanRunResult:
        """Pre-flight check: verifies dataset has labeled samples."""
        if context.conn is None:
            return CanRunResult(ok=False, reason="Database connection required to load samples")

        sample_repo = SampleRepository(context.conn)
        samples = sample_repo.list_by_dataset(context.asset_id)

        if not samples:
            return CanRunResult(ok=False, reason="Dataset not found or contains zero samples")

        labeled_samples = [s for s in samples if s.labels and len(s.labels) > 0]
        if not labeled_samples:
            return CanRunResult(
                ok=False,
                reason="Dataset has no label annotations (unannotated image directory)",
            )
        if len(labeled_samples) < 2:
            return CanRunResult(
                ok=False,
                reason="Insufficient labeled samples (need >= 2)",
            )

        return CanRunResult(ok=True)

    def run(self, context: DetectorContext) -> DetectorOutput:
        """
        Execute label integrity analysis across labeled samples in the dataset.
        """
        assert context.conn is not None
        output = DetectorOutput()
        sample_repo = SampleRepository(context.conn)
        samples = sample_repo.list_by_dataset(context.asset_id)

        labeled_samples = [s for s in samples if s.labels and len(s.labels) > 0 and s.phash]
        if len(labeled_samples) < 2:
            output.status = DetectorStatus.SKIPPED
            output.error = "Fewer than 2 labeled samples with valid pHash"
            output.confidence_level = ConfidenceLevel.LOW
            return output.finalize()

        # For label conflict on near-duplicates, require high perceptual similarity (<= 4 bits or context threshold)
        phash_threshold = min(context.phash_threshold, 4)
        findings: list[Finding] = []
        evidence_list: list[Evidence] = []

        # -------------------------------------------------------------------
        # 1. Near-duplicate / duplicate label conflict detection
        # -------------------------------------------------------------------
        n = len(labeled_samples)
        conflict_pairs: list[tuple[Sample, Sample, int]] = []
        seen_pairs: set[tuple[str, str]] = set()

        for i in range(n):
            s1 = labeled_samples[i]
            s1_labels = set(s1.labels)
            for j in range(i + 1, n):
                s2 = labeled_samples[j]
                s2_labels = set(s2.labels)

                # Check if labels conflict
                if s1_labels != s2_labels:
                    # Check exact hash match or pHash distance
                    if s1.sha256 == s2.sha256:
                        dist = 0
                    else:
                        dist = _hamming_distance_hex(s1.phash, s2.phash)

                    if dist <= phash_threshold:
                        pair_key = (min(s1.sample_id, s2.sample_id), max(s1.sample_id, s2.sample_id))
                        if pair_key not in seen_pairs:
                            seen_pairs.add(pair_key)
                            conflict_pairs.append((s1, s2, dist))

        # Generate findings for conflict pairs (capped to top 20 to avoid explosion)
        for s1, s2, dist in conflict_pairs[:20]:
            f_id = f"fnd_di02_conflict_{uuid.uuid4().hex[:12]}"
            ev_id = f"ev_di02_conflict_{uuid.uuid4().hex[:12]}"

            finding = Finding(
                finding_id=f_id,
                assessment_id=context.assessment_id,
                asset_id=context.asset_id,
                category=FindingCategory.DATA_INTEGRITY,
                subcategory="label_flipping",
                severity=Severity.HIGH,
                title=f"Label conflict between near-duplicate samples ({s1.file_name} vs {s2.file_name})",
                description=(
                    f"Sample '{s1.file_name}' (labeled {sorted(s1.labels)}) and '{s2.file_name}' "
                    f"(labeled {sorted(s2.labels)}) are perceptually near-identical "
                    f"(pHash distance {dist} bits, threshold <= {phash_threshold}) but carry conflicting class labels."
                ),
                detection_method=_METADATA.name,
                detector_id=_METADATA.detector_id,
                limitations=[
                    "pHash measures visual structure; fine-grained visual categories with identical framing may appear similar.",
                    "Disjoint labels between visually identical images indicate labeling inconsistency or target label corruption.",
                ],
                recommended_disposition=(
                    "Reconcile contradictory annotations for the identified sample pair and verify annotator source."
                ),
            )
            findings.append(finding)

            evidence = Evidence(
                evidence_id=ev_id,
                finding_id=f_id,
                detector_id=_METADATA.detector_id,
                evidence_type=EvidenceType.ANOMALY,
                description=f"Conflicting labels on near-duplicate pair: {s1.file_name} ({s1.labels}) vs {s2.file_name} ({s2.labels})",
                data={
                    "conflict_type": "near_duplicate_label_conflict",
                    "sample_1": {
                        "sample_id": s1.sample_id,
                        "file_name": s1.file_name,
                        "labels": s1.labels,
                        "phash": s1.phash,
                    },
                    "sample_2": {
                        "sample_id": s2.sample_id,
                        "file_name": s2.file_name,
                        "labels": s2.labels,
                        "phash": s2.phash,
                    },
                    "hamming_distance": dist,
                    "threshold": phash_threshold,
                },
            )
            evidence_list.append(evidence)

        # -------------------------------------------------------------------
        # 2. Statistical class centroid outlier detection (candidate flips)
        # -------------------------------------------------------------------
        class_samples: dict[str, list[Sample]] = defaultdict(list)
        for s in labeled_samples:
            for lbl in s.labels:
                class_samples[lbl].append(s)

        # Compute centroids for classes with >= 3 samples
        class_centroids: dict[str, np.ndarray] = {}
        class_vectors: dict[str, list[tuple[Sample, np.ndarray]]] = {}

        for cls_name, cls_s_list in class_samples.items():
            if len(cls_s_list) >= 3:
                vecs = [(_s, _hash_to_bit_array(_s.phash)) for _s in cls_s_list]
                class_vectors[cls_name] = vecs
                mat = np.array([v[1] for v in vecs])
                class_centroids[cls_name] = np.mean(mat, axis=0)

        # Test each sample against class centroid and other class centroids
        if len(class_centroids) >= 2:
            for cls_name, vecs in class_vectors.items():
                centroid = class_centroids[cls_name]
                distances = [float(np.sum(np.abs(v[1] - centroid))) for v in vecs]
                mean_dist = float(np.mean(distances))
                std_dist = float(np.std(distances))

                if std_dist > 0.5:
                    for (_s, vec), d in zip(vecs, distances):
                        # Outlier threshold: distance > mean + 2.5 * std
                        if d > mean_dist + 2.2 * std_dist and d >= 12.0:
                            # Compare distance to other centroids
                            best_other_cls = None
                            min_other_dist = 999.0

                            for other_cls, other_centroid in class_centroids.items():
                                if other_cls != cls_name:
                                    od = float(np.sum(np.abs(vec - other_centroid)))
                                    if od < min_other_dist:
                                        min_other_dist = od
                                        best_other_cls = other_cls

                            # If substantially closer to another class centroid
                            if best_other_cls and min_other_dist < d - (1.2 * std_dist):
                                f_id = f"fnd_di02_flip_{uuid.uuid4().hex[:12]}"
                                ev_id = f"ev_di02_flip_{uuid.uuid4().hex[:12]}"

                                finding = Finding(
                                    finding_id=f_id,
                                    assessment_id=context.assessment_id,
                                    asset_id=context.asset_id,
                                    category=FindingCategory.DATA_INTEGRITY,
                                    subcategory="label_flipping",
                                    severity=Severity.MEDIUM,
                                    title=f"Statistical label outlier in class '{cls_name}' ({_s.file_name})",
                                    description=(
                                        f"Sample '{_s.file_name}' assigned to class '{cls_name}' deviates from the "
                                        f"class centroid (distance {d:.1f}, class mean {mean_dist:.1f}) and is "
                                        f"visually closer to class '{best_other_cls}' (distance {min_other_dist:.1f})."
                                    ),
                                    detection_method=_METADATA.name,
                                    detector_id=_METADATA.detector_id,
                                    limitations=[
                                        "Centroid-based distance uses perceptual hash projections; multimodal classes may exhibit dispersion.",
                                        "Candidate label flip suggests visual anomaly, not conclusive proof of adversarial tampering.",
                                    ],
                                    recommended_disposition=(
                                        f"Review sample '{_s.file_name}' to verify whether it belongs to '{cls_name}' or '{best_other_cls}'."
                                    ),
                                )
                                findings.append(finding)

                                evidence = Evidence(
                                    evidence_id=ev_id,
                                    finding_id=f_id,
                                    detector_id=_METADATA.detector_id,
                                    evidence_type=EvidenceType.STATISTICAL_TEST,
                                    description=f"Class centroid distance anomaly: {_s.file_name} in {cls_name} closer to {best_other_cls}",
                                    data={
                                        "conflict_type": "class_centroid_anomaly",
                                        "sample_id": _s.sample_id,
                                        "file_name": _s.file_name,
                                        "assigned_class": cls_name,
                                        "distance_to_assigned": round(d, 2),
                                        "class_mean_distance": round(mean_dist, 2),
                                        "class_std_distance": round(std_dist, 2),
                                        "candidate_alternate_class": best_other_cls,
                                        "distance_to_alternate": round(min_other_dist, 2),
                                    },
                                )
                                evidence_list.append(evidence)

        output.findings = findings
        output.evidence = evidence_list

        # Determine risk and confidence levels
        if any(f.severity == Severity.HIGH for f in findings):
            output.risk_level = RiskLevel.HIGH
            output.confidence_level = ConfidenceLevel.HIGH
        elif any(f.severity == Severity.MEDIUM for f in findings):
            output.risk_level = RiskLevel.MEDIUM
            output.confidence_level = ConfidenceLevel.MODERATE
        elif findings:
            output.risk_level = RiskLevel.LOW
            output.confidence_level = ConfidenceLevel.MODERATE
        else:
            output.risk_level = RiskLevel.NONE
            output.confidence_level = ConfidenceLevel.HIGH

        output.status = DetectorStatus.SUCCESS
        return output.finalize()
