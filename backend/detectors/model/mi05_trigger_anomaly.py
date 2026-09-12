"""
MI-05: Model Trigger & Behavioral Perturbation Search Detector.

Detector ID : model.integrity.mi05_trigger_anomaly
Version     : 1.0.0
Category    : MODEL_INTEGRITY

What this detector does
-----------------------
Investigates whether candidate localized spatial transformations or trigger patterns
cause abnormal, consistent output behavior or Trojan-like target output convergence:
- Generates 4 diverse baseline clean probe inputs (neutral gray, horizontal ramp, vertical ramp, noise)
- Applies a bounded candidate perturbation suite:
    1. patch_top_left (high-contrast corner checkerboard)
    2. patch_bottom_right (high-contrast corner checkerboard)
    3. patch_center_mark (solid localized center patch)
    4. control_uniform_bias (uniform brightness shift, used as negative control)
- Evaluates output shift and Target Mode Convergence Ratio (CR):
    CR = PairwiseDiversity(perturbed) / PairwiseDiversity(clean)
    When CR << 1.0 and shift is elevated, diverse inputs collapse towards an invariant
    target output mode — the classic signature of backdoor / Trojan shortcut insertion.

Risk/Confidence semantics (ADR-003)
-----------------------------------
- Abnormal target convergence detected -> HIGH / HIGH
- Smooth perturbation response          -> NONE / HIGH (INFO finding)
- Non-executable model format           -> UNAVAILABLE / LOW (explicit coverage gap)

Honest engineering boundaries
-----------------------------
PRAMAAN explicitly notes that candidate trigger search tests concrete localized patch
hypotheses; it does NOT guarantee absence of blended, invisible, or complex semantic triggers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.detectors.base import (
    CanRunResult,
    DetectorContext,
    DetectorMetadata,
    DetectorOutput,
)
from backend.domain.entities import Evidence, Finding
from backend.domain.enums import (
    AssetType,
    ConfidenceLevel,
    DetectorStatus,
    EvidenceType,
    FindingCategory,
    RiskLevel,
    Severity,
)
from backend.infra.model_loader import (
    _ORT_AVAILABLE,
    _TORCH_AVAILABLE,
)

log = logging.getLogger(__name__)

_METADATA = DetectorMetadata(
    detector_id="model.integrity.mi05_trigger_anomaly",
    version="1.0.0",
    name="MI-05: Model Trigger & Behavioral Perturbation Search",
    description=(
        "Applies a bounded battery of localized candidate spatial patches and pattern "
        "perturbations across diverse inputs to detect Trojan-like target output convergence "
        "or abnormal trigger sensitivity."
    ),
    applicable_asset_types=frozenset({AssetType.MODEL.value}),
)

_SEED = 0x54524947  # 'TRIG' in hex
_CONVERGENCE_COLLAPSE_THRESHOLD = 0.15  # < 15% clean diversity -> strong convergence
_MIN_DIVERSITY_FOR_TRIGGER_ANALYSIS = 0.05


@dataclass
class PerturbationEvaluation:
    """Evaluation metrics for a candidate perturbation."""
    perturbation_name: str
    output_shift_l2: float
    perturbed_diversity_l2: float
    convergence_ratio: float
    suspicious: bool


@dataclass
class MI05Context:
    """Context for MI-05 detector execution."""
    model_path: Path
    max_model_size_bytes: int = 5 * 1024 * 1024 * 1024


def _create_clean_inputs(shape: list[int]) -> list[tuple[str, Any]]:
    """Create 4 distinct baseline clean probe inputs."""
    import numpy as np

    n_elem = int(np.prod(shape))
    # 1. Neutral mid-gray
    gray = np.full(shape, 0.5, dtype=np.float32)

    # 2. Horizontal / 1D ramp
    ramp_h = np.linspace(0.0, 1.0, n_elem, dtype=np.float32).reshape(shape)

    # 3. Inverted ramp / distinct pattern
    ramp_v = np.linspace(1.0, 0.0, n_elem, dtype=np.float32).reshape(shape)

    # 4. Seeded random texture
    rng = np.random.default_rng(_SEED)
    noise = rng.uniform(0.1, 0.9, size=shape).astype(np.float32)

    return [
        ("clean_gray", gray),
        ("clean_ramp_h", ramp_h),
        ("clean_ramp_v", ramp_v),
        ("clean_noise", noise),
    ]


def _apply_candidate_perturbation(
    base: Any,
    perturbation_name: str,
) -> Any:
    """Apply candidate trigger pattern or control perturbation to input array."""
    import numpy as np

    arr = base.copy()
    ndim = arr.ndim

    if perturbation_name == "control_uniform_bias":
        # Control: subtle +0.05 uniform shift
        return np.clip(arr + 0.05, 0.0, 1.0)

    # For 3D or 4D spatial inputs [..., H, W]
    if ndim >= 2 and arr.shape[-2] >= 4 and arr.shape[-1] >= 4:
        h = arr.shape[-2]
        w = arr.shape[-1]
        pw = max(2, min(8, w // 4))
        ph = max(2, min(8, h // 4))

        if perturbation_name == "patch_top_left":
            # Checkerboard pattern in top-left
            chk = np.indices((ph, pw)).sum(axis=0) % 2
            arr[..., :ph, :pw] = chk.astype(np.float32)
        elif perturbation_name == "patch_bottom_right":
            chk = np.indices((ph, pw)).sum(axis=0) % 2
            arr[..., h - ph:, w - pw:] = chk.astype(np.float32)
        elif perturbation_name == "patch_center_mark":
            ch = h // 2
            cw = w // 2
            arr[..., max(0, ch - ph // 2): min(h, ch + ph // 2),
                max(0, cw - pw // 2): min(w, cw + pw // 2)] = 1.0
    else:
        # 1D or flat input
        length = arr.shape[-1]
        pw = max(1, min(4, length // 4))
        if perturbation_name == "patch_top_left":
            arr[..., :pw] = 1.0
        elif perturbation_name == "patch_bottom_right":
            arr[..., length - pw:] = 1.0
        elif perturbation_name == "patch_center_mark":
            c = length // 2
            arr[..., max(0, c - pw // 2): min(length, c + pw // 2)] = 1.0

    return np.clip(arr, 0.0, 1.0)


def _compute_pairwise_diversity(outputs: list[Any]) -> float:
    """Average pairwise L2 Euclidean distance between a list of output arrays."""
    import numpy as np

    if len(outputs) < 2:
        return 0.0

    flat_outputs = [o.astype(np.float64).flatten() for o in outputs]
    dists: list[float] = []
    n = len(flat_outputs)
    for i in range(n):
        for j in range(i + 1, n):
            d = float(np.linalg.norm(flat_outputs[i] - flat_outputs[j]))
            dists.append(d)
    return float(np.mean(dists)) if dists else 0.0


def _evaluate_onnx_triggers(model_path: Path) -> tuple[float, list[PerturbationEvaluation]]:
    """Evaluate candidate trigger battery on ONNX model via ORT."""
    if not _ORT_AVAILABLE:
        raise RuntimeError("onnxruntime not installed")

    import numpy as np
    import onnxruntime as ort

    sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    inputs_meta = sess.get_inputs()
    if not inputs_meta:
        raise RuntimeError("Model has no inputs")

    primary_input = inputs_meta[0]
    shape = [d if isinstance(d, int) and d > 0 else (3 if idx == 1 and len(primary_input.shape) == 4 else 1)
             for idx, d in enumerate(primary_input.shape)]
    if len(shape) == 4 and shape[2] == 1 and shape[3] == 1:
        shape[2] = 32
        shape[3] = 32

    clean_probes = _create_clean_inputs(shape)

    # 1. Run clean probes
    clean_outputs: list[np.ndarray] = []
    for _, arr in clean_probes:
        feed = {primary_input.name: arr}
        for other_inp in inputs_meta[1:]:
            c_shape = [d if isinstance(d, int) and d > 0 else 1 for d in other_inp.shape]
            feed[other_inp.name] = np.zeros(c_shape, dtype=np.float32)
        out = sess.run(None, feed)[0]
        clean_outputs.append(out)

    clean_diversity = _compute_pairwise_diversity(clean_outputs)

    # 2. Evaluate candidate perturbations
    perturbations = [
        "control_uniform_bias",
        "patch_top_left",
        "patch_bottom_right",
        "patch_center_mark",
    ]
    evaluations: list[PerturbationEvaluation] = []
    control_shift = 0.0

    for p_name in perturbations:
        p_outputs: list[np.ndarray] = []
        shifts: list[float] = []

        for (_, clean_arr), c_out in zip(clean_probes, clean_outputs):
            perturbed_arr = _apply_candidate_perturbation(clean_arr, p_name)
            feed = {primary_input.name: perturbed_arr}
            for other_inp in inputs_meta[1:]:
                c_shape = [d if isinstance(d, int) and d > 0 else 1 for d in other_inp.shape]
                feed[other_inp.name] = np.zeros(c_shape, dtype=np.float32)

            out = sess.run(None, feed)[0]
            p_outputs.append(out)

            shift = float(np.linalg.norm(out.flatten() - c_out.flatten()))
            shifts.append(shift)

        avg_shift = float(np.mean(shifts))
        if p_name == "control_uniform_bias":
            control_shift = avg_shift

        p_diversity = _compute_pairwise_diversity(p_outputs)
        cr = float(p_diversity / (clean_diversity + 1e-7))

        # Suspicious if diversity collapses severely and shift is notably higher than control
        suspicious = False
        if clean_diversity >= _MIN_DIVERSITY_FOR_TRIGGER_ANALYSIS:
            if cr < _CONVERGENCE_COLLAPSE_THRESHOLD and avg_shift > (max(control_shift, 0.01) * 2.0):
                suspicious = True

        evaluations.append(PerturbationEvaluation(
            perturbation_name=p_name,
            output_shift_l2=avg_shift,
            perturbed_diversity_l2=p_diversity,
            convergence_ratio=cr,
            suspicious=suspicious,
        ))

    return clean_diversity, evaluations


class MI05TriggerAnomalyDetector:
    """
    MI-05: Model Trigger & Behavioral Perturbation Search Detector.
    Implements ADR-004 Detector protocol.
    """

    @property
    def metadata(self) -> DetectorMetadata:
        return _METADATA

    def can_run(self, context: DetectorContext) -> CanRunResult:
        mi_ctx = getattr(context, "mi05", None) or getattr(context, "mi01", None)
        if mi_ctx is None:
            return CanRunResult(
                ok=False,
                reason="MI-05 requires model context (context.mi05 or context.mi01) to be set.",
            )

        model_path: Path = getattr(mi_ctx, "model_path", None)
        if model_path is None or not model_path.exists():
            return CanRunResult(ok=False, reason=f"Model file not found: {model_path}")

        ext = model_path.suffix.lower()
        if ext in (".pt", ".pth"):
            return CanRunResult(
                ok=False,
                reason=(
                    "PyTorch state dict is non-executable; trigger perturbation search requires "
                    "an executable computation graph (.onnx or .ts)."
                ),
            )

        if ext not in (".onnx", ".ts", ".torchscript"):
            return CanRunResult(ok=False, reason=f"Unsupported format for trigger analysis: {ext!r}")

        return CanRunResult(ok=True)

    def run(self, context: DetectorContext) -> DetectorOutput:
        output = DetectorOutput()
        did = _METADATA.detector_id
        mi_ctx = getattr(context, "mi05", None) or getattr(context, "mi01", None)
        model_path: Path = getattr(mi_ctx, "model_path")

        ext = model_path.suffix.lower()
        try:
            if ext == ".onnx":
                clean_div, evaluations = _evaluate_onnx_triggers(model_path)
            else:
                output.status = DetectorStatus.UNAVAILABLE
                output.error = f"Execution battery not implemented for {ext}"
                return output.finalize()
        except Exception as exc:
            log.exception("MI-05 trigger search failed for %s", model_path)
            output.status = DetectorStatus.FAILED
            output.error = f"Trigger search execution failed: {exc}"
            return output.finalize()

        findings: list[Finding] = []
        evidences: list[Evidence] = []

        suspicious_evals = [e for e in evaluations if e.suspicious]

        if clean_div < _MIN_DIVERSITY_FOR_TRIGGER_ANALYSIS:
            output.status = DetectorStatus.PARTIAL
            output.risk_level = RiskLevel.NONE
            output.confidence_level = ConfidenceLevel.LOW
            f = Finding(
                assessment_id=context.assessment_id,
                asset_id=context.asset_id,
                category=FindingCategory.MODEL_INTEGRITY,
                subcategory="trigger_analysis_insufficient_diversity",
                severity=Severity.INFO,
                title="Trigger analysis: insufficient probe diversity",
                description=(
                    "Model output diversity on synthetic probes is insufficient for reliable trigger analysis. "
                    "Test with domain-representative input data."
                ),
                detection_method=_METADATA.name,
                detector_id=did,
                limitations=[
                    f"Clean probe pairwise diversity ({clean_div:.4f}) is below minimum threshold ({_MIN_DIVERSITY_FOR_TRIGGER_ANALYSIS}).",
                    "Target mode convergence ratio is statistically uninterpretable on invariant outputs.",
                ],
            )
            findings.append(f)
        elif suspicious_evals:
            output.status = DetectorStatus.SUCCESS
            output.risk_level = RiskLevel.HIGH
            output.confidence_level = ConfidenceLevel.HIGH
            p_names = [e.perturbation_name for e in suspicious_evals]
            f = Finding(
                assessment_id=context.assessment_id,
                asset_id=context.asset_id,
                category=FindingCategory.MODEL_INTEGRITY,
                subcategory="suspicious_trigger_convergence",
                severity=Severity.HIGH,
                title=f"Suspicious trigger sensitivity detected ({', '.join(p_names)})",
                description=(
                    f"Candidate perturbation patterns [{', '.join(p_names)}] cause diverse input probes "
                    f"to collapse towards an invariant target output mode (convergence ratio < 15% of clean diversity). "
                    f"This abnormal output invariance is characteristic of Trojan shortcut / backdoor insertion."
                ),
                detection_method=_METADATA.name,
                detector_id=did,
                limitations=[
                    "Tested against candidate localized spatial patches (corner checkerboard, center mark).",
                    "Does not establish origin or malicious intent; analyst inspection required.",
                ],
                recommended_disposition="Quarantine artifact. Conduct targeted activation attribution on candidate trigger coordinates.",
            )
            findings.append(f)
        else:
            output.status = DetectorStatus.SUCCESS
            output.risk_level = RiskLevel.NONE
            output.confidence_level = ConfidenceLevel.HIGH
            min_cr = min((e.convergence_ratio for e in evaluations), default=1.0)
            baseline = Finding(
                assessment_id=context.assessment_id,
                asset_id=context.asset_id,
                category=FindingCategory.MODEL_INTEGRITY,
                subcategory="trigger_search_completed",
                severity=Severity.INFO,
                title="Trigger search completed: no abnormal convergence to candidate perturbation suite",
                description=(
                    f"Evaluated {len(evaluations)} candidate perturbations across diverse clean probe inputs. "
                    f"Clean output diversity: {clean_div:.4f}. Minimum observed convergence ratio: {min_cr:.2f}. "
                    f"Outputs maintained expected representation dispersion without invariant target collapse."
                ),
                detection_method=_METADATA.name,
                detector_id=did,
                limitations=[
                    "Candidate search tests localized corner patches, center marks, and high-frequency grids.",
                    "Does NOT guarantee absence of sophisticated blended, invisible, or semantic triggers.",
                ],
            )
            findings.append(baseline)

        evidence = Evidence(
            finding_id=findings[0].finding_id,
            detector_id=did,
            evidence_type=EvidenceType.MEASUREMENT,
            description=f"Behavioral perturbation and trigger convergence battery for {model_path.name}",
            data={
                "model_path": str(model_path.name),
                "clean_pairwise_diversity": round(clean_div, 6),
                "min_diversity_threshold": _MIN_DIVERSITY_FOR_TRIGGER_ANALYSIS,
                "insufficient_diversity": clean_div < _MIN_DIVERSITY_FOR_TRIGGER_ANALYSIS,
                "perturbation_evaluations": [
                    {
                        "name": e.perturbation_name,
                        "output_shift_l2": round(e.output_shift_l2, 6),
                        "perturbed_diversity_l2": round(e.perturbed_diversity_l2, 6),
                        "convergence_ratio": round(e.convergence_ratio, 4),
                        "suspicious": e.suspicious,
                    }
                    for e in evaluations
                ],
            },
        )
        evidences.append(evidence)

        output.findings = findings
        output.evidence = evidences
        return output.finalize()
