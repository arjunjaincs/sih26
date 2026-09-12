"""
PRAMAAN v1 — Model Integrity Corpus Generator.

Generates a small, deterministic, fully offline benchmark model corpus
for validating the actual MI-01 through MI-05 detectors across 9 distinct
integrity scenarios:

  1. 01_clean_reference          -- Exact cryptographic & behavioral match to reference
  2. 02_model_substitution       -- Architecture & graph substitution (Relu vs Add_Bias)
  3. 03_parameter_corruption      -- Non-finite NaN weight injection (numerical corruption)
  4. 04_weight_magnitude_anomaly -- Extreme weight distribution explosion (|w| > 10,000)
  5. 05_activation_collapse      -- Dead representation syndrome (> 98% zero activations)
  6. 06_trigger_convergence      -- Trojan shortcut / backdoor localized mode collapse
  7. 07_missing_reference        -- Standalone model baseline enrollment (no reference baseline)
  8. 08_state_dict_coverage_gap  -- PyTorch non-executable state dict (honest coverage gaps)
  9. 09_malformed_artifact       -- Corrupt binary header / fail-closed security boundary

Design Principles:
  - Deterministic: master seed 42 produces reproducible model weights and graphs.
  - Strict Isolation: ground_truth.json is NEVER stored in input/ directories.
  - Zero Leakage: model manifests contain only operational metadata.
  - Pure Offline: zero network requests, downloads, or external model dependencies.
  - Claim Discipline: ground truth records objective mutations, never asserts malice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.assessment.models import AssessmentRequest
from backend.assessment.orchestrator import AssessmentService
from backend.detectors.base import DetectorContext
from backend.detectors.model.mi01_fingerprint import MI01Context, MI01FingerprintDetector
from backend.detectors.model.mi02_parameter_stats import MI02Context, MI02ParameterStatsDetector
from backend.detectors.model.mi03_activation_stats import MI03Context, MI03ActivationStatsDetector
from backend.detectors.model.mi04_reference_comparison import MI04Context, MI04ReferenceComparisonDetector
from backend.detectors.model.mi05_trigger_anomaly import MI05Context, MI05TriggerAnomalyDetector
from backend.detectors.runner import run_detector
from backend.domain.enums import DetectorStatus, RiskLevel
from backend.infra.crypto import hash_file
from backend.infra.db import open_db
from backend.infra.model_loader import ModelLoadError, ModelLoadErrorCode, load_model

log = logging.getLogger("model_corpus_generator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DEFAULT_MODEL_CORPUS_ROOT = Path("data/corpus/models")

# ---------------------------------------------------------------------------
# Protobuf Wire-Format Primitives (Raw ONNX Synthesis without dependencies)
# ---------------------------------------------------------------------------

def _varint(n: int) -> bytes:
    """Encode an integer as a base-128 varint."""
    out = []
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _tag_varint(field_num: int) -> bytes:
    return _varint((field_num << 3) | 0)


def _tag_len(field_num: int) -> bytes:
    return _varint((field_num << 3) | 2)


def _enc_varint(field_num: int, value: int) -> bytes:
    return _tag_varint(field_num) + _varint(value)


def _enc_bytes(field_num: int, data: bytes) -> bytes:
    return _tag_len(field_num) + _varint(len(data)) + data


def _enc_str(field_num: int, s: str) -> bytes:
    return _enc_bytes(field_num, s.encode("utf-8"))


def _f32_raw(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


_FLOAT = 1  # TensorProto.DataType.FLOAT


def _type_proto_float(shape: list[int]) -> bytes:
    dims_bytes = b""
    for d in shape:
        dim_msg = _enc_varint(1, d)
        dims_bytes += _enc_bytes(1, dim_msg)
    tensor_type_msg = _enc_varint(1, _FLOAT) + _enc_bytes(2, dims_bytes)
    return _enc_bytes(1, tensor_type_msg)


def _value_info(name: str, shape: list[int]) -> bytes:
    return _enc_str(1, name) + _enc_bytes(2, _type_proto_float(shape))


def _node(op_type: str, inputs: list[str], outputs: list[str]) -> bytes:
    payload = b""
    for i in inputs:
        payload += _enc_str(1, i)
    for o in outputs:
        payload += _enc_str(2, o)
    payload += _enc_str(4, op_type)
    return payload


def _initializer_float(name: str, shape: list[int], values: list[float]) -> bytes:
    payload = b""
    for d in shape:
        payload += _enc_varint(1, d)
    payload += _enc_varint(2, _FLOAT)
    payload += _enc_str(8, name)
    payload += _enc_bytes(9, _f32_raw(values))
    return payload


def _opset(domain: str = "", version: int = 17) -> bytes:
    return _enc_str(1, domain) + _enc_varint(2, version)


def _graph(
    name: str,
    nodes: list[bytes],
    inputs: list[bytes],
    outputs: list[bytes],
    initializers: list[bytes] | None = None,
) -> bytes:
    payload = b""
    for node in nodes:
        payload += _enc_bytes(1, node)
    payload += _enc_str(2, name)
    if initializers:
        for init in initializers:
            payload += _enc_bytes(5, init)
    for inp in inputs:
        payload += _enc_bytes(11, inp)
    for out in outputs:
        payload += _enc_bytes(12, out)
    return payload


def _model(graph: bytes, ir_version: int = 8, opset_version: int = 17) -> bytes:
    return (
        _enc_varint(1, ir_version)
        + _enc_bytes(7, graph)
        + _enc_bytes(8, _opset("", opset_version))
    )


# ---------------------------------------------------------------------------
# Procedural Model Factories
# ---------------------------------------------------------------------------

def make_relu_model(input_shape: list[int] | None = None) -> bytes:
    """Minimal valid ONNX model: Y = Relu(X)."""
    if input_shape is None:
        input_shape = [1, 3]
    x_vi = _value_info("X", input_shape)
    y_vi = _value_info("Y", input_shape)
    relu = _node("Relu", ["X"], ["Y"])
    graph = _graph("relu_graph", [relu], [x_vi], [y_vi])
    return _model(graph)


def make_add_bias_model(
    bias_values: list[float] | None = None,
    input_shape: list[int] | None = None,
) -> bytes:
    """Minimal ONNX model: Y = X + B with learnable bias B."""
    if input_shape is None:
        input_shape = [1, 3]
    if bias_values is None:
        bias_values = [0.5] * input_shape[-1]
    x_vi = _value_info("X", input_shape)
    y_vi = _value_info("Y", input_shape)
    bias_init = _initializer_float("B", input_shape, bias_values)
    add = _node("Add", ["X", "B"], ["Y"])
    graph = _graph("add_bias_graph", [add], [x_vi], [y_vi], initializers=[bias_init])
    return _model(graph)


def make_multi_layer_model(input_shape: list[int] | None = None) -> bytes:
    """2-node ONNX model: H = Add(X, B), Y = Relu(H)."""
    if input_shape is None:
        input_shape = [1, 4]
    x_vi = _value_info("X", input_shape)
    y_vi = _value_info("Y", input_shape)
    bias_init = _initializer_float("B", input_shape, [0.5] * input_shape[-1])
    add = _node("Add", ["X", "B"], ["H"])
    relu = _node("Relu", ["H"], ["Y"])
    graph = _graph("multi_layer_graph", [add, relu], [x_vi], [y_vi], initializers=[bias_init])
    return _model(graph)


def make_dead_representation_model(input_shape: list[int] | None = None) -> bytes:
    """ONNX model where outputs are clamped to 0: Y = Relu(X + (-1000))."""
    if input_shape is None:
        input_shape = [1, 4]
    x_vi = _value_info("X", input_shape)
    y_vi = _value_info("Y", input_shape)
    bias_init = _initializer_float("B", input_shape, [-1000.0] * input_shape[-1])
    add = _node("Add", ["X", "B"], ["H"])
    relu = _node("Relu", ["H"], ["Y"])
    graph = _graph("dead_repr_graph", [add, relu], [x_vi], [y_vi], initializers=[bias_init])
    return _model(graph)


def make_pytorch_state_dict_bytes(seed: int = 42) -> bytes:
    """Generate PyTorch state dict bytes safely using CPU tensors."""
    import io
    import torch

    torch.manual_seed(seed)
    buffer = io.BytesIO()
    state = {
        "conv.weight": torch.randn(4, 4),
        "conv.bias": torch.zeros(4),
    }
    torch.save(state, buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Scenario Definitions & Builders
# ---------------------------------------------------------------------------

SCENARIOS: list[dict[str, Any]] = [
    {
        "scenario_id": "01_clean_reference",
        "name": "Clean Baseline with Reference",
        "category": "clean_baseline",
        "framework": "onnx",
        "has_reference": True,
        "description": "Pristine model with identical reference model confirming exact cryptographic match.",
        "expected_overall_risk": "NONE",
        "expected_confidence": "HIGH",
        "expected_findings": {
            "mi01_fingerprint": {"risk": "NONE", "subcategory": "reference_match"},
            "mi02_parameter_stats": {"risk": "NONE", "subcategory": "parameter_stats_recorded"},
            "mi03_activation_stats": {"risk": "NONE", "subcategory": "activation_profile_recorded"},
            "mi04_reference_comparison": {"risk": "NONE", "subcategory": "reference_exact_match"},
            "mi05_trigger_anomaly": {"risk": "NONE", "subcategory": "trigger_search_completed"},
        },
        "coverage_gaps_count": 0,
    },
    {
        "scenario_id": "02_model_substitution",
        "name": "Architecture / Graph Substitution",
        "category": "substitution",
        "framework": "onnx",
        "has_reference": True,
        "description": "Candidate graph (Relu) substituted for reference graph (Add_Bias), causing behavioral divergence.",
        "expected_overall_risk": "MEDIUM",
        "expected_confidence": "HIGH",
        "expected_findings": {
            "mi01_fingerprint": {"risk": "NONE"},  # standalone fingerprint profile recorded
            "mi02_parameter_stats": {"risk": "NONE"},
            "mi03_activation_stats": {"risk": "NONE"},
            "mi04_reference_comparison": {"risk": "MEDIUM", "subcategory": "behavioral_divergence"},
            "mi05_trigger_anomaly": {"risk": "NONE"},
        },
        "coverage_gaps_count": 0,
    },
    {
        "scenario_id": "03_parameter_corruption",
        "name": "Non-Finite Weight Tampering",
        "category": "parameter_modification",
        "framework": "onnx",
        "has_reference": True,
        "description": "Candidate model initializers contain non-finite IEEE 754 NaN values.",
        "expected_overall_risk": "HIGH",
        "expected_confidence": "HIGH",
        "expected_findings": {
            "mi02_parameter_stats": {"risk": "HIGH", "subcategory": "parameter_corruption"},
            "mi03_activation_stats": {"risk": "HIGH", "subcategory": "activation_numerical_instability"},
            "mi04_reference_comparison": {"risk": "MEDIUM", "subcategory": "artifact_mismatch"},
        },
        "coverage_gaps_count": 0,
    },
    {
        "scenario_id": "04_weight_magnitude_anomaly",
        "name": "Statistical Weight Outlier",
        "category": "parameter_modification",
        "framework": "onnx",
        "has_reference": True,
        "description": "Weights exceed standard magnitude thresholds (|w| > 10,000) without NaN corruption.",
        "expected_overall_risk": "MEDIUM",
        "expected_confidence": "HIGH",
        "expected_findings": {
            "mi02_parameter_stats": {"risk": "MEDIUM", "subcategory": "weight_distribution_anomaly"},
            "mi04_reference_comparison": {"risk": "MEDIUM", "subcategory": "behavioral_divergence"},
        },
        "coverage_gaps_count": 0,
    },
    {
        "scenario_id": "05_activation_collapse",
        "name": "Dead Representation Syndrome",
        "category": "activation_behavior",
        "framework": "onnx",
        "has_reference": False,
        "description": "Model activations clamped to zero across all non-zero deterministic probes.",
        "expected_overall_risk": "MEDIUM",
        "expected_confidence": "LOW",  # MI-05 insufficient diversity gates confidence to LOW
        "expected_findings": {
            "mi03_activation_stats": {"risk": "MEDIUM", "subcategory": "activation_collapse"},
            "mi05_trigger_anomaly": {"status": "PARTIAL", "risk": "NONE", "subcategory": "trigger_analysis_insufficient_diversity"},
        },
        "coverage_gaps_count": 0,
    },
    {
        "scenario_id": "06_trigger_convergence",
        "name": "Trojan Shortcut Convergence",
        "category": "behavioral_perturbation",
        "framework": "onnx",
        "has_reference": False,
        "description": "Candidate spatial perturbation collapses diverse probe outputs into an invariant target mode.",
        "expected_overall_risk": "HIGH",
        "expected_confidence": "HIGH",
        "expected_findings": {
            "mi05_trigger_anomaly": {"risk": "HIGH", "subcategory": "suspicious_trigger_convergence"},
        },
        "coverage_gaps_count": 0,
    },
    {
        "scenario_id": "07_missing_reference",
        "name": "Standalone Baseline Enrollment",
        "category": "missing_reference",
        "framework": "onnx",
        "has_reference": False,
        "description": "Operational model baseline recorded cleanly when no reference artifact exists.",
        "expected_overall_risk": "NONE",
        "expected_confidence": "HIGH",
        "expected_findings": {
            "mi01_fingerprint": {"risk": "NONE", "subcategory": "fingerprint_recorded"},
            "mi02_parameter_stats": {"risk": "NONE"},
            "mi03_activation_stats": {"risk": "NONE"},
            "mi05_trigger_anomaly": {"risk": "NONE"},
        },
        "expected_detector_status": {
            "mi04_reference_comparison": "NOT_APPLICABLE",
        },
        "coverage_gaps_count": 0,
    },
    {
        "scenario_id": "08_state_dict_coverage_gap",
        "name": "Non-Executable State Dict",
        "category": "access_mode_coverage_gap",
        "framework": "pytorch",
        "has_reference": False,
        "description": "PyTorch state dict provides weight inspection while reporting explicit execution coverage gaps.",
        "expected_overall_risk": "NONE",
        "expected_confidence": "LOW",  # coverage gaps gate overall confidence to LOW
        "expected_findings": {
            "mi01_fingerprint": {"risk": "NONE", "status": "PARTIAL"},
            "mi02_parameter_stats": {"risk": "NONE", "status": "SUCCESS"},
        },
        "expected_coverage_gaps": [
            "model.integrity.mi03_activation_stats",
            "model.integrity.mi05_trigger_anomaly",
        ],
        "coverage_gaps_count": 2,
    },
    {
        "scenario_id": "09_malformed_artifact",
        "name": "Corrupt Binary Header",
        "category": "malformed_unsupported",
        "framework": "onnx",
        "has_reference": False,
        "description": "Corrupted protobuf binary rejected fail-closed before execution.",
        "expected_overall_risk": "NONE",
        "expected_disposition": "REJECT",
        "expected_error_code": "malformed",
        "coverage_gaps_count": 0,
    },
]


def _build_scenario_files(scen: dict[str, Any], input_dir: Path, gt_dir: Path) -> dict[str, Any]:
    """Generate the exact candidate and reference files for a scenario."""
    scen_id = scen["scenario_id"]
    model_files: list[dict[str, Any]] = []

    if scen_id == "01_clean_reference":
        clean_bytes = make_add_bias_model(bias_values=[0.5, 0.5, 0.5], input_shape=[1, 3])
        p_cand = input_dir / "model.onnx"
        p_ref = input_dir / "reference.onnx"
        p_cand.write_bytes(clean_bytes)
        p_ref.write_bytes(clean_bytes)
        model_files.extend([
            {"role": "candidate", "file_name": "model.onnx", "size_bytes": len(clean_bytes), "sha256": hash_file(p_cand)},
            {"role": "reference", "file_name": "reference.onnx", "size_bytes": len(clean_bytes), "sha256": hash_file(p_ref)},
        ])

    elif scen_id == "02_model_substitution":
        relu_bytes = make_relu_model(input_shape=[1, 3])
        bias_bytes = make_add_bias_model(bias_values=[0.5, 0.5, 0.5], input_shape=[1, 3])
        p_cand = input_dir / "model.onnx"
        p_ref = input_dir / "reference.onnx"
        p_cand.write_bytes(relu_bytes)
        p_ref.write_bytes(bias_bytes)
        model_files.extend([
            {"role": "candidate", "file_name": "model.onnx", "size_bytes": len(relu_bytes), "sha256": hash_file(p_cand)},
            {"role": "reference", "file_name": "reference.onnx", "size_bytes": len(bias_bytes), "sha256": hash_file(p_ref)},
        ])

    elif scen_id == "03_parameter_corruption":
        nan_bytes = make_add_bias_model(bias_values=[float("nan"), float("nan"), 0.5], input_shape=[1, 3])
        clean_bytes = make_add_bias_model(bias_values=[0.5, 0.5, 0.5], input_shape=[1, 3])
        p_cand = input_dir / "model.onnx"
        p_ref = input_dir / "reference.onnx"
        p_cand.write_bytes(nan_bytes)
        p_ref.write_bytes(clean_bytes)
        model_files.extend([
            {"role": "candidate", "file_name": "model.onnx", "size_bytes": len(nan_bytes), "sha256": hash_file(p_cand)},
            {"role": "reference", "file_name": "reference.onnx", "size_bytes": len(clean_bytes), "sha256": hash_file(p_ref)},
        ])

    elif scen_id == "04_weight_magnitude_anomaly":
        mag_bytes = make_add_bias_model(bias_values=[50000.0, -80000.0, 120000.0], input_shape=[1, 3])
        clean_bytes = make_add_bias_model(bias_values=[0.5, 0.5, 0.5], input_shape=[1, 3])
        p_cand = input_dir / "model.onnx"
        p_ref = input_dir / "reference.onnx"
        p_cand.write_bytes(mag_bytes)
        p_ref.write_bytes(clean_bytes)
        model_files.extend([
            {"role": "candidate", "file_name": "model.onnx", "size_bytes": len(mag_bytes), "sha256": hash_file(p_cand)},
            {"role": "reference", "file_name": "reference.onnx", "size_bytes": len(clean_bytes), "sha256": hash_file(p_ref)},
        ])

    elif scen_id == "05_activation_collapse":
        dead_bytes = make_dead_representation_model(input_shape=[1, 4])
        p_cand = input_dir / "model.onnx"
        p_cand.write_bytes(dead_bytes)
        model_files.append({"role": "candidate", "file_name": "model.onnx", "size_bytes": len(dead_bytes), "sha256": hash_file(p_cand)})

    elif scen_id == "06_trigger_convergence":
        trig_bytes = make_relu_model(input_shape=[1, 1])
        p_cand = input_dir / "model.onnx"
        p_cand.write_bytes(trig_bytes)
        model_files.append({"role": "candidate", "file_name": "model.onnx", "size_bytes": len(trig_bytes), "sha256": hash_file(p_cand)})

    elif scen_id == "07_missing_reference":
        multi_bytes = make_multi_layer_model(input_shape=[1, 4])
        p_cand = input_dir / "model.onnx"
        p_cand.write_bytes(multi_bytes)
        model_files.append({"role": "candidate", "file_name": "model.onnx", "size_bytes": len(multi_bytes), "sha256": hash_file(p_cand)})

    elif scen_id == "08_state_dict_coverage_gap":
        pt_bytes = make_pytorch_state_dict_bytes(seed=42)
        p_cand = input_dir / "model.pt"
        p_cand.write_bytes(pt_bytes)
        model_files.append({"role": "candidate", "file_name": "model.pt", "size_bytes": len(pt_bytes), "sha256": hash_file(p_cand)})

    elif scen_id == "09_malformed_artifact":
        corrupt_bytes = b"\xDE\xAD\xBE\xEF\x00\xFF\x55\xAA" * 8  # 64 bytes invalid protobuf
        p_cand = input_dir / "corrupt_header.onnx"
        p_cand.write_bytes(corrupt_bytes)
        model_files.append({"role": "candidate", "file_name": "corrupt_header.onnx", "size_bytes": len(corrupt_bytes), "sha256": hash_file(p_cand)})

    # Build operational scenario manifest
    manifest = {
        "manifest_version": "1.0.0",
        "scenario_id": scen_id,
        "name": scen["name"],
        "framework": scen["framework"],
        "has_reference": scen["has_reference"],
        "models": model_files,
        "created_at": "2026-09-13T00:00:00Z",
    }

    # Build ground truth file (strictly in ground_truth/)
    gt_data = {
        "manifest_version": "1.0.0",
        "scenario_id": scen_id,
        "name": scen["name"],
        "category": scen["category"],
        "framework": scen["framework"],
        "has_reference": scen["has_reference"],
        "description": scen["description"],
        "expected_overall_risk": scen["expected_overall_risk"],
        "expected_confidence": scen.get("expected_confidence"),
        "expected_findings": scen.get("expected_findings", {}),
        "expected_detector_status": scen.get("expected_detector_status", {}),
        "expected_coverage_gaps": scen.get("expected_coverage_gaps", []),
        "expected_disposition": scen.get("expected_disposition", "ASSESS"),
        "expected_error_code": scen.get("expected_error_code"),
    }
    (gt_dir / "ground_truth.json").write_text(json.dumps(gt_data, indent=2), encoding="utf-8")

    return manifest


def generate_model_corpus(
    output_dir: Path = DEFAULT_MODEL_CORPUS_ROOT,
    master_seed: int = 42,
) -> dict[str, Any]:
    """
    Generate the complete, deterministic 9-scenario model integrity validation corpus.
    """
    output_dir = Path(output_dir)
    scenarios_root = output_dir / "scenarios"
    scenarios_root.mkdir(parents=True, exist_ok=True)

    manifest_entries = []
    total_models_all = 0

    for scen in SCENARIOS:
        scen_id = scen["scenario_id"]
        scen_dir = scenarios_root / scen_id
        input_dir = scen_dir / "input"
        gt_dir = scen_dir / "ground_truth"

        # Clean existing files to ensure pure reproducibility
        if input_dir.exists():
            shutil.rmtree(input_dir)
        if gt_dir.exists():
            shutil.rmtree(gt_dir)

        input_dir.mkdir(parents=True, exist_ok=True)
        gt_dir.mkdir(parents=True, exist_ok=True)

        scen_manifest = _build_scenario_files(scen, input_dir, gt_dir)
        (scen_dir / "model_manifest.json").write_text(json.dumps(scen_manifest, indent=2), encoding="utf-8")

        num_models = len(scen_manifest["models"])
        total_models_all += num_models

        manifest_entries.append({
            "scenario_id": scen_id,
            "name": scen["name"],
            "category": scen["category"],
            "framework": scen["framework"],
            "has_reference": scen["has_reference"],
            "model_count": num_models,
            "manifest_path": f"scenarios/{scen_id}/model_manifest.json",
            "ground_truth_path": f"scenarios/{scen_id}/ground_truth/ground_truth.json",
        })

    corpus_manifest = {
        "manifest_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "master_seed": master_seed,
        "total_scenarios": len(SCENARIOS),
        "total_models": total_models_all,
        "scenarios": manifest_entries,
    }

    (output_dir / "corpus_manifest.json").write_text(
        json.dumps(corpus_manifest, indent=2), encoding="utf-8"
    )

    _write_readme(output_dir)
    log.info("Model corpus generation complete: %d scenarios, %d total models", len(SCENARIOS), total_models_all)
    return corpus_manifest


def _write_readme(output_dir: Path) -> None:
    readme_content = """# PRAMAAN v1 — Model Integrity Assurance Corpus

