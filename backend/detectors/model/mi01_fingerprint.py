"""
MI-01: Model Integrity Fingerprinting and Comparison Detector.

Detector ID : model.integrity.mi01_fingerprint
Version     : 1.0.0
Category    : MODEL_INTEGRITY

What this detector does
-----------------------
Produces a multi-layer fingerprint of a model artifact and compares it
against a user-supplied reference fingerprint (when provided).

Layer 1 — Artifact identity (always)
  SHA-256 of the raw model bytes
  File size, format, PRAMAAN version, analysis timestamp

Layer 2 — Structural fingerprint (where access permits)
  For ONNX (via onnxruntime):
    graph name, domain, description
    input/output names and shapes/types
    node count (where available via onnx package)
    initializer count (where onnx package present)
    opset info (where onnx package present)

  For PyTorch (state dict via torch):
    top-level key names
    total parameter count
    dtype distribution

Layer 3 — Behavioral fingerprint (ONNX via onnxruntime)
  A deterministic reference-input battery: zeros, ones, seeded noise.
  For each input:
    Output shape, dtype
    SHA-256 of the quantized output bytes
    Mean, std, min, max
  PyTorch state dicts: marked UNAVAILABLE (no architecture class to execute)

Layer 4 — Reference comparison (when reference_fingerprint provided)
  Compares artifact hash, structural fields, behavioral outputs.
  Any material difference → Finding with evidence showing observed vs expected.

Risk/Confidence semantics (ADR-003)
-------------------------------------
  Exact match (all layers)          → NONE / HIGH
  Artifact hash mismatch only       → LOW / MODERATE
  Artifact + structure mismatch     → MEDIUM / MODERATE
  Behavioral divergence             → MEDIUM / MODERATE
  No reference provided             → NONE / HIGH (fingerprint recorded)
  Framework unavailable             → NONE / LOW (explicit coverage gap)

Findings are never labelled 'backdoor' or 'malicious' automatically.
"""

from __future__ import annotations

import hashlib
import json
import logging
import struct
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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
    ModelLoadErrorCode,
    _ONNX_AVAILABLE,
    _ORT_AVAILABLE,
    _TORCH_AVAILABLE,
    framework_available,
    load_model,
)

log = logging.getLogger(__name__)

_METADATA = DetectorMetadata(
    detector_id="model.integrity.mi01_fingerprint",
    version="1.0.0",
    name="MI-01: Model Integrity Fingerprinting",
    description=(
        "Produces a cryptographic + structural + behavioral fingerprint of a model "
        "artifact and optionally compares it against a reference fingerprint. "
        "Identifies integrity differences; does not classify changes as malicious."
    ),
    applicable_asset_types=frozenset({AssetType.MODEL.value}),
)

_PRAMAAN_VERSION = "1.0.0"
_BATTERY_SEED = 0x50524D4E  # 'PRMN' in hex


# ---------------------------------------------------------------------------
# Fingerprint data structures
# ---------------------------------------------------------------------------

@dataclass
class ArtifactFingerprint:
    """Cryptographic identity of the model file."""
    sha256: str
    file_size_bytes: int
    format: str
    pramaan_version: str
    analyzed_at_utc: str


@dataclass
class StructuralFingerprint:
    """Deterministic structural properties extracted from the model graph."""
    available: bool
    framework: str
    error: str | None = None
    # ONNX / ORT fields
    graph_name: str | None = None
    domain: str | None = None
    description: str | None = None
    ir_version: int | None = None
    opset_versions: dict[str, int] = field(default_factory=dict)
    input_names: list[str] = field(default_factory=list)
    input_shapes: list[Any] = field(default_factory=list)
    output_names: list[str] = field(default_factory=list)
    output_shapes: list[Any] = field(default_factory=list)
    node_count: int | None = None
    operator_types: list[str] = field(default_factory=list)
    initializer_count: int | None = None
    dtype_distribution: dict[str, int] = field(default_factory=dict)
    # PyTorch fields
    parameter_count: int | None = None
    top_level_keys: list[str] = field(default_factory=list)


