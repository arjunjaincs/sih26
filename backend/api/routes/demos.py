"""
PRAMAAN demo preset routes.

GET /api/v1/demos -- list authentic offline demo presets backed by real corpus artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from backend.api.schemas import DemoListResponse, DemoPresetSchema

router = APIRouter(prefix="/api/v1", tags=["demos"])

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CORPUS_DIR = _PROJECT_ROOT / "data" / "corpus"


def _build_presets() -> list[DemoPresetSchema]:
    presets: list[DemoPresetSchema] = []

    # 1. Clean Reference Baseline
    clean_model = _CORPUS_DIR / "models" / "scenarios" / "01_clean_reference" / "input" / "model.onnx"
    clean_ref = _CORPUS_DIR / "models" / "scenarios" / "01_clean_reference" / "input" / "reference.onnx"
    if clean_model.exists() and clean_ref.exists():
        presets.append(
            DemoPresetSchema(
                id="clean_baseline",
                name="Clean Reference Baseline",
                category="Model Integrity",
                description=(
                    "Validates an untampered ONNX candidate against its reference baseline. "
                    "Verifies cryptographic fingerprint match (MI-01), zero parameter drift (MI-02), "
                    "and full architectural equivalence (MI-04)."
                ),
                expected_risk="NONE",
                expected_confidence="HIGH",
                detectors_targeted=["MI-01", "MI-02", "MI-04"],
                payload={
                    "title": "Demo: Clean Reference Baseline",
                    "model_path": str(clean_model.resolve()),
                    "model_reference_path": str(clean_ref.resolve()),
                },
            )
        )

    # 2. Dataset Duplicates & Collisions
    dup_images = _CORPUS_DIR / "scenarios" / "02_exact_duplicate" / "input" / "images"
    if dup_images.exists():
        presets.append(
            DemoPresetSchema(
                id="duplicate_data",
                name="Dataset Duplicates & Collisions",
                category="Dataset Integrity",
                description=(
                    "Evaluates a computer vision dataset containing exact byte duplicates and "
                    "DCT perceptual near-duplicates. Demonstrates DI-01 cluster discovery and hash matching."
                ),
                expected_risk="HIGH",
                expected_confidence="HIGH",
                detectors_targeted=["DI-01"],
                payload={
                    "title": "Demo: Dataset Duplicate Analysis",
                    "dataset_path": str(dup_images.resolve()),
                    "dataset_format": "image_dir",
                    "phash_threshold": 10,
                    "dhash_threshold": 10,
                    "min_cluster_size": 2,
                },
            )
        )

    # 3. Parameter Corruption (NaN/Inf Weights)
    corrupt_model = _CORPUS_DIR / "models" / "scenarios" / "03_parameter_corruption" / "input" / "model.onnx"
    corrupt_ref = _CORPUS_DIR / "models" / "scenarios" / "03_parameter_corruption" / "input" / "reference.onnx"
    if corrupt_model.exists() and corrupt_ref.exists():
        presets.append(
            DemoPresetSchema(
                id="corrupted_model",
                name="Parameter Tampering (NaN/Inf)",
                category="Model Integrity",
                description=(
                    "Analyzes an ONNX candidate with corrupted non-finite tensor parameters "
                    "against an authoritative baseline. Demonstrates immediate MI-02 and MI-04 defect detection."
                ),
                expected_risk="HIGH",
                expected_confidence="HIGH",
                detectors_targeted=["MI-02", "MI-04"],
                payload={
                    "title": "Demo: Corrupted Model Weights",
                    "model_path": str(corrupt_model.resolve()),
                    "model_reference_path": str(corrupt_ref.resolve()),
                },
            )
        )

    # 4. Trojan Trigger Search
    trojan_model = _CORPUS_DIR / "models" / "scenarios" / "06_trigger_convergence" / "input" / "model.onnx"
    if trojan_model.exists():
        presets.append(
            DemoPresetSchema(
                id="trojan_model",
                name="Trojan Shortcut Convergence",
                category="Model Integrity",
                description=(
                    "Executes adversarial trigger anomaly search (MI-05) and parameter numerical "
                    "distribution analysis on a backdoored model artifact."
                ),
                expected_risk="HIGH",
                expected_confidence="HIGH",
                detectors_targeted=["MI-01", "MI-02", "MI-05"],
                payload={
                    "title": "Demo: Trojan Trigger Search",
                    "model_path": str(trojan_model.resolve()),
                },
            )
        )

    # 5. Inference Provenance Attestation
    prov_dir = _CORPUS_DIR / "provenance" / "scenarios" / "01_clean_provenance" / "input"
    manifest_file = prov_dir / "manifest.json"
    pub_key_file = prov_dir / "public_key.hex"
    model_sha_file = prov_dir / "model_sha256.txt"
    input_file = prov_dir / "input_image.png"
    output_file = prov_dir / "output.json"

    if (
        manifest_file.exists()
        and pub_key_file.exists()
        and model_sha_file.exists()
        and input_file.exists()
        and output_file.exists()
    ):
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            pub_hex = pub_key_file.read_text(encoding="utf-8").strip()
            model_sha = model_sha_file.read_text(encoding="utf-8").strip()
            input_hex = input_file.read_bytes().hex()
            output_hex = output_file.read_bytes().hex()

            presets.append(
                DemoPresetSchema(
                    id="provenance_attestation",
                    name="Cryptographic Inference Provenance",
                    category="Inference Provenance",
                    description=(
                        "Validates an Ed25519 digital signature, monotonic sequence counter, cryptographic nonce, "
                        "and SHA-256 byte bindings between input image, model graph, and inference output."
                    ),
                    expected_risk="NONE",
                    expected_confidence="HIGH",
                    detectors_targeted=["PI-01"],
                    payload={
                        "title": "Demo: Signed Inference Provenance",
                        "provenance_manifest": manifest_data,
                        "provenance_public_key_hex": pub_hex,
                        "actual_model_sha256": model_sha,
                        "actual_input_bytes_hex": input_hex,
                        "actual_output_bytes_hex": output_hex,
                    },
                )
            )
        except Exception:
            pass

    return presets


@router.get(
    "/demos",
    response_model=DemoListResponse,
    summary="List reproducible demo scenarios for evaluation",
)
def list_demos() -> DemoListResponse:
    """
    Return pre-configured, offline demo assessment scenarios backed by real corpus artifacts.

    Enables SIH judges and evaluators to trigger authentic end-to-end assessments
    with 1-click execution.
    """
    presets = _build_presets()
    return DemoListResponse(total=len(presets), demos=presets)
