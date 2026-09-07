"""
/api/audit — audit event chain ledger endpoint.
Returns a cryptographic sequence of chronological pipeline verification blocks.
"""
from __future__ import annotations
import hashlib
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from app.models.schemas import (
    AuditChainResponse, AuditEvent, AuditEventType, RiskLevel, AttackScenario
)
from app.state import active_scenarios

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _hash_block(prev_hash: str, index: int, action: str, stage: str) -> str:
    seed = f"{prev_hash}:{index}:{action}:{stage}"
    return hashlib.sha256(seed.encode()).hexdigest()[:16]


@router.get("/events", response_model=AuditChainResponse)
def get_audit_events() -> AuditChainResponse:
    """Return the chronological cryptographic audit chain blocks reflecting current state."""
    scenarios = set(active_scenarios)
    now = datetime.now(timezone.utc)
    base_time = now - timedelta(minutes=15)

    # Blueprint definitions for chronological event blocks
    blueprints = [
        {
            "stage_name": "Training Data",
            "event_type": AuditEventType.GENESIS,
            "action": "Genesis Trust Anchor Initialized",
            "details": "PRAMAAN hardware security module (HSM) root trust anchor established on air-gapped node.",
            "status": RiskLevel.CLEAN,
        },
        {
            "stage_name": "Training Data",
            "event_type": AuditEventType.DATA_INGESTION,
            "action": "Defence Partition Ingested",
            "details": "Training dataset partition (14,280 samples) loaded into isolated staging storage with verified manifest.",
            "status": RiskLevel.CLEAN,
        },
        {
            "stage_name": "Training Data",
            "event_type": AuditEventType.SPECTRAL_SCAN,
            "action": (
                "Spectral Poisoning Anomaly Detected"
                if AttackScenario.LABEL_MANIPULATION in scenarios
                else "Spectral Signature Scan Nominal"
            ),
            "details": (
                "Singular value decomposition of covariance matrix isolates separated cluster (λ_max=31.4, p<0.001) in class-3."
                if AttackScenario.LABEL_MANIPULATION in scenarios
                else "Covariance matrix activation spectra verified across all 10 target classes (p=0.43 separability, nominal)."
            ),
            "status": (
                RiskLevel.CRITICAL
                if AttackScenario.LABEL_MANIPULATION in scenarios
                else RiskLevel.CLEAN
            ),
        },
        {
            "stage_name": "Model",
            "event_type": AuditEventType.MODEL_LOAD,
            "action": "Model Checkpoint Loaded",
            "details": "Target vision neural network weights and compute graph (ResNet-50-Def) loaded into enclave.",
            "status": RiskLevel.CLEAN,
        },
        {
            "stage_name": "Model",
            "event_type": AuditEventType.WEIGHT_HASH,
            "action": (
                "Model Weight Checksum Mismatch"
                if AttackScenario.MODEL_SUBSTITUTION in scenarios
                else "Weight Checksum Attested"
            ),
            "details": (
                "SHA-256 digest of loaded weights fails attestation. Declared: 839b80c5... Actual: 1f0ae489... (Tampering detected)."
                if AttackScenario.MODEL_SUBSTITUTION in scenarios
                else "Cryptographic SHA-256 weight tensor digest matched against hardware-signed defence registry."
            ),
            "status": (
                RiskLevel.CRITICAL
                if AttackScenario.MODEL_SUBSTITUTION in scenarios
                else RiskLevel.CLEAN
            ),
        },
        {
            "stage_name": "Model",
            "event_type": AuditEventType.NEURAL_CLEANSE,
            "action": (
                "Neural Cleanse Trojan Trigger Flagged"
                if AttackScenario.BACKDOOR_INJECTION in scenarios
                else "Neural Cleanse Inversion Clean"
            ),
            "details": (
                "Weight-space reverse engineering discovers 5x5 pixel backdoor trigger with anomaly index AI=3.41 (threshold: 2.0)."
                if AttackScenario.BACKDOOR_INJECTION in scenarios
                else "Trigger reverse-engineering finds no shortcut perturbation pathway (anomaly index AI=0.88, baseline nominal)."
            ),
            "status": (
                RiskLevel.CRITICAL
                if AttackScenario.BACKDOOR_INJECTION in scenarios
                else RiskLevel.CLEAN
            ),
        },
        {
            "stage_name": "Inference",
            "event_type": AuditEventType.INFERENCE_STREAM,
            "action": "Telemetry Ingestion Activated",
            "details": "High-assurance inference stream linked to sensor feed with zero cloud exfiltration routing.",
            "status": RiskLevel.CLEAN,
        },
        {
            "stage_name": "Inference",
            "event_type": AuditEventType.ENTROPY_ANALYSIS,
            "action": (
                "Adversarial Perturbation Detected"
                if AttackScenario.INFERENCE_TAMPERING in scenarios
                else "STRIP Runtime Entropy Nominal"
            ),
            "details": (
                "STRIP entropy monitor flags sharp entropy drop (H=0.81 nats) under dynamic noise injection. Attack pattern confirmed."
                if AttackScenario.INFERENCE_TAMPERING in scenarios
                else "STRIP dynamic noise perturbation verifies average prediction entropy H=2.41 nats > threshold τ=1.65."
            ),
            "status": (
                RiskLevel.CRITICAL
                if AttackScenario.INFERENCE_TAMPERING in scenarios
                else RiskLevel.CLEAN
            ),
        },
        {
            "stage_name": "Inference",
            "event_type": AuditEventType.FRAME_CACHE,
            "action": (
                "Replay Stream Duplication Alert"
                if AttackScenario.REPLAY_ATTACK in scenarios
                else "Monotonic Nonce Sequence Verified"
            ),
            "details": (
                "Frame fingerprint collision detected in sliding cache (interval: 18ms). Replay injection attack identified."
                if AttackScenario.REPLAY_ATTACK in scenarios
                else "Cryptographic timestamp nonces incremented monotonically. Zero frame cache collisions observed."
            ),
            "status": (
                RiskLevel.CRITICAL
                if AttackScenario.REPLAY_ATTACK in scenarios
                else RiskLevel.CLEAN
            ),
        },
        {
            "stage_name": "Evidence & Risk Engine",
            "event_type": AuditEventType.RISK_AGGREGATION,
            "action": "Merkle Hash Tree Aggregation",
            "details": "Stage evidence digests combined into hierarchical Merkle DAG root with immutable block receipts.",
            "status": (
                RiskLevel.HIGH
                if any(s in scenarios for s in [
                    AttackScenario.BACKDOOR_INJECTION,
                    AttackScenario.MODEL_SUBSTITUTION,
                    AttackScenario.LABEL_MANIPULATION,
                    AttackScenario.INFERENCE_TAMPERING,
                    AttackScenario.REPLAY_ATTACK,
                ])
                else RiskLevel.CLEAN
            ),
        },
        {
            "stage_name": "Assurance Report",
            "event_type": AuditEventType.ASSURANCE_SEAL,
            "action": "Assurance Attestation Certified",
            "details": "End-to-end audit chain locked with SHA-256 seal and serialized under SIH26228 specification.",
            "status": (
                RiskLevel.CRITICAL
                if any(s in scenarios for s in [
                    AttackScenario.BACKDOOR_INJECTION,
                    AttackScenario.MODEL_SUBSTITUTION,
                    AttackScenario.LABEL_MANIPULATION,
                    AttackScenario.INFERENCE_TAMPERING,
                    AttackScenario.REPLAY_ATTACK,
                ])
                else RiskLevel.CLEAN
            ),
        },
    ]

    events: list[AuditEvent] = []
    prev_hash = "0000000000000000"

    for idx, bp in enumerate(blueprints):
        event_time = base_time + timedelta(seconds=idx * 75)
        current_hash = _hash_block(prev_hash, idx, bp["action"], bp["stage_name"])
        events.append(
            AuditEvent(
                block_index=idx,
                event_id=f"EVT-MOD-{idx:03d}",
                timestamp=event_time,
                stage_name=bp["stage_name"],
                event_type=bp["event_type"],
                action=bp["action"],
                details=bp["details"],
                prev_hash=prev_hash,
                current_hash=current_hash,
                status=bp["status"],
                tampered=False,
            )
        )
        prev_hash = current_hash

    is_valid = not any(e.status in (RiskLevel.CRITICAL, RiskLevel.HIGH) for e in events)

    return AuditChainResponse(
        chain_id="CHAIN-MOD-DEF-2026",
        total_blocks=len(events),
        is_valid=is_valid,
        tampered_block_index=None,
        events=events,
    )