@dataclass
class BehavioralProbe:
    """Single behavioral probe result."""
    probe_name: str
    input_shape: list[int]
    output_shape: list[int] | None
    output_dtype: str | None
    output_sha256: str | None
    output_mean: float | None
    output_std: float | None
    output_min: float | None
    output_max: float | None
    error: str | None = None


@dataclass
class BehavioralFingerprint:
    """Behavioral characterization from a deterministic probe battery."""
    available: bool
    framework: str
    error: str | None = None
    probes: list[BehavioralProbe] = field(default_factory=list)


@dataclass
class ModelFingerprint:
    """Complete fingerprint for a model artifact."""
    artifact: ArtifactFingerprint
    structural: StructuralFingerprint
    behavioral: BehavioralFingerprint

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# ONNX structural fingerprint (ORT-primary, onnx-package-optional)
# ---------------------------------------------------------------------------

def _fingerprint_onnx_structural(model_path: Path) -> StructuralFingerprint:
    """
    Extract structural fingerprint from an ONNX model.

    Primary path: onnxruntime.InferenceSession (always available when ORT installed).
    Supplemental path: onnx package (provides node/initializer counts, opsets).
    Either path can be missing; both being missing → unavailable.
    """
    if not _ORT_AVAILABLE:
        return StructuralFingerprint(
            available=False, framework="onnx",
            error="onnxruntime not installed; structural analysis unavailable",
        )

    import onnxruntime as ort

    try:
        sess = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
    except Exception as exc:
        return StructuralFingerprint(
            available=False, framework="onnx",
            error=f"ORT session creation failed: {exc}",
        )

    try:
        meta = sess.get_modelmeta()
        graph_name = meta.graph_name or None
        domain = meta.domain or None
        description = meta.description or None
    except Exception:
        graph_name = domain = description = None

    inputs = sess.get_inputs()
    outputs = sess.get_outputs()

    input_names = [i.name for i in inputs]
    input_shapes = [{"shape": i.shape, "type": i.type} for i in inputs]
    output_names = [o.name for o in outputs]
    output_shapes = [{"shape": o.shape, "type": o.type} for o in outputs]

    # Supplemental structural data from onnx package (optional)
    ir_version = None
    opset_versions: dict[str, int] = {}
    node_count: int | None = None
    operator_types: list[str] = []
    initializer_count: int | None = None
    dtype_distribution: dict[str, int] = {}

    if _ONNX_AVAILABLE:
        try:
            import onnx
            model_proto = onnx.load(str(model_path))
            ir_version = model_proto.ir_version
            for op in model_proto.opset_import:
                dom = op.domain if op.domain else "ai.onnx"
                opset_versions[dom] = op.version
            graph = model_proto.graph
            node_count = len(graph.node)
            operator_types = sorted({n.op_type for n in graph.node})
            initializer_count = len(graph.initializer)
            for init in graph.initializer:
                try:
                    dtype_name = onnx.TensorProto.DataType.Name(init.data_type)
                except Exception:
                    dtype_name = str(init.data_type)
                dtype_distribution[dtype_name] = dtype_distribution.get(dtype_name, 0) + 1
        except Exception as exc:
            log.debug("onnx package structural extraction failed: %s", exc)

    return StructuralFingerprint(
        available=True,
        framework="onnx",
        graph_name=graph_name,
        domain=domain,
        description=description,
        ir_version=ir_version,
        opset_versions=opset_versions,
        input_names=input_names,
        input_shapes=input_shapes,
        output_names=output_names,
        output_shapes=output_shapes,
        node_count=node_count,
        operator_types=operator_types,
        initializer_count=initializer_count,
        dtype_distribution=dtype_distribution,
    )


# ---------------------------------------------------------------------------
# PyTorch structural fingerprint
# ---------------------------------------------------------------------------

