"""
Tests for the provenance manifest builder.

Coverage:
  - build_and_sign_manifest produces a fully signed manifest
  - output_sha256 is computed from actual output_bytes (not hardcoded)
  - nonce is unique per call (random)
  - timestamp is set to a valid ISO 8601 UTC string
  - sequence is stored correctly
  - the returned manifest verifies with the corresponding public key
  - wrong public key fails
  - negative sequence raises ValueError
"""

from __future__ import annotations

import re

import pytest

from backend.infra.crypto import (
    generate_signing_key,
    hash_bytes,
    public_key_from_private,
)
from backend.provenance.builder import build_and_sign_manifest
from backend.provenance.signing import verify_manifest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def keypair():
    priv = generate_signing_key()
    pub = public_key_from_private(priv)
    return priv, pub


@pytest.fixture(scope="module")
def other_keypair():
    priv = generate_signing_key()
    pub = public_key_from_private(priv)
    return priv, pub


_PREPROCESSING = {"resize": [224, 224], "normalize": True, "mean": [0.485, 0.456, 0.406]}
_INFERENCE = {"confidence_threshold": 0.5, "top_k": 5, "device": "cpu"}
_INPUT_SHA = "a" * 64
_MODEL_SHA = "b" * 64
_OUTPUT_BYTES = b'{"class": "cat", "confidence": 0.95, "top5": ["cat", "dog", "rabbit"]}'


