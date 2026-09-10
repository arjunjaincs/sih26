"""
PRAMAAN provenance signing and verification.

This module is the cryptographic heart of Phase 5.  It operates exclusively
on existing PRAMAAN primitives (crypto.py, domain entities) — no new crypto.

Architecture
------------

Signing pipeline:
    ProvenanceManifest (without digest/signature)
        │
        ▼
    canonicalize_manifest()  →  deterministic UTF-8 JSON bytes
        │
        ▼
    hash_bytes()             →  SHA-256 hex digest
        │
        ▼
    sign()                   →  Ed25519 signature (hex)
        │
        ▼
    ProvenanceManifest (with digest + signature)

Verification pipeline:
    ProvenanceManifest + Ed25519PublicKey
        │
        ├─→ signature check  (re-canonicalize → re-digest → verify sig)
        ├─→ input binding    (re-hash actual input bytes vs manifest.input_sha256)
        ├─→ model binding    (compare supplied model SHA-256 vs manifest.model_sha256)
        └─→ output binding   (re-hash actual output bytes vs manifest.output_sha256)

Canonical form
--------------
Only the inference-binding fields are signed.  Administrative fields
(assessment_id) and self-referential fields (digest, signature) are excluded.

Signed fields (sorted JSON keys, no whitespace):
    inference_config, input_sha256, manifest_id, manifest_version,
    model_sha256, nonce, output_sha256, pramaan_version,
    preprocessing_config, sequence, timestamp_utc

This set is stable across V1.  Adding a field requires a manifest_version bump.

Limitations (documented per ADR-003)
--------------------------------------
- assessment_id is not bound (administrative metadata only)
- Timestamp is not cryptographically ordered (wall-clock can be set back)
- Key revocation is not implemented in V1 (per ADR-005)
- Output/input binding only as strong as the SHA-256 pre-image resistance
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from backend.domain.entities import ProvenanceManifest
from backend.infra.crypto import canonical_json, hash_bytes, sign, verify


# ---------------------------------------------------------------------------
# The set of fields included in the canonical (signed) representation.
# THIS SET MUST NOT CHANGE without bumping manifest_version.
# ---------------------------------------------------------------------------

_SIGNED_FIELDS: frozenset[str] = frozenset({
    "inference_config",
    "input_sha256",
    "manifest_id",
    "manifest_version",
    "model_sha256",
    "nonce",
    "output_sha256",
    "pramaan_version",
    "preprocessing_config",
    "sequence",
    "timestamp_utc",
})


# ---------------------------------------------------------------------------
# Verification result types
# ---------------------------------------------------------------------------

@dataclass
class VerificationCheck:
    """
    Result of a single cryptographic or hash-binding check.

    expected and observed are string representations of the compared values
    (hash hex, or short descriptors for composite checks).
    """
    check_name: str        # "signature" | "input_binding" | "model_binding" | "output_binding"
    passed: bool
    expected: str | None   # What the manifest records / what we should see
    observed: str | None   # What we actually computed from the supplied data
    description: str


@dataclass
class VerificationResult:
    """
    Aggregate result of verifying a ProvenanceManifest.

    valid is True iff ALL checks passed.
    checks lists every individual check performed.
    error is set when verification could not be attempted (e.g. missing digest).
    """
    valid: bool
    checks: list[VerificationCheck] = field(default_factory=list)
    error: str | None = None

    def add_check(self, check: VerificationCheck) -> None:
        self.checks.append(check)
        if not check.passed:
            self.valid = False

    @property
    def failed_checks(self) -> list[VerificationCheck]:
        return [c for c in self.checks if not c.passed]

    @property
    def passed_checks(self) -> list[VerificationCheck]:
        return [c for c in self.checks if c.passed]


# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------

def canonicalize_manifest(manifest: ProvenanceManifest) -> bytes:
    """
    Produce the canonical UTF-8 JSON bytes for signing/digest.

    Only the inference-binding fields (SIGNED_FIELDS) are included.
    digest and signature are excluded to prevent circular dependency.
    assessment_id is excluded — it is administrative metadata, not
    inference-binding.

    The result is deterministic: the same logical manifest always produces
    the same bytes regardless of Python dict insertion order.
    """
    payload: dict[str, Any] = {}
    manifest_dict = manifest.model_dump()

    for field_name in _SIGNED_FIELDS:
        if field_name in manifest_dict:
            payload[field_name] = manifest_dict[field_name]

    # canonical_json sorts keys and uses no whitespace (from crypto.py)
    return canonical_json(payload)


def digest_manifest(manifest: ProvenanceManifest) -> str:
    """
    Compute the SHA-256 digest of the manifest's canonical form.

    Returns the lowercase hex digest string.
    """
    return hash_bytes(canonicalize_manifest(manifest))


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

def sign_manifest(
    manifest: ProvenanceManifest,
    private_key: Ed25519PrivateKey,
) -> ProvenanceManifest:
    """
    Sign a ProvenanceManifest.

    Returns a *new* manifest with digest and signature fields populated.
    The input manifest is not mutated.

    Raises ValueError if digest or signature are already set (prevents
    double-signing and avoids confusion about which digest was signed).
    """
    if manifest.digest is not None or manifest.signature is not None:
        raise ValueError(
            "Manifest already has a digest or signature. "
            "Create a fresh manifest before signing."
        )

    digest_hex = digest_manifest(manifest)
    sig_hex = sign(private_key, digest_hex)

    return manifest.model_copy(update={"digest": digest_hex, "signature": sig_hex})


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def verify_signature(
    manifest: ProvenanceManifest,
    public_key: Ed25519PublicKey,
) -> VerificationCheck:
    """
    Verify the Ed25519 signature on a signed manifest.

    Process:
      1. Re-canonicalize the manifest (using the same _SIGNED_FIELDS)
      2. Re-compute the SHA-256 digest of canonical bytes
      3. Verify the stored signature over the re-computed digest

    This catches:
      - Modification of any signed field after signing
      - Signature forged with a different key
      - Corrupted signature bytes
      - Corrupted digest field (we always re-compute, never trust the stored digest)
    """
    if manifest.digest is None or manifest.signature is None:
        return VerificationCheck(
            check_name="signature",
            passed=False,
            expected="non-null digest and signature",
            observed=f"digest={manifest.digest!r} signature={manifest.signature!r}",
            description="Manifest has no digest or signature — was not signed.",
        )

    # Always re-compute from canonical bytes, never trust the stored digest
    recomputed_digest = digest_manifest(manifest)

    sig_valid = verify(public_key, recomputed_digest, manifest.signature)

    if sig_valid:
        return VerificationCheck(
            check_name="signature",
            passed=True,
            expected=recomputed_digest,
            observed=recomputed_digest,
            description="Ed25519 signature is valid over the re-computed canonical digest.",
        )
    else:
        return VerificationCheck(
            check_name="signature",
            passed=False,
            expected=recomputed_digest,
            observed=manifest.signature[:16] + "…",  # Don't expose full sig in evidence
            description=(
                "Ed25519 signature verification FAILED. "
                "The manifest may have been tampered with after signing, "
                "or the wrong public key was supplied."
            ),
        )


# ---------------------------------------------------------------------------
# Binding verification
# ---------------------------------------------------------------------------

def verify_input_binding(
    manifest: ProvenanceManifest,
    actual_input_bytes: bytes,
) -> VerificationCheck:
    """
    Verify that *actual_input_bytes* match the input hash bound in the manifest.

    The manifest.input_sha256 was recorded at signing time by hashing the actual
    input fed to the model.  Re-hashing the supplied input and comparing proves
    (up to SHA-256 pre-image resistance) that the same input was used.

    A mismatch means either:
      - The input was substituted after signing
      - The wrong input was supplied for verification
    """
    recomputed = hash_bytes(actual_input_bytes)
    passed = recomputed == manifest.input_sha256
    return VerificationCheck(
        check_name="input_binding",
        passed=passed,
        expected=manifest.input_sha256,
        observed=recomputed,
        description=(
            "Input SHA-256 matches the manifest binding."
            if passed else
            "Input SHA-256 MISMATCH — the supplied input differs from the signed record. "
            "The input may have been substituted."
        ),
    )


def verify_model_binding(
    manifest: ProvenanceManifest,
    actual_model_sha256: str,
) -> VerificationCheck:
    """
    Verify that *actual_model_sha256* matches the model hash bound in the manifest.

    The manifest.model_sha256 was recorded as the SHA-256 of the model artifact
    used to run this inference.  A mismatch means the inference was run with a
    different model than the one the manifest claims.
    """
    passed = actual_model_sha256 == manifest.model_sha256
    return VerificationCheck(
        check_name="model_binding",
        passed=passed,
        expected=manifest.model_sha256,
        observed=actual_model_sha256,
        description=(
            "Model SHA-256 matches the manifest binding."
            if passed else
            "Model SHA-256 MISMATCH — the supplied model differs from the signed record. "
            "The model identity may have been substituted."
        ),
    )


def verify_output_binding(
    manifest: ProvenanceManifest,
    actual_output_bytes: bytes,
) -> VerificationCheck:
    """
    Verify that *actual_output_bytes* match the output hash bound in the manifest.

    IMPORTANT: A valid Ed25519 signature proves the signed record has not been
    tampered with.  It does NOT prove the output is trustworthy — the output hash
    must be verified separately (this function).

    A valid signature + matching output hash together prove that:
      - The record was created by the key holder
      - The output supplied for verification matches what the record claims

    A valid signature + mismatching output hash means:
      - The record is authentic
      - The output has been substituted
    """
    recomputed = hash_bytes(actual_output_bytes)
    passed = recomputed == manifest.output_sha256
    return VerificationCheck(
        check_name="output_binding",
        passed=passed,
        expected=manifest.output_sha256,
        observed=recomputed,
        description=(
            "Output SHA-256 matches the manifest binding."
            if passed else
            "Output SHA-256 MISMATCH — the supplied output differs from the signed record. "
            "The inference output may have been substituted."
        ),
    )


# ---------------------------------------------------------------------------
# Full verification
# ---------------------------------------------------------------------------

def verify_manifest(
    manifest: ProvenanceManifest,
    public_key: Ed25519PublicKey,
    *,
    actual_input_bytes: bytes | None = None,
    actual_output_bytes: bytes | None = None,
    actual_model_sha256: str | None = None,
) -> VerificationResult:
    """
    Run the full provenance verification pipeline.

    Always verifies:
      - Ed25519 signature (required; returns error if manifest is unsigned)

    Conditionally verifies (when data supplied):
      - Input binding (if actual_input_bytes is not None)
      - Model binding (if actual_model_sha256 is not None)
      - Output binding (if actual_output_bytes is not None)

    Note: Binding verification is independent of signature verification.
    A valid signature proves the record has not been tampered with.
    Binding verification proves the supplied artefacts match the record.
    Both must pass for a fully trustworthy provenance claim.
    """
    if manifest.digest is None or manifest.signature is None:
        return VerificationResult(
            valid=False,
            error="Manifest is unsigned (digest or signature is None). Cannot verify.",
        )

    result = VerificationResult(valid=True)

    # 1. Signature (always)
    sig_check = verify_signature(manifest, public_key)
    result.add_check(sig_check)

    # 2. Input binding (optional)
    if actual_input_bytes is not None:
        result.add_check(verify_input_binding(manifest, actual_input_bytes))

    # 3. Model binding (optional)
    if actual_model_sha256 is not None:
        result.add_check(verify_model_binding(manifest, actual_model_sha256))

    # 4. Output binding (optional)
    if actual_output_bytes is not None:
        result.add_check(verify_output_binding(manifest, actual_output_bytes))

    return result
