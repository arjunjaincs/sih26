"""Tests for PRAMAAN crypto utilities."""

import hashlib
from pathlib import Path

import pytest

from backend.infra.crypto import (
    canonical_json,
    generate_nonce,
    generate_signing_key,
    hash_bytes,
    hash_file,
    load_private_key,
    load_public_key,
    public_key_from_private,
    save_private_key,
    save_public_key,
    sign,
    verify,
)


# ---------------------------------------------------------------------------
# SHA-256 hashing
# ---------------------------------------------------------------------------

class TestHashBytes:
    def test_known_value(self):
        # SHA-256 of empty bytes is well-known
        expected = hashlib.sha256(b"").hexdigest()
        assert hash_bytes(b"") == expected

    def test_deterministic(self):
        data = b"hello pramaan"
        assert hash_bytes(data) == hash_bytes(data)

    def test_different_data_different_hash(self):
        assert hash_bytes(b"foo") != hash_bytes(b"bar")

    def test_returns_lowercase_hex(self):
        result = hash_bytes(b"test")
        assert result == result.lower()
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


class TestHashFile:
    def test_matches_hash_bytes(self, tmp_path: Path):
        data = b"pramaan file content"
        f = tmp_path / "test.bin"
        f.write_bytes(data)
        assert hash_file(f) == hash_bytes(data)

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            hash_file(tmp_path / "nonexistent.bin")

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        assert hash_file(f) == hash_bytes(b"")

    def test_large_file_chunked(self, tmp_path: Path):
        """File larger than the 64 KiB read buffer is hashed correctly."""
        data = b"X" * (200 * 1024)  # 200 KiB
        f = tmp_path / "large.bin"
        f.write_bytes(data)
        assert hash_file(f) == hash_bytes(data)


# ---------------------------------------------------------------------------
# Canonical JSON
# ---------------------------------------------------------------------------

class TestCanonicalJson:
    def test_deterministic_regardless_of_insertion_order(self):
        a = canonical_json({"z": 1, "a": 2, "m": 3})
        b = canonical_json({"a": 2, "m": 3, "z": 1})
        assert a == b

    def test_nested_keys_sorted(self):
        obj = {"b": {"z": 1, "a": 2}, "a": {"z": 1, "a": 2}}
        result = canonical_json(obj)
        # Both outer and inner keys must be sorted
        assert b'"a":{"a":2,"z":1},"b":{"a":2,"z":1}' in result

    def test_returns_bytes(self):
        result = canonical_json({"key": "value"})
        assert isinstance(result, bytes)

    def test_utf8_encoding(self):
        result = canonical_json({"lang": "हिन्दी"})
        assert isinstance(result, bytes)
        decoded = result.decode("utf-8")
        assert "हिन्दी" in decoded

    def test_no_extra_whitespace(self):
        result = canonical_json({"a": 1, "b": [1, 2, 3]})
        assert b" " not in result

    def test_none_becomes_null(self):
        result = canonical_json({"x": None})
        assert b"null" in result

    def test_bool_values(self):
        result = canonical_json({"t": True, "f": False})
        assert b"true" in result
        assert b"false" in result

    def test_nan_rejected(self):
        import math
        with pytest.raises((ValueError, TypeError)):
            canonical_json({"x": math.nan})

    def test_same_dict_same_hash(self):
        obj = {"nonce": "abc", "ts": "2026-01-01T00:00:00Z", "val": 42}
        h1 = hash_bytes(canonical_json(obj))
        h2 = hash_bytes(canonical_json(obj))
        assert h1 == h2


# ---------------------------------------------------------------------------
# Ed25519 key management
# ---------------------------------------------------------------------------

class TestKeyManagement:
    def test_generate_key(self):
        key = generate_signing_key()
        assert key is not None

    def test_save_and_load_private_key(self, tmp_path: Path):
        key = generate_signing_key()
        path = tmp_path / "signing_key.pem"
        save_private_key(key, path)
        assert path.exists()
        loaded = load_private_key(path)
        assert loaded is not None

    def test_save_and_load_public_key(self, tmp_path: Path):
        priv = generate_signing_key()
        pub = public_key_from_private(priv)
        path = tmp_path / "signing_key.pub"
        save_public_key(pub, path)
        assert path.exists()
        loaded = load_public_key(path)
        assert loaded is not None

    def test_roundtrip_key_produces_same_signatures(self, tmp_path: Path):
        priv = generate_signing_key()
        priv_path = tmp_path / "key.pem"
        pub_path = tmp_path / "key.pub"
        save_private_key(priv, priv_path)
        save_public_key(public_key_from_private(priv), pub_path)

        loaded_priv = load_private_key(priv_path)
        loaded_pub = load_public_key(pub_path)

        digest = hash_bytes(b"test payload")
        sig = sign(loaded_priv, digest)
        assert verify(loaded_pub, digest, sig)

    def test_keys_directory_created(self, tmp_path: Path):
        priv = generate_signing_key()
        nested = tmp_path / "a" / "b" / "c" / "key.pem"
        save_private_key(priv, nested)
        assert nested.exists()


# ---------------------------------------------------------------------------
# Signing and verification
# ---------------------------------------------------------------------------

class TestSignVerify:
    def setup_method(self):
        self.priv = generate_signing_key()
        self.pub = public_key_from_private(self.priv)

    def test_valid_signature_verifies(self):
        digest = hash_bytes(b"authentic message")
        sig = sign(self.priv, digest)
        assert verify(self.pub, digest, sig) is True

    def test_tampered_digest_fails(self):
        digest = hash_bytes(b"original")
        sig = sign(self.priv, digest)
        tampered = hash_bytes(b"tampered")
        assert verify(self.pub, tampered, sig) is False

    def test_wrong_key_fails(self):
        digest = hash_bytes(b"test")
        sig = sign(self.priv, digest)
        other_priv = generate_signing_key()
        other_pub = public_key_from_private(other_priv)
        assert verify(other_pub, digest, sig) is False

    def test_truncated_signature_fails(self):
        digest = hash_bytes(b"test")
        sig = sign(self.priv, digest)
        truncated = sig[:-4]  # Remove last 2 bytes
        assert verify(self.pub, digest, truncated) is False

    def test_empty_signature_fails(self):
        digest = hash_bytes(b"test")
        assert verify(self.pub, digest, "") is False

    def test_sign_is_deterministic_same_key_and_data(self):
        """Ed25519 is deterministic — same key + message → same signature."""
        digest = hash_bytes(b"deterministic test")
        sig1 = sign(self.priv, digest)
        sig2 = sign(self.priv, digest)
        assert sig1 == sig2

    def test_different_messages_different_signatures(self):
        d1 = hash_bytes(b"message A")
        d2 = hash_bytes(b"message B")
        assert sign(self.priv, d1) != sign(self.priv, d2)


# ---------------------------------------------------------------------------
# Nonce
# ---------------------------------------------------------------------------

class TestNonce:
    def test_nonce_is_64_hex_chars(self):
        n = generate_nonce()
        assert len(n) == 64
        assert all(c in "0123456789abcdef" for c in n)

    def test_nonces_are_unique(self):
        nonces = {generate_nonce() for _ in range(100)}
        assert len(nonces) == 100
