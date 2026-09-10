# PRAMAAN Implementation Plan

> Phased implementation from foundation to demonstration.

Version: 2.0-DRAFT  
Last Updated: 2026-09-10

---

## Phase 0: Foundation (Days 1–3)

### Objective
Establish project skeleton, domain model, persistence layer, and crypto primitives.
No detection logic yet — build the scaffolding that everything else depends on.

### Modules Created

| Module | Purpose |
|--------|---------|
| `backend/domain/entities.py` | All Pydantic models: Assessment, Asset, Finding, Evidence, etc. |
| `backend/domain/enums.py` | All enums: RiskLevel, Severity, AccessLevel, AssessmentState, etc. |
| `backend/domain/protocols.py` | Detector protocol, EvidenceCollector protocol |
| `backend/domain/risk.py` | Risk/confidence calculation logic |
| `backend/infra/db.py` | SQLite setup, schema creation, repository pattern |
| `backend/infra/blob_store.py` | Content-addressed file storage |
| `backend/infra/crypto.py` | SHA-256, Ed25519, canonical JSON serialization |
| `backend/infra/config.py` | Configuration loading (TOML) |
| `backend/infra/model_loader.py` | Safe model loading (stub — actual loading in Phase 2) |
| `backend/infra/image_loader.py` | Safe image loading with validation |

### Tests
- `tests/unit/test_entities.py`
- `tests/unit/test_enums.py`
- `tests/unit/test_risk.py`
- `tests/unit/test_db.py`
- `tests/unit/test_blob_store.py`
- `tests/crypto/test_crypto.py`
- `tests/security/test_image_loader.py`

### Acceptance Criteria
- [ ] All domain entities construct and serialize correctly
- [ ] SQLite database creates with full schema
- [ ] Blob store stores and retrieves by hash
- [ ] SHA-256 and Ed25519 produce deterministic, verifiable results
- [ ] Canonical JSON serialization is deterministic
- [ ] Image loader rejects oversized and non-image files
- [ ] All tests pass

### What Must NOT Be Implemented
- Detectors
- API endpoints
- Frontend
- Assessment orchestration

---

## Phase 1: Core Vertical Slice (Days 4–8)

### Objective
Implement the simplest end-to-end vertical slice: ingest a dataset, run the
simplest detector (perceptual hash duplicate detection), produce a finding,
record audit events, generate a minimal report. This validates the entire
pipeline architecture before adding complexity.

### Modules Created

| Module | Purpose |
|--------|---------|
| `backend/engines/orchestrator.py` | Assessment lifecycle state machine |
| `backend/engines/data_integrity.py` | Data integrity engine (dispatcher) |
| `backend/engines/evidence_fusion.py` | Basic evidence → risk aggregation |
| `backend/detectors/base.py` | Base detector implementation |
| `backend/detectors/data/phash_duplicates.py` | DI-01: Perceptual hash duplicate detector |
| `backend/detectors/model/artifact_fingerprint.py` | MI-01: SHA-256 model fingerprinting |
| `backend/detectors/registry.py` | Detector discovery and registry |
| `backend/engines/audit_ledger.py` | Append-only audit chain with hash linking |
| `backend/engines/provenance.py` | IP-01, IP-02, IP-03: Manifest construction, signing, verification |
| `backend/infra/ingestion.py` | COCO and YOLO dataset ingestion |
| `backend/api/main.py` | FastAPI app setup |
| `backend/api/routes/assessments.py` | Create/get/list assessment endpoints |
| `backend/api/routes/assets.py` | Asset upload endpoints |
| `backend/api/routes/findings.py` | Query findings |
| `backend/api/routes/audit.py` | Query and verify audit chain |
| `backend/api/routes/reports.py` | Generate report |
| `backend/api/deps.py` | Dependency injection (DB, blob store, config) |