def _fingerprint_pytorch_structural(raw_obj: Any) -> StructuralFingerprint:
    """Extract structural fingerprint from a PyTorch state dict."""
    try:
        import torch
        if not isinstance(raw_obj, dict):
            return StructuralFingerprint(
                available=False,
                framework="pytorch",
                error=f"Expected dict (state_dict), got {type(raw_obj).__name__}",
            )

        top_keys = sorted(raw_obj.keys())[:100]
        total_params = 0
        dtype_dist: dict[str, int] = {}

        for v in raw_obj.values():
            if isinstance(v, torch.Tensor):
                total_params += v.numel()
                dtype_name = str(v.dtype).replace("torch.", "")
                dtype_dist[dtype_name] = dtype_dist.get(dtype_name, 0) + 1

        return StructuralFingerprint(
            available=True,
            framework="pytorch",
            parameter_count=total_params,
            top_level_keys=top_keys,
            dtype_distribution=dtype_dist,
        )
    except Exception as exc:
        log.warning("PyTorch structural fingerprint failed: %s", exc)
        return StructuralFingerprint(available=False, framework="pytorch", error=str(exc))


# ---------------------------------------------------------------------------
# Behavioral fingerprint helpers
# ---------------------------------------------------------------------------

def _make_probe_input(
    shape: list[int | str | None],
    ort_type: str,
    fill: str,
    seed: int = 0,
) -> Any | None:
    """
    Create a deterministic numpy array for a behavioral probe.

    Symbolic / dynamic dimensions (strings, None, ≤0) are replaced with 1.
    fill: "zeros" | "ones" | "noise"
    Returns None if the type is unsupported (e.g., string tensors).
    """
    import numpy as np

    concrete = [d if isinstance(d, int) and d > 0 else 1 for d in shape]

    dtype_map: dict[str, type] = {
        "tensor(float)":  np.float32,
        "tensor(double)": np.float64,
        "tensor(int32)":  np.int32,
        "tensor(int64)":  np.int64,
        "tensor(uint8)":  np.uint8,
        "tensor(int8)":   np.int8,
        "tensor(bool)":   np.bool_,
    }
    np_dtype = dtype_map.get(ort_type)
    if np_dtype is None:
        return None  # Unsupported input type (e.g., string)

    if fill == "zeros":
        return np.zeros(concrete, dtype=np_dtype)
    elif fill == "ones":
        return np.ones(concrete, dtype=np_dtype)
    else:  # noise — deterministically seeded
        rng = np.random.default_rng(seed)
        if np.issubdtype(np_dtype, np.floating):
            return rng.standard_normal(concrete).astype(np_dtype)
        elif np.issubdtype(np_dtype, np.integer):
            info = np.iinfo(np_dtype)
            return rng.integers(info.min, info.max, size=concrete, dtype=np_dtype)
        else:
            return rng.integers(0, 2, size=concrete, dtype=np_dtype)


def _hash_array(arr: Any) -> str:
    """SHA-256 of numpy array raw bytes."""
    try:
        return hashlib.sha256(arr.tobytes()).hexdigest()
    except Exception:
        return ""


def _array_stats(arr: Any) -> tuple[float | None, float | None, float | None, float | None]:
    """Return (mean, std, min, max) as Python floats, or None on failure."""
    try:
        import numpy as np
        a = arr.astype(np.float64)
        return float(a.mean()), float(a.std()), float(a.min()), float(a.max())
    except Exception:
        return None, None, None, None


# ---------------------------------------------------------------------------
# ONNX behavioral fingerprint
# ---------------------------------------------------------------------------

