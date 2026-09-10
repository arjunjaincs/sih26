# PRAMAAN Testing Strategy

> How PRAMAAN validates its own correctness, security, and honesty.

Version: 2.0-DRAFT  
Last Updated: 2026-09-10

---

## 1. Testing Philosophy

1. **Tests prove real behavior**: Every test must assert against real logic, not mock everything.
2. **Detectors must not cheat**: Tests specifically verify detectors produce results from analysis, not hardcoded values.
3. **Security is tested**: Threat model mitigations are validated with adversarial test cases.
4. **Reproducibility is tested**: Same input + config + seed → same output.
5. **Failures are tested**: Missing data, corrupt files, insufficient access → explicit error, not silent pass.

---

## 2. Test Categories

### 2.1 Unit Tests (`tests/unit/`)

**Scope**: Individual functions and classes in isolation.

| Component | Test Focus |
|-----------|-----------|
| `domain/entities.py` | Entity construction, validation, serialization |
| `domain/risk.py` | Risk calculation logic, confidence computation, coverage |
| `domain/crypto.py` | SHA-256 hashing, Ed25519 signing/verification, canonical serialization |
| `infra/model_loader.py` | Safe loading, rejection of unsafe files |
| `infra/image_loader.py` | Size limits, dimension limits, format validation |
| `infra/blob_store.py` | Content-addressed storage, retrieval, integrity |
| `infra/db.py` | Schema creation, CRUD, migrations |

**Example: Anti-Fake Test**

```python
def test_detector_does_not_return_hardcoded_values():
    """Detector output must change when input changes."""
    result_a = detector.run(context_with_input_a)
    result_b = detector.run(context_with_input_b)
    # If inputs differ, at least the evidence data should differ
    assert result_a.evidence != result_b.evidence or \
           result_a.findings != result_b.findings, \
        "Detector appears to return hardcoded results regardless of input"
```

### 2.2 Detector Tests (`tests/detectors/`)

**Scope**: Each detector independently.

For every detector:

| Test | Purpose |
|------|---------|
| `test_metadata_complete` | Metadata has all required fields, valid values |
| `test_can_run_checks_access` | Returns `cannot_run` with reason when access insufficient |
| `test_clean_input_no_false_positive` | Clean known-good data → no HIGH/CRITICAL findings |
| `test_known_bad_input_detects` | Known-bad fixture → expected finding category |
| `test_output_schema_valid` | Output matches declared schema |
| `test_different_inputs_different_outputs` | Anti-hardcoding check |
| `test_deterministic_with_seed` | Same input + seed → identical output |
| `test_failure_mode` | Corrupt input → FAILED status, not silent pass |
| `test_timeout_respected` | Long-running detector obeys timeout |

### 2.3 Integration Tests (`tests/integration/`)

**Scope**: Multi-component interactions.

| Test Suite | Components | Purpose |
|-----------|------------|---------|
| `test_assessment_lifecycle` | Orchestrator + Engines + Detectors + DB | Full CREATED → COMPLETE lifecycle |
| `test_evidence_chain` | Detectors → Evidence Store → Findings | Evidence correctly linked to findings |
| `test_audit_chain_integrity` | Audit Ledger + DB | Chain verification across operations |
| `test_provenance_roundtrip` | Manifest → Sign → Verify | End-to-end provenance verification |
| `test_coverage_reporting` | Orchestrator + Access Profiles | Correct coverage gaps when access is restricted |

### 2.4 API Tests (`tests/api/`)

**Scope**: FastAPI endpoints.

| Test Suite | Purpose |
|-----------|---------|
| `test_assessment_endpoints` | Create, get, list, delete assessments |
| `test_asset_upload` | File upload, validation, rejection of bad files |
| `test_findings_endpoints` | Query findings by assessment, category, severity |
| `test_report_endpoints` | Generate and retrieve reports |
| `test_audit_endpoints` | Query audit chain, verify chain integrity |
| `test_input_validation` | Reject malformed requests, verify Pydantic validation |
| `test_error_responses` | Proper HTTP status codes, error schemas |

