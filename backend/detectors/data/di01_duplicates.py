"""
DI-01: Duplicate and Near-Duplicate Image Detector.

Detector ID : data.integrity.di01_duplicates
Version     : 1.0.0
Category    : DATA_INTEGRITY
Subcategory : duplicate_flooding

What this detector does
-----------------------
Scans the stored fingerprints (sha256, phash, dhash) for all samples in a
dataset and identifies:

  1. EXACT duplicates   — two or more samples with identical SHA-256 values.
     Exact equality means byte-identical files.  This is a hard fact, not
     a suspicion.

  2. NEAR-DUPLICATES    — two or more samples whose perceptual hash (pHash)
     Hamming distance is ≤ phash_threshold.  This is a candidate relationship.
     Near-duplicates might be legitimate augmentations, watermark variants, or
     actual flooding.  This detector only reports the observation; interpretation
     is left to the analyst.

What this detector does NOT do
-------------------------------
  - It does NOT claim duplicates are "poisoning" or "malicious".
  - It does NOT produce contributor risk scores.
  - It does NOT run embeddings or CLIP.
  - It does NOT generate a global trust score.

Algorithm
---------
EXACT:
  Group samples by sha256.  Groups with size >= 2 are exact-duplicate clusters.
  Cost: O(n) with a dictionary.

NEAR-DUPLICATE:
  For each pair (i, j) with i < j, compute Hamming distance between pHash
  values.  If distance <= threshold, record them as a candidate pair.
  Then group connected pairs into clusters using union-find.
  Cost: O(n²) in the worst case.

  V1 Rationale: For demo-scale datasets (≤ 10,000 samples), O(n²) is
  acceptable.  The implementation is isolated in _build_near_duplicate_groups()
  so it can be replaced with a BK-tree or LSH approach later without touching
  the rest of the detector.

Threshold
---------
Default phash_threshold = 10 bits Hamming distance (out of 64 bits).
Rationale: imagehash research and standard practice suggest:
  - 0 bits  → identical (but we already catch these via SHA-256)
  - 1–5     → near-identical; very likely the same image
  - 6–10    → perceptually similar; plausible near-duplicate candidate
  - 11–20   → loosely similar; might share subject/composition
  - >20     → different images
10 bits is a conservative starting point for V1.  The threshold is
caller-configurable via DetectorContext.

Risk/Confidence semantics
--------------------------
  Exact duplicates  → RiskLevel.MEDIUM (MODERATE confidence if many)
  Near-duplicates   → RiskLevel.LOW    (LOW confidence — candidates only)
  No duplicates     → RiskLevel.NONE   (HIGH confidence — we checked all)
  Insufficient data (< 2 samples or missing hashes) → RiskLevel.NONE,
                                                       ConfidenceLevel.LOW

  Risk and confidence are always separate (ADR-003).

Evidence schema (data dict keys)
----------------------------------
For each finding, one Evidence item of type CLUSTER is attached:

  cluster_type       : "exact" | "near_duplicate"
  cluster_size       : int — number of samples in the group
  representative_hash: str — the shared SHA-256 (exact) or seed pHash
  phash_threshold    : int — threshold used (near-duplicate only)
  max_hamming_distance: int — worst-case distance seen in cluster (near-dup)
  sample_ids         : list[str] — sample_ids of all members
  file_names         : list[str] — file_names for analyst readability
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

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

# ---------------------------------------------------------------------------
# Detector identity
# ---------------------------------------------------------------------------

_METADATA = DetectorMetadata(
    detector_id="data.integrity.di01_duplicates",
    version="1.0.0",
    name="DI-01: Duplicate / Near-Duplicate Image Detector",
    description=(
        "Detects byte-identical images (via SHA-256) and perceptually similar "
        "near-duplicate candidates (via pHash Hamming distance). "
        "Evidence of duplicate flooding; does not classify as malicious."
    ),
    applicable_asset_types=frozenset({AssetType.DATASET.value}),
)

# ---------------------------------------------------------------------------
# Union-Find for cluster grouping
# ---------------------------------------------------------------------------

class _UnionFind:
    """Minimal union-find (disjoint set) for clustering near-duplicates."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        if x not in self._parent:
            self._parent[x] = x
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])  # Path compression
        return self._parent[x]

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra

    def groups(self, members: list[str]) -> dict[str, list[str]]:
        """Return a dict of root_id → [member_ids] for all given members."""
        result: dict[str, list[str]] = defaultdict(list)
        for m in members:
            result[self.find(m)].append(m)
        return dict(result)


