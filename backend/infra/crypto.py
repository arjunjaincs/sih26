"""
PRAMAAN cryptographic utilities.

All cryptographic operations in PRAMAAN go through this module.
No other module should import `hashlib`, `cryptography`, or perform
raw crypto directly — centralisation makes auditing possible.

Capabilities:
  - SHA-256 hashing (bytes and files)
  - Canonical JSON serialization (deterministic, order-stable)
  - Ed25519 keypair generation
  - Ed25519 signing and verification

Security notes:
  - Ed25519 private keys are stored only on disk; never in-process globals.
  - Callers must load and discard key objects; do not cache them.
  - Canonical JSON is UTF-8 with sorted keys and no extra whitespace.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature


# ---------------------------------------------------------------------------
# SHA-256
# ---------------------------------------------------------------------------

_CHUNK = 1 << 16  # 64 KiB read buffer for file hashing


def hash_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    """
    Return the SHA-256 hex digest of the file at *path*.

    Reads in 64 KiB chunks so large files do not exhaust memory.
    Raises FileNotFoundError if *path* does not exist.
    """
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Canonical JSON
# ---------------------------------------------------------------------------

def canonical_json(obj: Any) -> bytes:
    """
    Produce a deterministic UTF-8 JSON encoding of *obj*.

    Rules (must be followed consistently throughout PRAMAAN):
      - Keys are sorted lexicographically (recursive)
      - No extra whitespace (separators=(',', ':'))
      - All strings are UTF-8
      - Floats are represented at full Python precision (not rounded here;
        callers must pre-round if they need bounded precision)
      - None → null, True → true, False → false
      - dict/list recursion is handled by json.dumps with sort_keys=True

    This function produces the same bytes for the same logical object
    regardless of the order in which dict keys were inserted.
    """
    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Ed25519 key management
# ---------------------------------------------------------------------------

def generate_signing_key() -> Ed25519PrivateKey:
    """Generate a new Ed25519 private key."""
    return Ed25519PrivateKey.generate()


def save_private_key(key: Ed25519PrivateKey, path: Path) -> None:
    """
    Serialize *key* to PEM format at *path* with no encryption.

    On POSIX systems the file is created with mode 0o600 (owner read/write only).
    On Windows the mode call is a no-op; callers should use NTFS ACLs separately.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.write_bytes(pem)
    # Attempt to restrict permissions (best-effort on Windows)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def save_public_key(key: Ed25519PublicKey, path: Path) -> None:
    """Serialize the public key to PEM format at *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pem = key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    path.write_bytes(pem)


def load_private_key(path: Path) -> Ed25519PrivateKey:
    """Load an Ed25519 private key from a PEM file."""
    pem = path.read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError(f"Expected Ed25519PrivateKey, got {type(key).__name__}")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    """Load an Ed25519 public key from a PEM file."""
    pem = path.read_bytes()
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError(f"Expected Ed25519PublicKey, got {type(key).__name__}")
    return key


def public_key_from_private(key: Ed25519PrivateKey) -> Ed25519PublicKey:
    """Extract the Ed25519 public key from a private key."""
    pub = key.public_key()
    if not isinstance(pub, Ed25519PublicKey):  # pragma: no cover
        raise TypeError("Unexpected public key type")
    return pub


# ---------------------------------------------------------------------------
# Signing and verification
# ---------------------------------------------------------------------------

def sign(private_key: Ed25519PrivateKey, digest_hex: str) -> str:
    """
    Sign *digest_hex* (a hex-encoded SHA-256 digest) with *private_key*.

    Returns the Ed25519 signature as a lowercase hex string.

    We sign the raw digest bytes, not the hex string, to keep the
    signed payload compact and unambiguous.
    """
    digest_bytes = bytes.fromhex(digest_hex)
    sig_bytes = private_key.sign(digest_bytes)
    return sig_bytes.hex()


def verify(public_key: Ed25519PublicKey, digest_hex: str, signature_hex: str) -> bool:
    """
    Verify *signature_hex* (hex) over *digest_hex* using *public_key*.

    Returns True if the signature is valid, False otherwise.
    Never raises on invalid signatures — only returns False.
    """
    try:
        digest_bytes = bytes.fromhex(digest_hex)
        sig_bytes = bytes.fromhex(signature_hex)
        public_key.verify(sig_bytes, digest_bytes)
        return True
    except (InvalidSignature, ValueError):
        return False


# ---------------------------------------------------------------------------
# Nonce
# ---------------------------------------------------------------------------

def generate_nonce() -> str:
    """Return a cryptographically random 32-byte hex nonce."""
    return secrets.token_hex(32)