Uses `httpx.AsyncClient` with `app` fixture (no real server needed).

### 2.5 Cryptographic Verification Tests (`tests/crypto/`)

| Test | Purpose |
|------|---------|
| `test_sha256_deterministic` | Same input → same hash, always |
| `test_ed25519_sign_verify` | Valid signatures verify; tampered data fails |
| `test_ed25519_wrong_key_fails` | Signature from key A does not verify with key B |
| `test_canonical_json_deterministic` | Same object → same canonical bytes regardless of insertion order |
| `test_hash_chain_detects_tampering` | Modify one event → chain verification fails |
| `test_hash_chain_detects_deletion` | Remove one event → chain verification fails |
| `test_hash_chain_detects_insertion` | Insert extra event → chain verification fails |
| `test_manifest_canonical_roundtrip` | Serialize → hash → deserialize → re-hash → same hash |

### 2.6 Security Tests (`tests/security/`)

| Test | Threat | Purpose |
|------|--------|---------|
| `test_reject_pickle_model` | T-01 | Ensure `torch.load` without `weights_only=True` is never called |
| `test_reject_oversized_image` | T-02, T-05 | Images exceeding max dimensions are rejected |
| `test_reject_path_traversal` | T-03 | Filenames with `..` are rejected |
| `test_reject_zip_bomb` | T-04 | Archives that expand beyond limit are aborted |
| `test_reject_nested_archive` | T-04 | Zip-in-zip is rejected |
| `test_model_load_timeout` | T-05 | Model loading obeys timeout |
| `test_audit_append_only` | T-07 | No UPDATE/DELETE SQL possible on audit table |
| `test_reject_non_image_with_image_ext` | T-02 | Executable file named `.jpg` is rejected |

### 2.7 Reproducibility Tests (`tests/reproducibility/`)

| Test | Purpose |
|------|---------|
| `test_same_input_same_output` | Run assessment twice with same config + seed → identical findings |
| `test_config_hash_changes_with_config` | Different configs → different config hashes |
| `test_environment_recorded` | Environment info is persisted in assessment |
| `test_detector_versions_recorded` | All detector versions are captured |

### 2.8 Demo Tests (`tests/demo/`)

| Test | Purpose |
|------|---------|
| `test_demo_findings_marked` | All demo findings have `source: DEMO_FIXTURE` |
| `test_demo_does_not_import_live` | Demo module has no imports from `engines/` or `detectors/` |
| `test_live_does_not_import_demo` | Live modules have no imports from `demo/` |
| `test_demo_scenarios_complete` | All declared scenarios have fixture data |
| `test_demo_scenarios_deterministic` | Same scenario → identical output every time |

### 2.9 Dataset Ingestion Tests (`tests/ingestion/`)

| Test | Purpose |
|------|---------|
| `test_coco_format_ingestion` | Valid COCO dataset loads correctly |
| `test_yolo_format_ingestion` | Valid YOLO dataset loads correctly |
| `test_reject_invalid_coco` | Malformed COCO JSON is rejected with error |
| `test_reject_invalid_yolo` | Missing label files are reported |
| `test_sample_hashing` | All samples are SHA-256 and perceptually hashed |
| `test_large_dataset_limits` | Datasets exceeding configured limits are rejected |

### 2.10 Model Loading Tests (`tests/model_loading/`)

| Test | Purpose |
|------|---------|
| `test_load_onnx_model` | Valid ONNX model loads, metadata extracted |
| `test_load_pytorch_model_safe` | PyTorch model loads with `weights_only=True` |
| `test_load_torchscript_model` | TorchScript model loads via `torch.jit.load` |
| `test_reject_corrupt_onnx` | Corrupt ONNX file → clear error |
| `test_reject_pickle_exploit` | Model with malicious pickle → rejected before execution |
| `test_access_profile_white_box` | PyTorch model → WHITE_BOX profile |
| `test_access_profile_black_box` | ONNX model without weights → BLACK_BOX profile |

### 2.11 End-to-End Tests (`tests/e2e/`)

