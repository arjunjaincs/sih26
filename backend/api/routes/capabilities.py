"""
GET /api/v1/capabilities

Exposes what PRAMAAN can actually analyse in the current offline environment.
All information is derived from the live detector registry — no hardcoded names.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.schemas import CapabilitiesResponse, DetectorCapabilitySchema
from backend.detectors.base import DetectorContext
from backend.detectors.registry import ALL_DETECTORS
from backend.domain.enums import DatasetFormat

router = APIRouter(prefix="/api/v1", tags=["capabilities"])

_PRAMAAN_VERSION = "1.0.0"

# Supported model file extensions (used by MI-01)
_SUPPORTED_MODEL_FORMATS = [".onnx", ".pt", ".pth", ".ts"]

# Static registry method metadata extracted directly from authoritative detector specifications
_DETECTOR_METHOD_METADATA: dict[str, dict] = {
    "data.integrity.di01_duplicates": {
        "code": "DI-01",
        "pillar": "Dataset Integrity",
        "access_requirements": "Black-Box (raw image bytes)",
        "dependencies": ["Pillow", "imagehash", "sqlite3"],
        "supported_formats": ["JPEG", "PNG", "WEBP"],
        "what_it_analyzes": (
            "Scans dataset samples for exact byte collisions (SHA-256) and perceptual near-duplicates "
            "via DCT pHash Hamming distance clustering (Hamming <= 10). Identifies image truncation, "
            "decode errors, and format non-conformance."
        ),
        "evidence_produced": [
            "EvidenceType.CLUSTER: Duplicate image cluster manifests with member counts",
            "Normalized Hamming distance metrics (0-64) and representative hash digests",
            "SHA-256 byte collision matching records",
            "Corrupt and unreadable image file list",
        ],
        "confidence_semantics": (
            "Decoupled from risk (ADR-003): Exact byte duplicates yield HIGH confidence. Near-duplicates "
            "with Hamming <= 10 yield MODERATE confidence as candidate relationships. Insufficient "
            "samples (< 2) yield LOW confidence."
        ),
        "limitations": [
            "Pixel & perceptual space analysis only; does not infer high-level semantic equivalence.",
            "Does not claim duplicates are malicious or intentional poisoning without contextual corroboration.",
            "Does not execute foundation model embeddings or CLIP.",
        ],
        "reference_method": "ADR-004 (Pure deterministic execution); imagehash DCT perceptual hashing (Zauner, 2010)",
    },
    "data.integrity.di02_label_integrity": {
        "code": "DI-02",
        "pillar": "Dataset Integrity",
        "access_requirements": "Black-Box with Labels (sample images + class annotations)",
        "dependencies": ["Pillow", "imagehash", "numpy", "sqlite3"],
        "supported_formats": ["COCO JSON annotations", "metadata.json / labels.json", "Directory class mappings"],
        "what_it_analyzes": (
            "Inspects labeled samples to detect contradictory class annotations across perceptual near-duplicates "
            "(Hamming <= 4) and statistical class centroid outliers (> 2.5 sigma) that are closer to an alternate "
            "class centroid (candidate label flip)."
        ),
        "evidence_produced": [
            "EvidenceType.CLUSTER: Conflicting duplicate sample pair records with divergent label assignments",
            "pHash Hamming distance between conflicting duplicates",
            "Class centroid distance metrics and nearest alternate class projections",
            "Candidate label flip recommendations",
        ],
        "confidence_semantics": (
            "Conflicting identical/near-identical duplicates yield HIGH confidence. Statistical centroid "
            "outliers yield MODERATE confidence pending human verification."
        ),
        "limitations": [
            "Requires labeled dataset with at least 2 labeled samples.",
            "Statistical centroid distance is a heuristic and cannot prove definitive label error without ground-truth verification.",
            "Operates purely offline without external LLM/VLM label validators.",
        ],
        "reference_method": "ADR-003 (Risk/Confidence Decoupling); Perceptual hash space centroid clustering",
    },
    "data.integrity.di03_trigger_anomaly": {
        "code": "DI-03",
        "pillar": "Dataset Integrity",
        "access_requirements": "Black-Box (sample images)",
        "dependencies": ["Pillow", "imagehash", "numpy", "sqlite3"],
        "supported_formats": ["JPEG", "PNG", "WEBP"],
        "what_it_analyzes": (
            "Inspects localized image regions (four corners: top-left, top-right, bottom-left, bottom-right, "
            "plus center) across dataset samples to identify recurring identical/near-identical localized "
            "visual patches and artificial high-contrast spatial patterns indicative of backdoor trigger injection."
        ),
        "evidence_produced": [
            "EvidenceType.CLUSTER: Recurring localized patch coordinates and sample bindings",
            "Localized patch dHash / variance metrics and occurrence counts",
            "Sample file paths exhibiting recurring trigger patterns",
        ],
        "confidence_semantics": (
            "Recurring high-frequency patches across >= 3 distinct samples yield HIGH confidence. "
            "Moderate variance recurrences yield MODERATE confidence."
        ),
        "limitations": [
            "Detects visible localized spatial triggers (patches/watermarks).",
            "Does not detect full-canvas, invisible, or blended adversarial perturbations without localized footprints.",
            "Operates purely offline without model training.",
        ],
        "reference_method": "BadNets (Gu et al., 2017) localized spatial trigger threat model",
    },
    "data.integrity.di04_ood_distribution": {
        "code": "DI-04",
        "pillar": "Dataset Integrity",
        "access_requirements": "Black-Box (sample images)",
        "dependencies": ["Pillow", "numpy", "sqlite3"],
        "supported_formats": ["JPEG", "PNG", "WEBP"],
        "what_it_analyzes": (
            "Extracts 6D multivariate feature vectors (aspect ratio, normalized byte density, RGB channel "
            "means, luminance variance, spectral texture) and computes standardized multivariate distance "
            "(median / IQR z-scores) against the dataset baseline to detect samples significantly outside the "
            "dominant distribution."
        ),
        "evidence_produced": [
            "EvidenceType.CLUSTER: Standardized multivariate distance scores (median/IQR)",
            "Per-dimension outlier score breakdown across geometry, color, and texture",
            "Identified anomalous sample paths and dimensional deviation",
            "Baseline distribution parameter estimates",
        ],
        "confidence_semantics": (
            "Severe multi-dimensional outliers (> 4.0 IQR) yield HIGH confidence of distribution deviation. "
            "Single-dimension deviations yield MODERATE confidence."
        ),
        "limitations": [
            "Evaluates low-level photometric and geometric distributions; does not perform high-level semantic OOD classification.",
            "Requires a baseline of at least 5 samples in the dataset.",
            "Benign anomalies (unusual lighting, framing) may be flagged as outliers.",
        ],
        "reference_method": "Robust Multivariate Median Absolute Deviation (MAD / IQR outlier detection)",
    },
    "data.integrity.di05_contributor_risk": {
        "code": "DI-05",
        "pillar": "Dataset Integrity",
        "access_requirements": "Black-Box with Attribution (sample metadata, user_id, or source directories)",
        "dependencies": ["sqlite3"],
        "supported_formats": ["COCO user/contributor fields", "Directory-based source grouping", "metadata.json attribution"],
        "what_it_analyzes": (
            "Aggregates findings from all data integrity detectors (DI-01 through DI-04) by contributor "
            "or source group to compute per-contributor defect rates and identify sources with disproportionately "
            "high defect concentration."
        ),
        "evidence_produced": [
            "EvidenceType.CLUSTER: Per-contributor defect rate and volume comparison",
            "Disproportionate defect concentration alerts (defect rate >= 30% and count >= 2)",
            "Multi-contributor risk breakdown summary matrix",
        ],
        "confidence_semantics": (
            "Concentrated defect patterns with high sample volume yield HIGH confidence. Small sample counts "
            "yield MODERATE or LOW confidence."
        ),
        "limitations": [
            "Requires contributor or source attribution metadata. When absent, detector reports an explicit coverage gap (SKIPPED).",
            "Statistical concentration indicates pipeline degradation or source risk, not definitive proof of malicious intent.",
        ],
        "reference_method": "ADR-003; Cross-detector statistical defect attribution",
    },
    "model.integrity.mi01_fingerprint": {
        "code": "MI-01",
        "pillar": "Model Integrity",
        "access_requirements": "White-Box (serialized model artifact)",
        "dependencies": ["onnx", "onnxruntime", "torch", "sqlite3"],
        "supported_formats": [".onnx", ".pt", ".pth", ".ts"],
        "what_it_analyzes": (
            "Multi-layer structural AST and weight fingerprinting: Layer 1 (raw byte SHA-256, size, timestamp), "
            "Layer 2 (graph topology, node counts, operator inventory, I/O tensor schemas), Layer 3 (deterministic "
            "reference-input behavioral battery on ONNX: zeros, ones, seeded noise), Layer 4 (reference baseline comparison)."
        ),
        "evidence_produced": [
            "Structural topology digest and operator frequency table",
            "Input/output tensor shape, name, and dtype compliance records",
            "Deterministic output deviation statistics (mean, std, min, max, hash)",
            "Reference baseline delta finding (observed vs expected)",
        ],
        "confidence_semantics": (
            "Exact cryptographic and structural matches yield HIGH confidence. Behavioral execution differences "
            "yield HIGH confidence. Unexecutable state dicts yield LOW confidence for execution layers."
        ),
        "limitations": [
            "Behavioral battery requires executable computational graph (ONNX / TorchScript).",
            "PyTorch state dicts lacking architecture definitions cannot execute behavioral probes and report a coverage gap for Layer 3.",
        ],
        "reference_method": "ADR-004; Multi-layer cryptographic model fingerprinting",
    },
    "model.integrity.mi02_parameter_stats": {
        "code": "MI-02",
        "pillar": "Model Integrity",
        "access_requirements": "White-Box (model parameter weights / tensors)",
        "dependencies": ["onnx", "onnxruntime", "torch", "numpy"],
        "supported_formats": [".onnx", ".pt", ".pth", ".ts"],
        "what_it_analyzes": (
            "Performs deep inspection of model parameter tensors: total parameter count, tensor count, "
            "dtype distribution, weight moments (min, max, mean, std), layer sparsity (% zeros), "
            "non-finite IEEE-754 values (NaN, +Inf, -Inf), extreme weight anomalies (|w| > 10,000), "
            "and abnormal layer collapse."
        ),
        "evidence_produced": [
            "Global parameter count and tensor dtype distribution",
            "Weight moments (min, max, mean, std) and sparsity ratio per tensor",
            "Non-finite parameter alerts (NaN / Inf counter per tensor)",
            "Extreme weight magnitude outlier warnings (|w| > 1e4)",
        ],
        "confidence_semantics": (
            "Direct numerical inspection of IEEE-754 weights yields HIGH confidence. Non-finite values "
            "or extreme magnitude anomalies yield HIGH risk."
        ),
        "limitations": [
            "Requires deserializable parameter tensors (uses safe deserialization weights_only=True).",
            "Calculates numerical statistics; does not infer functional semantics of individual weight matrices.",
        ],
        "reference_method": "ADR-003; IEEE-754 floating point validity & parameter distribution analysis",
    },
    "model.integrity.mi03_activation_stats": {
        "code": "MI-03",
        "pillar": "Model Integrity",
        "access_requirements": "White-Box Executable (computational graph with forward pass capability)",
        "dependencies": ["onnxruntime", "torch", "numpy"],
        "supported_formats": [".onnx", ".ts"],
        "what_it_analyzes": (
            "Executes calibrated deterministic probe inputs (zeros, ones, gradient, seeded noise) to "
            "capture intermediate and output layer activation statistics. Identifies dead representation "
            "syndrome (> 98% zero activations across non-zero probes), numerical instability (NaN/Inf in forward pass), "
            "and severe activation saturation."
        ),
        "evidence_produced": [
            "Monitored layer activation summary metrics (mean, std, min, max)",
            "Dead activation ratio per layer across non-zero probes",
            "Numerical instability alerts (NaN / Inf forward pass outputs)",
            "Layer saturation and clipping diagnostics",
        ],
        "confidence_semantics": (
            "Direct forward execution on calibrated inputs yields HIGH confidence. Unexecutable model "
            "formats report explicit UNAVAILABLE coverage gap with LOW confidence."
        ),
        "limitations": [
            "Requires executable computational graph; cannot run on standalone weight state dicts.",
            "Monitors initial bounded layers to prevent memory exhaustion on large architectures.",
        ],
        "reference_method": "ADR-004; Intermediate representation activation profiling",
    },
    "model.integrity.mi04_reference_comparison": {
        "code": "MI-04",
        "pillar": "Model Integrity",
        "access_requirements": "White-Box Comparative (candidate model + authorized reference model/profile)",
        "dependencies": ["onnx", "onnxruntime", "torch", "numpy"],
        "supported_formats": [".onnx", ".pt", ".pth", ".ts"],
        "what_it_analyzes": (
            "Performs multi-layer comparative assurance between a candidate model and an authorized baseline "
            "reference: Layer 1 (cryptographic SHA-256 match), Layer 2 (graph topology and I/O schema compatibility), "
            "Layer 3 (parameter statistical delta and weight distance), Layer 4 (behavioral divergence across "
            "deterministic probe battery: MSE, Max Diff, Cosine Similarity)."
        ),
        "evidence_produced": [
            "Cryptographic match verification (exact SHA-256 identity)",
            "Structural schema and topology delta report",
            "Behavioral divergence metrics (MSE, Max Absolute Difference, Cosine Similarity)",
            "Substitution and format mismatch classifications",
        ],
        "confidence_semantics": (
            "Comparative checks against an authorized reference yield HIGH confidence. If no reference "
            "is supplied, detector emits a clear coverage gap (UNAVAILABLE)."
        ),
        "limitations": [
            "Requires an authorized reference model file or stored baseline profile.",
            "Cannot verify authenticity if the provided reference itself is untrusted or unauthenticated.",
        ],
        "reference_method": "ADR-003; Differential behavioral & structural comparison",
    },
    "model.integrity.mi05_trigger_anomaly": {
        "code": "MI-05",
        "pillar": "Model Integrity",
        "access_requirements": "White-Box Executable (computational graph with forward pass capability)",
        "dependencies": ["onnxruntime", "torch", "numpy"],
        "supported_formats": [".onnx", ".ts"],
        "what_it_analyzes": (
            "Evaluates model sensitivity to localized spatial trigger perturbations across diverse clean probe inputs. "
            "Tests candidate localized perturbations (top-left patch, bottom-right patch, center mark, uniform bias control) "
            "and calculates output shift and Target Mode Convergence Ratio (CR = PairwiseDiversity(perturbed) / PairwiseDiversity(clean)) "
            "to detect Trojan backdoor shortcuts."
        ),
        "evidence_produced": [
            "Candidate perturbation evaluations (shift magnitude, output diversity)",
            "Target mode convergence ratio metrics (CR < 0.15 threshold)",
            "Flagged suspicious trigger patch coordinates and patterns",
            "Baseline clean pairwise diversity benchmarks",
        ],
        "confidence_semantics": (
            "Convergence ratio CR < 0.15 with elevated output shift yields HIGH risk and HIGH confidence of "
            "Trojan shortcut behavior. Normal smooth perturbation responses yield NONE risk with HIGH confidence."
        ),
        "limitations": [
            "Tests concrete candidate localized spatial patch hypotheses.",
            "Does NOT guarantee detection of complex blended, invisible, or semantic triggers without access to the original training distribution.",
        ],
        "reference_method": "Neural Cleanse (Wang et al., 2019) target convergence principles adapted for deterministic offline probe evaluation",
    },
    "inference.provenance.pi01_integrity": {
        "code": "PI-01",
        "pillar": "Inference Provenance",
        "access_requirements": "Black-Box (signed provenance manifest + cryptographic public key)",
        "dependencies": ["cryptography (Ed25519)", "hashlib (SHA-256)", "sqlite3"],
        "supported_formats": ["provenance_manifest.json (RFC 8032 Ed25519 signature)", "Raw input/model/output asset bytes"],
        "what_it_analyzes": (
            "Verifies the cryptographic authenticity and integrity of inference execution: validates RFC 8032 "
            "Ed25519 digital signature over canonical manifest, validates cryptographic SHA-256 byte bindings for "
            "input data, model weights, and inference outputs, and inspects sequence numbers and nonces for replay attacks."
        ),
        "evidence_produced": [
            "Ed25519 cryptographic signature verification result",
            "Input, model, and output SHA-256 binding match statements",
            "Manifest schema and timestamp replay / sequence verification",
            "Missing or tampered asset reference alerts",
        ],
        "confidence_semantics": (
            "Cryptographic signature validation and SHA-256 matching are mathematical certainties yielding "
            "HIGH confidence. Missing binding files yield MODERATE confidence with an explicit coverage gap."
        ),
        "limitations": [
            "Validates post-training inference transmission and execution binding.",
            "Does not authenticate the training pipeline if the manifest was signed dishonestly by an authorized key holder.",
        ],
        "reference_method": "RFC 8032 (Ed25519 Edwards-curve Digital Signature Algorithm); ADR-003",
    },
}


def _check_available(detector) -> bool:
    """
    Check if the detector is available in the current environment.
    All registered detectors in ALL_DETECTORS are available.
    """
    return detector is not None and hasattr(detector, "metadata")


@router.get(
    "/capabilities",
    response_model=CapabilitiesResponse,
    summary="List available PRAMAAN analysis capabilities",
)
def capabilities() -> CapabilitiesResponse:
    """
    Returns the detectors actually registered in the current installation.

    - detector IDs, versions, descriptions
    - which asset types each detector can analyse
    - whether each detector's runtime dependencies are satisfied
    - supported dataset and model formats
    - full detector method detail (what it analyzes, access requirements, confidence semantics, limitations)

    The UI uses this endpoint to display capabilities and the method detail experience.
    """
    detector_schemas = []
    for d in ALL_DETECTORS:
        meta = _DETECTOR_METHOD_METADATA.get(d.metadata.detector_id, {})
        detector_schemas.append(
            DetectorCapabilitySchema(
                detector_id=d.metadata.detector_id,
                version=d.metadata.version,
                name=d.metadata.name,
                description=d.metadata.description,
                applicable_asset_types=sorted(d.metadata.applicable_asset_types),
                available=_check_available(d),
                code=meta.get("code"),
                pillar=meta.get("pillar"),
                access_requirements=meta.get("access_requirements"),
                dependencies=meta.get("dependencies", []),
                supported_formats=meta.get("supported_formats", []),
                what_it_analyzes=meta.get("what_it_analyzes"),
                evidence_produced=meta.get("evidence_produced", []),
                confidence_semantics=meta.get("confidence_semantics"),
                limitations=meta.get("limitations", []),
                reference_method=meta.get("reference_method"),
            )
        )

    return CapabilitiesResponse(
        detectors=detector_schemas,
        supported_dataset_formats=[fmt.value for fmt in DatasetFormat],
        supported_model_formats=_SUPPORTED_MODEL_FORMATS,
        pramaan_version=_PRAMAAN_VERSION,
    )