def _fingerprint_onnx_behavioral(model_path: Path) -> BehavioralFingerprint:
    """Run the deterministic probe battery against an ONNX model via ORT."""
    if not _ORT_AVAILABLE:
        return BehavioralFingerprint(
            available=False, framework="onnx",
            error="onnxruntime not installed; behavioral analysis unavailable",
        )

    import onnxruntime as ort

    try:
        sess = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
    except Exception as exc:
        return BehavioralFingerprint(
            available=False, framework="onnx",
            error=f"ORT session creation failed: {exc}",
        )

    probes: list[BehavioralProbe] = []

    for probe_idx, fill in enumerate(["zeros", "ones", "noise"]):
        probe_name = f"probe_{fill}"
        try:
            feed: dict[str, Any] = {}
            input_shapes_used: list[int] = []
            skip_reason: str | None = None

            for inp in sess.get_inputs():
                shape = [d if isinstance(d, int) and d > 0 else 1 for d in inp.shape]
                input_shapes_used = shape
                arr = _make_probe_input(
                    inp.shape, inp.type, fill,
                    seed=_BATTERY_SEED + probe_idx,
                )
                if arr is None:
                    skip_reason = f"Unsupported input type: {inp.type}"
                    break
                feed[inp.name] = arr

            if skip_reason:
                probes.append(BehavioralProbe(
                    probe_name=probe_name, input_shape=input_shapes_used,
                    output_shape=None, output_dtype=None, output_sha256=None,
                    output_mean=None, output_std=None, output_min=None, output_max=None,
                    error=skip_reason,
                ))
                continue

            outputs = sess.run(None, feed)
            if outputs:
                out = outputs[0]
                mean, std, mn, mx = _array_stats(out)
                probes.append(BehavioralProbe(
                    probe_name=probe_name,
                    input_shape=input_shapes_used,
                    output_shape=list(out.shape),
                    output_dtype=str(out.dtype),
                    output_sha256=_hash_array(out),
                    output_mean=mean, output_std=std,
                    output_min=mn, output_max=mx,
                ))
            else:
                probes.append(BehavioralProbe(
                    probe_name=probe_name, input_shape=input_shapes_used,
                    output_shape=None, output_dtype=None, output_sha256=None,
                    output_mean=None, output_std=None, output_min=None, output_max=None,
                    error="Model produced no outputs",
                ))

        except Exception as exc:
            probes.append(BehavioralProbe(
                probe_name=probe_name, input_shape=[],
                output_shape=None, output_dtype=None, output_sha256=None,
                output_mean=None, output_std=None, output_min=None, output_max=None,
                error=str(exc),
            ))

    return BehavioralFingerprint(available=True, framework="onnx", probes=probes)


# ---------------------------------------------------------------------------
# PyTorch behavioral fingerprint
# ---------------------------------------------------------------------------

def _fingerprint_pytorch_behavioral() -> BehavioralFingerprint:
    """
    PyTorch state dicts cannot be executed without the architecture class.
    This is an explicit coverage limitation, not a false clean result.
    """
    return BehavioralFingerprint(
        available=False,
        framework="pytorch",
        error=(
            "PyTorch state dicts cannot be executed without the model architecture class. "
            "Behavioral fingerprint is unavailable for raw .pt/.pth state dicts. "
            "Use TorchScript (.ts) for behavioral fingerprinting."
        ),
    )


# ---------------------------------------------------------------------------
# Full fingerprint builder
# ---------------------------------------------------------------------------

def build_fingerprint(
    model_path: Path,
    *,
    max_size_bytes: int = 5 * 1024 * 1024 * 1024,
) -> ModelFingerprint:
    """
    Build a complete ModelFingerprint for the model at *model_path*.

    Does NOT persist anything.
    Does NOT raise on unavailable frameworks — returns structured unavailability.
    """
    from backend.infra.crypto import hash_file
    from backend.infra.model_loader import SUPPORTED_EXTENSIONS

    analyzed_at = datetime.now(timezone.utc).isoformat()
    framework = SUPPORTED_EXTENSIONS.get(model_path.suffix.lower(), "unknown")

    try:
        sha256 = hash_file(model_path)
        file_size = model_path.stat().st_size
    except Exception as exc:
        log.error("Failed to compute artifact fingerprint: %s", exc)
        sha256 = ""
        file_size = 0

    artifact = ArtifactFingerprint(
        sha256=sha256,
        file_size_bytes=file_size,
        format=framework,
        pramaan_version=_PRAMAAN_VERSION,
        analyzed_at_utc=analyzed_at,
    )

    # Try loading the model (needed for PyTorch structural)
    loaded = None
    load_error: str | None = None
    if framework in ("pytorch", "torchscript"):
        try:
            loaded = load_model(model_path, max_size_bytes=max_size_bytes)
        except ModelLoadError as exc:
            load_error = f"{exc.code.value}: {exc}"

    # Structural fingerprint
    if framework == "onnx":
        structural = _fingerprint_onnx_structural(model_path)
    elif framework == "pytorch" and loaded is not None:
        structural = _fingerprint_pytorch_structural(loaded.raw_object)
    elif framework in ("pytorch", "torchscript") and load_error:
        structural = StructuralFingerprint(
            available=False, framework=framework, error=load_error
        )
    else:
        structural = StructuralFingerprint(
            available=False, framework=framework,
            error=f"No structural extractor for framework: {framework}",
        )

    # Behavioral fingerprint
    if framework == "onnx":
        behavioral = _fingerprint_onnx_behavioral(model_path)
    elif framework == "pytorch":
        behavioral = _fingerprint_pytorch_behavioral()
    else:
        behavioral = BehavioralFingerprint(
            available=False, framework=framework,
            error=f"Behavioral fingerprinting not supported for: {framework}",
        )

    return ModelFingerprint(artifact=artifact, structural=structural, behavioral=behavioral)