| Test | Purpose |
|------|---------|
| `test_data_integrity_scenario` | Upload dataset with known issues → correct findings in report |
| `test_model_substitution_scenario` | Upload mismatched model → substitution finding |
| `test_provenance_tamper_scenario` | Generate manifest → tamper → verification fails |
| `test_full_assessment_report` | Complete assessment → report contains all sections |
| `test_offline_operation` | Run with network blocked → everything works |

### 2.12 Offline / Network Isolation Tests (`tests/offline/`)

| Test | Purpose |
|------|---------|
| `test_no_outbound_network` | Mock/block all network calls; assessment completes normally |
| `test_no_dns_resolution` | Block DNS; system functions |
| `test_models_load_offline` | Pretrained models loaded from local cache |

---

## 3. Test Fixtures

### Location: `tests/fixtures/`

```
tests/fixtures/
├── datasets/
│   ├── clean_coco_10/          # 10-image clean COCO dataset
│   ├── clean_yolo_10/          # 10-image clean YOLO dataset
│   ├── duplicated_coco_10/     # COCO with 3 near-duplicate pairs
│   ├── mislabeled_coco_10/     # COCO with 2 flipped labels
│   └── ood_coco_10/            # COCO with 2 OOD images inserted
├── models/
│   ├── tiny_resnet.onnx        # Minimal valid ONNX model
│   ├── tiny_resnet.pt          # Minimal valid PyTorch model (weights_only safe)
│   ├── corrupt.onnx            # Corrupt ONNX file
│   └── reference_outputs.json  # Expected outputs for reference battery
├── images/
│   ├── clean_sample.jpg        # Known-good image
│   ├── oversized.jpg           # Exceeds dimension limits
│   └── not_an_image.jpg        # Executable disguised as image
├── manifests/
│   ├── valid_manifest.json     # Correctly signed manifest
│   ├── tampered_manifest.json  # Manifest with altered output hash
│   └── replayed_manifest.json  # Manifest with duplicate nonce
└── keys/
    ├── test_private.pem        # Ed25519 test private key
    └── test_public.pem         # Ed25519 test public key
```

### Fixture Principles

1. **Tiny**: All fixtures use minimal data (10 images, tiny models) for fast test execution
2. **Deterministic**: Fixtures are checked into git (except large model files — use generation scripts)
3. **Documented**: Each fixture directory has a README explaining its purpose and expected behavior
4. **No real data**: No real-world images, models, or sensitive data in fixtures

---

## 4. CI / Local Testing

### Commands

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Security tests
pytest tests/security/ -v -m security

# Reproducibility tests
pytest tests/reproducibility/ -v -m reproducibility

# With coverage
pytest tests/ --cov=backend --cov-report=html
```

### Markers

```python
# pytest.ini
[pytest]
markers =
    security: Security-critical tests
    reproducibility: Reproducibility verification
    slow: Tests that take > 5 seconds
    e2e: End-to-end integration tests
    offline: Tests that verify offline operation
```

### Coverage Targets

| Component | Minimum Coverage |
|-----------|-----------------|
| `domain/` | 90% |
| `infra/crypto.py` | 95% |
| `infra/model_loader.py` | 95% |
| `engines/` | 80% |
| `detectors/` | 80% |
| `api/` | 75% |
| Overall | 80% |

---

## 5. Anti-Fake Testing Strategy

PRAMAAN includes a dedicated anti-fake testing layer because the v1 codebase
was entirely fixture-driven. These tests ensure the v2 codebase produces
real analysis:

1. **Input variation test**: Every detector is tested with ≥ 2 meaningfully different inputs.
   Outputs must differ.

2. **No magic numbers test**: Static analysis scans detector code for hardcoded risk levels,
   confidence values, or finding descriptions that are not derived from computation.

3. **Demo isolation test**: Import graph analysis ensures `demo/` and `engines/` never
   cross-import.

4. **Source field test**: All findings in live assessments have `source: LIVE_ANALYSIS`.
   All findings in demo assessments have `source: DEMO_FIXTURE`.

5. **Evidence traceability test**: Every finding at severity ≥ MEDIUM must reference at
   least one evidence item with non-empty `data`.