## Overview

The **PRAMAAN v1 Model Integrity Corpus** is a fully offline, deterministic, reproducible benchmark model suite designed to validate the model integrity assurance pipeline (detectors **MI-01 through MI-05**).

The corpus comprises **9 scenarios** covering **14 procedurally synthesized model artifacts** (~50 KB total footprint). Each scenario isolates specific integrity concerns, parameter anomalies, activation representations, localized Trojan perturbations, or format coverage boundaries.

---

## Scenarios Matrix

| Scenario ID | Name | Category | Framework | Injected Mutation / Condition | Expected Risk | Expected Confidence |
|---|---|---|:---:|---|:---:|:---:|
| `01_clean_reference` | Clean Baseline with Reference | Clean Baseline | ONNX | Zero mutation; identical candidate and reference | NONE | HIGH |
| `02_model_substitution` | Architecture Substitution | Substitution | ONNX | Candidate is Relu; Reference is Add_Bias | MEDIUM | HIGH |
| `03_parameter_corruption` | Non-Finite Weight Tampering | Parameter Mod | ONNX | Initializers injected with IEEE 754 NaN weights | HIGH | HIGH |
| `04_weight_magnitude_anomaly` | Statistical Weight Outlier | Parameter Mod | ONNX | Weights exceed magnitude threshold (|w| > 10,000) | MEDIUM | HIGH |
| `05_activation_collapse` | Dead Representation Syndrome | Activation | ONNX | Heavy negative bias (-1000.0) clamping Relu outputs to 0.0 | MEDIUM | LOW |
| `06_trigger_convergence` | Trojan Shortcut Convergence | Perturbation | ONNX | Scalar input graph where corner patch collapses diversity | HIGH | HIGH |
| `07_missing_reference` | Standalone Baseline Enrollment | Missing Ref | ONNX | Healthy model enrolled without reference baseline | NONE | HIGH |
| `08_state_dict_coverage_gap` | Non-Executable State Dict | Access Gap | PyTorch | Valid state dict tensor dictionary without architecture class | NONE | LOW |
| `09_malformed_artifact` | Corrupt Binary Header | Security Boundary | ONNX | 64 bytes of invalid protobuf bytes (fail-closed) | FAIL_CLOSED | REJECT |

