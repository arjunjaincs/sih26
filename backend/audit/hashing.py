"""
PRAMAAN audit event hashing.

Defines the EXACT canonical form and hashing algorithm used for
the audit chain.  Every component that produces or verifies audit
events must use ONLY these functions.

Hash algorithm
--------------
Canonical form of an event (fields included in hash):
  - event_id
  - event_type     (string value)
  - timestamp_utc
  - assessment_id  (may be null — stored as JSON null)
  - actor
  - payload_digest (SHA-256 of the payload JSON bytes)
  - previous_hash

The stored current_hash itself is EXCLUDED when computing current_hash
(otherwise the computation would be circular).

current_hash = SHA-256(canonical_json({
    "actor":          event.actor,
    "assessment_id":  event.assessment_id,
    "event_id":       event.event_id,
    "event_type":     event.event_type.value,
    "payload_digest": event.payload_digest,
    "previous_hash":  event.previous_hash,
    "timestamp_utc":  event.timestamp_utc,
}))

canonical_json uses sorted keys, no whitespace, UTF-8 encoding.
This is the same canonical_json used throughout PRAMAAN (infra/crypto.py).

Payload hashing
---------------
payload_digest = SHA-256(canonical_json(payload_dict))

Both hashes use the same canonical_json function so the algorithm
is unambiguous and deterministic.

Signing (optional, ADR-005)
----------------------------
Critical events may be signed with Ed25519.  The signature covers the
current_hash bytes (not the hex string).  Signing is separate from
hash chaining:

  hash chain  = sequence integrity
  signature   = authenticity of who produced the event

Signing never replaces hash chaining.

Limitations
-----------
- A root-level attacker who can rewrite the entire SQLite file can
  recompute the full hash chain.  Ed25519 signing on critical events
  provides partial mitigation per ADR-008.
- Chain verification only covers events stored in this database.
  Cross-database tampering is not detected.
- Time ordering is based on the wall clock at insertion time;
  monotonic sequencing is enforced by the hash chain linkage, not
  by timestamp values.
"""

from __future__ import annotations

from backend.domain.entities import AuditEvent
from backend.infra.crypto import canonical_json, hash_bytes


# ---------------------------------------------------------------------------
# Fields included in the chain hash (MUST NOT include current_hash itself)
# ---------------------------------------------------------------------------

_CHAIN_HASH_FIELDS: frozenset[str] = frozenset({
    "actor",
    "assessment_id",
    "event_id",
    "event_type",
    "payload_digest",
    "previous_hash",
    "timestamp_utc",
})


def compute_payload_digest(payload: dict) -> str:
    """
    Return the SHA-256 hex digest of the canonical JSON encoding of *payload*.

    This is what gets stored in AuditEvent.payload_digest.
    Recomputing this from the stored payload allows detecting payload tampering.

    Parameters
    ----------
    payload : dict
        Must be JSON-serializable.  Keys are sorted automatically.
    """
    return hash_bytes(canonical_json(payload))


def compute_event_hash(event: AuditEvent) -> str:
    """
    Compute (or recompute) the canonical SHA-256 hash for *event*.

    Includes exactly the fields in _CHAIN_HASH_FIELDS.
    Does NOT include current_hash (circular) or any other fields.

    The returned hex string is what should be stored in event.current_hash.

    Parameters
    ----------
    event : AuditEvent
        The event to hash.  digest/current_hash fields are ignored.

    Returns
    -------
    str
        64-character lowercase hex SHA-256 digest.
    """
    signable: dict = {
        "actor":          event.actor,
        "assessment_id":  event.assessment_id,
        "event_id":       event.event_id,
        "event_type":     event.event_type.value,
        "payload_digest": event.payload_digest,
        "previous_hash":  event.previous_hash,
        "timestamp_utc":  event.timestamp_utc,
    }
    return hash_bytes(canonical_json(signable))


def verify_event_hash(event: AuditEvent) -> bool:
    """
    Return True if event.current_hash matches the recomputed hash.

    A False result means the event's fields have been modified after
    the hash was computed.
    """
    return compute_event_hash(event) == event.current_hash
