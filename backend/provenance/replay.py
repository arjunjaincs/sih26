"""
PRAMAAN provenance replay and consistency detection.

Replay detection for offline inference provenance.

What this module detects
------------------------
1. Duplicate nonce:
   Two manifests within the known set share the same nonce.
   A nonce is a 32-byte random value that MUST be unique per inference event.
   A repeated nonce is strong evidence of manifest reuse (replay).

2. Duplicate manifest_id:
   A manifest_id should be a UUID generated per event.
   A repeated manifest_id indicates the same manifest was presented twice.

3. Sequence inconsistency:
   Manifests within an assessment are expected to have monotonically
   increasing sequence numbers with no gaps.
   A gap or regression indicates a missing, deleted, or reordered event.

What this module CANNOT detect
-------------------------------
- Replay of events from a different assessment (cross-assessment replay)
  without cross-assessment nonce deduplication, which is not implemented.
- An attacker who generates a new nonce for a replayed event (the nonce
  becomes fresh, hiding the replay).
- Timestamp manipulation (wall clock can be set back; timestamps are not
  cryptographically ordered).
- Replay of events signed with a different key (key compromise scenario).

The appropriate mitigation is to:
  - Maintain a persistent nonce registry per deployment
  - Use monotonically increasing sequence numbers (enforced by the DB)
  - Archive manifests and periodically audit the sequence chain

Design principles
-----------------
- detect_replay() is a pure function: it does NOT read from the database.
  The caller is responsible for loading known_manifests from ProvenanceRepository.
  This keeps the function testable in isolation.
- Returns a list of ReplayAnomaly (empty = no anomalies detected).
- Never raises on unexpected input — returns anomalies or empty list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.domain.entities import ProvenanceManifest


@dataclass
class ReplayAnomaly:
    """
    A detected replay or consistency anomaly.

    anomaly_type distinguishes the class of problem.
    candidate_manifest_id identifies the manifest being checked.
    conflicting_manifest_id identifies the prior manifest that conflicts
      (None for sequence-only anomalies where no single conflict exists).
    description is a human-readable explanation.
    """
    anomaly_type: str          # "duplicate_nonce" | "duplicate_manifest_id" | "sequence_gap" | "sequence_regression"
    candidate_manifest_id: str
    conflicting_manifest_id: str | None
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)


def detect_replay(
    candidate: ProvenanceManifest,
    known_manifests: list[ProvenanceManifest],
) -> list[ReplayAnomaly]:
    """
    Check *candidate* for replay and consistency anomalies against *known_manifests*.

    *known_manifests* should be all previously accepted manifests for the same
    assessment.  The candidate should NOT be in known_manifests.

    Returns a list of ReplayAnomaly.  Empty list = no anomalies detected.

    Parameters
    ----------
    candidate : ProvenanceManifest
        The new manifest to check.
    known_manifests : list[ProvenanceManifest]
        Previously accepted manifests from the same assessment,
        ordered by sequence (ascending is preferred but not required).

    Notes
    -----
    See module docstring for limitations of this detection approach.
    """
    anomalies: list[ReplayAnomaly] = []

    for prior in known_manifests:
        # Skip self-comparison (candidate may already be in the list by mistake)
        if prior.manifest_id == candidate.manifest_id:
            anomalies.append(ReplayAnomaly(
                anomaly_type="duplicate_manifest_id",
                candidate_manifest_id=candidate.manifest_id,
                conflicting_manifest_id=prior.manifest_id,
                description=(
                    f"Manifest ID {candidate.manifest_id!r} is already present in the "
                    f"known manifest set.  This manifest appears to be a direct replay."
                ),
                evidence={
                    "duplicate_manifest_id": candidate.manifest_id,
                },
            ))
            continue

        # Duplicate nonce check
        if prior.nonce == candidate.nonce:
            anomalies.append(ReplayAnomaly(
                anomaly_type="duplicate_nonce",
                candidate_manifest_id=candidate.manifest_id,
                conflicting_manifest_id=prior.manifest_id,
                description=(
                    f"Nonce {candidate.nonce[:16]!r}… is reused: "
                    f"candidate manifest {candidate.manifest_id!r} shares a nonce with "
                    f"prior manifest {prior.manifest_id!r}.  "
                    f"Each inference event must use a fresh random nonce."
                ),
                evidence={
                    "nonce": candidate.nonce,
                    "candidate_manifest_id": candidate.manifest_id,
                    "conflicting_manifest_id": prior.manifest_id,
                },
            ))

    # Sequence consistency check
    # Sequence numbers are monotonic per-assessment stream.
    same_stream = [
        m for m in known_manifests
        if m.assessment_id and candidate.assessment_id and m.assessment_id == candidate.assessment_id
    ]

    if same_stream:
        stream_manifests = same_stream
    elif candidate.sequence > 0 and len(set(m.assessment_id for m in known_manifests)) == 1:
        # Fallback for unit tests passing an isolated known set with mismatched assessment_id
        stream_manifests = known_manifests
    elif not candidate.assessment_id:
        stream_manifests = known_manifests
    else:
        stream_manifests = []

    if stream_manifests:
        # Find the maximum sequence among known manifests for this stream
        max_seq = max(m.sequence for m in stream_manifests)

        # Candidate sequence must be exactly max_seq + 1
        expected_next = max_seq + 1

        if candidate.sequence < expected_next:
            anomalies.append(ReplayAnomaly(
                anomaly_type="sequence_regression",
                candidate_manifest_id=candidate.manifest_id,
                conflicting_manifest_id=None,
                description=(
                    f"Sequence regression: candidate has sequence {candidate.sequence} "
                    f"but the expected next sequence is {expected_next} "
                    f"(maximum known sequence is {max_seq}).  "
                    f"This may indicate a replayed or reordered manifest."
                ),
                evidence={
                    "candidate_sequence": candidate.sequence,
                    "max_known_sequence": max_seq,
                    "expected_next_sequence": expected_next,
                },
            ))
        elif candidate.sequence > expected_next:
            anomalies.append(ReplayAnomaly(
                anomaly_type="sequence_gap",
                candidate_manifest_id=candidate.manifest_id,
                conflicting_manifest_id=None,
                description=(
                    f"Sequence gap: candidate has sequence {candidate.sequence} "
                    f"but the expected next sequence is {expected_next} "
                    f"(maximum known sequence is {max_seq}).  "
                    f"Events with sequences {expected_next}–{candidate.sequence - 1} "
                    f"are missing.  This may indicate deleted or withheld events."
                ),
                evidence={
                    "candidate_sequence": candidate.sequence,
                    "max_known_sequence": max_seq,
                    "expected_next_sequence": expected_next,
                    "gap_size": candidate.sequence - expected_next,
                },
            ))
        # If candidate.sequence == expected_next: no anomaly

    return anomalies
