"""
Tests for provenance signing, verification, and binding.

Coverage:
  - Canonicalization: determinism, key-order independence, field exclusions
  - Digest: same canonical → same digest; changed field → changed digest
  - Signing: sign_manifest fills digest + signature
  - Signature verification: valid, wrong key, modified fields (per-field)
  - Input binding: correct input passes, substituted input fails
  - Model binding: correct model SHA passes, wrong SHA fails
  - Output binding: correct output passes, modified output fails
  - Full verify_manifest pipeline
  - Anti-fake: every important signed field independently tampered
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest

from backend.domain.entities import ProvenanceManifest
from backend.infra.crypto import (
    generate_nonce,
    generate_signing_key,
    hash_bytes,
    public_key_from_private,
)
from backend.provenance.signing import (
    _SIGNED_FIELDS,
    canonicalize_manifest,
    digest_manifest,
    sign_manifest,
    verify_input_binding,
    verify_manifest,
    verify_model_binding,
    verify_output_binding,
    verify_signature,
    VerificationResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def keypair():
    """Generate a fresh Ed25519 keypair once per test module."""
    priv = generate_signing_key()
    pub = public_key_from_private(priv)
    return priv, pub


@pytest.fixture(scope="module")
def other_keypair():
    """A second keypair for wrong-key tests."""
    priv = generate_signing_key()
    pub = public_key_from_private(priv)
    return priv, pub


def _make_manifest(
    *,
    input_sha256: str = "a" * 64,
    model_sha256: str = "b" * 64,
    output_sha256: str = "c" * 64,
    preprocessing_config: dict | None = None,
    inference_config: dict | None = None,
    nonce: str | None = None,
    sequence: int = 0,
    timestamp_utc: str = "2026-01-01T00:00:00Z",
    assessment_id: str = "assess-1",
) -> ProvenanceManifest:
    """Create an unsigned ProvenanceManifest with given or default fields."""
    return ProvenanceManifest(
        assessment_id=assessment_id,
        input_sha256=input_sha256,
        model_sha256=model_sha256,
        preprocessing_config=preprocessing_config or {"resize": [224, 224], "normalize": True},
        inference_config=inference_config or {"confidence_threshold": 0.5, "top_k": 5},
        output_sha256=output_sha256,
        timestamp_utc=timestamp_utc,
        nonce=nonce or generate_nonce(),
        sequence=sequence,
    )


@pytest.fixture
def unsigned_manifest():
    return _make_manifest()


@pytest.fixture
def signed_manifest(unsigned_manifest, keypair):
    priv, _ = keypair
    return sign_manifest(unsigned_manifest, priv)


# ---------------------------------------------------------------------------
# Tests: Canonicalization
# ---------------------------------------------------------------------------

class TestCanonicalization:

    def test_same_manifest_same_canonical_bytes(self, unsigned_manifest):
        """Same logical manifest must always produce identical canonical bytes."""
        c1 = canonicalize_manifest(unsigned_manifest)
        c2 = canonicalize_manifest(unsigned_manifest)
        assert c1 == c2

    def test_canonical_bytes_are_utf8(self, unsigned_manifest):
        b = canonicalize_manifest(unsigned_manifest)
        assert isinstance(b, bytes)
        # Must decode as UTF-8 without error
        decoded = b.decode("utf-8")
        assert len(decoded) > 10

    def test_canonical_is_valid_json(self, unsigned_manifest):
        b = canonicalize_manifest(unsigned_manifest)
        obj = json.loads(b)
        assert isinstance(obj, dict)

    def test_canonical_keys_sorted(self, unsigned_manifest):
        b = canonicalize_manifest(unsigned_manifest)
        obj = json.loads(b)
        keys = list(obj.keys())
        assert keys == sorted(keys), "Canonical JSON keys must be sorted"

    def test_canonical_contains_only_signed_fields(self, unsigned_manifest):
        b = canonicalize_manifest(unsigned_manifest)
        obj = json.loads(b)
        assert set(obj.keys()) == _SIGNED_FIELDS

    def test_canonical_excludes_assessment_id(self, unsigned_manifest):
        b = canonicalize_manifest(unsigned_manifest)
        obj = json.loads(b)
        assert "assessment_id" not in obj, (
            "assessment_id must not be signed (administrative field)"
        )

    def test_canonical_excludes_digest_and_signature(self, unsigned_manifest):
        b = canonicalize_manifest(unsigned_manifest)
        obj = json.loads(b)
        assert "digest" not in obj
        assert "signature" not in obj

    def test_canonical_no_extra_whitespace(self, unsigned_manifest):
        b = canonicalize_manifest(unsigned_manifest)
        s = b.decode("utf-8")
        assert "  " not in s, "Canonical JSON must not have extra whitespace"
        assert "\n" not in s
        assert "\r" not in s

    def test_dict_insertion_order_does_not_affect_canonical(self):
        """
        ANTI-FAKE: dict insertion order must NOT affect canonicalization.
        Both configs produce the same canonical bytes.
        """
        config_v1 = {"alpha": 1, "beta": 2, "gamma": 3}
        config_v2 = {"gamma": 3, "alpha": 1, "beta": 2}  # Different insertion order

        m1 = _make_manifest(preprocessing_config=config_v1)
        m2 = _make_manifest(preprocessing_config=config_v2)

        # Set same nonce and timestamp so the only variable is dict order
        nonce = generate_nonce()
        m1 = m1.model_copy(update={"nonce": nonce, "timestamp_utc": "2026-01-01T00:00:00Z"})
        m2 = m2.model_copy(update={"nonce": nonce, "timestamp_utc": "2026-01-01T00:00:00Z",
                                    "manifest_id": m1.manifest_id})

        c1 = canonicalize_manifest(m1)
        c2 = canonicalize_manifest(m2)
        assert c1 == c2, (
            "ANTI-FAKE: canonical bytes must be identical regardless of dict insertion order"
        )

    def test_changing_input_sha256_changes_canonical(self, unsigned_manifest):
        """ANTI-FAKE: modifying a signed field must change canonical bytes."""
        original = canonicalize_manifest(unsigned_manifest)
        modified = canonicalize_manifest(
            unsigned_manifest.model_copy(update={"input_sha256": "f" * 64})
        )
        assert original != modified

    def test_changing_model_sha256_changes_canonical(self, unsigned_manifest):
        original = canonicalize_manifest(unsigned_manifest)
        modified = canonicalize_manifest(
            unsigned_manifest.model_copy(update={"model_sha256": "e" * 64})
        )
        assert original != modified

    def test_changing_output_sha256_changes_canonical(self, unsigned_manifest):
        original = canonicalize_manifest(unsigned_manifest)
        modified = canonicalize_manifest(
            unsigned_manifest.model_copy(update={"output_sha256": "d" * 64})
        )
        assert original != modified

    def test_changing_nonce_changes_canonical(self, unsigned_manifest):
        original = canonicalize_manifest(unsigned_manifest)
        modified = canonicalize_manifest(
            unsigned_manifest.model_copy(update={"nonce": generate_nonce()})
        )
        assert original != modified

    def test_changing_timestamp_changes_canonical(self, unsigned_manifest):
        original = canonicalize_manifest(unsigned_manifest)
        modified = canonicalize_manifest(
            unsigned_manifest.model_copy(update={"timestamp_utc": "2030-12-31T23:59:59Z"})
        )
        assert original != modified

    def test_changing_sequence_changes_canonical(self, unsigned_manifest):
        original = canonicalize_manifest(unsigned_manifest)
        modified = canonicalize_manifest(
            unsigned_manifest.model_copy(update={"sequence": 999})
        )
        assert original != modified

    def test_changing_preprocessing_config_changes_canonical(self, unsigned_manifest):
        original = canonicalize_manifest(unsigned_manifest)
        modified = canonicalize_manifest(
            unsigned_manifest.model_copy(
                update={"preprocessing_config": {"resize": [512, 512]}}
            )
        )
        assert original != modified

    def test_changing_inference_config_changes_canonical(self, unsigned_manifest):
        original = canonicalize_manifest(unsigned_manifest)
        modified = canonicalize_manifest(
            unsigned_manifest.model_copy(
                update={"inference_config": {"confidence_threshold": 0.99}}
            )
        )
        assert original != modified

    def test_assessment_id_does_not_affect_canonical(self):
        """
        assessment_id is NOT signed. Two manifests differing only in
        assessment_id must produce the same canonical bytes (other fields equal).
        """
        nonce = generate_nonce()
        m1 = _make_manifest(assessment_id="assessment-A")
        m2 = _make_manifest(assessment_id="assessment-B")
        # Equalise all signed fields
        m2 = m2.model_copy(update={
            "manifest_id": m1.manifest_id,
            "nonce": m1.nonce,
            "timestamp_utc": m1.timestamp_utc,
            "input_sha256": m1.input_sha256,
            "model_sha256": m1.model_sha256,
            "output_sha256": m1.output_sha256,
            "preprocessing_config": m1.preprocessing_config,
            "inference_config": m1.inference_config,
            "sequence": m1.sequence,
        })
        assert canonicalize_manifest(m1) == canonicalize_manifest(m2)


# ---------------------------------------------------------------------------
# Tests: Digest
# ---------------------------------------------------------------------------

class TestDigest:

    def test_digest_is_64_hex_chars(self, unsigned_manifest):
        d = digest_manifest(unsigned_manifest)
        assert len(d) == 64
        assert all(c in "0123456789abcdef" for c in d)

    def test_digest_deterministic(self, unsigned_manifest):
        d1 = digest_manifest(unsigned_manifest)
        d2 = digest_manifest(unsigned_manifest)
        assert d1 == d2

    def test_changed_field_changes_digest(self, unsigned_manifest):
        """ANTI-FAKE: any modification to a signed field must change the digest."""
        d_orig = digest_manifest(unsigned_manifest)
        d_mod = digest_manifest(
            unsigned_manifest.model_copy(update={"input_sha256": "f" * 64})
        )
        assert d_orig != d_mod


# ---------------------------------------------------------------------------
# Tests: Signing
# ---------------------------------------------------------------------------

class TestSigning:

    def test_sign_fills_digest_and_signature(self, unsigned_manifest, keypair):
        priv, _ = keypair
        signed = sign_manifest(unsigned_manifest, priv)
        assert signed.digest is not None
        assert signed.signature is not None
        assert len(signed.digest) == 64
        assert len(signed.signature) == 128  # 64 bytes Ed25519 sig → 128 hex chars

    def test_sign_does_not_mutate_original(self, unsigned_manifest, keypair):
        priv, _ = keypair
        _ = sign_manifest(unsigned_manifest, priv)
        assert unsigned_manifest.digest is None
        assert unsigned_manifest.signature is None

    def test_sign_rejects_already_signed(self, signed_manifest, keypair):
        priv, _ = keypair
        with pytest.raises(ValueError, match="already has a digest"):
            sign_manifest(signed_manifest, priv)

    def test_sign_digest_matches_digest_manifest(self, unsigned_manifest, keypair):
        priv, _ = keypair
        signed = sign_manifest(unsigned_manifest, priv)
        expected_digest = digest_manifest(unsigned_manifest)
        assert signed.digest == expected_digest


# ---------------------------------------------------------------------------
# Tests: Signature Verification
# ---------------------------------------------------------------------------

class TestSignatureVerification:

    def test_valid_signature_passes(self, signed_manifest, keypair):
        _, pub = keypair
        check = verify_signature(signed_manifest, pub)
        assert check.passed is True
        assert check.check_name == "signature"

    def test_wrong_public_key_fails(self, signed_manifest, other_keypair):
        """ANTI-FAKE: wrong public key must fail verification."""
        _, wrong_pub = other_keypair
        check = verify_signature(signed_manifest, wrong_pub)
        assert check.passed is False

    def test_unsigned_manifest_fails(self, unsigned_manifest, keypair):
        _, pub = keypair
        check = verify_signature(unsigned_manifest, pub)
        assert check.passed is False
        desc = check.description.lower()
        assert "no digest" in desc or "not signed" in desc or "digest=none" in desc or "was not signed" in desc

    # --- Per-field tamper tests ---
    # Each test creates a valid signed manifest, then modifies ONE field
    # and proves that verification fails.

    def _tamper_and_check(self, signed_manifest, keypair, **updates) -> bool:
        _, pub = keypair
        tampered = signed_manifest.model_copy(update=updates)
        check = verify_signature(tampered, pub)
        return check.passed

    def test_tamper_input_sha256_fails(self, signed_manifest, keypair):
        assert not self._tamper_and_check(signed_manifest, keypair, input_sha256="f" * 64)

    def test_tamper_model_sha256_fails(self, signed_manifest, keypair):
        assert not self._tamper_and_check(signed_manifest, keypair, model_sha256="e" * 64)

    def test_tamper_output_sha256_fails(self, signed_manifest, keypair):
        assert not self._tamper_and_check(signed_manifest, keypair, output_sha256="d" * 64)

    def test_tamper_nonce_fails(self, signed_manifest, keypair):
        assert not self._tamper_and_check(signed_manifest, keypair, nonce=generate_nonce())

    def test_tamper_timestamp_fails(self, signed_manifest, keypair):
        assert not self._tamper_and_check(
            signed_manifest, keypair, timestamp_utc="2099-12-31T23:59:59Z"
        )

    def test_tamper_sequence_fails(self, signed_manifest, keypair):
        assert not self._tamper_and_check(signed_manifest, keypair, sequence=9999)

    def test_tamper_preprocessing_config_fails(self, signed_manifest, keypair):
        assert not self._tamper_and_check(
            signed_manifest, keypair,
            preprocessing_config={"resize": [512, 512], "normalize": False}
        )

    def test_tamper_inference_config_fails(self, signed_manifest, keypair):
        assert not self._tamper_and_check(
            signed_manifest, keypair,
            inference_config={"confidence_threshold": 0.99, "top_k": 100}
        )

    def test_tamper_manifest_id_fails(self, signed_manifest, keypair):
        """manifest_id is a signed field; changing it must fail verification."""
        import uuid
        assert not self._tamper_and_check(
            signed_manifest, keypair, manifest_id=str(uuid.uuid4())
        )

    def test_tamper_pramaan_version_fails(self, signed_manifest, keypair):
        assert not self._tamper_and_check(signed_manifest, keypair, pramaan_version="9.9.9")

    def test_tamper_signature_field_fails(self, signed_manifest, keypair):
        """A corrupted signature hex must fail."""
        _, pub = keypair
        # Flip one character in the signature
        orig_sig = signed_manifest.signature
        corrupted = "0" * 128  # All zeros — definitely wrong
        tampered = signed_manifest.model_copy(update={"signature": corrupted})
        check = verify_signature(tampered, pub)
        assert check.passed is False

    def test_assessment_id_change_does_not_break_sig(self, signed_manifest, keypair):
        """
        assessment_id is NOT signed.  Changing it must NOT break the signature.
        """
        _, pub = keypair
        # assessment_id is not in _SIGNED_FIELDS
        changed = signed_manifest.model_copy(update={"assessment_id": "different-assessment"})
        check = verify_signature(changed, pub)
        assert check.passed is True, (
            "assessment_id is not a signed field; changing it must not break the signature"
        )


# ---------------------------------------------------------------------------
# Tests: Input Binding
# ---------------------------------------------------------------------------

class TestInputBinding:

    def test_correct_input_passes(self, signed_manifest):
        actual = b"the actual input image bytes"
        # Set manifest.input_sha256 to hash of actual bytes
        sha = hash_bytes(actual)
        m = signed_manifest.model_copy(update={"input_sha256": sha})
        check = verify_input_binding(m, actual)
        assert check.passed is True
        assert check.check_name == "input_binding"

    def test_substituted_input_fails(self, signed_manifest):
        """ANTI-FAKE: a different input must fail binding verification."""
        actual = b"the real input"
        sha = hash_bytes(actual)
        m = signed_manifest.model_copy(update={"input_sha256": sha})

        fake_input = b"a different image"
        check = verify_input_binding(m, fake_input)
        assert check.passed is False
        assert check.observed != check.expected

    def test_input_binding_check_name(self, signed_manifest):
        check = verify_input_binding(signed_manifest, b"anything")
        assert check.check_name == "input_binding"

    def test_input_binding_records_expected_and_observed(self, signed_manifest):
        actual = b"test input"
        actual_sha = hash_bytes(actual)
        m = signed_manifest.model_copy(update={"input_sha256": actual_sha})
        check = verify_input_binding(m, actual)
        assert check.expected == actual_sha
        assert check.observed == actual_sha


# ---------------------------------------------------------------------------
# Tests: Model Binding
# ---------------------------------------------------------------------------

class TestModelBinding:

    def test_correct_model_sha256_passes(self, signed_manifest):
        model_sha = "b" * 64
        m = signed_manifest.model_copy(update={"model_sha256": model_sha})
        check = verify_model_binding(m, model_sha)
        assert check.passed is True

    def test_wrong_model_sha256_fails(self, signed_manifest):
        """ANTI-FAKE: a different model SHA must fail binding."""
        m = signed_manifest.model_copy(update={"model_sha256": "b" * 64})
        check = verify_model_binding(m, "c" * 64)
        assert check.passed is False
        assert check.observed != check.expected

    def test_model_binding_check_name(self, signed_manifest):
        check = verify_model_binding(signed_manifest, "a" * 64)
        assert check.check_name == "model_binding"


# ---------------------------------------------------------------------------
# Tests: Output Binding
# ---------------------------------------------------------------------------

class TestOutputBinding:

    def test_correct_output_passes(self, signed_manifest):
        actual_output = b'{"class": "cat", "confidence": 0.95}'
        sha = hash_bytes(actual_output)
        m = signed_manifest.model_copy(update={"output_sha256": sha})
        check = verify_output_binding(m, actual_output)
        assert check.passed is True

    def test_modified_output_fails(self, signed_manifest):
        """ANTI-FAKE: modifying the output bytes must fail binding."""
        original_output = b'{"class": "cat", "confidence": 0.95}'
        sha = hash_bytes(original_output)
        m = signed_manifest.model_copy(update={"output_sha256": sha})

        modified_output = b'{"class": "dog", "confidence": 0.95}'
        check = verify_output_binding(m, modified_output)
        assert check.passed is False

    def test_substituted_output_fails(self, signed_manifest):
        """ANTI-FAKE: a completely substituted output must fail."""
        original_output = b"original predictions"
        sha = hash_bytes(original_output)
        m = signed_manifest.model_copy(update={"output_sha256": sha})

        substituted_output = b"attacker substituted predictions"
        check = verify_output_binding(m, substituted_output)
        assert check.passed is False

    def test_valid_sig_plus_wrong_output_both_reported(self, signed_manifest, keypair):
        """
        Core invariant: valid signature does NOT mean valid output.
        Both must be checked independently.
        """
        _, pub = keypair
        original_output = b"correct output"
        sha = hash_bytes(original_output)
        m = signed_manifest.model_copy(update={"output_sha256": sha})
        # Re-sign the updated manifest so the sig is valid for the new output_sha256
        from backend.infra.crypto import generate_signing_key
        priv, pub2 = keypair
        m_unsigned = m.model_copy(update={"digest": None, "signature": None})
        m_signed = sign_manifest(m_unsigned, priv)

        # Now verify with correct output → both pass
        result = verify_manifest(m_signed, pub2, actual_output_bytes=original_output)
        assert result.valid is True

        # Verify with substituted output → output check fails
        result2 = verify_manifest(
            m_signed, pub2, actual_output_bytes=b"substituted output"
        )
        assert result2.valid is False
        output_checks = [c for c in result2.checks if c.check_name == "output_binding"]
        assert len(output_checks) == 1
        assert output_checks[0].passed is False

    def test_output_binding_check_name(self, signed_manifest):
        check = verify_output_binding(signed_manifest, b"output")
        assert check.check_name == "output_binding"


# ---------------------------------------------------------------------------
# Tests: Full verify_manifest pipeline
# ---------------------------------------------------------------------------

class TestVerifyManifest:

    def _make_fully_signed(self, keypair):
        priv, pub = keypair
        actual_input = b"test input image bytes"
        actual_output = b'{"class": "airplane", "confidence": 0.88}'
        model_sha = hash_bytes(b"fake model binary")

        m = _make_manifest(
            input_sha256=hash_bytes(actual_input),
            model_sha256=model_sha,
            output_sha256=hash_bytes(actual_output),
        )
        signed = sign_manifest(m, priv)
        return signed, actual_input, actual_output, model_sha, pub

    def test_all_checks_pass(self, keypair):
        signed, actual_input, actual_output, model_sha, pub = self._make_fully_signed(keypair)
        result = verify_manifest(
            signed, pub,
            actual_input_bytes=actual_input,
            actual_output_bytes=actual_output,
            actual_model_sha256=model_sha,
        )
        assert result.valid is True
        assert result.error is None
        assert len(result.failed_checks) == 0
        assert len(result.passed_checks) == 4  # sig + input + model + output

    def test_unsigned_manifest_returns_error(self, unsigned_manifest, keypair):
        _, pub = keypair
        result = verify_manifest(unsigned_manifest, pub)
        assert result.valid is False
        assert result.error is not None

    def test_signature_only_when_no_binding_data(self, signed_manifest, keypair):
        _, pub = keypair
        result = verify_manifest(signed_manifest, pub)
        assert result.valid is True
        assert len(result.checks) == 1
        assert result.checks[0].check_name == "signature"

    def test_invalid_signature_propagates(self, signed_manifest, other_keypair):
        _, wrong_pub = other_keypair
        result = verify_manifest(signed_manifest, wrong_pub)
        assert result.valid is False
        sig_checks = [c for c in result.checks if c.check_name == "signature"]
        assert sig_checks[0].passed is False

    def test_input_substitution_detected(self, keypair):
        signed, _, actual_output, model_sha, pub = self._make_fully_signed(keypair)
        result = verify_manifest(
            signed, pub,
            actual_input_bytes=b"wrong input bytes",
        )
        assert result.valid is False
        input_check = next(c for c in result.checks if c.check_name == "input_binding")
        assert not input_check.passed

    def test_output_substitution_detected(self, keypair):
        signed, actual_input, _, model_sha, pub = self._make_fully_signed(keypair)
        result = verify_manifest(
            signed, pub,
            actual_output_bytes=b"substituted output",
        )
        assert result.valid is False

    def test_model_substitution_detected(self, keypair):
        signed, _, _, _, pub = self._make_fully_signed(keypair)
        result = verify_manifest(
            signed, pub,
            actual_model_sha256="f" * 64,  # Wrong model
        )
        assert result.valid is False
        model_check = next(c for c in result.checks if c.check_name == "model_binding")
        assert not model_check.passed
