"""
PRAMAAN v1 — Machine-Readable Structured JSON Exporter.

Serializes an assessment into an offline, portable, machine-readable JSON
assurance package containing metadata, assets, findings, evidence references,
provenance, and audit trail.

Enforces zero leakage of server filesystem paths, private keys, API keys,
or raw artifact binary bytes.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.api.errors import AssessmentNotFound
from backend.reporting.extractor import extract_report_data_from_db
from backend.reporting.formatting import censor_paths
from backend.reporting.models import AssuranceReportData

_SECRET_KEY_PATTERN = re.compile(
    r"(?:api_?key|secret|private_?key|token|password|auth(?:orization)?|credential)",
    re.IGNORECASE,
)
_SECRET_VAL_PATTERN = re.compile(
    r"(?:sk-[a-zA-Z0-9_\-]{20,}|ghp_[a-zA-Z0-9]{30,}|Bearer\s+[a-zA-Z0-9_\-\.]+)",
    re.IGNORECASE,
)


def _sanitize_json_tree(node: Any) -> Any:
    """
    Recursively sanitize JSON data:
    - Removes filesystem paths via censor_paths.
    - Masks any known API key or credential string pattern.
    - Strips secret dictionary keys.
    - Sanitizes non-finite floats (NaN, Inf) to None (JSON null) for strict RFC 8259 compliance.
    """
    if isinstance(node, str):
        censored = censor_paths(node)
        masked = _SECRET_VAL_PATTERN.sub("[REDACTED_SECRET]", censored)
        return masked
    elif isinstance(node, dict):
        sanitized: dict[str, Any] = {}
        for k, v in node.items():
            if _SECRET_KEY_PATTERN.search(k):
                continue
            sanitized[k] = _sanitize_json_tree(v)
        return sanitized
    elif isinstance(node, (list, tuple)):
        return [_sanitize_json_tree(item) for item in node]
    elif isinstance(node, float):
        if math.isnan(node) or math.isinf(node):
            return None
        return node
    elif isinstance(node, (int, bool)) or node is None:
        return node
    else:
        return str(node)


def build_assessment_export_dict(report_data: AssuranceReportData) -> dict[str, Any]:
    """
    Transform normalized AssuranceReportData into the canonical PRAMAAN
    machine-readable JSON export structure.
    """
    meta = report_data.meta

    # 1. Assessment metadata
    assessment_meta = {
        "assessment_id": meta.assessment_id,
        "title": meta.title,
        "status": meta.status,
        "software_version": meta.software_version,
        "created_at": meta.created_at,
        "started_at": meta.started_at,
        "completed_at": meta.completed_at,
        "overall_risk": meta.overall_risk,
        "risk_qualitative": meta.risk_qualitative,
        "overall_confidence": meta.overall_confidence,
        "confidence_qualifier": meta.confidence_qualifier,
        "coverage_fraction": meta.coverage_fraction,
        "error": meta.error,
    }

    # 2. Recommended disposition
    disposition = {
        "recommended_disposition": report_data.recommended_disposition,
        "rationale": report_data.disposition_rationale,
    }

    # 3. Assets
    assets_list = [
        {
            "asset_id": a.asset_id,
            "asset_type": a.asset_type,
            "name": a.name,
            "sha256": a.sha256,
            "size_bytes": a.size_bytes,
            "format": a.format,
            "details": a.details,
        }
        for a in report_data.assets
    ]

    # 4. Detector battery
    total_dets = len(report_data.detectors)
    executed_count = sum(1 for d in report_data.detectors if d.status not in ("NOT_APPLICABLE", "SKIPPED"))
    skipped_count = total_dets - executed_count

    battery_info = {
        "total_detectors": total_dets,
        "executed_count": executed_count,
        "skipped_count": skipped_count,
        "detectors": [
            {
                "detector_id": d.detector_id,
                "detector_name": d.detector_name,
                "category": d.category,
                "status": d.status,
                "risk_level": d.risk_level,
                "confidence_level": d.confidence_level,
                "findings_count": d.findings_count,
                "evidence_count": d.evidence_count,
                "error": d.error,
            }
            for d in report_data.detectors
        ],
    }

    # 5. Coverage gaps
    coverage_gaps = [
        {
            "detector_id": g.detector_id,
            "detector_name": g.detector_name,
            "reason": g.reason,
            "required_capability": g.required_capability,
            "observed_capability": g.observed_capability,
            "impact": g.impact,
            "recommended_action": g.recommended_action,
        }
        for g in report_data.coverage_gaps
    ]

    # 6. Findings & Evidence
    findings_list = []
    for f in report_data.findings:
        evidence_items = [
            {
                "evidence_id": e.evidence_id,
                "detector_id": e.detector_id,
                "evidence_type": e.evidence_type,
                "description": e.description,
                "data": _sanitize_json_tree(e.data),
            }
            for e in f.evidence
        ]
        findings_list.append(
            {
                "finding_id": f.finding_id,
                "asset_id": f.asset_id,
                "detector_id": f.detector_id,
                "category": f.category,
                "subcategory": f.subcategory,
                "severity": f.severity,
                "title": f.title,
                "description": f.description,
                "limitations": f.limitations,
                "recommended_disposition": f.recommended_disposition,
                "evidence": evidence_items,
            }
        )

    # 7. Provenance
    provenance_dict: dict[str, Any] | None = None
    if report_data.provenance:
        p = report_data.provenance
        provenance_dict = {
            "has_provenance": True,
            "manifest_id": p.manifest_id,
            "assessment_id": p.assessment_id,
            "input_sha256": p.input_sha256,
            "model_sha256": p.model_sha256,
            "output_sha256": p.output_sha256,
            "preprocessing_config": _sanitize_json_tree(p.preprocessing_config),
            "inference_config": _sanitize_json_tree(p.inference_config),
            "timestamp_utc": p.timestamp_utc,
            "nonce": p.nonce,
            "sequence": p.sequence,
            "digest": p.digest,
            "signature_status": p.signature_status,
            "replay_status": p.replay_status,
            "anomalies": p.anomalies,
        }
    else:
        provenance_dict = {
            "has_provenance": False,
            "manifest_id": None,
            "signature_status": "NOT_PROVIDED",
            "replay_status": "NOT_EVALUATED",
            "anomalies": [],
        }

    # 8. Audit verification
    audit_dict: dict[str, Any] | None = None
    if report_data.audit:
        aud = report_data.audit
        audit_dict = {
            "chain_valid": aud.chain_valid,
            "events_checked": aud.events_checked,
            "first_invalid_event_id": aud.first_invalid_event_id,
            "failures": aud.failures,
            "first_event_hash": aud.first_event_hash,
            "last_event_hash": aud.last_event_hash,
            "events": [
                {
                    "event_id": e.get("event_id"),
                    "event_type": e.get("event_type"),
                    "timestamp_utc": e.get("timestamp_utc"),
                    "actor": e.get("actor"),
                    "current_hash": e.get("current_hash"),
                    "previous_hash": e.get("previous_hash"),
                }
                for e in aud.events
            ],
        }

    raw_package = {
        "export_format": "pramaan_assurance_export",
        "export_schema_version": "1.0.0",
        "pramaan_version": meta.software_version or "1.0.0",
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "assessment": assessment_meta,
        "disposition": disposition,
        "assets": assets_list,
        "battery": battery_info,
        "coverage_gaps": coverage_gaps,
        "limitations": report_data.limitations,
        "findings": findings_list,
        "provenance": provenance_dict,
        "audit": audit_dict,
    }

    # Final deep sanitization pass
    return _sanitize_json_tree(raw_package)


def export_assessment_json(
    conn: sqlite3.Connection,
    assessment_id: str,
) -> dict[str, Any]:
    """
    Assemble the complete machine-readable assessment assurance package
    directly from persisted SQLite repositories.

    Raises:
      AssessmentNotFound: If the assessment_id does not exist.
    """
    report_data = extract_report_data_from_db(conn, assessment_id)
    return build_assessment_export_dict(report_data)


def _evaluate_event_signature(
    event: Any,
    payload: dict[str, Any] | None,
) -> tuple[str, str | None, str | None, str | None]:
    """
    Evaluate the Ed25519 signature on an audit event payload.

    Returns:
      (signature_status, pre_signature_hash, signing_key_id, signature)
      signature_status is one of: "verified" | "invalid" | "unsigned"
    """
    if not payload or not isinstance(payload, dict):
        return ("unsigned", None, None, None)

    sig_hex = payload.get("__signature")
    pre_sig_hash = payload.get("__pre_sig_hash")
    signing_key_id = payload.get("__signing_key_id")

    if not sig_hex or not pre_sig_hash or not signing_key_id:
        return ("unsigned", None, None, None)

    if not isinstance(sig_hex, str) or not isinstance(pre_sig_hash, str) or not isinstance(signing_key_id, str):
        return ("invalid", str(pre_sig_hash) if pre_sig_hash else None, str(signing_key_id) if signing_key_id else None, str(sig_hex) if sig_hex else None)

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from backend.audit.hashing import compute_event_hash, compute_payload_digest
        from backend.domain.entities import AuditEvent
        from backend.infra.crypto import verify as crypto_verify

        # 1. Strip transient signing metadata keys from payload to evaluate unsigned digest
        unsigned_payload = {
            k: v for k, v in payload.items()
            if not k.startswith("__")
        }
        recomputed_unsigned_digest = compute_payload_digest(unsigned_payload)

        # 2. Reconstruct the unsigned event representation to verify against pre_sig_hash
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

        if pre_sig_hash != expected_pre_sig_hash:
            return ("invalid", pre_sig_hash, signing_key_id, sig_hex)

        # 3. Verify signature with Ed25519 public key
        pub_bytes = bytes.fromhex(signing_key_id)
        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        is_valid = crypto_verify(pub_key, expected_pre_sig_hash, sig_hex)
        status = "verified" if is_valid else "invalid"
        return (status, pre_sig_hash, signing_key_id, sig_hex)
    except Exception:
        return ("invalid", pre_sig_hash, signing_key_id, sig_hex)


def export_audit_trail_json(
    conn: sqlite3.Connection,
    assessment_id: str,
) -> dict[str, Any]:
    """
    Assemble the complete machine-readable verified audit trail export package
    directly from persisted SQLite repositories without mutating any state.

    Raises:
      AssessmentNotFound: If the assessment_id does not exist.
    """
    from backend.audit.verifier import ChainVerifier
    from backend.infra.db import (
        AssessmentRepository,
        AuditPayloadRepository,
        AuditRepository,
    )

    assessment_repo = AssessmentRepository(conn)
    asm = assessment_repo.get(assessment_id)
    if asm is None:
        raise AssessmentNotFound(assessment_id)

    audit_repo = AuditRepository(conn)
    payload_repo = AuditPayloadRepository(conn)

    # 1. Run authoritative ChainVerifier
    verifier = ChainVerifier(audit_repo, payload_repo)
    chain_result = verifier.verify_assessment(assessment_id)

    # 2. Retrieve sequential audit events for this assessment
    events = audit_repo.list_by_assessment(assessment_id)
    event_ids = [e.event_id for e in events]
    payloads = payload_repo.get_all_for_events(event_ids) if event_ids else {}

    # 3. Genesis linkage
    genesis_hash = AuditRepository.GENESIS_HASH
    is_first_genesis = (
        events[0].previous_hash == genesis_hash
        if events else None
    )

    # 4. Format verification info truthfully from ChainVerifier
    verification_info = {
        "chain_valid": chain_result.valid,
        "events_checked": chain_result.events_checked,
        "verified_at": chain_result.verified_at,
        "first_invalid_event_id": chain_result.first_invalid_event_id,
        "failure_count": len(chain_result.failures),
        "failures": [
            f.description if hasattr(f, "description") else str(f)
            for f in chain_result.failures
        ],
        "failure_details": [
            f.to_dict() if hasattr(f, "to_dict") else {"description": str(f)}
            for f in chain_result.failures
        ],
    }

    # 5. Process events sequentially
    processed_events = []
    for seq_idx, event in enumerate(events, start=1):
        raw_payload = payloads.get(event.event_id, {})
        sig_status, pre_sig_hash, signing_key_id, signature = _evaluate_event_signature(
            event, raw_payload
        )

        clean_payload = {
            k: v for k, v in raw_payload.items()
            if not k.startswith("__")
        }

        processed_events.append({
            "sequence": seq_idx,
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "timestamp_utc": event.timestamp_utc,
            "actor": event.actor,
            "assessment_id": event.assessment_id,
            "current_hash": event.current_hash,
            "previous_hash": event.previous_hash,
            "payload_digest": event.payload_digest,
            "pre_signature_hash": pre_sig_hash,
            "signature_status": sig_status,
            "signing_key_id": signing_key_id,
            "signature": signature,
            "payload": _sanitize_json_tree(clean_payload),
        })

    summary = {
        "total_events": len(events),
        "first_event_id": events[0].event_id if events else None,
        "last_event_id": events[-1].event_id if events else None,
        "first_event_hash": events[0].current_hash if events else None,
        "last_event_hash": events[-1].current_hash if events else None,
    }

    raw_export = {
        "export_format": "pramaan-audit-export-v1",
        "specification": "AT-01: Tamper-Evident Append-Only Audit Trail Ledger",
        "pramaan_version": asm.software_version or "1.0.0",
        "is_verification_artifact": True,
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "assessment_id": assessment_id,
        "genesis": {
            "genesis_hash": genesis_hash,
            "is_first_event_genesis_linked": is_first_genesis,
        },
        "verification": verification_info,
        "summary": summary,
        "events": processed_events,
    }

    # Final deep sanitization pass (ensures zero leakage of paths or secrets anywhere)
    return _sanitize_json_tree(raw_export)
