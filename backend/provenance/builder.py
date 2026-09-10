"""
PRAMAAN provenance manifest builder.

Convenience factory for constructing and signing a ProvenanceManifest from
raw inference artefacts.  This is the intended production entry point for
inference systems that call PRAMAAN to record a provenance event.

Usage (typical)
---------------
    from backend.infra.crypto import generate_signing_key, public_key_from_private
    from backend.provenance.builder import build_and_sign_manifest
    from backend.infra.db import ProvenanceRepository

    private_key = load_private_key(key_path)
    manifest = build_and_sign_manifest(
        assessment_id=assessment_id,
        input_sha256=hash_file(input_image_path),
        model_sha256=hash_file(model_path),
        output_bytes=json_encode(model_output),
        preprocessing_config={"resize": [224, 224], "normalize": True},
        inference_config={"confidence_threshold": 0.5, "top_k": 5},
        sequence=next_sequence,
        private_key=private_key,
    )
    ProvenanceRepository(conn).insert(manifest)

What the builder does
---------------------
1. Computes output_sha256 = SHA-256(output_bytes)
2. Generates a fresh nonce (32 random bytes, hex)
3. Records the current UTC timestamp in ISO 8601 format with Z suffix
4. Canonicalizes the signable fields
5. Computes the SHA-256 digest of canonical bytes
6. Signs the digest with Ed25519
7. Returns a signed ProvenanceManifest (immutable after return)

What the builder does NOT do
-----------------------------
- It does NOT store anything in the database (caller's responsibility)
- It does NOT validate that the input_sha256 was computed correctly
  (the caller must compute SHA-256 of the actual input)
- It does NOT validate that model_sha256 matches a registered model
  (the caller should use hash_file() against the actual model file)
- It does NOT retry or batch (one call = one manifest)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.domain.entities import ProvenanceManifest
from backend.infra.crypto import generate_nonce, hash_bytes
from backend.provenance.signing import sign_manifest


_PRAMAAN_VERSION = "1.0.0"


def build_and_sign_manifest(
    *,
    assessment_id: str,
    input_sha256: str,
    model_sha256: str,
    output_bytes: bytes,
    preprocessing_config: dict[str, Any],
    inference_config: dict[str, Any],
    sequence: int,
    private_key: Ed25519PrivateKey,
    pramaan_version: str = _PRAMAAN_VERSION,
) -> ProvenanceManifest:
    """
    Build and sign a ProvenanceManifest for one inference event.

    Parameters
    ----------
    assessment_id : str
        The PRAMAAN assessment this manifest belongs to.
    input_sha256 : str
        SHA-256 hex digest of the input image/data fed to the model.
        Compute with crypto.hash_bytes() or crypto.hash_file().
    model_sha256 : str
        SHA-256 hex digest of the model artifact file.
        Compute with crypto.hash_file() for the model binary.
    output_bytes : bytes
        Canonical byte representation of the model's inference output.
        Typically JSON-encoded sorted prediction dict, or raw logit bytes.
        The builder computes output_sha256 = SHA-256(output_bytes).
    preprocessing_config : dict
        Configuration parameters used during input preprocessing
        (e.g. resize dimensions, normalisation means/stds).
        Must be JSON-serializable. Will be sorted and stored canonically.
    inference_config : dict
        Configuration parameters used during inference
        (e.g. confidence threshold, top_k, batch_size).
        Must be JSON-serializable.
    sequence : int
        Monotonically increasing sequence number for this assessment.
        Use ProvenanceRepository.max_sequence(assessment_id) + 1.
    private_key : Ed25519PrivateKey
        The signing key. Load with crypto.load_private_key().
    pramaan_version : str
        PRAMAAN software version (defaults to "1.0.0").

    Returns
    -------
    ProvenanceManifest
        A fully signed manifest with digest and signature set.
    """
    if sequence < 0:
        raise ValueError(f"sequence must be >= 0, got {sequence}")

    # Compute output hash from actual output bytes
    output_sha256 = hash_bytes(output_bytes)

    # ISO 8601 timestamp with Z suffix (per domain entity spec)
    timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build unsigned manifest
    manifest = ProvenanceManifest(
        assessment_id=assessment_id,
        input_sha256=input_sha256,
        model_sha256=model_sha256,
        preprocessing_config=preprocessing_config,
        inference_config=inference_config,
        output_sha256=output_sha256,
        timestamp_utc=timestamp_utc,
        nonce=generate_nonce(),
        sequence=sequence,
        pramaan_version=pramaan_version,
        # digest and signature left None — sign_manifest fills them
    )

    # Sign and return
    return sign_manifest(manifest, private_key)
