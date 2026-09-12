"""
MI-02: Model Parameter Statistics Detector.

Detector ID : model.integrity.mi02_parameter_stats
Version     : 1.0.0
Category    : MODEL_INTEGRITY

What this detector does
-----------------------
Performs deep white-box inspection of model parameter tensors across supported
formats (ONNX, PyTorch, TorchScript):
- Total parameter count, tensor count, dtype distribution
- Global and per-tensor summary statistics (min, max, mean, std, sparsity)
- Detection of non-finite weights (NaN, +Inf, -Inf) indicating corruption or overflow
- Detection of extreme weight anomalies (|w| > 10,000, variance explosion)
- Detection of abnormal layer collapse or extreme sparsity (> 99.9% zeros)

Risk/Confidence semantics (ADR-003)
-----------------------------------
- NaN/Inf detected                  -> HIGH / HIGH (or CRITICAL if widespread)
- Extreme magnitude anomaly         -> MEDIUM / MODERATE
- Abnormal layer sparsity           -> LOW / MODERATE
- Healthy distribution baseline     -> NONE / HIGH (INFO finding)
- Framework/loading unavailable     -> NONE / LOW (coverage gap)
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
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
    ModelLoadError,
    _ONNX_AVAILABLE,
    _TORCH_AVAILABLE,
    load_model,
)

log = logging.getLogger(__name__)

_METADATA = DetectorMetadata(
    detector_id="model.integrity.mi02_parameter_stats",
    version="1.0.0",
    name="MI-02: Model Parameter Statistics",
    description=(
        "Analyzes parameter counts, tensor distribution, sparsity, min/max/mean/std, "
        "and detects NaN/Inf corruption or extreme weight anomalies across model parameters."
    ),
    applicable_asset_types=frozenset({AssetType.MODEL.value}),
)

# Thresholds for weight anomaly detection
_MAX_ABS_WEIGHT_THRESHOLD = 1e4
_MAX_STD_THRESHOLD = 1e3
_MAX_SPARSITY_THRESHOLD = 0.999
_MIN_TENSOR_ELEMENTS_FOR_SPARSITY = 1000
_MAX_TENSORS_IN_EVIDENCE = 50


@dataclass
class TensorSummary:
    """Statistical summary for a single parameter tensor."""
    name: str
    shape: list[int]
    dtype: str
    numel: int
    nan_count: int
    inf_count: int
    sparsity: float
    min_val: float | None = None
    max_val: float | None = None
    mean_val: float | None = None
    std_val: float | None = None


@dataclass
class ParameterStatsReport:
    """Aggregate statistics across all parameter tensors in the model."""
    total_parameters: int
    total_tensors: int
    dtype_distribution: dict[str, int]
    nan_count: int
    inf_count: int
    global_sparsity: float
    global_min: float | None
    global_max: float | None
    global_mean: float | None
    global_std: float | None
    tensor_summaries: list[TensorSummary] = field(default_factory=list)


@dataclass
class MI02Context:
    """Context for MI-02 detector execution."""
    model_path: Path
    max_model_size_bytes: int = 5 * 1024 * 1024 * 1024


def _decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    res = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        res |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return res, pos


def _parse_protobuf_fields(data: bytes) -> dict[int, list[Any]]:
    pos = 0
    fields: dict[int, list[Any]] = {}
    while pos < len(data):
        tag, pos = _decode_varint(data, pos)
        wire_type = tag & 0x07
        field_num = tag >> 3
        if wire_type == 0:  # varint
            val, pos = _decode_varint(data, pos)
            fields.setdefault(field_num, []).append(val)
        elif wire_type == 2:  # length-delimited
            length, pos = _decode_varint(data, pos)
            val = data[pos : pos + length]
            pos += length
            fields.setdefault(field_num, []).append(val)
        elif wire_type == 5:  # 32-bit
            val = data[pos : pos + 4]
            pos += 4
            fields.setdefault(field_num, []).append(val)
        elif wire_type == 1:  # 64-bit
            val = data[pos : pos + 8]
            pos += 8
            fields.setdefault(field_num, []).append(val)
        else:
            break
    return fields


def _extract_onnx_parameter_stats(model_path: Path) -> ParameterStatsReport:
    """Extract parameter statistics from ONNX initializers."""
    import numpy as np

    tensors: list[TensorSummary] = []
    total_params = 0
    total_nans = 0
    total_infs = 0
    total_zeros = 0
    all_values: list[np.ndarray] = []
    dtype_dist: dict[str, int] = {}

    extracted_arrays: list[tuple[str, list[int], np.ndarray]] = []

    if _ONNX_AVAILABLE:
        try:
            import onnx
            from onnx import numpy_helper
            model_proto = onnx.load(str(model_path))
            for init in model_proto.graph.initializer:
                name = init.name or "unnamed"
                try:
                    arr = numpy_helper.to_array(init)
                    extracted_arrays.append((name, list(arr.shape), arr))
                except Exception as exc:
                    log.warning("Failed to convert ONNX initializer %s: %s", name, exc)
        except Exception as exc:
            log.debug("onnx package load failed, falling back to raw parser: %s", exc)

    if not extracted_arrays:
        # Fallback pure-Python protobuf parser
        raw_bytes = model_path.read_bytes()
        model_fields = _parse_protobuf_fields(raw_bytes)
        graph_msgs = model_fields.get(7, [])
        if graph_msgs:
            graph_fields = _parse_protobuf_fields(graph_msgs[0])
            for init_bytes in graph_fields.get(5, []):
                tf = _parse_protobuf_fields(init_bytes)
                name_bytes = tf.get(8, [b""])[0]
                name = name_bytes.decode("utf-8", errors="replace") or "unnamed"
                dims = tf.get(1, [])
                raw_data = tf.get(9, [b""])[0]
                if raw_data:
                    # little-endian float32 raw data
                    arr = np.frombuffer(raw_data, dtype=np.float32)
                    if dims:
                        try:
                            arr = arr.reshape(dims)
                        except Exception:
                            pass
                    extracted_arrays.append((name, list(arr.shape), arr))

    for name, shape, arr in extracted_arrays:

        numel = int(arr.size)
        total_params += numel
        dtype_str = str(arr.dtype)
        dtype_dist[dtype_str] = dtype_dist.get(dtype_str, 0) + 1

        if not np.issubdtype(arr.dtype, np.number):
            continue

        arr_f64 = arr.astype(np.float64, copy=False)
        nan_c = int(np.isnan(arr_f64).sum())
        inf_c = int(np.isinf(arr_f64).sum())
        zero_c = int((arr_f64 == 0).sum())
        sparsity = float(zero_c / numel) if numel > 0 else 0.0

        total_nans += nan_c
        total_infs += inf_c
        total_zeros += zero_c

        finite_mask = np.isfinite(arr_f64)
        if np.any(finite_mask):
            finite_vals = arr_f64[finite_mask]
            mn = float(np.min(finite_vals))
            mx = float(np.max(finite_vals))
            mean = float(np.mean(finite_vals))
            std = float(np.std(finite_vals))
            # Subsample for global moments if tensor is large
            if len(finite_vals) > 10000:
                all_values.append(finite_vals[:: max(1, len(finite_vals) // 10000)])
            else:
                all_values.append(finite_vals)
        else:
            mn = mx = mean = std = None

        tensors.append(TensorSummary(
            name=name,
            shape=list(arr.shape),
            dtype=dtype_str,
            numel=numel,
            nan_count=nan_c,
            inf_count=inf_c,
            sparsity=sparsity,
            min_val=mn,
            max_val=mx,
            mean_val=mean,
            std_val=std,
        ))

    if all_values:
        combined = np.concatenate(all_values)
        g_min = float(np.min(combined))
        g_max = float(np.max(combined))
        g_mean = float(np.mean(combined))
        g_std = float(np.std(combined))
    else:
        g_min = g_max = g_mean = g_std = None

    g_sparsity = float(total_zeros / total_params) if total_params > 0 else 0.0

    return ParameterStatsReport(
        total_parameters=total_params,
        total_tensors=len(tensors),
        dtype_distribution=dtype_dist,
        nan_count=total_nans,
        inf_count=total_infs,
        global_sparsity=g_sparsity,
        global_min=g_min,
        global_max=g_max,
        global_mean=g_mean,
        global_std=g_std,
        tensor_summaries=tensors,
    )


def _extract_pytorch_parameter_stats(raw_obj: Any) -> ParameterStatsReport:
    """Extract parameter statistics from a PyTorch state dict or model."""
    import numpy as np
    import torch

    tensors: list[TensorSummary] = []
    total_params = 0
    total_nans = 0
    total_infs = 0
    total_zeros = 0
    all_values: list[np.ndarray] = []
    dtype_dist: dict[str, int] = {}

    if hasattr(raw_obj, "state_dict"):
        state = raw_obj.state_dict()
    elif isinstance(raw_obj, dict):
        state = raw_obj
    else:
        raise ValueError(f"Expected dict or object with state_dict, got {type(raw_obj).__name__}")

    for name, t in state.items():
        if not isinstance(t, torch.Tensor):
            continue

        numel = t.numel()
        total_params += numel
        dtype_str = str(t.dtype).replace("torch.", "")
        dtype_dist[dtype_str] = dtype_dist.get(dtype_str, 0) + 1

        if not t.is_floating_point() and not t.is_complex() and not t.dtype.is_signed:
            continue

        arr = t.detach().cpu().to(torch.float32).numpy()
        numel = arr.size

        nan_c = int(np.isnan(arr).sum())
        inf_c = int(np.isinf(arr).sum())
        zero_c = int((arr == 0).sum())
        sparsity = float(zero_c / numel) if numel > 0 else 0.0

        total_nans += nan_c
        total_infs += inf_c
        total_zeros += zero_c

        finite_mask = np.isfinite(arr)
        if np.any(finite_mask):
            finite_vals = arr[finite_mask]
            mn = float(np.min(finite_vals))
            mx = float(np.max(finite_vals))
            mean = float(np.mean(finite_vals))
            std = float(np.std(finite_vals))
            if len(finite_vals) > 10000:
                all_values.append(finite_vals[:: max(1, len(finite_vals) // 10000)])
            else:
                all_values.append(finite_vals)
        else:
            mn = mx = mean = std = None

        tensors.append(TensorSummary(
            name=name,
            shape=list(t.shape),
            dtype=dtype_str,
            numel=numel,
            nan_count=nan_c,
            inf_count=inf_c,
            sparsity=sparsity,
            min_val=mn,
            max_val=mx,
            mean_val=mean,
            std_val=std,
        ))

    if all_values:
        combined = np.concatenate(all_values)
        g_min = float(np.min(combined))
        g_max = float(np.max(combined))
        g_mean = float(np.mean(combined))
        g_std = float(np.std(combined))
    else:
        g_min = g_max = g_mean = g_std = None

    g_sparsity = float(total_zeros / total_params) if total_params > 0 else 0.0

    return ParameterStatsReport(
        total_parameters=total_params,
        total_tensors=len(tensors),
        dtype_distribution=dtype_dist,
        nan_count=total_nans,
        inf_count=total_infs,
        global_sparsity=g_sparsity,
        global_min=g_min,
        global_max=g_max,
        global_mean=g_mean,
        global_std=g_std,
        tensor_summaries=tensors,
    )


def extract_parameter_stats(
    model_path: Path,
    *,
    max_size_bytes: int = 5 * 1024 * 1024 * 1024,
) -> ParameterStatsReport:
    """
    Extract parameter statistics from a model file.
    Safely loads the model and inspects weights without arbitrary code execution.
    """
    ext = model_path.suffix.lower()
    if ext == ".onnx":
        return _extract_onnx_parameter_stats(model_path)
    elif ext in (".pt", ".pth", ".ts", ".torchscript"):
        loaded = load_model(model_path, max_size_bytes=max_size_bytes)
        return _extract_pytorch_parameter_stats(loaded.raw_object)
    else:
        raise ModelLoadError(f"Unsupported model extension: {ext}", None)  # type: ignore


class MI02ParameterStatsDetector:
    """
    MI-02: Model Parameter Statistics Detector.
    Implements ADR-004 Detector protocol.
    """

    @property
    def metadata(self) -> DetectorMetadata:
        return _METADATA

    def can_run(self, context: DetectorContext) -> CanRunResult:
        mi_ctx = getattr(context, "mi02", None) or getattr(context, "mi01", None)
        if mi_ctx is None:
            return CanRunResult(
                ok=False,
                reason="MI-02 requires context.mi02 or context.mi01 (model context) to be set.",
            )

        path: Path = getattr(mi_ctx, "model_path", None)
        if path is None:
            return CanRunResult(ok=False, reason="model_path not specified in context")
        if not path.exists():
            return CanRunResult(ok=False, reason=f"Model file not found: {path}")
        if not path.is_file():
            return CanRunResult(ok=False, reason=f"Not a regular file: {path}")

        from backend.infra.model_loader import SUPPORTED_EXTENSIONS
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return CanRunResult(
                ok=False,
                reason=f"Unsupported model format: {path.suffix!r}",
            )

        return CanRunResult(ok=True)

    def run(self, context: DetectorContext) -> DetectorOutput:
        output = DetectorOutput()
        did = _METADATA.detector_id
        mi_ctx = getattr(context, "mi02", None) or getattr(context, "mi01", None)
        model_path: Path = getattr(mi_ctx, "model_path")
        max_size: int = getattr(mi_ctx, "max_model_size_bytes", 5 * 1024 * 1024 * 1024)

        try:
            report = extract_parameter_stats(model_path, max_size_bytes=max_size)
        except Exception as exc:
            log.exception("MI-02 parameter statistics extraction failed for %s", model_path)
            output.status = DetectorStatus.FAILED
            output.error = f"Parameter stats extraction failed: {exc}"
            return output.finalize()

        # Check for anomalies
        findings: list[Finding] = []
        evidences: list[Evidence] = []

        has_nan_inf = (report.nan_count > 0) or (report.inf_count > 0)
        has_extreme_mag = False
        if report.global_max is not None and report.global_min is not None:
            if (abs(report.global_max) > _MAX_ABS_WEIGHT_THRESHOLD or
                    abs(report.global_min) > _MAX_ABS_WEIGHT_THRESHOLD):
                has_extreme_mag = True
        if report.global_std is not None and report.global_std > _MAX_STD_THRESHOLD:
            has_extreme_mag = True

        # Check for abnormal sparse layers (non-bias layers with > 99.9% zeros)
        sparse_tensors = [
            t.name for t in report.tensor_summaries
            if t.numel >= _MIN_TENSOR_ELEMENTS_FOR_SPARSITY and t.sparsity >= _MAX_SPARSITY_THRESHOLD
        ]

        if has_nan_inf:
            output.risk_level = RiskLevel.HIGH if (report.nan_count + report.inf_count) < 100 else RiskLevel.CRITICAL
            output.confidence_level = ConfidenceLevel.HIGH
            f = Finding(
                assessment_id=context.assessment_id,
                asset_id=context.asset_id,
                category=FindingCategory.MODEL_INTEGRITY,
                subcategory="parameter_corruption",
                severity=Severity.HIGH if output.risk_level == RiskLevel.HIGH else Severity.CRITICAL,
                title=f"Parameter corruption detected: {report.nan_count} NaN and {report.inf_count} Inf weights found",
                description=(
                    f"Model weights contain non-finite numbers ({report.nan_count} NaN, {report.inf_count} Inf). "
                    f"This indicates severe parameter corruption, numerical overflow, or deliberate tampering. "
                    f"Inference results will be undefined or corrupt."
                ),
                detection_method=_METADATA.name,
                detector_id=did,
                limitations=[
                    "Does not identify origin of corruption (training divergence vs artifact modification).",
                    "Assumes weights_only safety boundary during extraction.",
                ],
                recommended_disposition="Quarantine artifact immediately. Do not deploy to production.",
            )
            findings.append(f)

        elif has_extreme_mag:
            output.risk_level = RiskLevel.MEDIUM
            output.confidence_level = ConfidenceLevel.MODERATE
            f = Finding(
                assessment_id=context.assessment_id,
                asset_id=context.asset_id,
                category=FindingCategory.MODEL_INTEGRITY,
                subcategory="weight_distribution_anomaly",
                severity=Severity.MEDIUM,
                title="Extreme weight magnitude anomaly detected",
                description=(
                    f"Model parameter distributions exceed normal bounds. Observed min={report.global_min}, "
                    f"max={report.global_max}, std={report.global_std}. "
                    f"Extreme weights may indicate untamed gradients, unclipped fine-tuning, or parameter tampering."
                ),
                detection_method=_METADATA.name,
                detector_id=did,
                limitations=["Statistical heuristic on weight distributions; some custom architectures deliberately scale weights."],
                recommended_disposition="Review training provenance and verify whether weights are within expected operational range.",
            )
            findings.append(f)

        elif sparse_tensors:
            output.risk_level = RiskLevel.LOW
            output.confidence_level = ConfidenceLevel.MODERATE
            f = Finding(
                assessment_id=context.assessment_id,
                asset_id=context.asset_id,
                category=FindingCategory.MODEL_INTEGRITY,
                subcategory="extreme_sparsity_anomaly",
                severity=Severity.LOW,
                title=f"Abnormal layer sparsity detected: {len(sparse_tensors)} tensor(s) > 99.9% zeros",
                description=(
                    f"Found {len(sparse_tensors)} large parameter tensor(s) with over 99.9% zero values: "
                    f"{', '.join(sparse_tensors[:5])}. Verify if model was intentionally pruned or compressed."
                ),
                detection_method=_METADATA.name,
                detector_id=did,
                limitations=["Intentional pruning or sparse weight architectures can legitimately produce high sparsity."],
                recommended_disposition="Verify model quantization and pruning specifications.",
            )
            findings.append(f)

        else:
            output.risk_level = RiskLevel.NONE
            output.confidence_level = ConfidenceLevel.HIGH

        # Baseline measurement finding (always recorded)
        baseline_finding = Finding(
            assessment_id=context.assessment_id,
            asset_id=context.asset_id,
            category=FindingCategory.MODEL_INTEGRITY,
            subcategory="parameter_stats_recorded",
            severity=Severity.INFO,
            title=f"Model parameter statistics recorded ({report.total_parameters:,} params, {report.total_tensors} tensors)",
            description=(
                f"Inspected {report.total_tensors} parameter tensors ({report.total_parameters:,} total parameters). "
                f"Sparsity: {report.global_sparsity:.2%}. Min: {report.global_min}, Max: {report.global_max}, "
                f"Mean: {report.global_mean}, Std: {report.global_std}. NaN: {report.nan_count}, Inf: {report.inf_count}."
            ),
            detection_method=_METADATA.name,
            detector_id=did,
            limitations=["Analysis restricted to parameter tensors extracted via safe loading boundaries."],
        )
        findings.append(baseline_finding)

        # Evidence record
        evidence_data = {
            "model_path": str(model_path.name),
            "total_parameters": report.total_parameters,
            "total_tensors": report.total_tensors,
            "dtype_distribution": report.dtype_distribution,
            "nan_count": report.nan_count,
            "inf_count": report.inf_count,
            "global_sparsity": report.global_sparsity,
            "global_min": report.global_min,
            "global_max": report.global_max,
            "global_mean": report.global_mean,
            "global_std": report.global_std,
            "sample_tensors": [
                {
                    "name": t.name,
                    "shape": t.shape,
                    "dtype": t.dtype,
                    "numel": t.numel,
                    "nan_count": t.nan_count,
                    "inf_count": t.inf_count,
                    "sparsity": round(t.sparsity, 4),
                    "min": round(t.min_val, 6) if t.min_val is not None else None,
                    "max": round(t.max_val, 6) if t.max_val is not None else None,
                    "mean": round(t.mean_val, 6) if t.mean_val is not None else None,
                    "std": round(t.std_val, 6) if t.std_val is not None else None,
                }
                for t in report.tensor_summaries[:_MAX_TENSORS_IN_EVIDENCE]
            ],
        }

        evidence = Evidence(
            finding_id=baseline_finding.finding_id,
            detector_id=did,
            evidence_type=EvidenceType.MEASUREMENT,
            description=f"Parameter statistics report for {model_path.name}",
            data=evidence_data,
        )
        evidences.append(evidence)

        output.findings = findings
        output.evidence = evidences
        output.status = DetectorStatus.SUCCESS
        return output.finalize()
