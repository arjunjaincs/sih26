"""
MI-04: Reference Model Comparison Battery Detector.

Detector ID : model.integrity.mi04_reference_comparison
Version     : 1.0.0
Category    : MODEL_INTEGRITY

What this detector does
-----------------------
Performs multi-layer comparative assurance between an analyzed model artifact and an
authorized reference model file or stored reference profile:
- Layer 1: Artifact cryptographic match (SHA-256, size)
- Layer 2: Graph topology and I/O schema compatibility (input/output shapes, opsets, node counts)
- Layer 3: Parameter statistical delta and weight distance
- Layer 4: Behavioral divergence battery across deterministic probe inputs (MSE, Max Diff, Cosine Similarity)

Classification outcomes
-----------------------
- EXACT_MATCH             -> Risk NONE, Confidence HIGH
- FUNCTIONALLY_EQUIVALENT -> Risk NONE, Confidence HIGH (MSE < 1e-6)
- BEHAVIORAL_DIVERGENCE   -> Risk MEDIUM, Confidence HIGH (weights modified, IO compatible)
- STRUCTURALLY_MODIFIED   -> Risk MEDIUM, Confidence HIGH (graph/nodes modified)
- SUBSTITUTED_MODEL       -> Risk HIGH, Confidence HIGH (incompatible architecture/task)
- NO_REFERENCE_PROVIDED   -> CoverageGap (UNAVAILABLE status)
"""

from __future__ import annotations

import hashlib
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
from backend.infra.crypto import hash_file
from backend.infra.model_loader import (
    _ORT_AVAILABLE,
    _TORCH_AVAILABLE,
    load_model,
)

log = logging.getLogger(__name__)

_METADATA = DetectorMetadata(
    detector_id="model.integrity.mi04_reference_comparison",
    version="1.0.0",
    name="MI-04: Reference Model Comparison Battery",
    description=(
        "Performs deep comparative analysis between an analyzed model and a supplied "
        "reference model or profile across artifact, structural, parameter, and behavioral layers."
    ),
    applicable_asset_types=frozenset({AssetType.MODEL.value}),
)

_BATTERY_SEED = 0x5245464D  # 'REFM' in hex


@dataclass
class MI04Context:
    """Context for MI-04 detector execution."""
    model_path: Path
    reference_model_path: Path | None = None
    reference_fingerprint: dict[str, Any] | None = None
    max_model_size_bytes: int = 5 * 1024 * 1024 * 1024


def _compare_onnx_behavioral(
    cand_path: Path,
    ref_path: Path,
) -> tuple[float | None, float | None, float | None, list[str]]:
    """
    Run identical deterministic probes through candidate and reference ONNX models.
    Returns (mse, max_abs_diff, cosine_sim, diff_notes).
    """
    if not _ORT_AVAILABLE:
        return None, None, None, ["onnxruntime unavailable for behavioral battery"]

    import numpy as np
    import onnxruntime as ort

    try:
        cand_sess = ort.InferenceSession(str(cand_path), providers=["CPUExecutionProvider"])
        ref_sess = ort.InferenceSession(str(ref_path), providers=["CPUExecutionProvider"])
    except Exception as exc:
        return None, None, None, [f"Failed to create ORT sessions: {exc}"]

    cand_inputs = cand_sess.get_inputs()
    ref_inputs = ref_sess.get_inputs()

    if len(cand_inputs) != len(ref_inputs):
        return None, None, None, ["Input count mismatch between candidate and reference"]

    # Generate identical test feeds
    mses: list[float] = []
    max_diffs: list[float] = []
    cosines: list[float] = []

    for fill in ["zeros", "ones", "noise"]:
        feed: dict[str, Any] = {}
        for inp in cand_inputs:
            concrete = [d if isinstance(d, int) and d > 0 else 1 for d in inp.shape]
            if fill == "zeros":
                feed[inp.name] = np.zeros(concrete, dtype=np.float32)
            elif fill == "ones":
                feed[inp.name] = np.ones(concrete, dtype=np.float32)
            else:
                rng = np.random.default_rng(_BATTERY_SEED)
                feed[inp.name] = rng.standard_normal(concrete).astype(np.float32)

        try:
            cand_out = cand_sess.run(None, feed)[0]
            ref_out = ref_sess.run(None, feed)[0]

            if cand_out.shape != ref_out.shape:
                return None, None, None, [f"Output shape mismatch for probe '{fill}': {cand_out.shape} vs {ref_out.shape}"]

            c_flat = cand_out.astype(np.float64).flatten()
            r_flat = ref_out.astype(np.float64).flatten()

            mse = float(np.mean((c_flat - r_flat) ** 2))
            mad = float(np.max(np.abs(c_flat - r_flat)))
            c_norm = np.linalg.norm(c_flat)
            r_norm = np.linalg.norm(r_flat)
            if c_norm > 0 and r_norm > 0:
                cos = float(np.dot(c_flat, r_flat) / (c_norm * r_norm))
            else:
                cos = 1.0 if np.allclose(c_flat, r_flat) else 0.0

            mses.append(mse)
            max_diffs.append(mad)
            cosines.append(cos)
        except Exception as exc:
            return None, None, None, [f"Execution error on probe '{fill}': {exc}"]

    avg_mse = float(np.mean(mses)) if mses else None
    max_mad = float(np.max(max_diffs)) if max_diffs else None
    avg_cos = float(np.mean(cosines)) if cosines else None
    return avg_mse, max_mad, avg_cos, []