# ---------------------------------------------------------------------------
# Hamming distance on hex pHash strings
# ---------------------------------------------------------------------------

def _hamming_distance(hex_a: str, hex_b: str) -> int:
    """
    Compute the Hamming distance between two hex-encoded pHash/dHash values.

    Each hex string represents a 64-bit hash (16 hex chars).
    Returns the number of differing bits.
    Returns -1 if either string is None/empty or cannot be decoded.
    """
    if not hex_a or not hex_b:
        return -1
    try:
        int_a = int(hex_a, 16)
        int_b = int(hex_b, 16)
    except ValueError:
        return -1
    return (int_a ^ int_b).bit_count()



# ---------------------------------------------------------------------------
# Cluster types
# ---------------------------------------------------------------------------

@dataclass
class _DuplicateCluster:
    cluster_type: str            # "exact" or "near_duplicate"
    sample_ids: list[str]
    file_names: list[str]
    representative_hash: str     # SHA-256 (exact) or pHash of first member
    max_hamming_distance: int    # 0 for exact clusters


# ---------------------------------------------------------------------------
# Analysis functions (pure — no DB writes)
# ---------------------------------------------------------------------------

def _build_exact_duplicate_groups(samples: list[Sample]) -> list[_DuplicateCluster]:
    """Group samples by SHA-256.  Return clusters with size >= 2."""
    by_hash: dict[str, list[Sample]] = defaultdict(list)
    for s in samples:
        by_hash[s.sha256].append(s)

    clusters: list[_DuplicateCluster] = []
    for sha256, group in by_hash.items():
        if len(group) >= 2:
            clusters.append(_DuplicateCluster(
                cluster_type="exact",
                sample_ids=[s.sample_id for s in group],
                file_names=[s.file_name for s in group],
                representative_hash=sha256,
                max_hamming_distance=0,
            ))
    return clusters