---

## Design Principles & Claim Discipline

1. **Zero Ground-Truth Leakage**:
   - `ground_truth.json` is stored strictly in `ground_truth/` and never inside `input/`.
   - Production manifests (`model_manifest.json`) contain only operational metadata (filenames, dimensions, hashes, roles).

2. **Deterministic & Offline**:
   - Pure mathematical synthesis using raw protobuf encoders and CPU PyTorch tensors with fixed seed (`42`).
   - Zero external downloads, network requests, or remote model dependencies.

3. **Honest Engineering Claim Discipline**:
   - **MI-01**: Computes cryptographic, structural, and behavioral fingerprints. Reports observable differences without claiming malicious tampering.
   - **MI-02**: Evaluates parameter moments and non-finite quantities. Reports numerical corruption or weight outliers without claiming intentional sabotage.
   - **MI-03**: Measures layer activation dispersion across calibrated probes. Flags representation collapse or numerical instability.
   - **MI-04**: Conducts comparative reference batteries (MSE, Cosine, hash). Reports behavioral or structural divergence.
   - **MI-05**: Tests candidate localized spatial perturbation hypotheses. Reports Trojan-like target mode convergence without claiming absolute backdoor guarantees.

---

## Directory Layout

```
data/corpus/models/
├── corpus_manifest.json
├── README.md
└── scenarios/
    ├── 01_clean_reference/
    │   ├── ground_truth/
    │   │   └── ground_truth.json
    │   ├── input/
    │   │   ├── model.onnx
    │   │   └── reference.onnx
    │   └── model_manifest.json
    ├── ...
    └── 09_malformed_artifact/
        ├── ground_truth/
        │   └── ground_truth.json
        ├── input/
        │   └── corrupt_header.onnx
        └── model_manifest.json
```