### Tests
- `tests/detectors/test_phash_duplicates.py`
- `tests/detectors/test_artifact_fingerprint.py`
- `tests/integration/test_assessment_lifecycle.py`
- `tests/integration/test_audit_chain_integrity.py`
- `tests/integration/test_provenance_roundtrip.py`
- `tests/api/test_assessment_endpoints.py`
- `tests/api/test_asset_upload.py`
- `tests/ingestion/test_coco_format.py`
- `tests/ingestion/test_yolo_format.py`
- `tests/security/test_model_loader.py`

### Acceptance Criteria
- [ ] Can create assessment via API
- [ ] Can upload COCO dataset via API
- [ ] Perceptual hash detector runs and produces real findings on duplicate images
- [ ] Model fingerprint detector verifies/rejects model hash
- [ ] Audit chain records all lifecycle events
- [ ] Audit chain verification detects tampering
- [ ] Provenance manifest construction, signing, and verification works
- [ ] Replay detection works (duplicate nonce rejection)
- [ ] Basic report generation works
- [ ] All tests pass
- [ ] Anti-fake tests pass (different inputs → different outputs)

### What Must NOT Be Implemented
- Embedding-based detectors (require torch models)
- Frontend
- Neural Cleanse / Spectral Signatures
- Drift detection
- Demo scenarios
- Copilot

---

## Phase 2: Detection Depth (Days 9–14)

### Objective
Add the core detection algorithms that require embeddings and statistical
analysis. Implement model loading for PyTorch and ONNX.

### Modules Created

| Module | Purpose |
|--------|---------|
| `backend/infra/model_loader.py` | Full safe model loading (PyTorch, ONNX, TorchScript) |
| `backend/infra/embedding.py` | Embedding extraction using pretrained backbone |
| `backend/detectors/data/embedding_similarity.py` | DI-02: Embedding-based similarity |
| `backend/detectors/data/label_anomaly.py` | DI-03: Label anomaly detection |
| `backend/detectors/data/ood_statistical.py` | DI-05: OOD via Mahalanobis distance |
| `backend/detectors/data/contributor_aggregation.py` | DI-04: Contributor risk aggregation |
| `backend/detectors/model/behavioral_consistency.py` | MI-02: Behavioral testing |
| `backend/detectors/model/parameter_statistics.py` | MI-03: Weight statistics |
| `backend/detectors/drift/embedding_distribution.py` | DD-01: MMD-based drift |
| `backend/detectors/drift/statistical_tests.py` | DD-02: KS/PSI tests |
| `backend/detectors/drift/metadata_drift.py` | DD-03: Image metadata drift |
| `backend/engines/model_integrity.py` | Model integrity engine |
| `backend/engines/drift.py` | Drift engine |

### Tests
- `tests/detectors/test_embedding_similarity.py`
- `tests/detectors/test_label_anomaly.py`
- `tests/detectors/test_ood_statistical.py`
- `tests/detectors/test_behavioral_consistency.py`
- `tests/detectors/test_parameter_statistics.py`
- `tests/detectors/test_drift_*.py`
- `tests/model_loading/test_load_onnx.py`
- `tests/model_loading/test_load_pytorch.py`
- `tests/reproducibility/test_deterministic.py`

### Acceptance Criteria
- [ ] PyTorch models load safely (weights_only=True)
- [ ] ONNX models load and run inference
- [ ] Embedding extraction works offline (pretrained backbone cached locally)
- [ ] Label anomaly detector flags known mislabeled samples
- [ ] OOD detector flags known out-of-distribution samples
- [ ] Behavioral consistency detector flags model with altered weights
- [ ] Drift detectors detect meaningful distribution shift
- [ ] All detectors produce different results for different inputs
- [ ] Coverage gaps are correctly reported for BLACK_BOX model access
- [ ] All tests pass

### What Must NOT Be Implemented
- Neural Cleanse / Spectral Signatures (Phase 3)
- Frontend (Phase 4)
- Demo scenarios (Phase 4)

---

## Phase 3: Advanced Methods & Research (Days 15–18)

### Objective
Implement research-grade detection methods. These are explicitly marked
EXPERIMENTAL and their limitations are documented.

### Modules Created

