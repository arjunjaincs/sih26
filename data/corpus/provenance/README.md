# PRAMAAN v1 — Phase 17 Provenance Assurance Validation Corpus

Deterministic, fully offline validation corpus for **PI-01: Inference Provenance Integrity** and its integration with replay detection and the tamper-evident audit chain.

## Scenarios Overview

Total Scenarios: 13

| Scenario ID | Name | Category | Primary Detection Target |
|---|---|---|---|
| `01_clean_provenance` | Clean Baseline Provenance | `clean_baseline` | Valid Ed25519 signature & all bindings match |
| `02_input_tampering` | Input Image Tampering | `binding_tampering` | Actual input bytes hash mismatch |
| `03_model_tampering` | Model Identity Tampering | `binding_tampering` | Model SHA-256 mismatch |
| `04_output_tampering` | Inference Output Tampering | `binding_tampering` | Output predictions hash mismatch |
| `05_manifest_tampering` | Signed Field Alteration | `manifest_tampering` | Signature verification failure |
| `06_duplicate_replay` | Direct Manifest / Nonce Replay | `replay_anomaly` | Reused nonce / duplicate manifest ID |
| `07_sequence_regression` | Monotonic Sequence Regression | `replay_anomaly` | Regressing sequence counter |
| `08_sequence_gap` | Missing Stream Events Gap | `replay_anomaly` | Gaps in sequence counter stream |
| `09_fresh_nonce_limitation` | Fresh Nonce Duplicate Inference | `documented_limitation` | ADR-003 limitation representation |
| `10_audit_integration` | End-to-End Audit Trail Integration | `audit_integration` | Verified provenance & valid audit chain |
| `11_signature_binding` | SEC-01 Signature Transplant Rejection | `security_regression` | Signature transplantation fail-closed |
| `12_malformed_provenance` | Corrupted / Malformed Payload | `malformed_unsupported` | Unsigned/corrupt manifest fails closed |
| `13_persistence_restart` | Persistence & Service Restart | `persistence` | SQLite WAL replay state retention |

## Reproduction

Run the generator:
```bash
python backend/tools/provenance_corpus_generator.py --corpus-root data/corpus/provenance
```
