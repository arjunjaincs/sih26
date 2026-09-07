"""
PRAMAAN fixture data — baseline clean pipeline state and all 7 attack scenario mutations.

All findings use terminology consistent with published adversarial ML research:
- Neural Cleanse (Wang et al., 2019) for backdoor detection
- STRIP (Gao et al., 2019) for run-time trojan detection
- Spectral Signatures (Tran et al., 2018) for poisoning detection
- JPEG compression / input-transformation defences for inference tampering
"""
from __future__ import annotations
import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.models.schemas import AttackScenario, RiskLevel, StageFinding, StageState


# ---------------------------------------------------------------------------
# Deterministic hash helpers
# ---------------------------------------------------------------------------

def _stage_hash(stage_data: Dict[str, Any]) -> str:
    """Return a reproducible SHA-256 prefix for a stage state snapshot."""
    blob = json.dumps(stage_data, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def _finding_hash(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Baseline clean pipeline — all 5 stages, no active attack
# ---------------------------------------------------------------------------

BASELINE: List[Dict[str, Any]] = [
    {
        "stage_id": "stage_1",
        "stage_name": "Training Data",
        "risk": RiskLevel.CLEAN,
        "confidence": 0.97,
        "coverage_pct": 98.4,
        "findings": [
            {
                "finding_id": "F-TD-001",
                "severity": RiskLevel.LOW,
                "detector": "Spectral Signature Analysis",
                "description": (
                    "Spectral signature scan of class-conditional feature representations "
                    "identifies a marginal cluster dispersion anomaly in class-7 (night-scene) "
                    "samples. Singular value decomposition of the activation covariance matrix "
                    "shows no statistically significant separability (p=0.43) between clean "
                    "and flagged samples. Consistent with natural long-tail variance in "
                    "low-illumination capture conditions. No poisoning signal detected."
                ),
                "evidence_hash": _finding_hash("td-spectral-baseline"),
                "mitigated": True,
            }
        ],
    },
    {
        "stage_id": "stage_2",
        "stage_name": "Model",
        "risk": RiskLevel.CLEAN,
        "confidence": 0.94,
        "coverage_pct": 100.0,
        "findings": [],
    },
    {
        "stage_id": "stage_3",
        "stage_name": "Inference",
        "risk": RiskLevel.CLEAN,
        "confidence": 0.91,
        "coverage_pct": 95.6,
        "findings": [
            {
                "finding_id": "F-INF-001",
                "severity": RiskLevel.LOW,
                "detector": "STRIP Entropy Monitor",
                "description": (
                    "STRIP runtime entropy analysis records a transient entropy dip "
                    "(H=1.82 nats, baseline μ=2.41) across 3 consecutive inference "
                    "frames during a 40-minute observation window. Spike does not "
                    "exceed the adaptive threshold τ=1.65 and is attributable to "
                    "scene homogeneity during camera pan. No persistent activation "
                    "pattern consistent with trojan trigger detected."
                ),
                "evidence_hash": _finding_hash("inf-strip-baseline"),
                "mitigated": True,
            }
        ],
    },
    {
        "stage_id": "stage_4",
        "stage_name": "Evidence & Risk Engine",
        "risk": RiskLevel.CLEAN,
        "confidence": 0.99,
        "coverage_pct": 100.0,
        "findings": [],
    },
    {
        "stage_id": "stage_5",
        "stage_name": "Assurance Report",
        "risk": RiskLevel.CLEAN,
        "confidence": 0.99,
        "coverage_pct": 100.0,
        "findings": [],
    },
]


# ---------------------------------------------------------------------------
# Attack scenario delta patches
# Each entry specifies stage mutations to apply over the baseline.
# ---------------------------------------------------------------------------

SCENARIO_PATCHES: Dict[AttackScenario, List[Dict[str, Any]]] = {

    AttackScenario.LABEL_MANIPULATION: [
        {
            "stage_id": "stage_1",
            "risk": RiskLevel.HIGH,
            "confidence": 0.88,
            "findings": [
                {
                    "finding_id": "F-TD-LM-001",
                    "severity": RiskLevel.HIGH,
                    "detector": "Confident Learning (CL) Label-Error Estimator",
                    "description": (
                        "Confident Learning cross-validation estimates 6.3 % label error rate "
                        "in the vehicle detection class — 4.1× above the acceptable threshold "
                        "of 1.5 %. Out-of-distribution softmax confidence histograms show a "
                        "bimodal distribution (peaks at p=0.31 and p=0.89) inconsistent with "
                        "clean single-annotator labelling. Cluster analysis reveals 214 samples "
                        "where the ground-truth label and model-predicted soft-label diverge "
                        "by >40 %, a pattern consistent with systematic adversarial relabelling."
                    ),
                    "evidence_hash": _finding_hash("td-label-manip-001"),
                    "mitigated": False,
                },
                {
                    "finding_id": "F-TD-LM-002",
                    "severity": RiskLevel.MEDIUM,
                    "detector": "Inter-Annotator Agreement Audit",
                    "description": (
                        "Fleiss κ inter-annotator agreement score drops to κ=0.41 (fair) "
                        "for the affected class, compared to κ=0.79 (substantial) across "
                        "all other classes. Temporal metadata audit shows the anomalous "
                        "labels were submitted within a 22-minute burst window from a single "
                        "annotator session — inconsistent with organic labelling workflows."
                    ),
                    "evidence_hash": _finding_hash("td-label-manip-002"),
                    "mitigated": False,
                },
            ],
        },
        {"stage_id": "stage_4", "risk": RiskLevel.HIGH, "confidence": 0.87, "findings": []},
    ],

    AttackScenario.DUPLICATE_FLOODING: [
        {
            "stage_id": "stage_1",
            "risk": RiskLevel.MEDIUM,
            "confidence": 0.91,
            "findings": [
                {
                    "finding_id": "F-TD-DF-001",
                    "severity": RiskLevel.MEDIUM,
                    "detector": "Perceptual Hash Deduplication (pHash + dHash ensemble)",
                    "description": (
                        "Perceptual hash ensemble (pHash + dHash) identifies 1,847 near-duplicate "
                        "sample clusters with pairwise Hamming distance ≤4 bits, representing "
                        "18.7 % of the declared unique training corpus. SSIM analysis confirms "
                        "mean structural similarity of 0.994 within clusters — effectively "
                        "identical frames. Overrepresentation of a single scene geometry biases "
                        "the learned feature manifold and inflates per-class accuracy metrics "
                        "without genuine generalisation gain."
                    ),
                    "evidence_hash": _finding_hash("td-dup-flood-001"),
                    "mitigated": False,
                }
            ],
        }
    ],

    AttackScenario.BACKDOOR_INJECTION: [
        {
            "stage_id": "stage_1",
            "risk": RiskLevel.CRITICAL,
            "confidence": 0.96,
            "findings": [
                {
                    "finding_id": "F-TD-BI-001",
                    "severity": RiskLevel.CRITICAL,
                    "detector": "Spectral Signature Analysis + Neural Cleanse Reverse Engineering",
                    "description": (
                        "Spectral signature decomposition (Tran et al., 2018) isolates a learned "
                        "feature cluster with anomalous singular value λ_max=47.3 (baseline: 11.8) "
                        "concentrated in 0.4 % of training samples — a strong indicator of "
                        "distributed backdoor poisoning. Neural Cleanse reverse-engineering of "
                        "the model weight space recovers a 5×5 pixel patch trigger pattern with "
                        "L1 norm=12.4, well below the clean-model baseline of L1=38.7, confirming "
                        "a minimal, surgically inserted trigger. Trigger activates target class "
                        "prediction with confidence p=0.9997 on 100 % of tested trigger-embedded "
                        "samples."
                    ),
                    "evidence_hash": _finding_hash("td-backdoor-001"),
                    "mitigated": False,
                }
            ],
        },
        {
            "stage_id": "stage_2",
            "risk": RiskLevel.CRITICAL,
            "confidence": 0.98,
            "findings": [
                {
                    "finding_id": "F-MD-BI-001",
                    "severity": RiskLevel.CRITICAL,
                    "detector": "Neural Cleanse Weight-Space Inversion",
                    "description": (
                        "Neural Cleanse optimisation converges on a trigger pattern with anomaly "
                        "index AI=3.41 (threshold: AI>2 indicates backdoor). Weight-space probing "
                        "reveals a distinct internal representation pathway — neurons {L12:847, "
                        "L12:1203, L13:91} exhibit activation amplitudes 6.8σ above the clean "
                        "neuron distribution when the recovered trigger is presented. The "
                        "pathway is absent in reference clean-room models trained on identical "
                        "declared architecture. Model integrity SHA-256 does not match the "
                        "certified training-run checkpoint hash."
                    ),
                    "evidence_hash": _finding_hash("md-backdoor-001"),
                    "mitigated": False,
                }
            ],
        },
        {"stage_id": "stage_3", "risk": RiskLevel.HIGH, "confidence": 0.91, "findings": [
            {
                "finding_id": "F-INF-BI-001",
                "severity": RiskLevel.HIGH,
                "detector": "STRIP Run-time Trojan Detector",
                "description": (
                    "STRIP superimposition test detects a persistent low-entropy region "
                    "(H=0.94 nats) across 100 random superimposition perturbations for frames "
                    "containing a pattern matching the recovered trigger geometry. Clean frames "
                    "yield entropy H≈2.37 nats (σ=0.18). The entropy gap Δ=1.43 nats exceeds "
                    "the STRIP decision boundary τ=0.80, confirming live backdoor activation "
                    "at inference time."
                ),
                "evidence_hash": _finding_hash("inf-backdoor-001"),
                "mitigated": False,
            }
        ]},
        {"stage_id": "stage_4", "risk": RiskLevel.CRITICAL, "confidence": 0.97, "findings": []},
    ],

    AttackScenario.MODEL_SUBSTITUTION: [
        {
            "stage_id": "stage_2",
            "risk": RiskLevel.CRITICAL,
            "confidence": 0.99,
            "findings": [
                {
                    "finding_id": "F-MD-MS-001",
                    "severity": RiskLevel.CRITICAL,
                    "detector": "Cryptographic Weight Integrity Verifier",
                    "description": (
                        "SHA-256 hash of the deployed model weight file (ckpt_deploy.pt) "
                        "does not match the certified training-run checkpoint recorded in "
                        "the immutable audit ledger. Hamming distance between parameter "
                        "tensors is 0 for layers L1–L8 and non-zero for L9–L16, consistent "
                        "with a surgical graft attack where only the task-head and final "
                        "feature extraction layers have been replaced. The substituted layers "
                        "share architectural signatures with a publicly known adversarial "
                        "model variant flagged in CVE-ML-2025-0312."
                    ),
                    "evidence_hash": _finding_hash("md-substitution-001"),
                    "mitigated": False,
                }
            ],
        },
        {"stage_id": "stage_4", "risk": RiskLevel.CRITICAL, "confidence": 0.98, "findings": []},
    ],

    AttackScenario.INFERENCE_TAMPERING: [
        {
            "stage_id": "stage_3",
            "risk": RiskLevel.HIGH,
            "confidence": 0.89,
            "findings": [
                {
                    "finding_id": "F-INF-IT-001",
                    "severity": RiskLevel.HIGH,
                    "detector": "Input Transformation Consistency Checker",
                    "description": (
                        "Adaptive input-transformation defence (JPEG compression at q=75, "
                        "bit-depth reduction to 4bpc) causes a mean prediction shift of 0.61 "
                        "in top-1 confidence across 1,200 test frames. Clean models exhibit "
                        "shift ≤0.08 under identical transformations (σ=0.03). The elevated "
                        "sensitivity is consistent with gradient-masking or adversarial "
                        "perturbation tuned to the undefended inference pipeline. L∞ norm "
                        "analysis confirms 34 frames contain perturbations exceeding ε=8/255 "
                        "— the standard imperceptibility bound."
                    ),
                    "evidence_hash": _finding_hash("inf-tamper-001"),
                    "mitigated": False,
                }
            ],
        },
        {"stage_id": "stage_4", "risk": RiskLevel.HIGH, "confidence": 0.88, "findings": []},
    ],

    AttackScenario.REPLAY_ATTACK: [
        {
            "stage_id": "stage_3",
            "risk": RiskLevel.HIGH,
            "confidence": 0.93,
            "findings": [
                {
                    "finding_id": "F-INF-RA-001",
                    "severity": RiskLevel.HIGH,
                    "detector": "Temporal Consistency & Frame Sequence Validator",
                    "description": (
                        "Frame sequence timestamp audit detects 47 replay windows where "
                        "optical-flow divergence between consecutive frames drops below "
                        "the sensor-noise floor (mean flow magnitude μ=0.003 px/frame, "
                        "expected μ≥0.41 for live feed). Scene hash comparison confirms "
                        "the injected segments are verbatim duplicates of frames captured "
                        "18 minutes prior — consistent with a buffered replay attack "
                        "designed to mask real-time physical activity from the vision pipeline."
                    ),
                    "evidence_hash": _finding_hash("inf-replay-001"),
                    "mitigated": False,
                }
            ],
        },
        {"stage_id": "stage_4", "risk": RiskLevel.HIGH, "confidence": 0.92, "findings": []},
    ],

    AttackScenario.DISTRIBUTION_SHIFT: [
        {
            "stage_id": "stage_1",
            "risk": RiskLevel.MEDIUM,
            "confidence": 0.84,
            "findings": [
                {
                    "finding_id": "F-TD-DS-001",
                    "severity": RiskLevel.MEDIUM,
                    "detector": "Maximum Mean Discrepancy (MMD) Drift Detector",
                    "description": (
                        "Maximum Mean Discrepancy computed between the certified training "
                        "distribution and the current operational data stream yields "
                        "MMD²=0.087 (rejection threshold: 0.05 at α=0.01). Kernel PCA "
                        "visualisation shows the operational embedding cloud has drifted "
                        "~2.3σ along the principal scene-illumination axis — consistent "
                        "with a seasonal or environmental shift not represented in the "
                        "original training corpus. Model accuracy is expected to degrade "
                        "by 12–18 % on out-of-distribution samples until retraining."
                    ),
                    "evidence_hash": _finding_hash("td-drift-001"),
                    "mitigated": False,
                }
            ],
        },
        {
            "stage_id": "stage_3",
            "risk": RiskLevel.MEDIUM,
            "confidence": 0.80,
            "findings": [
                {
                    "finding_id": "F-INF-DS-001",
                    "severity": RiskLevel.MEDIUM,
                    "detector": "Inference Confidence Calibration Monitor",
                    "description": (
                        "Expected Calibration Error (ECE) on the live inference stream "
                        "has risen to ECE=0.19 (baseline ECE=0.04), indicating the model's "
                        "softmax confidence scores are poorly calibrated for the shifted "
                        "input distribution. Reliability diagram shows systematic "
                        "overconfidence in the 0.7–0.9 probability bin — a known failure "
                        "mode when models are deployed outside their training manifold."
                    ),
                    "evidence_hash": _finding_hash("inf-drift-001"),
                    "mitigated": False,
                }
            ],
        },
        {"stage_id": "stage_4", "risk": RiskLevel.MEDIUM, "confidence": 0.83, "findings": []},
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_stages(active_scenarios: list[AttackScenario]) -> list[dict]:
    """
    Return the full 5-stage list with all applicable scenario patches merged in.
    Findings are deduplicated by finding_id; risk escalates to the worst level.
    """
    RISK_ORDER = [
        RiskLevel.CLEAN, RiskLevel.LOW, RiskLevel.MEDIUM,
        RiskLevel.HIGH, RiskLevel.CRITICAL,
    ]

    def escalate(current: RiskLevel, incoming: RiskLevel) -> RiskLevel:
        return incoming if RISK_ORDER.index(incoming) > RISK_ORDER.index(current) else current

    stages = copy.deepcopy(BASELINE)
    stage_map = {s["stage_id"]: s for s in stages}

    for scenario in active_scenarios:
        patches = SCENARIO_PATCHES.get(scenario, [])
        for patch in patches:
            sid = patch["stage_id"]
            if sid not in stage_map:
                continue
            target = stage_map[sid]
            target["risk"] = escalate(target["risk"], patch["risk"])
            target["confidence"] = min(target["confidence"], patch.get("confidence", 1.0))
            existing_ids = {f["finding_id"] for f in target["findings"]}
            for f in patch.get("findings", []):
                if f["finding_id"] not in existing_ids:
                    target["findings"].append(copy.deepcopy(f))

    # Attach deterministic audit hashes after all mutations
    for stage in stages:
        stage["audit_hash"] = _stage_hash(stage)

    return stages