def _build(keypair, *, sequence=0, output_bytes=_OUTPUT_BYTES, **overrides):
    priv, _ = keypair
    return build_and_sign_manifest(
        assessment_id=overrides.pop("assessment_id", "assess-builder-test"),
        input_sha256=overrides.pop("input_sha256", _INPUT_SHA),
        model_sha256=overrides.pop("model_sha256", _MODEL_SHA),
        output_bytes=output_bytes,
        preprocessing_config=overrides.pop("preprocessing_config", _PREPROCESSING),
        inference_config=overrides.pop("inference_config", _INFERENCE),
        sequence=sequence,
        private_key=priv,
        **overrides,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuilderBasic:

    def test_returns_provenance_manifest(self, keypair):
        from backend.domain.entities import ProvenanceManifest
        m = _build(keypair)
        assert isinstance(m, ProvenanceManifest)

    def test_digest_is_set(self, keypair):
        m = _build(keypair)
        assert m.digest is not None
        assert len(m.digest) == 64

    def test_signature_is_set(self, keypair):
        m = _build(keypair)
        assert m.signature is not None
        assert len(m.signature) == 128  # 64-byte Ed25519 sig → 128 hex chars

    def test_output_sha256_from_output_bytes(self, keypair):
        """ANTI-FAKE: output_sha256 must be computed from the actual output_bytes."""
        output_bytes = b"real prediction output"
        m = _build(keypair, output_bytes=output_bytes)
        expected_sha = hash_bytes(output_bytes)
        assert m.output_sha256 == expected_sha, (
            "output_sha256 must equal SHA-256(output_bytes)"
        )

    def test_different_output_bytes_give_different_sha256(self, keypair):
        """ANTI-FAKE: different output must yield different output_sha256."""
        m1 = _build(keypair, output_bytes=b"output A")
        m2 = _build(keypair, output_bytes=b"output B")
        assert m1.output_sha256 != m2.output_sha256

    def test_input_sha256_preserved(self, keypair):
        m = _build(keypair)
        assert m.input_sha256 == _INPUT_SHA

    def test_model_sha256_preserved(self, keypair):
        m = _build(keypair)
        assert m.model_sha256 == _MODEL_SHA

    def test_sequence_preserved(self, keypair):
        m = _build(keypair, sequence=42)
        assert m.sequence == 42

    def test_sequence_zero(self, keypair):
        m = _build(keypair, sequence=0)
        assert m.sequence == 0

    def test_nonce_is_64_hex_chars(self, keypair):
        m = _build(keypair)
        assert len(m.nonce) == 64
        assert all(c in "0123456789abcdef" for c in m.nonce)

    def test_nonce_is_unique_per_call(self, keypair):
        """Each call must generate a fresh nonce (cryptographically random)."""
        nonces = {_build(keypair).nonce for _ in range(20)}
        assert len(nonces) == 20, "All nonces must be unique (random)"

    def test_timestamp_utc_format(self, keypair):
        m = _build(keypair)
        # Must be ISO 8601 with Z suffix: YYYY-MM-DDTHH:MM:SSZ
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
        assert re.match(pattern, m.timestamp_utc), (
            f"timestamp_utc {m.timestamp_utc!r} does not match expected ISO 8601 Z format"
        )

    def test_pramaan_version_default(self, keypair):
        m = _build(keypair)
        assert m.pramaan_version == "1.0.0"

    def test_manifest_version(self, keypair):
        m = _build(keypair)
        assert m.manifest_version == "1"

    def test_assessment_id_preserved(self, keypair):
        m = _build(keypair, assessment_id="custom-assess")
        assert m.assessment_id == "custom-assess"

    def test_preprocessing_config_preserved(self, keypair):
        m = _build(keypair)
        assert m.preprocessing_config == _PREPROCESSING

    def test_inference_config_preserved(self, keypair):
        m = _build(keypair)
        assert m.inference_config == _INFERENCE


class TestBuilderVerification:

    def test_built_manifest_verifies_with_correct_key(self, keypair):
        """ANTI-FAKE: the signed manifest must pass full verification."""
        _, pub = keypair
        output_bytes = b"correct output"
        m = _build(keypair, output_bytes=output_bytes)

        result = verify_manifest(
            m, pub,
            actual_output_bytes=output_bytes,
            actual_input_bytes=None,
            actual_model_sha256=_MODEL_SHA,
        )
        assert result.valid is True, (
            f"Built+signed manifest must verify. Failed checks: {result.failed_checks}"
        )

    def test_built_manifest_fails_with_wrong_key(self, keypair, other_keypair):
        """ANTI-FAKE: wrong key must reject the signature."""
        _, wrong_pub = other_keypair
        m = _build(keypair)
        result = verify_manifest(m, wrong_pub)
        assert result.valid is False

    def test_built_output_binding_correct(self, keypair):
        _, pub = keypair
        output_bytes = b"prediction: airplane"
        m = _build(keypair, output_bytes=output_bytes)
        result = verify_manifest(m, pub, actual_output_bytes=output_bytes)
        assert result.valid is True

    def test_built_output_binding_substitution_fails(self, keypair):
        """ANTI-FAKE: substituted output must fail output binding check."""
        _, pub = keypair
        output_bytes = b"prediction: airplane"
        m = _build(keypair, output_bytes=output_bytes)
        result = verify_manifest(m, pub, actual_output_bytes=b"prediction: bomb")
        assert result.valid is False
        output_check = next(
            c for c in result.checks if c.check_name == "output_binding"
        )
        assert not output_check.passed

    def test_full_pipeline(self, keypair):
        """
        Full end-to-end: build → sign → persist metadata → verify.
        Proves the complete provenance pipeline works with real data.
        """
        priv, pub = keypair
        actual_input = b"[224x224x3 JPEG bytes here]"
        actual_output = b'{"detections": [{"label": "person", "score": 0.91}]}'
        model_data = b"fake onnx model binary"

        m = build_and_sign_manifest(
            assessment_id="full-pipeline-test",
            input_sha256=hash_bytes(actual_input),
            model_sha256=hash_bytes(model_data),
            output_bytes=actual_output,
            preprocessing_config={"resize": [640, 640]},
            inference_config={"iou_threshold": 0.45, "conf_threshold": 0.25},
            sequence=0,
            private_key=priv,
        )

        # Verify all bindings
        result = verify_manifest(
            m, pub,
            actual_input_bytes=actual_input,
            actual_output_bytes=actual_output,
            actual_model_sha256=hash_bytes(model_data),
        )
        assert result.valid is True
        assert len(result.checks) == 4  # sig + input + model + output
        assert all(c.passed for c in result.checks)


class TestBuilderValidation:

    def test_negative_sequence_raises(self, keypair):
        priv, _ = keypair
        with pytest.raises(ValueError, match="sequence"):
            build_and_sign_manifest(
                assessment_id="a",
                input_sha256="a" * 64,
                model_sha256="b" * 64,
                output_bytes=b"x",
                preprocessing_config={},
                inference_config={},
                sequence=-1,
                private_key=priv,
            )
