"""
PRAMAAN AuditService — the only way application code creates audit events.

Responsibilities
----------------
1. Build a correctly-linked AuditEvent (previous_hash → current_hash chain)
2. Hash the payload and store the payload_digest
3. Optionally sign critical events with Ed25519 (ADR-005)
4. Append the event to the AuditRepository (atomic)
5. Store the payload to AuditPayloadRepository

What the service does NOT do
-----------------------------
- Read audit events (use AuditRepository directly)
- Verify the chain (use ChainVerifier)
- Orchestrate detectors
- Touch the filesystem (except signing-key load which the caller provides)

Append-only guarantee
----------------------
Once emit_event() is called, the event and payload are written to separate
tables.  AuditRepository and AuditPayloadRepository provide no UPDATE or DELETE.
Application code is the only enforcement mechanism (SQLite has no row-level
triggers that prevent UPDATE in this schema).

Signing (ADR-005)
-----------------
Signing is OPTIONAL per call.  When a private_key is provided:
  1. The event's current_hash (already computed) is signed
  2. The signature hex is stored in the payload under "signature"
  3. The public key raw bytes (hex) are stored under "signing_key_id"

This means:
  - Signing is separate from hash chaining
  - A tampered current_hash → signature invalid → both detected
  - The payload_digest in the chain hash covers the signature field,
    so tampering with the signature itself also breaks the payload digest

Private key material is NEVER stored in audit records.
Only the public key (as raw bytes hex for identification) is stored.

Thread safety
-------------
AuditService is NOT thread-safe.  Each thread/process should use its own
instance.  The underlying SQLite WAL mode permits concurrent reads.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from backend.audit.hashing import compute_event_hash, compute_payload_digest
from backend.domain.entities import AuditEvent
from backend.domain.enums import AuditEventType
from backend.infra.crypto import sign, public_key_from_private
from backend.infra.db import AuditPayloadRepository, AuditRepository

log = logging.getLogger(__name__)


class AuditService:
    """
    Creates and appends tamper-evident audit events.

    Parameters
    ----------
    audit_repo : AuditRepository
        Append-only repository for chain events.
    payload_repo : AuditPayloadRepository
        Append-only repository for event payloads.
    """

    def __init__(
        self,
        audit_repo: AuditRepository,
        payload_repo: AuditPayloadRepository,
    ) -> None:
        self._chain = audit_repo
        self._payloads = payload_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def emit_event(
        self,
        event_type: AuditEventType,
        payload: dict[str, Any],
        *,
        assessment_id: str | None = None,
        actor: str = "system",
        private_key: Ed25519PrivateKey | None = None,
    ) -> AuditEvent:
        """
        Build, sign (optionally), hash-link, and append one audit event.

        Parameters
        ----------
        event_type : AuditEventType
            The type of the event being recorded.
        payload : dict
            Structured JSON-serializable payload.  Do NOT include raw binary
            or model weights.  Store references (IDs, hashes) only.
        assessment_id : str | None
            The PRAMAAN assessment this event belongs to, if applicable.
        actor : str
            The logical actor producing this event.  Defaults to "system".
        private_key : Ed25519PrivateKey | None
            If provided, the event's current_hash will be signed with this
            key.  The signature and public-key identifier are stored in the
            payload.  Private key bytes are NEVER stored.

        Returns
        -------
        AuditEvent — the fully constructed and persisted event.

        Raises
        ------
        RuntimeError if the append fails.  The chain tail is not updated if
        the database write fails.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        previous_hash = self._chain.last_hash()

        effective_payload = dict(payload)

        if private_key is not None:
            # --- Signing protocol ---
            # Phase 1: compute current_hash from the unsigned payload
            #   (payload without __signature/__signing_key_id)
            # Phase 2: sign that hash
            # Phase 3: store the signature + key-id + pre-sig hash in payload
            # Phase 4: recompute payload_digest and current_hash over the
            #          signed payload (so tampering with the signature breaks
            #          the chain hash)
            pub: Ed25519PublicKey = public_key_from_private(private_key)
            pub_hex = pub.public_bytes_raw().hex()

            # Phase 1: unsigned payload digest and event hash
            unsigned_digest = compute_payload_digest(effective_payload)
            tmp_event = AuditEvent(
                event_type=event_type,
                timestamp_utc=timestamp,
                assessment_id=assessment_id,
                actor=actor,
                payload_digest=unsigned_digest,
                previous_hash=previous_hash,
                current_hash="",
            )
            pre_sig_hash = compute_event_hash(tmp_event)

            # Phase 2: sign the pre-signature hash
            sig_hex = sign(private_key, pre_sig_hash)

            # Phase 3: add signing metadata to payload
            effective_payload["__signing_key_id"] = pub_hex
            effective_payload["__pre_sig_hash"] = pre_sig_hash   # what was signed
            effective_payload["__signature"] = sig_hex

            # Phase 4: recompute everything with the signed payload
            payload_digest = compute_payload_digest(effective_payload)
            event = AuditEvent(
                event_id=tmp_event.event_id,
                event_type=event_type,
                timestamp_utc=timestamp,
                assessment_id=assessment_id,
                actor=actor,
                payload_digest=payload_digest,
                previous_hash=previous_hash,
                current_hash="",
            )
            current_hash = compute_event_hash(event)
            event = event.model_copy(update={"current_hash": current_hash})

        else:
            payload_digest = compute_payload_digest(effective_payload)
            event = AuditEvent(
                event_type=event_type,
                timestamp_utc=timestamp,
                assessment_id=assessment_id,
                actor=actor,
                payload_digest=payload_digest,
                previous_hash=previous_hash,
                current_hash="",
            )
            current_hash = compute_event_hash(event)
            event = event.model_copy(update={"current_hash": current_hash})

        # Persist
        self._chain.append(event)
        self._payloads.insert(event.event_id, effective_payload)

        log.debug(
            "Audit event appended: id=%s type=%s hash=%s",
            event.event_id, event_type.value, event.current_hash[:16],
        )
        return event

    def verify_event_signature(
        self,
        event: AuditEvent,
        payload: dict[str, Any],
        public_key: Ed25519PublicKey,
    ) -> bool:
        """
        Verify the Ed25519 signature stored in *payload*.

        The signature covers the pre-signature current_hash stored in
        payload["__pre_sig_hash"].  This is the current_hash that was
        computed from the unsigned payload and unsigned event fields
        before the signature was added.

        Returns True iff:
          1. The signature and __pre_sig_hash are present in payload
          2. The expected pre-signature hash recomputed from *event* and
             the unsigned payload matches payload["__pre_sig_hash"]
          3. The Ed25519 signature over that hash verifies with *public_key*
        """
        from backend.infra.crypto import verify as crypto_verify
        sig_hex = payload.get("__signature")
        pre_sig_hash = payload.get("__pre_sig_hash")
        if not sig_hex or not pre_sig_hash:
            return False
        if not isinstance(sig_hex, str) or not isinstance(pre_sig_hash, str):
            return False

        try:
            # Reconstruct unsigned payload by stripping signing metadata
            unsigned_payload = {
                k: v for k, v in payload.items()
                if not k.startswith("__")
            }
            recomputed_unsigned_digest = compute_payload_digest(unsigned_payload)

            # Reconstruct the unsigned event representation as signed in Phase 1
            unsigned_event = AuditEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                timestamp_utc=event.timestamp_utc,
                assessment_id=event.assessment_id,
                actor=event.actor,
                payload_digest=recomputed_unsigned_digest,
                previous_hash=event.previous_hash,
                current_hash="",
            )
            expected_pre_sig_hash = compute_event_hash(unsigned_event)

            # 1. Cryptographically bind pre_sig_hash to this event and payload
            if pre_sig_hash != expected_pre_sig_hash:
                return False

            # 2. Verify the Ed25519 signature over the expected pre-signature hash
            return crypto_verify(public_key, expected_pre_sig_hash, sig_hex)
        except Exception as exc:
            log.warning("verify_event_signature encountered an error: %s", exc)
            return False


    # ------------------------------------------------------------------
    # Convenience factories for specific event types
    # ------------------------------------------------------------------

    def record_assessment_created(
        self,
        assessment_id: str,
        title: str,
        assessment_type: str = "live",
        actor: str = "system",
    ) -> AuditEvent:
        return self.emit_event(
            AuditEventType.ASSESSMENT_CREATED,
            payload={
                "assessment_id": assessment_id,
                "title": title,
                "assessment_type": assessment_type,
            },
            assessment_id=assessment_id,
            actor=actor,
        )

    def record_asset_registered(
        self,
        assessment_id: str,
        asset_id: str,
        asset_type: str,
        name: str,
        sha256: str,
        size_bytes: int,
        actor: str = "system",
    ) -> AuditEvent:
        return self.emit_event(
            AuditEventType.ASSET_REGISTERED,
            payload={
                "assessment_id": assessment_id,
                "asset_id":      asset_id,
                "asset_type":    asset_type,
                "name":          name,
                "sha256":        sha256,
                "size_bytes":    size_bytes,
            },
            assessment_id=assessment_id,
            actor=actor,
        )

    def record_ingestion_complete(
        self,
        assessment_id: str,
        dataset_id: str,
        sample_count: int,
        actor: str = "system",
    ) -> AuditEvent:
        return self.emit_event(
            AuditEventType.INGESTION_COMPLETE,
            payload={
                "assessment_id": assessment_id,
                "dataset_id":    dataset_id,
                "sample_count":  sample_count,
            },
            assessment_id=assessment_id,
            actor=actor,
        )

    def record_detector_complete(
        self,
        assessment_id: str,
        asset_id: str,
        detector_id: str,
        detector_version: str,
        status: str,
        findings_count: int,
        evidence_count: int,
        duration_ms: int | None,
        result_id: str,
        actor: str = "system",
        private_key: Ed25519PrivateKey | None = None,
    ) -> AuditEvent:
        """
        Record the completion of a detector run.

        Stores compact metadata — not the full findings payload.
        Links by result_id, detector_id, asset_id so findings can be
        retrieved from the findings repository when needed.
        """
        return self.emit_event(
            AuditEventType.DETECTOR_COMPLETE,
            payload={
                "assessment_id":    assessment_id,
                "asset_id":         asset_id,
                "detector_id":      detector_id,
                "detector_version": detector_version,
                "status":           status,
                "findings_count":   findings_count,
                "evidence_count":   evidence_count,
                "duration_ms":      duration_ms,
                "result_id":        result_id,
            },
            assessment_id=assessment_id,
            actor=actor,
            private_key=private_key,
        )

    def record_provenance_verified(
        self,
        assessment_id: str,
        manifest_id: str,
        valid: bool,
        risk_level: str,
        confidence_level: str,
        finding_count: int,
        actor: str = "system",
        private_key: Ed25519PrivateKey | None = None,
    ) -> AuditEvent:
        event_type = (
            AuditEventType.PROVENANCE_VERIFIED if valid
            else AuditEventType.PROVENANCE_TAMPERED
        )
        return self.emit_event(
            event_type,
            payload={
                "assessment_id":   assessment_id,
                "manifest_id":     manifest_id,
                "valid":           valid,
                "risk_level":      risk_level,
                "confidence_level": confidence_level,
                "finding_count":   finding_count,
            },
            assessment_id=assessment_id,
            actor=actor,
            private_key=private_key,
        )

    def record_audit_verified(
        self,
        assessment_id: str | None,
        events_checked: int,
        chain_valid: bool,
        failure_count: int,
        first_invalid_event_id: str | None,
        actor: str = "system",
    ) -> AuditEvent:
        """
        Record the result of a chain verification run.

        This event itself becomes part of the chain, so each
        audit verification adds one more event to verify next time.
        """
        return self.emit_event(
            AuditEventType.AUDIT_VERIFIED,
            payload={
                "assessment_id":          assessment_id,
                "events_checked":         events_checked,
                "chain_valid":            chain_valid,
                "failure_count":          failure_count,
                "first_invalid_event_id": first_invalid_event_id,
            },
            assessment_id=assessment_id,
            actor=actor,
        )