def _build_near_duplicate_groups(
    samples: list[Sample],
    phash_threshold: int,
) -> list[_DuplicateCluster]:
    """
    Find near-duplicate clusters using pHash Hamming distance.

    Algorithm: O(N²) pairwise comparison with union-find clustering.
    Samples with missing pHash are silently excluded.
    Exact duplicates (same SHA-256) are excluded — DI-01 already catches
    those separately and we avoid double-counting.

    V1 Rationale: For demo-scale datasets (≤ 10,000 samples), O(N²) is
    acceptable.  Key constant-factor optimisations are applied:
      - All hex pHash strings are decoded to Python int exactly once, before
        the inner loop (saves N² calls to int(hex, 16)).
      - Per-pair distance uses int.bit_count() (Python 3.11+, C-level popcount)
        instead of bin().count('1'), which is 3–5× faster.
    This function is isolated so it can be replaced with a numpy-accelerated
    or LSH implementation without touching the rest of the detector.
    """
    # Only analyze samples that have a pHash
    eligible = [s for s in samples if s.phash]

    if len(eligible) < 2:
        return []

    # Decode hex pHash to int once per sample (avoids repeated int() in inner loop)
    int_hashes: list[int] = []
    valid_eligible: list[Sample] = []
    for s in eligible:
        try:
            int_hashes.append(int(s.phash, 16))  # type: ignore[arg-type]
            valid_eligible.append(s)
        except (ValueError, TypeError):
            continue  # Skip samples with malformed pHash

    N = len(valid_eligible)
    if N < 2:
        return []

    # Build adjacency: pairs within threshold (exclude exact SHA-256 duplicates)
    uf = _UnionFind()
    edge_max_dist: dict[tuple[str, str], int] = {}

    for i in range(N):
        ih_i = int_hashes[i]
        s_i = valid_eligible[i]
        for j in range(i + 1, N):
            # Skip byte-identical pairs — already handled by exact detection
            if s_i.sha256 == valid_eligible[j].sha256:
                continue
            # int.bit_count() is a C-level popcount (Python 3.11+), ~3–5× faster
            # than bin(x).count('1') because it avoids string allocation.
            dist = (ih_i ^ int_hashes[j]).bit_count()
            if dist <= phash_threshold:
                sid_i = s_i.sample_id
                sid_j = valid_eligible[j].sample_id
                uf.union(sid_i, sid_j)
                key = (min(sid_i, sid_j), max(sid_i, sid_j))
                edge_max_dist[key] = max(edge_max_dist.get(key, 0), dist)

    # Collect clusters
    all_ids = [s.sample_id for s in valid_eligible]
    groups = uf.groups(all_ids)
    sample_map = {s.sample_id: s for s in valid_eligible}

    clusters: list[_DuplicateCluster] = []
    for root, member_ids in groups.items():
        if len(member_ids) < 2:
            continue  # Singleton — not a near-duplicate cluster

        # Max Hamming distance across all discovered edges in this cluster.
        # Keys in edge_max_dist are always (min_sid, max_sid); normalise here
        # to match, since union-find may return member_ids in arbitrary order.
        max_dist = 0
        for ii in range(len(member_ids)):
            for jj in range(ii + 1, len(member_ids)):
                a, b = member_ids[ii], member_ids[jj]
                key = (min(a, b), max(a, b))
                if key in edge_max_dist:
                    max_dist = max(max_dist, edge_max_dist[key])

        members = [sample_map[sid] for sid in member_ids if sid in sample_map]
        clusters.append(_DuplicateCluster(
            cluster_type="near_duplicate",
            sample_ids=member_ids,
            file_names=[s.file_name for s in members],
            representative_hash=members[0].phash or "",
            max_hamming_distance=max_dist,
        ))

    return clusters



# ---------------------------------------------------------------------------
# Finding / Evidence construction
# ---------------------------------------------------------------------------

