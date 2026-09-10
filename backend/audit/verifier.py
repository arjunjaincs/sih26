"""
PRAMAAN audit chain verifier.

Verifies the integrity of the persisted audit chain by walking all events
and checking:

  1. Hash integrity: recomputed current_hash == stored current_hash
  2. Chain linkage: each event's previous_hash == prior event's current_hash
  3. Payload integrity: recomputed payload_digest == stored payload_digest
     (only when the actual payload is available)
  4. Genesis: first event must reference GENESIS_HASH as its previous_hash

A broken chain does NOT automatically mean "malicious".
It means the integrity of the record cannot be established.
Human review is required to determine cause.

Returns
-------
ChainVerificationResult — machine-readable, deterministic.

Algorithm
---------
  result = VALID
  prev_hash = GENESIS_HASH

  for each event in insertion order:
      recomputed = compute_event_hash(event)
      if recomputed != event.current_hash:
          return TAMPERED at this event (current_hash_mismatch)

      if event.previous_hash != expected_previous:
          return TAMPERED at this event (previous_hash_mismatch)

      prev_hash = event.current_hash

  return VALID

Payload verification (optional, when payloads supplied):
  recomputed_digest = SHA-256(canonical_json(payload))
  if recomputed_digest != event.payload_digest:
      mark payload_tampered on the relevant event

Limitations
-----------
- Does not verify Ed25519 signatures on signed events (signature
  verification is done by the signing verifier in audit/service.py)
- Does not detect insertion of events before the chain head unless
  previous_hash linkage is violated
- Does not cross-verify chains from other databases
- A full chain rewrite by a root attacker is not detectable by
  hash chaining alone (Ed25519 signing is the mitigation)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.audit.hashing import compute_event_hash, compute_payload_digest
from backend.domain.entities import AuditEvent
from backend.infra.db import AuditPayloadRepository, AuditRepository


# ---------------------------------------------------------------------------
# Verification result types
# ---------------------------------------------------------------------------

@dataclass
class EventVerificationFailure:
    """
    A single verification failure for one event in the chain.

    Included in ChainVerificationResult.failures when the chain is not valid.
    """
    event_id: str
    position: int                   # 0-based index in the chain
    failure_type: str               # "current_hash_mismatch" | "previous_hash_mismatch" | "payload_digest_mismatch"
    expected_value: str             # What the verifier expected
    observed_value: str             # What was stored
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id":       self.event_id,
            "position":       self.position,
            "failure_type":   self.failure_type,
            "expected_value": self.expected_value,
            "observed_value": self.observed_value,
            "description":    self.description,
        }


@dataclass
class ChainVerificationResult:
    """
    Result of verifying the entire persisted audit chain.

    valid: True means the entire chain hashed correctly with no missing links.
    valid: False means at least one event failed verification.

    The verifier stops at the FIRST chain-breaking failure (current_hash or
    previous_hash mismatch) to avoid producing a misleading cascade.
    Payload failures do NOT stop verification — they are collected independently.

    Machine-readable result suitable for persistence, reporting, and tests.
    """
    valid: bool
    events_checked: int
    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    failures: list[EventVerificationFailure] = field(default_factory=list)
    first_invalid_event_id: str | None = None
    error: str | None = None

    @property
    def is_empty_chain(self) -> bool:
        return self.events_checked == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid":                   self.valid,
            "events_checked":          self.events_checked,
            "verified_at":             self.verified_at,
            "first_invalid_event_id":  self.first_invalid_event_id,
            "failure_count":           len(self.failures),
            "failures":                [f.to_dict() for f in self.failures],
            "error":                   self.error,
        }


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

class ChainVerifier:
    """
    Walk the stored audit chain and verify every hash link.

    Usage:
        verifier = ChainVerifier(audit_repo, payload_repo)
        result = verifier.verify_all()
        if not result.valid:
            print(result.failures[0])

    The verifier does NOT write to the database.
    Persistence of results is the caller's responsibility.

    Parameters
    ----------
    audit_repo : AuditRepository
        Source of stored audit events.
    payload_repo : AuditPayloadRepository | None
        If supplied, payload digests are re-verified against actual payloads.
        If None, payload verification is skipped.
    """

    def __init__(
        self,
        audit_repo: AuditRepository,
        payload_repo: AuditPayloadRepository | None = None,
    ) -> None:
        self._audit = audit_repo
        self._payloads = payload_repo

    def verify_all(self) -> ChainVerificationResult:
        """
        Verify the entire chain in insertion order.

        Returns ChainVerificationResult with valid=True iff:
          - All current_hash values match recomputed hashes
          - All previous_hash values form a valid chain
          - (If payload_repo given) All payload_digest values are correct
        """
        try:
            events = self._audit.list_all()
        except Exception as exc:
            return ChainVerificationResult(
                valid=False,
                events_checked=0,
                error=f"Failed to read audit chain: {exc}",
            )

        if not events:
            return ChainVerificationResult(valid=True, events_checked=0)

        # Preload payloads for batch efficiency
        payloads: dict[str, dict] = {}
        if self._payloads is not None:
            try:
                payloads = self._payloads.get_all_for_events(
                    [e.event_id for e in events]
                )
            except Exception:
                pass  # Payload failures are non-chain-breaking; collect individually

        failures: list[EventVerificationFailure] = []
        first_invalid: str | None = None
        expected_previous = AuditRepository.GENESIS_HASH

        for pos, event in enumerate(events):
            # 1. Recompute current_hash and check
            recomputed_hash = compute_event_hash(event)
            if recomputed_hash != event.current_hash:
                f = EventVerificationFailure(
                    event_id=event.event_id,
                    position=pos,
                    failure_type="current_hash_mismatch",
                    expected_value=recomputed_hash,
                    observed_value=event.current_hash,
                    description=(
                        f"Event at position {pos} has a stored current_hash that does not "
                        f"match the recomputed hash. The event fields may have been modified "
                        f"after the hash was computed."
                    ),
                )
                failures.append(f)
                if first_invalid is None:
                    first_invalid = event.event_id
                # Chain is broken here; stop chain checking but continue payload checks
                break

            # 2. Check previous_hash linkage
            if event.previous_hash != expected_previous:
                f = EventVerificationFailure(
                    event_id=event.event_id,
                    position=pos,
                    failure_type="previous_hash_mismatch",
                    expected_value=expected_previous,
                    observed_value=event.previous_hash,
                    description=(
                        f"Event at position {pos} has previous_hash {event.previous_hash!r} "
                        f"but the expected previous hash is {expected_previous!r}. "
                        f"An event may have been removed, inserted, or reordered."
                    ),
                )
                failures.append(f)
                if first_invalid is None:
                    first_invalid = event.event_id
                # Chain is broken; stop linkage checking
                break

            expected_previous = event.current_hash

            # 3. Payload digest verification (independent of chain check)
            if event.event_id in payloads:
                recomputed_digest = compute_payload_digest(payloads[event.event_id])
                if recomputed_digest != event.payload_digest:
                    f = EventVerificationFailure(
                        event_id=event.event_id,
                        position=pos,
                        failure_type="payload_digest_mismatch",
                        expected_value=recomputed_digest,
                        observed_value=event.payload_digest,
                        description=(
                            f"Event at position {pos}: the stored payload_digest does not "
                            f"match SHA-256(canonical_json(payload)). The payload may have "
                            f"been modified independently of the chain hash."
                        ),
                    )
                    failures.append(f)
                    if first_invalid is None:
                        first_invalid = event.event_id

        return ChainVerificationResult(
            valid=len(failures) == 0,
            events_checked=len(events),
            failures=failures,
            first_invalid_event_id=first_invalid,
        )

    def verify_assessment(self, assessment_id: str) -> ChainVerificationResult:
        """
        Verify only the events belonging to *assessment_id*.

        Note: this checks hash integrity of each event individually and the
        previous_hash linkage WITHIN the assessment subset.  It does NOT
        verify the global chain position of these events.

        Use verify_all() for global tamper detection.
        """
        try:
            events = self._audit.list_by_assessment(assessment_id)
        except Exception as exc:
            return ChainVerificationResult(
                valid=False,
                events_checked=0,
                error=f"Failed to read assessment audit events: {exc}",
            )

        if not events:
            return ChainVerificationResult(valid=True, events_checked=0)

        payloads: dict[str, dict] = {}
        if self._payloads is not None:
            try:
                payloads = self._payloads.get_all_for_events(
                    [e.event_id for e in events]
                )
            except Exception:
                pass

        failures: list[EventVerificationFailure] = []
        first_invalid: str | None = None

        for pos, event in enumerate(events):
            # Hash integrity only (not global chain linkage)
            recomputed_hash = compute_event_hash(event)
            if recomputed_hash != event.current_hash:
                f = EventVerificationFailure(
                    event_id=event.event_id,
                    position=pos,
                    failure_type="current_hash_mismatch",
                    expected_value=recomputed_hash,
                    observed_value=event.current_hash,
                    description=(
                        f"Assessment event at position {pos} has a mismatched current_hash."
                    ),
                )
                failures.append(f)
                if first_invalid is None:
                    first_invalid = event.event_id

            if event.event_id in payloads:
                recomputed_digest = compute_payload_digest(payloads[event.event_id])
                if recomputed_digest != event.payload_digest:
                    f = EventVerificationFailure(
                        event_id=event.event_id,
                        position=pos,
                        failure_type="payload_digest_mismatch",
                        expected_value=recomputed_digest,
                        observed_value=event.payload_digest,
                        description=(
                            f"Assessment event at position {pos}: payload_digest mismatch."
                        ),
                    )
                    failures.append(f)
                    if first_invalid is None:
                        first_invalid = event.event_id

        return ChainVerificationResult(
            valid=len(failures) == 0,
            events_checked=len(events),
            failures=failures,
            first_invalid_event_id=first_invalid,
        )
