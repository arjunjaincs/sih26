# ADR-005: Ed25519 for Provenance Signing

**Status**: Accepted  
**Date**: 2026-09-10  
**Context**: Inference provenance manifests and critical audit events need cryptographic signatures to ensure integrity and non-repudiation.

## Decision

Use Ed25519 (EdDSA over Curve25519) via the `cryptography` library for
all signing operations. Local keypair, no PKI, no CA infrastructure
in the initial version.

## Rationale

- **Fast**: ~50x faster than RSA-2048 for signing
- **Small keys**: 32-byte private key, 32-byte public key, 64-byte signature
- **Deterministic**: Same message + key → same signature (important for reproducibility)
- **Well-understood**: Standardized (RFC 8032), widely implemented
- **No PKI needed**: Self-signed keys work for single-machine operation
- **`cryptography` library**: Well-maintained, audited, already needed for other crypto

## Key Management

- On first run, PRAMAAN generates an Ed25519 keypair and stores it locally
- Private key stored in `config/keys/signing_key.pem` (filesystem permissions)
- Public key stored in `config/keys/signing_key.pub`
- Key is per-installation, not per-user
- Key rotation: generate new key, re-sign old manifests is NOT supported (append-only)

## Consequences

- Key compromise means an attacker can forge signatures
- No way to distinguish "signed by this PRAMAAN instance" from
  "signed by an attacker with the stolen key" — acceptable for local deployment
- Future: optional X.509 local CA for multi-node deployments

## Rejected Alternatives

- RSA (slower, larger keys, no benefit for local use)
- HMAC (symmetric, no non-repudiation distinction)
- No signing (unacceptable — provenance claims need verification)
- X.509 PKI (too complex for single-machine prototype)