def _cluster_to_finding_and_evidence(
    cluster: _DuplicateCluster,
    assessment_id: str,
    asset_id: str,
    detector_id: str,
) -> tuple[Finding, Evidence]:
    """
    Build a Finding and a corresponding Evidence record for one cluster.

    Risk semantics:
      exact      → MEDIUM severity / MEDIUM risk (hard fact)
      near_dup   → LOW severity / LOW risk (candidate — interpret carefully)
    """
    n = len(cluster.sample_ids)

    if cluster.cluster_type == "exact":
        severity = Severity.MEDIUM
        title = f"Exact duplicate cluster: {n} byte-identical images"
        description = (
            f"{n} images share an identical SHA-256 ({cluster.representative_hash[:16]}…). "
            f"They are byte-for-byte identical files. "
            f"This may indicate dataset flooding, copy-paste errors, or a poorly "
            f"deduplicated collection. Exact duplicates do not by themselves prove "
            f"malicious intent."
        )
        subcategory = "exact_duplicate"
        evidence_type = EvidenceType.HASH_MATCH
        evidence_desc = (
            f"Exact SHA-256 match across {n} samples. "
            f"Hash: {cluster.representative_hash}"
        )
        limitations = [
            "SHA-256 equality proves byte-identical content, not intent.",
            "Legitimate augmentation pipelines may produce exact duplicates.",
        ]
        recommended = (
            "Review source attribution of all samples in this cluster. "
            "If from a single contributor, consider deduplication."
        )
    else:
        severity = Severity.LOW
        title = (
            f"Near-duplicate candidate cluster: {n} perceptually similar images "
            f"(max Hamming {cluster.max_hamming_distance} bits)"
        )
        description = (
            f"{n} images are perceptually similar by pHash with a maximum "
            f"Hamming distance of {cluster.max_hamming_distance} bits "
            f"(threshold: ≤ {cluster.max_hamming_distance} bits). "
            f"Near-duplicates may be legitimate augmentations, compression "
            f"artefacts, or watermark variants. "
            f"Further analyst review is required to determine if this "
            f"represents intentional flooding."
        )
        subcategory = "near_duplicate"
        evidence_type = EvidenceType.CLUSTER
        evidence_desc = (
            f"pHash near-duplicate cluster of {n} samples. "
            f"Max Hamming distance: {cluster.max_hamming_distance} bits."
        )
        limitations = [
            "pHash similarity does not prove identical content or malicious intent.",
            "Legitimate augmentations (crop, resize, brightness) produce similar pHash.",
            "False positives increase with lower Hamming thresholds.",
        ]
        recommended = (
            "Visually inspect samples in this cluster. "
            "If intentional augmentation, document in dataset provenance. "
            "If unexplained repetition, investigate contributor attribution."
        )

    finding = Finding(
        assessment_id=assessment_id,
        asset_id=asset_id,
        category=FindingCategory.DATA_INTEGRITY,
        subcategory=subcategory,
        severity=severity,
        title=title,
        description=description,
        detection_method=_METADATA.name,
        detector_id=detector_id,
        limitations=limitations,
        recommended_disposition=recommended,
        source="LIVE_ANALYSIS",
    )

    evidence = Evidence(
        finding_id=finding.finding_id,
        detector_id=detector_id,
        evidence_type=evidence_type,
        description=evidence_desc,
        data={
            "cluster_type": cluster.cluster_type,
            "cluster_size": n,
            "representative_hash": cluster.representative_hash,
            "max_hamming_distance": cluster.max_hamming_distance,
            "sample_ids": cluster.sample_ids,
            "file_names": cluster.file_names,
        },
    )

    return finding, evidence


# ---------------------------------------------------------------------------
# Risk / confidence derivation
# ---------------------------------------------------------------------------

def _derive_risk_and_confidence(
    exact_clusters: list[_DuplicateCluster],
    near_clusters: list[_DuplicateCluster],
    total_samples: int,
    samples_missing_phash: int,
) -> tuple[RiskLevel, ConfidenceLevel, str]:
    """
    Derive overall risk level and confidence for the detector run.

    Returns (risk_level, confidence_level, confidence_qualifier).
    """
    has_exact = len(exact_clusters) > 0
    has_near = len(near_clusters) > 0

    # Risk
    if has_exact and has_near:
        risk = RiskLevel.MEDIUM
    elif has_exact:
        risk = RiskLevel.MEDIUM
    elif has_near:
        risk = RiskLevel.LOW
    else:
        risk = RiskLevel.NONE

    # Confidence — based on data completeness
    missing_fraction = samples_missing_phash / total_samples if total_samples > 0 else 1.0

    if total_samples < 2:
        confidence = ConfidenceLevel.LOW
        qualifier = (
            "Fewer than 2 samples — duplicate analysis is not meaningful."
        )
    elif missing_fraction > 0.5:
        confidence = ConfidenceLevel.LOW
        qualifier = (
            f"{samples_missing_phash}/{total_samples} samples lack pHash fingerprints. "
            f"Near-duplicate coverage is severely limited."
        )
    elif missing_fraction > 0.1:
        confidence = ConfidenceLevel.MODERATE
        qualifier = (
            f"{samples_missing_phash}/{total_samples} samples lack pHash fingerprints. "
            f"Near-duplicate analysis may be incomplete."
        )
    elif risk == RiskLevel.NONE:
        confidence = ConfidenceLevel.HIGH
        qualifier = (
            f"All {total_samples} samples were analyzed. "
            f"No duplicates or near-duplicates found."
        )
    else:
        confidence = ConfidenceLevel.MODERATE
        qualifier = (
            f"Duplicate evidence found in {total_samples} samples. "
            f"Near-duplicate threshold: {10} bits Hamming distance."
        )

    return risk, confidence, qualifier


