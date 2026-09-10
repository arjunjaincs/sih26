# backend/audit/__init__.py
"""
PRAMAAN tamper-evident audit trail.

Provides:
  hashing.py    — canonical event hashing (event_hash / payload_hash)
  service.py    — AuditService: append events, manage chain
  verifier.py   — ChainVerifier: walk chain, detect tampering
  integration.py — helpers for emitting real events from detectors/operations

This is NOT a general logging framework.  Its sole purpose is tamper
evidence and event sequencing within the local PRAMAAN assessment.

A hash-linked audit chain is NOT a blockchain.  There is no distributed
consensus, no proof-of-work, no decentralisation — only a local,
append-only, hash-linked log that detects tampering.
"""