# ---------------------------------------------------------------------------
# Reference comparison
# ---------------------------------------------------------------------------

@dataclass
class ComparisonDifference:
    field: str
    reference_value: Any
    observed_value: Any
    description: str


def compare_fingerprints(
    observed: ModelFingerprint,
    reference: dict[str, Any],
) -> list[ComparisonDifference]:
    """
    Compare *observed* against a reference fingerprint dict.

    Returns a list of material differences, empty if all fields match.
    Missing reference fields are skipped (older fingerprint versions).
    """
    diffs: list[ComparisonDifference] = []
    obs_dict = observed.to_dict()

    def _check(path: str, ref_val: Any, obs_val: Any, desc: str) -> None:
        if ref_val is None or obs_val is None:
            return  # Cannot compare unavailable fields
        if ref_val != obs_val:
            diffs.append(ComparisonDifference(
                field=path, reference_value=ref_val,
                observed_value=obs_val, description=desc,
            ))

    ref_a = reference.get("artifact", {})
    obs_a = obs_dict.get("artifact", {})
    _check("artifact.sha256",
           ref_a.get("sha256"), obs_a.get("sha256"),
           "Model file SHA-256 has changed. The binary artifact has been modified.")
    _check("artifact.file_size_bytes",
           ref_a.get("file_size_bytes"), obs_a.get("file_size_bytes"),
           "Model file size differs from reference.")

    ref_s = reference.get("structural", {})
    obs_s = obs_dict.get("structural", {})
    if ref_s.get("available") and obs_s.get("available"):
        for fld, desc in [
            ("node_count", "Number of graph nodes changed — structural modification detected."),
            ("initializer_count", "Number of initializers (parameters) changed."),
            ("parameter_count", "Total parameter count differs from reference."),
            ("input_names", "Model input names changed."),
            ("output_names", "Model output names changed."),
            ("operator_types", "Set of operator types changed — architecture modification."),
            ("dtype_distribution", "Tensor dtype distribution changed."),
            ("ir_version", "ONNX IR version changed."),
        ]:
            _check(f"structural.{fld}", ref_s.get(fld), obs_s.get(fld), desc)

    ref_b = reference.get("behavioral", {})
    obs_b = obs_dict.get("behavioral", {})
    if ref_b.get("available") and obs_b.get("available"):
        ref_probes = {p["probe_name"]: p for p in ref_b.get("probes", [])}
        obs_probes = {p["probe_name"]: p for p in obs_b.get("probes", [])}
        for probe_name, ref_probe in ref_probes.items():
            obs_probe = obs_probes.get(probe_name)
            if obs_probe is None:
                continue
            _check(
                f"behavioral.{probe_name}.output_sha256",
                ref_probe.get("output_sha256"),
                obs_probe.get("output_sha256"),
                f"Behavioral output hash for probe '{probe_name}' differs — "
                f"model produces different outputs for identical deterministic inputs.",
            )
            _check(
                f"behavioral.{probe_name}.output_shape",
                ref_probe.get("output_shape"),
                obs_probe.get("output_shape"),
                f"Output tensor shape for probe '{probe_name}' changed.",
            )

    return diffs