# ---------------------------------------------------------------------------
# Detector implementation
# ---------------------------------------------------------------------------

class DI01DuplicateDetector:
    """
    DI-01: Duplicate and Near-Duplicate Image Detector.

    Implements the Detector protocol (ADR-004).
    Pure analysis: reads sample fingerprints, returns DetectorOutput.
    Does NOT write to the database.
    """

    @property
    def metadata(self) -> DetectorMetadata:
        return _METADATA

    def can_run(self, context: DetectorContext) -> CanRunResult:
        """
        Check whether this detector can run against the given context.

        Requires:
          - At least 1 sample in the dataset
          - At least 1 sample with a SHA-256 (should always be true post-ingestion)
        """
        try:
            repo = SampleRepository(context.conn)
            count = repo.count_by_dataset(context.asset_id)
        except Exception as exc:
            return CanRunResult(ok=False, reason=f"Database error: {exc}")

        if count == 0:
            return CanRunResult(
                ok=False,
                reason="Dataset contains no samples — nothing to analyze.",
            )
        return CanRunResult(ok=True)

    def run(self, context: DetectorContext) -> DetectorOutput:
        """
        Run duplicate/near-duplicate analysis on the dataset's stored fingerprints.

        Reads samples from the database.
        Returns DetectorOutput with findings and evidence.
        Does NOT persist anything — the caller persists the output.
        """
        output = DetectorOutput()
        did = _METADATA.detector_id

        try:
            samples = SampleRepository(context.conn).list_by_dataset(context.asset_id)
        except Exception as exc:
            output.status = DetectorStatus.FAILED
            output.error = f"Failed to read samples: {exc}"
            log.error("DI-01 failed to read samples for %s: %s", context.asset_id, exc)
            return output.finalize()

        total = len(samples)
        missing_phash = sum(1 for s in samples if not s.phash)
        log.info(
            "DI-01: analyzing %d samples for dataset %s (%d missing pHash)",
            total, context.asset_id, missing_phash,
        )

        # --- Exact duplicate detection (O(n), always runs) -------------------
        exact_clusters = _build_exact_duplicate_groups(samples)

        # --- Near-duplicate detection (O(n²), configurable threshold) --------
        near_clusters = _build_near_duplicate_groups(samples, context.phash_threshold)

        # --- Build findings and evidence for each cluster --------------------
        findings: list[Finding] = []
        evidence: list[Evidence] = []

        for cluster in exact_clusters:
            f, e = _cluster_to_finding_and_evidence(
                cluster, context.assessment_id, context.asset_id, did
            )
            findings.append(f)
            evidence.append(e)

        for cluster in near_clusters:
            f, e = _cluster_to_finding_and_evidence(
                cluster, context.assessment_id, context.asset_id, did
            )
            findings.append(f)
            evidence.append(e)

        # --- Risk and confidence ---------------------------------------------
        risk, confidence, qualifier = _derive_risk_and_confidence(
            exact_clusters, near_clusters, total, missing_phash
        )

        log.info(
            "DI-01 complete: %d exact clusters, %d near-dup clusters, "
            "risk=%s, confidence=%s",
            len(exact_clusters), len(near_clusters), risk.value, confidence.value,
        )

        output.findings = findings
        output.evidence = evidence
        output.risk_level = risk
        output.confidence_level = confidence
        output.status = (
            DetectorStatus.PARTIAL if missing_phash > 0 and total > 0
            else DetectorStatus.SUCCESS
        )
        return output.finalize()
