# ADR-008: Append-Only Hash-Linked Audit Chain

**Status**: Accepted  
**Date**: 2026-09-10  
**Context**: PRAMAAN must maintain a tamper-evident audit trail of all assessment operations.

## Decision

Audit events are stored in an append-only SQLite table. Each event includes a
SHA-256 hash of the previous event, forming a hash-linked chain (similar to a
blockchain's block chain, without consensus or distributed nodes).

## Design

```
Event 0 (Genesis)
  previous_hash = H("GENESIS")
  current_hash  = H(previous_hash || event_id || timestamp || payload_digest)

Event 1
  previous_hash = Event 0.current_hash
  current_hash  = H(previous_hash || event_id || timestamp || payload_digest)

Event N
  previous_hash = Event (N-1).current_hash
  current_hash  = H(...)
```

## Rationale

- **Tamper evidence**: Modifying any event breaks the hash chain from that point forward
- **Deletion evidence**: Removing an event creates a gap in the chain
- **Insertion evidence**: Inserting a fake event requires recomputing all subsequent hashes
- **Simple**: No distributed consensus needed; single-writer, local chain
- **Verifiable**: Chain verification is O(n) and straightforward

## Not a Blockchain

This is explicitly NOT a blockchain:
- No distributed consensus
- No proof of work/stake
- No decentralized verification
- Just a hash-linked append-only log

The word "blockchain" should NOT appear in PRAMAAN's marketing or documentation
because it implies distributed consensus that doesn't exist here.

## Consequences

- Application must enforce append-only (no SQL UPDATE/DELETE on audit table)
- Chain verification must be run on read and periodically
- A root-level attacker can rewrite the entire chain; Ed25519 signatures on
  critical events provide a partial mitigation
- Chain grows forever; may need archival strategy for very long-running deployments

## Rejected Alternatives

- Actual blockchain (massive overkill, requires consensus)
- Simple log file (no tamper evidence)
- Merkle tree only (hash chain is simpler and sufficient for linear events)