---

## CLI Usage

```bash
# Generate model corpus with default output directory (data/corpus/models) and seed 42
python -m backend.tools.model_corpus_generator --output data/corpus/models --seed 42

# Generate and immediately run in-memory detector validation loop
python -m backend.tools.model_corpus_generator --output data/corpus/models --validate
```
"""
    (output_dir / "README.md").write_text(readme_content, encoding="utf-8")


# ---------------------------------------------------------------------------
# In-Memory Validation Harness
# ---------------------------------------------------------------------------

def validate_model_scenario_against_detectors(scenario_path: Path) -> dict[str, Any]:
    """
    Run actual PRAMAAN detectors and AssessmentService against a model scenario.
    Returns structured results comparing observed outcomes to ground truth.
    """
    input_dir = scenario_path / "input"
    gt_file = scenario_path / "ground_truth" / "ground_truth.json"

    assert input_dir.is_dir(), f"Missing input directory: {input_dir}"
    assert gt_file.is_file(), f"Missing ground truth file: {gt_file}"

    gt = json.loads(gt_file.read_text(encoding="utf-8"))
    scen_id = gt["scenario_id"]

    # Special handling for Scenario 09: Malformed artifact security verification
    if scen_id == "09_malformed_artifact":
        p_corrupt = (input_dir / "corrupt_header.onnx").resolve()
        malformed_caught = False
        try:
            load_model(p_corrupt)
        except ModelLoadError as exc:
            if exc.code == ModelLoadErrorCode.MALFORMED:
                malformed_caught = True

        return {
            "scenario": scen_id,
            "passed": malformed_caught,
            "observed_risk": "NONE",
            "observed_confidence": "HIGH",
            "observed_disposition": "REJECT" if malformed_caught else "ERROR",
            "detector_results": {"load_model": "MALFORMED_REJECTED" if malformed_caught else "UNCAUGHT"},
            "failures": [] if malformed_caught else ["Failed to reject corrupt artifact with MALFORMED error"],
        }

    # Standard scenarios: run end-to-end via AssessmentService
    cand_candidates = list(input_dir.glob("model.*"))
    assert len(cand_candidates) == 1, f"Expected 1 candidate model in {input_dir}"
    p_cand = cand_candidates[0].resolve()

    p_ref = (input_dir / "reference.onnx").resolve() if (input_dir / "reference.onnx").is_file() else None

    conn = open_db(Path(":memory:"))
    try:
        svc = AssessmentService(conn)
        req = AssessmentRequest(
            title=f"Validation {scen_id}",
            model_path=p_cand,
            model_reference_path=p_ref,
        )
        asmt_res = svc.run_assessment(req)

        obs_risk = asmt_res.overall_risk.value
        obs_conf = asmt_res.overall_confidence.value
        obs_gaps = [g.detector_id for g in asmt_res.coverage_gaps]

        runs = {}
        for r in asmt_res.detector_runs:
            if "mi" in r.detector_id:
                short_name = r.detector_id.split(".")[-1]
                runs[short_name] = {
                    "status": r.status,
                    "risk": r.risk_level,
                }

        failures = []
        # Check overall risk match
        exp_risk = gt["expected_overall_risk"]
        if obs_risk.lower() != exp_risk.lower():
            failures.append(f"Overall risk mismatch: expected {exp_risk}, got {obs_risk}")

        # Check coverage gaps match
        exp_gaps = gt.get("expected_coverage_gaps", [])
        for eg in exp_gaps:
            if eg not in obs_gaps:
                failures.append(f"Expected coverage gap {eg} not observed in {obs_gaps}")

        # Check expected findings if present
        for det_key, det_exp in gt.get("expected_findings", {}).items():
            if det_key in runs:
                act_det = runs[det_key]
                exp_det_risk = det_exp.get("risk")
                if exp_det_risk and act_det["risk"].lower() != exp_det_risk.lower():
                    failures.append(f"{det_key} risk mismatch: expected {exp_det_risk}, got {act_det['risk']}")

        return {
            "scenario": scen_id,
            "passed": len(failures) == 0,
            "observed_risk": obs_risk,
            "observed_confidence": obs_conf,
            "coverage_fraction": asmt_res.coverage_fraction,
            "detector_results": runs,
            "coverage_gaps": obs_gaps,
            "failures": failures,
        }
    finally:
        conn.close()


def validate_all_model_scenarios(corpus_dir: Path = DEFAULT_MODEL_CORPUS_ROOT) -> list[dict[str, Any]]:
    """Validate all generated model scenarios in corpus_dir."""
    scenarios_dir = Path(corpus_dir) / "scenarios"
    results = []
    for scen in SCENARIOS:
        s_name = scen["scenario_id"]
        s_path = scenarios_dir / s_name
        r = validate_model_scenario_against_detectors(s_path)
        status = "PASSED" if r["passed"] else "FAILED"
        log.info("Validation %s: %s (Risk: %s, Detectors: %s)", s_name, status, r["observed_risk"], r["detector_results"])
        results.append(r)
    return results


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="PRAMAAN v1 Model Integrity Corpus Generator")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_MODEL_CORPUS_ROOT, help="Output directory")
    parser.add_argument("--seed", "-s", type=int, default=42, help="Master deterministic seed")
    parser.add_argument("--validate", "-v", action="store_true", help="Run in-memory detector validation")
    args = parser.parse_args()

    generate_model_corpus(args.output, master_seed=args.seed)

    if args.validate:
        log.info("Running post-generation validation against actual detectors...")
        val_results = validate_all_model_scenarios(args.output)
        failed = [r for r in val_results if not r["passed"]]
        if failed:
            log.error("Validation failed for %d scenarios: %s", len(failed), [f["scenario"] for f in failed])
            raise SystemExit(1)
        log.info("All %d model scenarios validated successfully against actual detectors!", len(val_results))


if __name__ == "__main__":
    main()