# ---------------------------------------------------------------------------
# Risk / confidence derivation (ADR-003)
# ---------------------------------------------------------------------------

def _derive_risk_confidence(
    diffs: list[ComparisonDifference],
    observed: ModelFingerprint,
    has_reference: bool,
) -> tuple[RiskLevel, ConfidenceLevel, str]:
    """
    Derive risk and confidence from comparison results.

    Risk and confidence are strictly independent (ADR-003).
    """
    if not has_reference:
        if not observed.structural.available and not observed.behavioral.available:
            return (
                RiskLevel.NONE, ConfidenceLevel.LOW,
                "Framework unavailable; fingerprint incomplete. Coverage gap.",
            )
        return (
            RiskLevel.NONE, ConfidenceLevel.HIGH,
            "Fingerprint recorded. No reference provided — no integrity comparison performed.",
        )

    if not diffs:
        confidence = (
            ConfidenceLevel.MODERATE if not observed.behavioral.available
            else ConfidenceLevel.HIGH
        )
        return (
            RiskLevel.NONE, confidence,
            "All compared fingerprint fields match the reference.",
        )

    has_artifact_diff = any(d.field.startswith("artifact.") for d in diffs)
    has_structural_diff = any(d.field.startswith("structural.") for d in diffs)
    has_behavioral_diff = any(d.field.startswith("behavioral.") for d in diffs)

    if has_behavioral_diff:
        risk = RiskLevel.MEDIUM
        qualifier = (
            "Behavioral output divergence detected. "
            "The model produces different outputs from the reference for identical deterministic inputs. "
            "This may indicate weight modification. Analyst review required."
        )
    elif has_structural_diff:
        risk = RiskLevel.MEDIUM
        qualifier = (
            "Structural differences detected (node count, parameters, or operator types). "
            "The model graph has been modified from the reference."
        )
    elif has_artifact_diff:
        risk = RiskLevel.LOW
        qualifier = (
            "Artifact hash or size differs. The binary file has changed. "
            "Structural and behavioral fingerprints were not compared or matched."
        )
    else:
        risk = RiskLevel.LOW
        qualifier = "Differences detected in comparison fields."

    # Confidence driven by analysis availability — independent of risk
    if not observed.structural.available:
        confidence = ConfidenceLevel.LOW
    elif not observed.behavioral.available:
        confidence = ConfidenceLevel.MODERATE
    else:
        confidence = ConfidenceLevel.MODERATE  # diffs found → never HIGH

    return risk, confidence, qualifier


# ---------------------------------------------------------------------------
# Finding and Evidence construction
# ---------------------------------------------------------------------------