| Module | Purpose |
|--------|---------|
| `backend/detectors/model/activation_analysis.py` | MI-04: Activation analysis |
| `backend/detectors/model/spectral_signatures.py` | MI-05: Spectral signature detection |
| `backend/detectors/model/neural_cleanse.py` | MI-06: Neural Cleanse (simplified) |
| `backend/engines/evidence_fusion.py` | Enhanced multi-source evidence fusion |

### Tests
- `tests/detectors/test_activation_analysis.py`
- `tests/detectors/test_spectral_signatures.py`
- `tests/detectors/test_neural_cleanse.py`
- `tests/integration/test_multi_detector_fusion.py`

### Acceptance Criteria
- [ ] Activation analysis extracts and analyzes intermediate activations
- [ ] Spectral signatures detect separable clusters in representations
- [ ] Neural Cleanse reconstructs approximate triggers (on known backdoored model)
- [ ] All three methods are marked EXPERIMENTAL in metadata
- [ ] All three methods report their limitations
- [ ] Evidence fusion correctly aggregates findings from multiple detectors
- [ ] All tests pass

### What Must NOT Be Implemented
- Frontend (Phase 4)
- The methods must NOT claim to be production-grade

---

## Phase 4: Frontend & Demo (Days 19–25)

### Objective
Build the analyst workstation frontend and the demo scenario layer.

### Modules Created

| Module | Purpose |
|--------|---------|
| `frontend/` | Full React + TypeScript + Tailwind application |
| `backend/demo/fixtures/` | Deterministic demo fixture data |
| `backend/demo/scenarios.py` | Demo scenario definitions |
| `backend/demo/runner.py` | Demo scenario executor |
| `backend/api/routes/demo.py` | Demo-specific API endpoints |

### Frontend Views
- Assessment creation wizard
- Assessment progress/status
- Findings list with filtering
- Finding detail with evidence inspection
- Coverage/limitations view
- Provenance verification view
- Audit chain verification view
- Report view
- Detector/method information
- Configuration
- Demo mode controls

### Tests
- `tests/demo/test_demo_isolation.py`
- `tests/demo/test_demo_deterministic.py`
- `tests/demo/test_demo_marked.py`
- `tests/e2e/test_full_scenario.py`
- Frontend: Component tests (Vitest)

### Acceptance Criteria
- [ ] All 8 demo scenarios produce correct fixture-based findings
- [ ] Demo findings are marked `DEMO_FIXTURE` everywhere
- [ ] UI displays `DEMO MODE` banner for demo assessments
- [ ] UI never displays arbitrary/fake numbers
- [ ] Analyst can create assessment, upload data, view findings, verify provenance
- [ ] Coverage view shows what was tested and what was not
- [ ] All tests pass

---

## Phase 5: Polish & Deployment (Days 26–30)

### Objective
Hardening, Docker deployment, documentation, and final testing.

### Tasks
- Docker compose for air-gapped deployment
- Offline dependency vendoring
- Report export (JSON + HTML/PDF)
- Performance optimization for large datasets
- Security hardening review
- End-to-end testing
- Offline/network isolation testing
- Documentation updates
- README with getting-started guide

### Acceptance Criteria
- [ ] `docker compose up` starts the full system
- [ ] System works without internet
- [ ] All tests pass
- [ ] No network calls in core operation
- [ ] Report generation produces valid output
- [ ] Documentation is accurate and complete

---

## Dependency Graph

```
Phase 0 (Foundation)
    │
    ▼
Phase 1 (Vertical Slice) ──────────────┐
    │                                    │
    ▼                                    │
Phase 2 (Detection Depth)               │
    │                                    │
    ▼                                    │
Phase 3 (Research Methods)               │
    │                                    │
    └──────────────┬─────────────────────┘
                   │
                   ▼
            Phase 4 (Frontend & Demo)
                   │
                   ▼
            Phase 5 (Polish & Deploy)
```

Phases 0→1→2→3 are sequential (each depends on the previous).  
Phase 4 can start in parallel with Phase 3 (frontend can begin once Phase 1 API exists).  
Phase 5 depends on all previous phases.