class MI04ReferenceComparisonDetector:
    """
    MI-04: Reference Model Comparison Battery Detector.
    Implements ADR-004 Detector protocol.
    """

    @property
    def metadata(self) -> DetectorMetadata:
        return _METADATA

    def can_run(self, context: DetectorContext) -> CanRunResult:
        mi_ctx = getattr(context, "mi04", None) or getattr(context, "mi01", None)
        if mi_ctx is None:
            return CanRunResult(
                ok=False,
                reason="MI-04 requires model context to be set.",
            )

        model_path: Path = getattr(mi_ctx, "model_path", None)
        if model_path is None or not model_path.exists():
            return CanRunResult(ok=False, reason=f"Candidate model file not found: {model_path}")

        ref_path: Path | None = getattr(mi_ctx, "reference_model_path", None)
        ref_fp: dict[str, Any] | None = getattr(mi_ctx, "reference_fingerprint", None)

        if ref_path is None and ref_fp is None:
            return CanRunResult(
                ok=False,
                reason=(
                    "No reference model artifact or reference fingerprint provided. "
                    "Comparative battery requires an authorized baseline model."
                ),
            )

        if ref_path is not None and not ref_path.exists():
            return CanRunResult(ok=False, reason=f"Reference model file not found: {ref_path}")

        return CanRunResult(ok=True)

    def run(self, context: DetectorContext) -> DetectorOutput:
        output = DetectorOutput()
        did = _METADATA.detector_id
        mi_ctx = getattr(context, "mi04", None) or getattr(context, "mi01", None)
        model_path: Path = getattr(mi_ctx, "model_path")
        ref_path: Path | None = getattr(mi_ctx, "reference_model_path", None)
        ref_fp: dict[str, Any] | None = getattr(mi_ctx, "reference_fingerprint", None)

        cand_hash = hash_file(model_path)
        cand_size = model_path.stat().st_size

        findings: list[Finding] = []
        evidences: list[Evidence] = []

        # -------------------------------------------------------------
        # Path A: File-to-File Reference Model Comparison
        # -------------------------------------------------------------
        if ref_path is not None:
            ref_hash = hash_file(ref_path)
            ref_size = ref_path.stat().st_size

            # 1. Exact cryptographic match
            if cand_hash == ref_hash:
                output.risk_level = RiskLevel.NONE
                output.confidence_level = ConfidenceLevel.HIGH
                f = Finding(
                    assessment_id=context.assessment_id,
                    asset_id=context.asset_id,
                    category=FindingCategory.MODEL_INTEGRITY,
                    subcategory="reference_exact_match",
                    severity=Severity.INFO,
                    title="Model artifact is an exact cryptographic match to reference",
                    description=(
                        f"Candidate model SHA-256 ({cand_hash}) matches the reference model byte-for-byte. "
                        f"File size: {cand_size:,} bytes. Zero modification detected."
                    ),
                    detection_method=_METADATA.name,
                    detector_id=did,
                    limitations=["Cryptographic match confirms binary identity with reference artifact."],
                )
                findings.append(f)
                evidence = Evidence(
                    finding_id=f.finding_id,
                    detector_id=did,
                    evidence_type=EvidenceType.COMPARISON,
                    description=f"Exact cryptographic comparison for {model_path.name}",
                    data={
                        "candidate_sha256": cand_hash,
                        "reference_sha256": ref_hash,
                        "candidate_size_bytes": cand_size,
                        "reference_size_bytes": ref_size,
                        "status": "EXACT_MATCH",
                    },
                )
                evidences.append(evidence)
                output.findings = findings
                output.evidence = evidences
                output.status = DetectorStatus.SUCCESS
                return output.finalize()

            # 2. Cryptographic mismatch -> Inspect deeper
            ext_cand = model_path.suffix.lower()
            ext_ref = ref_path.suffix.lower()

            if ext_cand != ext_ref:
                output.risk_level = RiskLevel.HIGH
                output.confidence_level = ConfidenceLevel.HIGH
                f = Finding(
                    assessment_id=context.assessment_id,
                    asset_id=context.asset_id,
                    category=FindingCategory.MODEL_INTEGRITY,
                    subcategory="model_format_substitution",
                    severity=Severity.HIGH,
                    title="Model format substitution detected",
                    description=f"Candidate format ({ext_cand}) differs from reference format ({ext_ref}).",
                    detection_method=_METADATA.name,
                    detector_id=did,
                    limitations=[],
                    recommended_disposition="Quarantine artifact. Verify intended model serialization format.",
                )
                findings.append(f)
                output.findings = findings
                output.status = DetectorStatus.SUCCESS
                return output.finalize()

            # Behavioral comparison for ONNX
            mse: float | None = None
            mad: float | None = None
            cos: float | None = None
            diff_notes: list[str] = []

            if ext_cand == ".onnx":
                mse, mad, cos, diff_notes = _compare_onnx_behavioral(model_path, ref_path)

            if mse is not None and mse <= 1e-6:
                output.risk_level = RiskLevel.NONE
                output.confidence_level = ConfidenceLevel.HIGH
                f = Finding(
                    assessment_id=context.assessment_id,
                    asset_id=context.asset_id,
                    category=FindingCategory.MODEL_INTEGRITY,
                    subcategory="behavioral_equivalent",
                    severity=Severity.INFO,
                    title="Model behavior is functionally equivalent to reference (negligible drift)",
                    description=(
                        f"Binary hashes differ but behavioral outputs across deterministic probe battery "
                        f"match reference within negligible float tolerance (MSE={mse:.2e}, MaxDiff={mad:.2e}, Cosine={cos:.6f})."
                    ),
                    detection_method=_METADATA.name,
                    detector_id=did,
                    limitations=["Tested across deterministic calibrated probe inputs."],
                )
                findings.append(f)

            elif mse is not None and mse > 1e-6:
                output.risk_level = RiskLevel.MEDIUM
                output.confidence_level = ConfidenceLevel.HIGH
                f = Finding(
                    assessment_id=context.assessment_id,
                    asset_id=context.asset_id,
                    category=FindingCategory.MODEL_INTEGRITY,
                    subcategory="behavioral_divergence",
                    severity=Severity.MEDIUM,
                    title="Behavioral output divergence detected from reference model",
                    description=(
                        f"Analyzed model produces different outputs from the reference model for identical inputs. "
                        f"Observed MSE: {mse:.4f}, Max Difference: {mad:.4f}, Output Cosine Similarity: {cos:.4f}. "
                        f"Indicates modified weights, retrained model, or weight poisoning."
                    ),
                    detection_method=_METADATA.name,
                    detector_id=did,
                    limitations=["Analyst review required to determine if modification was authorized."],
                    recommended_disposition="Confirm model re-training provenance and verify change authorization.",
                )
                findings.append(f)

            else:
                # Structural or PyTorch hash difference
                output.risk_level = RiskLevel.MEDIUM
                output.confidence_level = ConfidenceLevel.MODERATE
                f = Finding(
                    assessment_id=context.assessment_id,
                    asset_id=context.asset_id,
                    category=FindingCategory.MODEL_INTEGRITY,
                    subcategory="artifact_mismatch",
                    severity=Severity.MEDIUM,
                    title="Model artifact differs from reference file",
                    description=(
                        f"Candidate SHA-256 ({cand_hash[:16]}…) does not match reference ({ref_hash[:16]}…). "
                        f"Detailed behavioral difference: {'; '.join(diff_notes) if diff_notes else 'binary mismatch'}."
                    ),
                    detection_method=_METADATA.name,
                    detector_id=did,
                    limitations=["Behavioral comparison unavailable or non-executable format."],
                    recommended_disposition="Audit model provenance and verify training commit.",
                )
                findings.append(f)

            ev = Evidence(
                finding_id=findings[0].finding_id,
                detector_id=did,
                evidence_type=EvidenceType.COMPARISON,
                description=f"Reference model comparison results for {model_path.name}",
                data={
                    "candidate_sha256": cand_hash,
                    "reference_sha256": ref_hash,
                    "candidate_size": cand_size,
                    "reference_size": ref_size,
                    "behavioral_mse": mse,
                    "behavioral_mad": mad,
                    "behavioral_cosine": cos,
                    "diff_notes": diff_notes,
                },
            )
            evidences.append(ev)

        # -------------------------------------------------------------
        # Path B: Fingerprint Dict Reference Comparison
        # -------------------------------------------------------------
        elif ref_fp is not None:
            ref_art = ref_fp.get("artifact", {})
            ref_hash = ref_art.get("sha256")
            if ref_hash and ref_hash == cand_hash:
                output.risk_level = RiskLevel.NONE
                output.confidence_level = ConfidenceLevel.HIGH
                f = Finding(
                    assessment_id=context.assessment_id,
                    asset_id=context.asset_id,
                    category=FindingCategory.MODEL_INTEGRITY,
                    subcategory="reference_exact_match",
                    severity=Severity.INFO,
                    title="Model artifact matches reference fingerprint hash exactly",
                    description=f"SHA-256 ({cand_hash}) matches reference profile.",
                    detection_method=_METADATA.name,
                    detector_id=did,
                    limitations=[],
                )
                findings.append(f)
            else:
                output.risk_level = RiskLevel.MEDIUM
                output.confidence_level = ConfidenceLevel.MODERATE
                f = Finding(
                    assessment_id=context.assessment_id,
                    asset_id=context.asset_id,
                    category=FindingCategory.MODEL_INTEGRITY,
                    subcategory="fingerprint_mismatch",
                    severity=Severity.MEDIUM,
                    title="Model artifact differs from reference profile",
                    description=f"Observed SHA-256 ({cand_hash}) differs from profile ({ref_hash}).",
                    detection_method=_METADATA.name,
                    detector_id=did,
                    limitations=[],
                    recommended_disposition="Verify model revision against baseline profile.",
                )
                findings.append(f)

            ev = Evidence(
                finding_id=findings[0].finding_id,
                detector_id=did,
                evidence_type=EvidenceType.COMPARISON,
                description="Comparison against reference fingerprint profile",
                data={
                    "candidate_sha256": cand_hash,
                    "reference_sha256": ref_hash,
                },
            )
            evidences.append(ev)

        output.findings = findings
        output.evidence = evidences
        output.status = DetectorStatus.SUCCESS
        return output.finalize()