def _serialize_value(v: Any) -> Any:
    """Make a value JSON-serializable."""
    if isinstance(v, (str, int, float, bool, type(None))):
        return v
    if isinstance(v, (list, tuple)):
        return [_serialize_value(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _serialize_value(val) for k, val in v.items()}
    return str(v)


def _build_integrity_finding(
    diffs: list[ComparisonDifference],
    observed: ModelFingerprint,
    assessment_id: str,
    asset_id: str,
    detector_id: str,
    risk: RiskLevel,
) -> tuple[Finding, list[Evidence]]:
    """Build one Finding and one Evidence-per-diff for an integrity mismatch."""
    n = len(diffs)
    severity_map = {
        RiskLevel.NONE: Severity.INFO,
        RiskLevel.LOW: Severity.LOW,
        RiskLevel.MEDIUM: Severity.MEDIUM,
        RiskLevel.HIGH: Severity.HIGH,
        RiskLevel.CRITICAL: Severity.CRITICAL,
    }
    severity = severity_map.get(risk, Severity.MEDIUM)

    has_behavioral = any(d.field.startswith("behavioral.") for d in diffs)
    has_structural = any(d.field.startswith("structural.") for d in diffs)

    desc_parts = [f"{n} field(s) differ between the analyzed model and the reference fingerprint."]
    if has_behavioral:
        desc_parts.append(
            "Behavioral outputs differ for deterministic reference inputs — "
            "the model produces different predictions than the reference version."
        )
    if has_structural:
        desc_parts.append(
            "Structural properties (node count, parameters, operators) differ — "
            "the model graph has been modified."
        )
    desc_parts.append(
        "A changed model is an integrity difference. "
        "Analyst review is required to determine if the change is authorized."
    )

    finding = Finding(
        assessment_id=assessment_id,
        asset_id=asset_id,
        category=FindingCategory.MODEL_INTEGRITY,
        subcategory="integrity_mismatch",
        severity=severity,
        title=f"Model integrity difference detected: {n} field(s) differ from reference",
        description=" ".join(desc_parts),
        detection_method=_METADATA.name,
        detector_id=detector_id,
        limitations=[
            "SHA-256 difference does not prove malicious modification.",
            "Behavioral difference does not prove backdoor insertion.",
            "Analysis limited to safely loadable formats with available frameworks.",
        ],
        recommended_disposition=(
            "Verify model provenance and change history. "
            "Confirm differences are from authorized re-training or quantization. "
            "If unexplained, treat as unauthorized modification."
        ),
    )

    evidences: list[Evidence] = []
    for diff in diffs:
        ev = Evidence(
            finding_id=finding.finding_id,
            detector_id=detector_id,
            evidence_type=EvidenceType.COMPARISON,
            description=diff.description,
            data={
                "field": diff.field,
                "reference_value": _serialize_value(diff.reference_value),
                "observed_value": _serialize_value(diff.observed_value),
                "model_sha256": observed.artifact.sha256,
                "analysis_method": "deterministic_fingerprint_comparison",
                "detector_version": _METADATA.version,
            },
        )
        evidences.append(ev)

    return finding, evidences


def _build_fingerprint_evidence(
    observed: ModelFingerprint,
    detector_id: str,
    finding_id: str,
) -> Evidence:
    """Build an evidence record summarising the complete fingerprint."""
    return Evidence(
        finding_id=finding_id,
        detector_id=detector_id,
        evidence_type=EvidenceType.MEASUREMENT,
        description=f"Model fingerprint for artifact SHA-256 {observed.artifact.sha256[:16]}…",
        data={
            "artifact_sha256": observed.artifact.sha256,
            "artifact_file_size_bytes": observed.artifact.file_size_bytes,
            "artifact_format": observed.artifact.format,
            "structural_available": observed.structural.available,
            "behavioral_available": observed.behavioral.available,
            "node_count": observed.structural.node_count,
            "initializer_count": observed.structural.initializer_count,
            "parameter_count": observed.structural.parameter_count,
            "input_names": observed.structural.input_names,
            "output_names": observed.structural.output_names,
            "behavioral_probes": [
                {
                    "probe_name": p.probe_name,
                    "output_sha256": p.output_sha256,
                    "output_shape": p.output_shape,
                    "output_mean": p.output_mean,
                }
                for p in observed.behavioral.probes
            ],
            "analysis_timestamp_utc": observed.artifact.analyzed_at_utc,
            "pramaan_version": observed.artifact.pramaan_version,
        },
    )


# ---------------------------------------------------------------------------
# MI01Context
# ---------------------------------------------------------------------------

@dataclass
class MI01Context:
    """
    Additional MI-01 context that does not fit in the base DetectorContext.

    model_path: Absolute path to the model file to analyze.
    reference_fingerprint: Optional previously-captured fingerprint dict.
                           When None, fingerprint recorded, no comparison.
    """
    model_path: Path
    reference_fingerprint: dict[str, Any] | None = None
    max_model_size_bytes: int = 5 * 1024 * 1024 * 1024


# ---------------------------------------------------------------------------
# MI-01 Detector
# ---------------------------------------------------------------------------

class MI01FingerprintDetector:
    """
    MI-01: Model Integrity Fingerprinting and Comparison Detector.

    Implements the Detector protocol (ADR-004).
    Does NOT write to the database — that is the runner's responsibility.
    """

    @property
    def metadata(self) -> DetectorMetadata:
        return _METADATA

    def can_run(self, context: DetectorContext) -> CanRunResult:
        mi01 = getattr(context, "mi01", None)
        if mi01 is None:
            return CanRunResult(
                ok=False,
                reason="MI-01 requires context.mi01 (MI01Context) to be set.",
            )

        path: Path = mi01.model_path
        if not path.exists():
            return CanRunResult(ok=False, reason=f"Model file not found: {path}")
        if not path.is_file():
            return CanRunResult(ok=False, reason=f"Not a regular file: {path}")

        from backend.infra.model_loader import SUPPORTED_EXTENSIONS
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return CanRunResult(
                ok=False, reason=f"Unsupported model format: {path.suffix!r}",
            )

        return CanRunResult(ok=True)

    def run(self, context: DetectorContext) -> DetectorOutput:
        """
        Run fingerprinting and optional comparison.
        Does NOT persist. Caller uses runner.run_detector().
        """
        output = DetectorOutput()
        did = _METADATA.detector_id
        mi01: MI01Context = context.mi01  # type: ignore[attr-defined]

        try:
            fp = build_fingerprint(
                mi01.model_path,
                max_size_bytes=mi01.max_model_size_bytes,
            )
        except Exception as exc:
            output.status = DetectorStatus.FAILED
            output.error = f"Fingerprint build failed: {exc}"
            log.exception("MI-01 fingerprint build failed for %s", mi01.model_path)
            return output.finalize()

        has_reference = mi01.reference_fingerprint is not None
        diffs: list[ComparisonDifference] = []

        if has_reference:
            try:
                diffs = compare_fingerprints(fp, mi01.reference_fingerprint)
            except Exception as exc:
                log.warning("MI-01 comparison failed: %s", exc)
                output.status = DetectorStatus.PARTIAL
                output.error = f"Comparison failed: {exc}"

        risk, confidence, qualifier = _derive_risk_confidence(diffs, fp, has_reference)
        output.risk_level = risk
        output.confidence_level = confidence

        # Always create an INFO finding to record the fingerprint
        info_finding = Finding(
            assessment_id=context.assessment_id,
            asset_id=context.asset_id,
            category=FindingCategory.MODEL_INTEGRITY,
            subcategory="fingerprint_recorded",
            severity=Severity.INFO,
            title=f"Model fingerprint recorded: {mi01.model_path.name}",
            description=(
                f"SHA-256: {fp.artifact.sha256}. "
                f"Format: {fp.artifact.format}. "
                f"Structural: {'available' if fp.structural.available else 'unavailable'}. "
                f"Behavioral: {'available' if fp.behavioral.available else 'unavailable'}. "
                f"{qualifier}"
            ),
            detection_method=_METADATA.name,
            detector_id=did,
            limitations=(
                [
                    "Framework unavailable — structural/behavioral analysis incomplete.",
                    "Coverage gap — results have LOW confidence.",
                ]
                if not fp.structural.available
                else []
            ),
        )
        fp_evidence = _build_fingerprint_evidence(fp, did, info_finding.finding_id)
        output.findings.append(info_finding)
        output.evidence.append(fp_evidence)

        # Integrity mismatch finding (only when reference comparison found diffs)
        if diffs:
            mismatch_finding, mismatch_evidences = _build_integrity_finding(
                diffs, fp, context.assessment_id, context.asset_id, did, risk
            )
            output.findings.append(mismatch_finding)
            output.evidence.extend(mismatch_evidences)

        # Partial status when analysis was incomplete
        if output.status == DetectorStatus.SUCCESS:
            if not fp.structural.available or not fp.behavioral.available:
                output.status = DetectorStatus.PARTIAL

        log.info(
            "MI-01 complete: risk=%s confidence=%s diffs=%d "
            "structural=%s behavioral=%s",
            risk.value, confidence.value, len(diffs),
            fp.structural.available, fp.behavioral.available,
        )

        return output.finalize()
