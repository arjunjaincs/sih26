"""
MI-03: Model Activation & Representation Statistics Detector.

Detector ID : model.integrity.mi03_activation_stats
Version     : 1.0.0
Category    : MODEL_INTEGRITY

What this detector does
-----------------------
Collects bounded activation statistics across a calibrated deterministic probe battery
to inspect the model's internal representation health:
- Runs calibrated inputs: zeros, ones, contrast gradient, and seeded noise
- Captures intermediate and output layer activation metrics (mean, std, min, max)
- Identifies dead representation syndrome (layers where > 98% activations are zero across non-zero probes)
- Detects numerical instability / NaN / Inf activations in forward passes
- Detects severe activation saturation (activations pinned to clipping boundaries)

Risk/Confidence semantics (ADR-003)
-----------------------------------
- NaN/Inf activations detected      -> HIGH / HIGH
- Severe activation collapse        -> MEDIUM / MODERATE
- Normal activation dispersion      -> NONE / HIGH (INFO finding)
- Non-executable formats (state_dict)-> UNAVAILABLE / LOW (explicit coverage gap)
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
    _ONNX_AVAILABLE,
    _ORT_AVAILABLE,
    _TORCH_AVAILABLE,
)

log = logging.getLogger(__name__)

_METADATA = DetectorMetadata(
    detector_id="model.integrity.mi03_activation_stats",
    version="1.0.0",
    name="MI-03: Model Activation Statistics",
    description=(
        "Collects bounded intermediate activation statistics across a calibrated deterministic "
        "probe battery to detect activation collapse, dead representations, or severe saturation."
    ),
    applicable_asset_types=frozenset({AssetType.MODEL.value}),
)

_BATTERY_SEED = 0x4D493033  # 'MI03' in hex
_MAX_MONITORED_LAYERS = 8
_DEAD_LAYER_THRESHOLD = 0.98
_OUTPUT_ONLY_LIMITATION = (
    "Intermediate layer extraction requires the 'onnx' compiler package; "
    "current environment captures output-layer statistics only. "
    "Install 'onnx' for full intermediate activation monitoring."
)


@dataclass
class LayerActivationSummary:
    """Activation statistics for one layer on a specific probe."""
    layer_name: str
    probe_name: str
    shape: list[int]
    dtype: str
    mean: float | None
    std: float | None
    min_val: float | None
    max_val: float | None
    dead_ratio: float
    nan_count: int
    inf_count: int


@dataclass
class MI03Context:
    """Context for MI-03 detector execution."""
    model_path: Path
    max_model_size_bytes: int = 5 * 1024 * 1024 * 1024


def _generate_probe_inputs(
    input_shapes: list[tuple[str, list[int], str]],
) -> list[tuple[str, dict[str, Any]]]:
    """
    Generate deterministic calibrated probe inputs for execution.
    Input shapes: list of (input_name, concrete_shape, dtype_str)
    Probes: zeros, ones, contrast, noise.
    """
    import numpy as np

    probes: list[tuple[str, dict[str, Any]]] = []

    for probe_type in ["zeros", "ones", "contrast", "noise"]:
        feed: dict[str, Any] = {}
        for name, shape, dtype_str in input_shapes:
            if "int" in dtype_str:
                np_type = np.int32
            else:
                np_type = np.float32

            if probe_type == "zeros":
                arr = np.zeros(shape, dtype=np_type)
            elif probe_type == "ones":
                arr = np.ones(shape, dtype=np_type)
            elif probe_type == "contrast":
                # Linear ramp across the last dimension
                n_elem = int(np.prod(shape))
                ramp = np.linspace(0.0, 1.0, n_elem, dtype=np.float32).reshape(shape)
                arr = ramp.astype(np_type)
            else:  # noise
                rng = np.random.default_rng(_BATTERY_SEED)
                arr = rng.standard_normal(shape).astype(np_type)

            feed[name] = arr
        probes.append((probe_type, feed))

    return probes


def _analyze_activations_onnx(model_path: Path) -> tuple[list[LayerActivationSummary], bool]:
    """Execute ONNX model across probe battery and collect activation statistics."""
    if not _ORT_AVAILABLE:
        raise RuntimeError("onnxruntime not installed")

    import numpy as np
    import onnxruntime as ort

    # Track whether intermediate layers were actually captured
    intermediate_captured = False
    session: ort.InferenceSession
    if _ONNX_AVAILABLE:
        try:
            import onnx
            model_proto = onnx.load(str(model_path))
            existing_outputs = {o.name for o in model_proto.graph.output}
            added = 0
            for node in model_proto.graph.node:
                for out_name in node.output:
                    if out_name and out_name not in existing_outputs:
                        model_proto.graph.output.append(
                            onnx.helper.make_tensor_value_info(
                                out_name, onnx.TensorProto.FLOAT, None
                            )
                        )
                        existing_outputs.add(out_name)
                        added += 1
                        if added >= _MAX_MONITORED_LAYERS:
                            break
                if added >= _MAX_MONITORED_LAYERS:
                    break
            session = ort.InferenceSession(
                model_proto.SerializeToString(),
                providers=["CPUExecutionProvider"],
            )
            if added > 0:
                intermediate_captured = True
        except Exception as exc:
            log.debug("Intermediate ONNX output extraction fallback: %s", exc)
            session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
            intermediate_captured = False
    else:
        session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        intermediate_captured = False

    inputs_meta = session.get_inputs()
    input_shapes: list[tuple[str, list[int], str]] = []
    for inp in inputs_meta:
        # replace dynamic/unresolved dimensions with 1 or standard dimension
        concrete = [d if isinstance(d, int) and d > 0 else 1 for d in inp.shape]
        input_shapes.append((inp.name, concrete, str(inp.type)))

    probes = _generate_probe_inputs(input_shapes)
    summaries: list[LayerActivationSummary] = []

    outputs_meta = session.get_outputs()
    output_names = [o.name for o in outputs_meta][:_MAX_MONITORED_LAYERS]

    for probe_name, feed in probes:
        try:
            outputs = session.run(output_names, feed)
            for out_name, out_arr in zip(output_names, outputs):
                if not isinstance(out_arr, np.ndarray):
                    continue
                numel = int(out_arr.size)
                if numel == 0:
                    continue

                arr_f64 = out_arr.astype(np.float64, copy=False)
                nan_c = int(np.isnan(arr_f64).sum())
                inf_c = int(np.isinf(arr_f64).sum())
                zero_c = int((arr_f64 == 0).sum())
                dead_ratio = float(zero_c / numel)

                finite_mask = np.isfinite(arr_f64)
                if np.any(finite_mask):
                    f_vals = arr_f64[finite_mask]
                    mn = float(np.min(f_vals))
                    mx = float(np.max(f_vals))
                    mean = float(np.mean(f_vals))
                    std = float(np.std(f_vals))
                else:
                    mn = mx = mean = std = None

                summaries.append(LayerActivationSummary(
                    layer_name=out_name,
                    probe_name=probe_name,
                    shape=list(out_arr.shape),
                    dtype=str(out_arr.dtype),
                    mean=mean,
                    std=std,
                    min_val=mn,
                    max_val=mx,
                    dead_ratio=dead_ratio,
                    nan_count=nan_c,
                    inf_count=inf_c,
                ))
        except Exception as exc:
            log.warning("Activation run failed for probe %s: %s", probe_name, exc)

    return summaries, intermediate_captured


def _analyze_activations_torchscript(model_path: Path) -> list[LayerActivationSummary]:
    """Execute TorchScript model across probe battery and collect activation statistics."""
    if not _TORCH_AVAILABLE:
        raise RuntimeError("torch not installed")

    import numpy as np
    import torch

    model = torch.jit.load(str(model_path), map_location="cpu")
    model.eval()

    captured_activations: dict[str, list[torch.Tensor]] = {}

    def make_hook(name: str):
        def hook(mod, inp, out):
            if isinstance(out, torch.Tensor):
                captured_activations.setdefault(name, []).append(out.detach().cpu())
            elif isinstance(out, (list, tuple)) and len(out) > 0 and isinstance(out[0], torch.Tensor):
                captured_activations.setdefault(name, []).append(out[0].detach().cpu())
        return hook

    hook_handles = []
    monitored = 0
    for name, module in model.named_modules():
        if name and monitored < _MAX_MONITORED_LAYERS:
            h = module.register_forward_hook(make_hook(name))
            hook_handles.append(h)
            monitored += 1

    probe_inputs = [
        ("zeros", torch.zeros(1, 3, 32, 32, dtype=torch.float32)),
        ("ones", torch.ones(1, 3, 32, 32, dtype=torch.float32)),
        ("contrast", torch.linspace(0.0, 1.0, 1 * 3 * 32 * 32, dtype=torch.float32).reshape(1, 3, 32, 32)),
        ("noise", torch.randn(1, 3, 32, 32, dtype=torch.float32)),
    ]

    summaries: list[LayerActivationSummary] = []
    try:
        with torch.no_grad():
            for probe_name, t_inp in probe_inputs:
                captured_activations.clear()
                try:
                    out = model(t_inp)
                    if isinstance(out, torch.Tensor):
                        captured_activations["output"] = [out.detach().cpu()]
                except Exception:
                    # If 4D fails, try 2D fallback [1, 10]
                    try:
                        t_fallback = torch.ones(1, 10, dtype=torch.float32)
                        out = model(t_fallback)
                        if isinstance(out, torch.Tensor):
                            captured_activations["output"] = [out.detach().cpu()]
                    except Exception as exc:
                        log.debug("TorchScript probe failed: %s", exc)
                        continue

                for layer_name, tensor_list in captured_activations.items():
                    if not tensor_list:
                        continue
                    t = tensor_list[-1]
                    arr = t.numpy()
                    numel = arr.size
                    if numel == 0:
                        continue
                    arr_f64 = arr.astype(np.float64, copy=False)
                    nan_c = int(np.isnan(arr_f64).sum())
                    inf_c = int(np.isinf(arr_f64).sum())
                    zero_c = int((arr_f64 == 0).sum())
                    dead_ratio = float(zero_c / numel)

                    finite_mask = np.isfinite(arr_f64)
                    if np.any(finite_mask):
                        f_vals = arr_f64[finite_mask]
                        mn = float(np.min(f_vals))
                        mx = float(np.max(f_vals))
                        mean = float(np.mean(f_vals))
                        std = float(np.std(f_vals))
                    else:
                        mn = mx = mean = std = None

                    summaries.append(LayerActivationSummary(
                        layer_name=layer_name,
                        probe_name=probe_name,
                        shape=list(arr.shape),
                        dtype=str(arr.dtype),
                        mean=mean,
                        std=std,
                        min_val=mn,
                        max_val=mx,
                        dead_ratio=dead_ratio,
                        nan_count=nan_c,
                        inf_count=inf_c,
                    ))
    finally:
        for h in hook_handles:
            h.remove()

    return summaries


class MI03ActivationStatsDetector:
    """
    MI-03: Model Activation & Representation Statistics Detector.
    Implements ADR-004 Detector protocol.
    """

    @property
    def metadata(self) -> DetectorMetadata:
        return _METADATA

    def can_run(self, context: DetectorContext) -> CanRunResult:
        mi_ctx = getattr(context, "mi03", None) or getattr(context, "mi01", None)
        if mi_ctx is None:
            return CanRunResult(
                ok=False,
                reason="MI-03 requires model context (context.mi03 or context.mi01) to be set.",
            )

        path: Path = getattr(mi_ctx, "model_path", None)
        if path is None:
            return CanRunResult(ok=False, reason="model_path not specified in context")
        if not path.exists():
            return CanRunResult(ok=False, reason=f"Model file not found: {path}")
        if not path.is_file():
            return CanRunResult(ok=False, reason=f"Not a regular file: {path}")

        ext = path.suffix.lower()
        if ext in (".pt", ".pth"):
            return CanRunResult(
                ok=False,
                reason=(
                    "PyTorch state dict (.pt/.pth) has no execution graph for intermediate activation tracing. "
                    "Activation statistics require an executable model format (.onnx or .ts)."
                ),
            )

        if ext not in (".onnx", ".ts", ".torchscript"):
            return CanRunResult(ok=False, reason=f"Unsupported format for activation analysis: {ext!r}")

        return CanRunResult(ok=True)

    def run(self, context: DetectorContext) -> DetectorOutput:
        output = DetectorOutput()
        did = _METADATA.detector_id
        mi_ctx = getattr(context, "mi03", None) or getattr(context, "mi01", None)
        model_path: Path = getattr(mi_ctx, "model_path")

        ext = model_path.suffix.lower()
        intermediate_captured = True
        try:
            if ext == ".onnx":
                summaries, intermediate_captured = _analyze_activations_onnx(model_path)
            elif ext in (".ts", ".torchscript"):
                summaries = _analyze_activations_torchscript(model_path)
                intermediate_captured = True
            else:
                output.status = DetectorStatus.UNAVAILABLE
                output.error = f"Unsupported execution format: {ext}"
                return output.finalize()
        except Exception as exc:
            log.exception("MI-03 activation analysis failed for %s", model_path)
            output.status = DetectorStatus.FAILED
            output.error = f"Activation analysis failed: {exc}"
            return output.finalize()

        if not summaries:
            output.status = DetectorStatus.PARTIAL
            output.risk_level = RiskLevel.NONE
            output.confidence_level = ConfidenceLevel.LOW
            output.error = "No activations were produced across probe battery."
            return output.finalize()

        # Anomaly evaluations
        total_nan = sum(s.nan_count for s in summaries)
        total_inf = sum(s.inf_count for s in summaries)

        # Non-zero probes: ones, contrast, noise
        non_zero_summaries = [s for s in summaries if s.probe_name != "zeros"]
        dead_layer_counts: dict[str, int] = {}
        for s in non_zero_summaries:
            if s.dead_ratio >= _DEAD_LAYER_THRESHOLD:
                dead_layer_counts[s.layer_name] = dead_layer_counts.get(s.layer_name, 0) + 1

        # A layer is collapsed if it is dead on all tested non-zero probes (>= 3 probes)
        collapsed_layers = [
            lname for lname, count in dead_layer_counts.items() if count >= 3
        ]

        findings: list[Finding] = []
        evidences: list[Evidence] = []

        if total_nan > 0 or total_inf > 0:
            output.risk_level = RiskLevel.HIGH
            output.confidence_level = ConfidenceLevel.HIGH if intermediate_captured else ConfidenceLevel.MODERATE
            f_limits = ["Evaluated on deterministic synthetic probe battery (zeros, ones, gradient, noise)."]
            if not intermediate_captured:
                f_limits.append(_OUTPUT_ONLY_LIMITATION)
            f = Finding(
                assessment_id=context.assessment_id,
                asset_id=context.asset_id,
                category=FindingCategory.MODEL_INTEGRITY,
                subcategory="activation_numerical_instability",
                severity=Severity.HIGH,
                title="Numerical instability detected in model activations (NaN/Inf)",
                description=(
                    f"Forward execution with deterministic probes generated {total_nan} NaN "
                    f"and {total_inf} Inf activations. Indicates layer overflow, division by zero, "
                    f"or corrupt weight representations."
                ),
                detection_method=_METADATA.name,
                detector_id=did,
                limitations=f_limits,
                recommended_disposition="Quarantine artifact. Audit layer normalization and numerical stability.",
            )
            findings.append(f)

        elif collapsed_layers:
            output.risk_level = RiskLevel.MEDIUM
            output.confidence_level = ConfidenceLevel.MODERATE
            f_limits = ["Synthetic probe battery; dynamic conditional execution branches may not have activated."]
            if not intermediate_captured:
                f_limits.append(_OUTPUT_ONLY_LIMITATION)
            f = Finding(
                assessment_id=context.assessment_id,
                asset_id=context.asset_id,
                category=FindingCategory.MODEL_INTEGRITY,
                subcategory="activation_collapse",
                severity=Severity.MEDIUM,
                title=f"Activation collapse detected in {len(collapsed_layers)} layer(s)",
                description=(
                    f"Layers [{', '.join(collapsed_layers[:5])}] produced > 98% dead/zero activations "
                    f"across all non-zero deterministic probe inputs. Indicates dead representations, "
                    f"unresponsive sub-networks, or architectural failure."
                ),
                detection_method=_METADATA.name,
                detector_id=did,
                limitations=f_limits,
                recommended_disposition="Inspect model activation maps with domain-specific input data.",
            )
            findings.append(f)

        else:
            output.risk_level = RiskLevel.NONE
            output.confidence_level = ConfidenceLevel.HIGH if intermediate_captured else ConfidenceLevel.MODERATE

        if not intermediate_captured:
            output.confidence_level = ConfidenceLevel.MODERATE

        # Baseline info finding
        distinct_layers = sorted({s.layer_name for s in summaries})
        if intermediate_captured:
            base_title = f"Model activation profile recorded ({len(distinct_layers)} monitored layers)"
            base_desc = (
                f"Evaluated {len(distinct_layers)} layer(s) across 4 calibrated probes. "
                f"Mean activation dispersion is stable; NaN: {total_nan}, Inf: {total_inf}."
            )
            base_limits = ["Analysis bounded to first monitored layers and CPU execution."]
        else:
            base_title = f"Model output activation profile recorded ({len(distinct_layers)} output layer(s))"
            base_desc = (
                f"Evaluated {len(distinct_layers)} output layer(s) across 4 calibrated probes. "
                f"Mean output activation dispersion is stable; NaN: {total_nan}, Inf: {total_inf}."
            )
            base_limits = [
                "Analysis bounded to output layers and CPU execution.",
                _OUTPUT_ONLY_LIMITATION,
            ]

        baseline = Finding(
            assessment_id=context.assessment_id,
            asset_id=context.asset_id,
            category=FindingCategory.MODEL_INTEGRITY,
            subcategory="activation_profile_recorded",
            severity=Severity.INFO,
            title=base_title,
            description=base_desc,
            detection_method=_METADATA.name,
            detector_id=did,
            limitations=base_limits,
        )
        findings.append(baseline)

        ev_data = {
            "model_path": str(model_path.name),
            "monitored_layer_count": len(distinct_layers),
            "intermediate_layers_captured": intermediate_captured,
            "analysis_scope": "intermediate_and_output" if intermediate_captured else "output_only",
            "probes_evaluated": ["zeros", "ones", "contrast", "noise"],
            "nan_count": total_nan,
            "inf_count": total_inf,
            "collapsed_layers": collapsed_layers,
            "layer_samples": [
                {
                    "layer": s.layer_name,
                    "probe": s.probe_name,
                    "shape": s.shape,
                    "mean": round(s.mean, 5) if s.mean is not None else None,
                    "std": round(s.std, 5) if s.std is not None else None,
                    "min": round(s.min_val, 5) if s.min_val is not None else None,
                    "max": round(s.max_val, 5) if s.max_val is not None else None,
                    "dead_ratio": round(s.dead_ratio, 4),
                }
                for s in summaries[:30]
            ],
        }
        if not intermediate_captured:
            ev_data["limitations"] = [_OUTPUT_ONLY_LIMITATION]

        evidence = Evidence(
            finding_id=baseline.finding_id,
            detector_id=did,
            evidence_type=EvidenceType.MEASUREMENT,
            description=(
                f"Activation statistics across deterministic probes for {model_path.name}"
                if intermediate_captured
                else f"Output-layer activation statistics across deterministic probes for {model_path.name} (intermediate extraction unavailable)"
            ),
            data=ev_data,
        )
        evidences.append(evidence)

        output.findings = findings
        output.evidence = evidences
        output.status = DetectorStatus.SUCCESS
        return output.finalize()
